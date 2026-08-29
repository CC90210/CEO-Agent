"""Structured JSON logging for every Empire component.

One canonical formatter; one canonical rotation strategy; one canonical pair
of env vars (`EMPIRE_LOG_LEVEL`, `EMPIRE_LOG_FORMAT`). Drops into existing
`print()`-driven daemons incrementally — `get_logger("send_gateway")` returns
a logger whose .info / .warn / .error / .debug methods accept arbitrary
keyword context.

Usage:
    from lib.structured_log import get_logger
    log = get_logger("send_gateway")
    log.info("Email sent", to="user@example.com", interaction_id=row_id)
    log.warn("Daily cap warm", current=95, cap=100)
    log.error("SMTP auth failed", error=str(exc), retry_count=3)

Output (default JSON):
    {"timestamp": "2026-05-21T18:30:12.345Z", "level": "INFO",
     "module": "send_gateway", "message": "Email sent",
     "context": {"to": "user@example.com", "interaction_id": "abc-..."}}

Output (EMPIRE_LOG_FORMAT=text):
    2026-05-21 18:30:12 INFO  [send_gateway] Email sent  to=user@example.com interaction_id=abc-...

File output: state/logs/{module}.log (rotated at 5 MB, 5 gzipped backups).
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "state" / "logs"

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
_LOGGERS: dict[str, "StructuredLogger"] = {}


def _level_from_env() -> int:
    val = (os.environ.get("EMPIRE_LOG_LEVEL") or "INFO").upper()
    return logging.getLevelName(val) if val in logging._nameToLevel else logging.INFO  # type: ignore[attr-defined]


def _format_from_env() -> str:
    val = (os.environ.get("EMPIRE_LOG_FORMAT") or "json").lower()
    return "text" if val == "text" else "json"


def _short_name(record_name: str) -> str:
    """Strip the "empire." namespace prefix for display."""
    return record_name[7:] if record_name.startswith("empire.") else record_name


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%S.")
                + f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "module": _short_name(record.name),
            "message": record.getMessage(),
        }
        ctx = getattr(record, "context", None)
        if ctx:
            payload["context"] = ctx
        if record.exc_info:
            payload["stack_trace"] = "".join(traceback.format_exception(*record.exc_info)).rstrip()
        return json.dumps(payload, default=str)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ctx = getattr(record, "context", None) or {}
        ctx_str = "  " + " ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else ""
        line = f"{ts} {record.levelname:5s} [{_short_name(record.name)}] {record.getMessage()}{ctx_str}"
        if record.exc_info:
            line += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
        return line


def _make_formatter() -> logging.Formatter:
    return _JsonFormatter() if _format_from_env() == "json" else _TextFormatter()


class _GzipRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that gzips the rotated backup.

    ROLLOVER HAS TO SURVIVE A SHARING VIOLATION. Rotation renames the live file,
    and on Windows that fails with WinError 32 whenever another process holds it
    open — which, for a log every script writes to, is most of the time. The
    handler's default error path swallows that and keeps appending, so the file
    grows without limit and no backup is ever produced.

    Measured 2026-08-29: state/logs/db_turso.log was 190 MB against a 5 MB cap,
    38x over, with ZERO rotated backups on disk. Rotation had never once
    succeeded. The same race already produced a real WinError 32 recorded in
    tmp/cron_failures/booking-engine-py-20260809T220038Z.log.

    When the rename cannot be taken, truncating in place bounds the file. That
    loses the oldest lines, which is what rotation does anyway — and an
    unbounded log loses them too, just later and along with the disk.
    """

    def doRollover(self):  # noqa: N802 — stdlib name
        try:
            super().doRollover()
            return
        except OSError as exc:
            # Another process holds the file. Bound it in place instead.
            try:
                if self.stream:
                    self.stream.close()
                    self.stream = None
                with open(self.baseFilename, "w", encoding=self.encoding or "utf-8") as fh:
                    fh.write(json.dumps({
                        "level": "WARNING",
                        "module": "structured_log",
                        "message": "log truncated in place — rollover could not "
                                   "rename while another process held the file",
                        "context": {"error": str(exc)[:200],
                                    "max_bytes": self.maxBytes},
                    }) + "\n")
                self.stream = self._open()
            except OSError:
                # Truncation failed too. Reopen and keep logging: losing the
                # logger is worse than an oversized file.
                try:
                    self.stream = self._open()
                except OSError:
                    pass

    def doRollover(self) -> None:  # noqa: N802 — stdlib override
        try:
            super().doRollover()
            # Gzip the most recent rotated file (e.g., module.log.1)
            rotated = Path(f"{self.baseFilename}.1")
            if rotated.exists():
                gz_path = rotated.with_suffix(rotated.suffix + ".gz")
                try:
                    with rotated.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    rotated.unlink()
                except OSError:
                    pass  # leave uncompressed if gzip fails — don't break the daemon
        except OSError:
            pass  # Windows file lock collision on rotation — ignore gracefully


class StructuredLogger:
    """Thin wrapper around stdlib Logger that accepts keyword context."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._logger = logging.getLogger(f"empire.{name}")
        self._logger.setLevel(_level_from_env())
        self._logger.propagate = False
        if not self._logger.handlers:
            self._install_handlers()

    def _install_handlers(self) -> None:
        formatter = _make_formatter()

        # Console handler — stderr so it doesn't pollute --json subprocess stdout
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        self._logger.addHandler(console)

        # File handler — best-effort, never block the daemon if state/ is read-only
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = _GzipRotatingFileHandler(
                str(LOG_DIR / f"{self.name}.log"),
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)
        except OSError:
            pass

    def _emit(self, level: int, message: str, exc_info: bool = False, **context: Any) -> None:
        extra: dict[str, Any] = {"context": context} if context else {}
        self._logger.log(level, message, exc_info=exc_info, extra=extra)

    def debug(self, message: str, **context: Any) -> None:
        self._emit(logging.DEBUG, message, **context)

    def info(self, message: str, **context: Any) -> None:
        self._emit(logging.INFO, message, **context)

    def warn(self, message: str, **context: Any) -> None:
        self._emit(logging.WARNING, message, **context)

    warning = warn  # convenience alias

    def error(self, message: str, exc_info: bool = False, **context: Any) -> None:
        self._emit(logging.ERROR, message, exc_info=exc_info, **context)

    def critical(self, message: str, exc_info: bool = False, **context: Any) -> None:
        self._emit(logging.CRITICAL, message, exc_info=exc_info, **context)

    def exception(self, message: str, **context: Any) -> None:
        self._emit(logging.ERROR, message, exc_info=True, **context)


def get_logger(name: str) -> StructuredLogger:
    """Get-or-create the logger for `name`. Reuses handlers across calls."""
    if name not in _LOGGERS:
        _LOGGERS[name] = StructuredLogger(name)
    return _LOGGERS[name]


def reset_loggers() -> None:
    """Test hook — drop the cache + close handlers so a re-init picks up
    fresh env-var values."""
    for lg in _LOGGERS.values():
        for h in list(lg._logger.handlers):
            h.close()
            lg._logger.removeHandler(h)
    _LOGGERS.clear()
