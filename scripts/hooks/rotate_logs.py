"""Log rotation for state/*.log — size-based, gzipped backups.

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
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
MAX_BYTES = 5 * 1024 * 1024
KEEP_BACKUPS = 5
STAMP_PATH = STATE_DIR / ".rotate_logs.stamp"
MIN_INTERVAL_SEC = 60 * 60 * 12


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


def _rotate(path: Path, dry_run: bool) -> tuple[Path, int] | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= MAX_BYTES:
        return None

    if dry_run:
        return (path, size)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}.{ts}.log.gz")
    try:
        with path.open("rb") as src, gzip.open(backup, "wb") as dst:
            shutil.copyfileobj(src, dst)
        path.write_bytes(b"")
    except OSError as e:
        print(f"rotate {path.name}: ERROR {e}", file=sys.stderr)
        return None

    backups = sorted(
        path.parent.glob(f"{path.stem}.*.log.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[KEEP_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass

    return (path, size)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate state/*.log files larger than 5MB.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Skip 12h idempotency check")
    args = parser.parse_args()

    if not args.force and not args.dry_run and _should_skip_today():
        return 0

    if not STATE_DIR.exists():
        return 0

    rotated = []
    for log in sorted(STATE_DIR.glob("*.log")):
        result = _rotate(log, args.dry_run)
        if result:
            rotated.append(result)

    if args.dry_run:
        if not rotated:
            print("No logs need rotation.")
            return 0
        for p, sz in rotated:
            print(f"WOULD ROTATE: {p.name} ({sz / 1024:.1f} KB)")
        return 0

    if rotated:
        for p, sz in rotated:
            print(f"rotated: {p.name} ({sz / 1024:.1f} KB)")
    _touch_stamp()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
