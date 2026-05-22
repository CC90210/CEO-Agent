"""Single-source loader for `.env.agents` — used by every CLI tool wrapper.

Refuses to load if invoked from `tmp/` (LLM-written one-off scripts) or from
an interactive Python shell. Logs every load to `state/secret_access.log`
(jsonl) so we can audit which keys each script actually touched.

==============================================================================
CANONICAL PATTERN — use this for any new script that needs `.env.agents`:

    from lib.secret_loader import load_env
    env = load_env(required=["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
    url = env["SUPABASE_URL"]

Or, for a single key with a default:

    from lib.secret_loader import get
    debug = get("EMPIRE_DEBUG", "0")

DO NOT use `python-dotenv` (`from dotenv import load_dotenv`) for new code.
It bypasses the audit log and the tmp/-caller refusal, both of which the
guard-mode hooks expect. Existing scripts that still call `load_dotenv` are
on the V6.0 migration backlog — see audit 2026-05-21.
==============================================================================
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env.agents"
ACCESS_LOG = PROJECT_ROOT / "state" / "secret_access.log"

_CACHE: dict[str, str] | None = None


class SecretLoaderRefused(RuntimeError):
    """Raised when the loader refuses to operate (interactive shell, tmp/ caller)."""


def _is_interactive() -> bool:
    if os.environ.get("PYTHONINSPECT"):
        return True
    if hasattr(sys, "ps1"):
        return True
    if not sys.stdin.isatty():
        return False
    return bool(os.environ.get("PYTHON_INTERACTIVE"))


def _caller_file() -> Path | None:
    frame = sys._getframe(2) if hasattr(sys, "_getframe") else None
    while frame is not None:
        fname = frame.f_globals.get("__file__")
        if fname and "secret_loader" not in fname:
            return Path(fname).resolve()
        frame = frame.f_back
    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _log_access(caller: Path | None, keys: Iterable[str]) -> None:
    try:
        ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "caller": str(caller) if caller else "<unknown>",
            "keys": sorted(set(keys)),
        }
        with ACCESS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def load_env(required: Iterable[str] | None = None) -> Mapping[str, str]:
    """Return cached `.env.agents` dict, layered over `os.environ` for missing keys.

    Refuses to operate from tmp/ or interactive shell. Logs the keys requested
    by the calling script.
    """
    global _CACHE

    caller = _caller_file()
    if caller is not None:
        tmp_root = PROJECT_ROOT / "tmp"
        if tmp_root.exists() and _is_under(caller, tmp_root.resolve()):
            raise SecretLoaderRefused(
                f"refusing to load secrets for caller in tmp/: {caller}"
            )
    if _is_interactive():
        raise SecretLoaderRefused(
            "refusing to load secrets from interactive Python shell (PYTHONINSPECT or python -i)"
        )

    if _CACHE is None:
        env: dict[str, str] = {}
        if ENV_FILE.exists():
            env.update(_parse_env(ENV_FILE.read_text(encoding="utf-8")))
        for k, v in os.environ.items():
            env.setdefault(k, v)
        _CACHE = env

    requested = list(required) if required is not None else []
    if requested:
        missing = [k for k in requested if not _CACHE.get(k)]
        if missing:
            raise KeyError(f"missing required env keys: {sorted(missing)}")
    _log_access(caller, requested or _CACHE.keys())
    return _CACHE


def get(key: str, default: str | None = None) -> str | None:
    env = load_env()
    return env.get(key, default)


def bootstrap() -> dict[str, str]:
    """One-liner replacement for the 6-line module-load bootstrap pattern.

    Loads .env.agents via the canonical audit-logged path AND populates
    os.environ.setdefault for every key — so legacy `os.environ.get(...)`
    callsites keep working without a rewrite.

    Replaces this boilerplate in every script::

        from lib.secret_loader import load_env as _load_env
        for _k, _v in _load_env().items():
            os.environ.setdefault(_k, str(_v))

    with::

        from lib.secret_loader import bootstrap
        bootstrap()

    Returns the loaded env dict for callers who want it; safe to ignore.
    Idempotent — second call is a cache hit + no-op on os.environ.
    """
    env = load_env()
    for k, v in env.items():
        os.environ.setdefault(k, v)
    return dict(env)


def reset_cache() -> None:
    """Test hook — reset the in-process cache."""
    global _CACHE
    _CACHE = None
