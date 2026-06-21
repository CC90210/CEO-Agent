"""SQLite backup + restore for V6 state databases.

Uses the native `sqlite3.Connection.backup()` API — a consistent snapshot
even while the source DB is in WAL mode and being written to. Pre-backup,
we run `PRAGMA wal_checkpoint(TRUNCATE)` so the WAL file is folded back
into the main DB and the backup is a single self-contained file.

Backup file naming: `backup_{db_name}_{YYYYMMDD_HHMMSS}.db`
Backup directory:   `state/backups/`

Usage:
    python scripts/state/backup_db.py backup [--keep N] [--json]
    python scripts/state/backup_db.py restore --file backup_empire_state_20260521_030000.db [--json]
    python scripts/state/backup_db.py list [--json]
    python scripts/state/backup_db.py verify --file <name> [--json]
    python scripts/state/backup_db.py prune --keep N [--json]

Cron entry (registered in cron_engine.py SEED_JOBS):
    daily 03:00 -> python scripts/state/backup_db.py backup --keep 7

Exit codes: 0 success, 1 failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
BACKUP_DIR = STATE_DIR / "backups"

# Databases to back up. Each entry: (name, path). Missing files are skipped
# with a warning — backup never fails because the secondary DB isn't there.
DB_TARGETS: list[tuple[str, Path]] = [
    ("empire_state", STATE_DIR / "empire_state.db"),
    ("memory_index", STATE_DIR / "memory_index.db"),
    ("site_reputation", STATE_DIR / "site_reputation.db"),
]

_BACKUP_NAME_RE = re.compile(r"^backup_(?P<db>[a-z_]+)_(?P<ts>\d{8}_\d{6})\.db$")


def _logger():
    """Use structured_log when available; fall back to stderr prints."""
    try:
        from lib.structured_log import get_logger  # type: ignore
        return get_logger("backup_db")
    except Exception:
        class _StubLog:
            def info(self, msg, **ctx): print(f"[backup_db] INFO {msg} {ctx}", file=sys.stderr)
            def warn(self, msg, **ctx): print(f"[backup_db] WARN {msg} {ctx}", file=sys.stderr)
            def error(self, msg, **ctx): print(f"[backup_db] ERR  {msg} {ctx}", file=sys.stderr)
        return _StubLog()


# ── Core operations ─────────────────────────────────────────────────────

def _ensure_backup_dir() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _backup_one(name: str, src: Path, ts: str) -> dict[str, Any]:
    """Snapshot one DB to backup dir. Returns metadata for the entry."""
    log = _logger()
    if not src.exists():
        log.warn("source_db_missing", db=name, path=str(src))
        return {"db": name, "status": "skipped", "reason": "source_missing"}

    dest = BACKUP_DIR / f"backup_{name}_{ts}.db"

    src_conn = sqlite3.connect(str(src))
    try:
        # Checkpoint WAL → main so the backup is a single self-contained file
        try:
            src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass  # not in WAL mode, nothing to checkpoint

        # Atomic snapshot via SQLite's native backup API
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    # Verify the snapshot
    verify = _verify_one(dest)
    size = dest.stat().st_size
    log.info("backup_complete", db=name, dest=str(dest), size_bytes=size, integrity=verify["status"])
    return {
        "db": name,
        "status": "ok" if verify["status"] == "ok" else "verify_failed",
        "dest": str(dest),
        "size_bytes": size,
        "integrity": verify["status"],
    }


def _verify_one(path: Path) -> dict[str, Any]:
    """`PRAGMA integrity_check` on a backup file."""
    if not path.exists():
        return {"status": "missing", "file": str(path)}
    # A valid SQLite database is at least 100 bytes (the file header alone is
    # exactly 100 bytes). Reject anything smaller deterministically — sqlite's
    # PRAGMA integrity_check can behave inconsistently across platforms on a
    # truncated/empty file (e.g. treat it as a fresh empty db -> "ok"), which
    # would let a corrupt backup pass verification.
    if path.stat().st_size < 100:
        return {"status": "corrupt", "file": str(path),
                "error": f"file too small to be a sqlite db ({path.stat().st_size} bytes)"}
    try:
        conn = sqlite3.connect(str(path))
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return {"status": "corrupt", "file": str(path), "error": str(exc)}
    result = row[0] if row else "no_result"
    return {"status": "ok" if result == "ok" else "fail", "file": str(path), "result": result}


def _list_backups() -> list[dict[str, Any]]:
    """Enumerate backups newest-first, with parsed metadata."""
    if not BACKUP_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for p in BACKUP_DIR.iterdir():
        if not p.is_file():
            continue
        m = _BACKUP_NAME_RE.match(p.name)
        if not m:
            continue
        ts_raw = m.group("ts")
        try:
            ts_iso = datetime.strptime(ts_raw, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            ts_iso = ts_raw
        items.append({
            "name": p.name,
            "db": m.group("db"),
            "timestamp": ts_iso,
            "size_bytes": p.stat().st_size,
            "path": str(p),
        })
    items.sort(key=lambda x: x["name"], reverse=True)
    return items


def _restore_one(backup_name: str) -> dict[str, Any]:
    """Atomic-swap restore. Verifies the backup before clobbering the live DB."""
    log = _logger()
    src = BACKUP_DIR / backup_name
    if not src.exists():
        return {"status": "error", "reason": "backup_not_found", "file": backup_name}

    m = _BACKUP_NAME_RE.match(backup_name)
    if not m:
        return {"status": "error", "reason": "bad_filename", "file": backup_name}
    db_name = m.group("db")

    target = next((p for n, p in DB_TARGETS if n == db_name), None)
    if target is None:
        return {"status": "error", "reason": "unknown_db", "db": db_name}

    verify = _verify_one(src)
    if verify["status"] != "ok":
        log.error("restore_aborted_corrupt_backup", file=backup_name, integrity=verify)
        return {"status": "error", "reason": "backup_corrupt", "integrity": verify}

    # Atomic swap: copy to <target>.new, then rename over <target>
    new_path = target.with_suffix(target.suffix + ".new")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, new_path)
    except OSError as exc:
        log.error("restore_copy_failed", error=str(exc))
        return {"status": "error", "reason": "copy_failed", "error": str(exc)}

    try:
        os.replace(new_path, target)
    except OSError as exc:
        new_path.unlink(missing_ok=True)
        log.error("restore_swap_failed", error=str(exc))
        return {"status": "error", "reason": "swap_failed", "error": str(exc)}

    log.info("restore_complete", db=db_name, restored_from=backup_name, target=str(target))
    return {"status": "ok", "db": db_name, "restored_from": backup_name, "target": str(target)}


def _prune(keep: int) -> dict[str, Any]:
    """Keep last N backups PER DB; delete older ones."""
    if keep < 1:
        return {"status": "error", "reason": "keep_must_be_>=1"}
    log = _logger()
    by_db: dict[str, list[dict[str, Any]]] = {}
    for item in _list_backups():
        by_db.setdefault(item["db"], []).append(item)
    removed: list[str] = []
    for db_name, items in by_db.items():
        for stale in items[keep:]:
            try:
                Path(stale["path"]).unlink()
                removed.append(stale["name"])
            except OSError as exc:
                log.warn("prune_unlink_failed", file=stale["name"], error=str(exc))
    log.info("prune_complete", kept=keep, removed_count=len(removed))
    return {"status": "ok", "kept_per_db": keep, "removed": removed, "removed_count": len(removed)}


# ── CLI surface ─────────────────────────────────────────────────────────

def _emit(payload: dict[str, Any], as_json: bool, ok: bool = True) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        if "results" in payload:
            for r in payload["results"]:
                marker = "OK" if r.get("status") == "ok" else "FAIL"
                print(f"  [{marker}] {r}")
        else:
            print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


def cmd_backup(args: argparse.Namespace) -> int:
    _ensure_backup_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results = [_backup_one(name, path, ts) for name, path in DB_TARGETS]
    all_ok = all(r.get("status") in ("ok", "skipped") for r in results)
    payload = {"action": "backup", "timestamp": ts, "results": results}
    if args.keep:
        prune = _prune(args.keep)
        payload["prune"] = prune
    return _emit(payload, args.json, ok=all_ok)


def cmd_restore(args: argparse.Namespace) -> int:
    result = _restore_one(args.file)
    return _emit({"action": "restore", **result}, args.json, ok=result.get("status") == "ok")


def cmd_list(args: argparse.Namespace) -> int:
    items = _list_backups()
    return _emit({"action": "list", "count": len(items), "backups": items}, args.json, ok=True)


def cmd_verify(args: argparse.Namespace) -> int:
    path = BACKUP_DIR / args.file
    result = _verify_one(path)
    return _emit({"action": "verify", **result}, args.json, ok=result.get("status") == "ok")


def cmd_prune(args: argparse.Namespace) -> int:
    result = _prune(args.keep)
    return _emit({"action": "prune", **result}, args.json, ok=result.get("status") == "ok")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="action", required=True)

    s_backup = sub.add_parser("backup", help="snapshot all state DBs")
    s_backup.add_argument("--keep", type=int, default=None, help="prune to last N per DB after backup")
    s_backup.set_defaults(func=cmd_backup)

    s_restore = sub.add_parser("restore", help="atomic-swap restore from a named backup")
    s_restore.add_argument("--file", required=True, help="backup filename (under state/backups/)")
    s_restore.set_defaults(func=cmd_restore)

    s_list = sub.add_parser("list", help="enumerate available backups")
    s_list.set_defaults(func=cmd_list)

    s_verify = sub.add_parser("verify", help="run PRAGMA integrity_check on a backup")
    s_verify.add_argument("--file", required=True, help="backup filename (under state/backups/)")
    s_verify.set_defaults(func=cmd_verify)

    s_prune = sub.add_parser("prune", help="keep last N per-DB, delete older")
    s_prune.add_argument("--keep", type=int, required=True, help="number of backups to keep per DB")
    s_prune.set_defaults(func=cmd_prune)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
