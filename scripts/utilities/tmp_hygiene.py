"""tmp/ hygiene — purge orphan files older than N days.

Background: 2026-06-06 audit revealed tmp/ had ballooned to 6.0 GB (5.8 GB
of frozen CI artifacts + 348 MB Skool browser profile + 93 loose experiment
scripts). Manual purge recovered 99.8%. This script keeps it that way.

Allowlist (NEVER delete, regardless of age):
- pm2-*.log (PM2 manages its own rotation)
- events_offline.jsonl (V6 Apex offline event bus fallback)
- *.lock, *.lock.json, *.pid, *.heartbeat (live IPC state)
- *.env (env files — file-guard also blocks)
- .gitkeep (anchor files)

Default cutoff: 30 days. Override with --days. Dry-run by default for safety;
use --apply to actually delete.

CLI:
    python scripts/utilities/tmp_hygiene.py                # dry-run, 30 days
    python scripts/utilities/tmp_hygiene.py --apply        # actually delete
    python scripts/utilities/tmp_hygiene.py --days 14      # tighter cutoff
    python scripts/utilities/tmp_hygiene.py --apply --json # cron-friendly
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = PROJECT_ROOT / "tmp"

ALLOWLIST_PATTERNS = (
    "pm2-*.log",
    "events_offline.jsonl",
    # Live IPC / dedup state — purging these causes real damage, not just a
    # cold cache. inbound_processed_msgids.json is the inbound-email idempotency
    # ledger: delete it and the next UNSEEN sweep re-classifies, re-drafts and
    # re-hands-off every still-unread email (LLM cost + duplicate ledger rows +
    # duplicate Atlas hand-offs). It's rewritten every 5 min so its mtime is
    # normally fresh anyway; this makes the intent explicit and covers a paused
    # sweep. imap_poison_uids.json is the sibling fetch-failure tracker.
    "inbound_processed_msgids.json",
    "imap_poison_uids.json",
    "notify_dedup.json",
    "*.lock",
    "*.lock.json",
    "*.pid",
    "*.heartbeat",
    "*.env",
    ".gitkeep",
)


def _is_allowlisted(name: str) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in ALLOWLIST_PATTERNS)


def _scan(days: int) -> tuple[list[Path], list[Path]]:
    if not TMP_DIR.exists():
        return [], []
    cutoff = time.time() - (days * 86400)
    to_delete: list[Path] = []
    kept: list[Path] = []
    for entry in TMP_DIR.iterdir():
        if entry.name == "" or entry.name.startswith("."):
            continue
        if _is_allowlisted(entry.name):
            kept.append(entry)
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            to_delete.append(entry)
        else:
            kept.append(entry)
    return to_delete, kept


def _bytes_for(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for sub in path.rglob("*"):
            try:
                if sub.is_file():
                    total += sub.stat().st_size
            except OSError:
                continue
        return total
    except OSError:
        return 0


def _delete(path: Path) -> bool:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
        else:
            import shutil
            shutil.rmtree(path)
        return True
    except OSError:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--days", type=int, default=30, help="Max age in days (default 30)")
    p.add_argument("--apply", action="store_true", help="Actually delete (default dry-run)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    args = p.parse_args()

    to_delete, kept = _scan(args.days)
    bytes_total = sum(_bytes_for(p) for p in to_delete)

    deleted: list[str] = []
    failed: list[str] = []
    if args.apply:
        for path in to_delete:
            if _delete(path):
                deleted.append(path.name)
            else:
                failed.append(path.name)

    result = {
        "tmp_dir": str(TMP_DIR),
        "cutoff_days": args.days,
        "applied": args.apply,
        "candidates": [p.name for p in to_delete],
        "candidate_count": len(to_delete),
        "bytes_recoverable": bytes_total,
        "kept_count": len(kept),
        "deleted": deleted,
        "failed": failed,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    verb = "Deleted" if args.apply else "Would delete"
    mb = bytes_total / (1024 * 1024)
    print(f"{verb} {len(to_delete)} entries ({mb:.1f} MB) older than {args.days} days from {TMP_DIR}")
    if to_delete:
        for path in to_delete[:20]:
            print(f"  - {path.name}")
        if len(to_delete) > 20:
            print(f"  ... and {len(to_delete) - 20} more")
    if failed:
        print(f"FAILED to delete {len(failed)}: {', '.join(failed[:5])}", file=sys.stderr)
    print(f"Kept {len(kept)} entries (allowlist + fresh).")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
