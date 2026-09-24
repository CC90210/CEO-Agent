"""Log rotation for state/*.log and active bridge logs.

Hook logs grow unbounded (secret_guard.log at 108KB, exec_guard.log at 191KB
as of 2026-05-14). Rotates any state/*.log file exceeding MAX_BYTES, keeps
KEEP_BACKUPS gzipped backups, removes older.

Designed to be called once per day from session_start.py (cheap idempotency:
exits in <10ms if no files need rotation). Can also be invoked manually.

CLI:
  python scripts/hooks/rotate_logs.py            # rotate as needed
  python scripts/hooks/rotate_logs.py --dry-run  # report what would rotate
"""
from __future__ import annotations

import argparse
import gzip
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
MEMORY_DIR = PROJECT_ROOT / "memory"
ACTIVE_BRIDGE_LOG_NAMES = (
    "telegram_bridge.log",
    "coordination_bridge.log",
)
MAX_BYTES = 5 * 1024 * 1024
KEEP_BACKUPS = 5
STAMP_PATH = STATE_DIR / ".rotate_logs.stamp"
MIN_INTERVAL_SEC = 60 * 60 * 12
ORPHAN_MIN_AGE_SEC = 5 * 60
_ORPHAN_RE = re.compile(
    r"^\.(?P<live>.+\.log)\.(?P<stamp>\d{8}T\d{6}(?:\d{6})?Z)\."
    r"(?P<pid>\d+)\.rotating$"
)


def _should_skip_today() -> bool:
    if not STAMP_PATH.exists():
        return False
    try:
        last = float(STAMP_PATH.read_text().strip())
    except (OSError, ValueError):
        return False
    return (time.time() - last) < MIN_INTERVAL_SEC


def _touch_stamp() -> None:
    try:
        STATE_DIR.mkdir(exist_ok=True)
        STAMP_PATH.write_text(str(time.time()))
    except OSError:
        pass


def _compress_detached(detached: Path, backup: Path) -> None:
    """Compress to a temporary archive, then publish it atomically."""
    temporary = backup.with_name(f".{backup.name}.{os.getpid()}.tmp")
    try:
        with detached.open("rb") as src, gzip.open(temporary, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.replace(temporary, backup)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _wait_for_detached_writer(detached: Path) -> None:
    """Let a writer that opened the old inode before rename finish its append."""
    previous = -1
    stable_samples = 0
    for _ in range(40):
        size = detached.stat().st_size
        if size == previous:
            stable_samples += 1
            if stable_samples >= 4:
                return
        else:
            stable_samples = 0
        previous = size
        time.sleep(0.025)
    raise OSError(f"detached log is still changing: {detached.name}")


def _prune_backups(path: Path) -> None:
    backups = sorted(
        path.parent.glob(f"{path.stem}.*.log.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[KEEP_BACKUPS:]:
        old.unlink()


def _orphan_target(orphan: Path) -> tuple[Path, Path] | None:
    """Map a trusted orphan filename to its live path and archive path."""
    match = _ORPHAN_RE.fullmatch(orphan.name)
    if not match:
        return None
    live = orphan.with_name(match.group("live"))
    if orphan.parent == MEMORY_DIR and live.name not in ACTIVE_BRIDGE_LOG_NAMES:
        return None
    if orphan.parent not in {STATE_DIR, MEMORY_DIR}:
        return None
    archive = orphan.with_name(f"{live.stem}.{match.group('stamp')}.log.gz")
    return live, archive


def _recover_orphaned_rotations(
    *, dry_run: bool = False
) -> tuple[list[Path], list[tuple[Path, OSError]]]:
    """Retry crash-left raw rotations once they are old enough to be inactive."""
    recovered: list[Path] = []
    failures: list[tuple[Path, OSError]] = []
    now = time.time()
    for directory in (STATE_DIR, MEMORY_DIR):
        if not directory.exists():
            continue
        for orphan in sorted(directory.glob(".*.rotating")):
            target = _orphan_target(orphan)
            if target is None:
                continue
            try:
                if now - orphan.stat().st_mtime < ORPHAN_MIN_AGE_SEC:
                    continue
                live, archive = target
                if dry_run:
                    recovered.append(orphan)
                    continue
                _wait_for_detached_writer(orphan)
                _compress_detached(orphan, archive)
                orphan.unlink()
                _prune_backups(live)
                recovered.append(orphan)
            except OSError as exc:
                failures.append((orphan, exc))
    return recovered, failures


def _rotate(path: Path, dry_run: bool) -> tuple[Path, int] | None:
    size = path.stat().st_size
    if size <= MAX_BYTES:
        return None

    if dry_run:
        return (path, size)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.stem}.{ts}.log.gz")
    detached = path.with_name(f".{path.name}.{ts}.{os.getpid()}.rotating")
    try:
        # Rename is the cutover: all future appendFile/open calls target a new
        # live path. Compression happens only after that boundary, so a bridge
        # write during slow gzip work can never be erased by truncation.
        path.replace(detached)
        path.touch(exist_ok=True)
        _wait_for_detached_writer(detached)
        _compress_detached(detached, backup)
        detached.unlink()
    except OSError:
        # _compress_detached publishes only a complete gzip. The detached raw
        # log remains on disk for the next run's explicit recovery pass, while
        # the new active path continues accepting bridge writes.
        if detached.exists() and not path.exists():
            detached.replace(path)
        raise

    _prune_backups(path)

    return (path, size)


def _iter_log_paths() -> list[Path]:
    """Return the bounded log set; do not sweep unrelated memory evidence."""
    logs = sorted(STATE_DIR.glob("*.log")) if STATE_DIR.exists() else []
    if MEMORY_DIR.exists():
        logs.extend(
            path
            for name in ACTIVE_BRIDGE_LOG_NAMES
            if (path := MEMORY_DIR / name).is_file()
        )
    return logs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rotate state/*.log and active bridge logs larger than 5MB."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Skip 12h idempotency check")
    args = parser.parse_args()

    recovered, orphan_failures = _recover_orphaned_rotations(dry_run=args.dry_run)
    for orphan, exc in orphan_failures:
        print(f"recover orphan {orphan.name}: ERROR {exc}", file=sys.stderr)

    if not args.force and not args.dry_run and _should_skip_today():
        return 1 if orphan_failures else 0

    rotated = []
    failures: list[tuple[Path, OSError]] = list(orphan_failures)
    for log in _iter_log_paths():
        try:
            result = _rotate(log, args.dry_run)
        except OSError as exc:
            failures.append((log, exc))
            print(f"rotate {log.name}: ERROR {exc}", file=sys.stderr)
            continue
        if result:
            rotated.append(result)

    if args.dry_run:
        for orphan in recovered:
            print(f"WOULD RECOVER ORPHAN: {orphan.name}")
        if not rotated and not recovered:
            print("No logs need rotation.")
            return 1 if failures else 0
        for p, sz in rotated:
            print(f"WOULD ROTATE: {p.name} ({sz / 1024:.1f} KB)")
        return 1 if failures else 0

    if rotated:
        for p, sz in rotated:
            print(f"rotated: {p.name} ({sz / 1024:.1f} KB)")
    for orphan in recovered:
        print(f"recovered orphan rotation: {orphan.name}")
    if failures:
        return 1
    _touch_stamp()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
