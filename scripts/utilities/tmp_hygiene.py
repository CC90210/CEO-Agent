"""tmp/ hygiene — purge orphan files older than N days.

Background: 2026-06-06 audit revealed tmp/ had ballooned to 6.0 GB (5.8 GB
of frozen CI artifacts + 348 MB Skool browser profile + 93 loose experiment
scripts). Manual purge recovered 99.8%. This script keeps it that way.

Allowlist (NEVER delete, regardless of age):
- events_offline.jsonl (V6 Apex offline event bus fallback)
- agent_inbox/ (durable cross-agent handoffs awaiting acknowledgement)
- *.lock, *.lock.json, *.pid, *.heartbeat (live IPC state)
- *.env (env files — file-guard also blocks)
- .gitkeep (anchor files)

Default cutoff: 30 days. Override with --days. Dry-run by default for safety;
use --apply to move stale entries into a seven-day recovery quarantine. Only a
later run purges items whose quarantine grace period has expired.

CLI:
    python scripts/utilities/tmp_hygiene.py                # dry-run, 30 days
    python scripts/utilities/tmp_hygiene.py --apply        # quarantine, then age out
    python scripts/utilities/tmp_hygiene.py --days 14      # tighter cutoff
    python scripts/utilities/tmp_hygiene.py --apply --json # cron-friendly
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = PROJECT_ROOT / "tmp"
QUARANTINE_DIR_NAME = ".hygiene_quarantine"
QUARANTINE_RETENTION_DAYS = 7

ALLOWLIST_PATTERNS = (
    # This directory is governed by _purge_quarantine. Letting the generic
    # top-level scan move the quarantine into itself would destroy the
    # two-stage recovery boundary once the directory became old and empty.
    QUARANTINE_DIR_NAME,
    "events_offline.jsonl",
    # Cross-agent handoffs may be old precisely because the receiving agent is
    # offline. Treat this directory as durable queue state, not generic scratch.
    "agent_inbox",
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
    # DB restore points (db_snapshot.py, 2026-08-02). The directory's mtime only
    # moves when a new snapshot lands, so a 30-day gap in migrations would have
    # purged every baseline — a backup a cron deletes is worse than none, because
    # the gate still reports "verified" right up until the file is gone.
    "snapshots",
    # Cron failure archive (2026-08-28). Same trap as `snapshots` above, one
    # directory over: this scan is TOP-LEVEL ONLY (TMP_DIR.iterdir()), so
    # cron_failures/ is judged by its own mtime, which only moves when a job
    # FAILS. A quiet 90-day stretch — the outcome we are working toward — would
    # therefore delete the entire failure archive in one pass, and the evidence
    # of what used to break is exactly what you need the first time it breaks
    # again. Individual files inside it are aged by _prune_cron_failures below,
    # which is what the retention policy actually wanted.
    "cron_failures",
    "*.lock",
    "*.lock.json",
    "*.pid",
    "*.heartbeat",
    "*.env",
    ".gitkeep",
)


def _is_allowlisted(name: str) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in ALLOWLIST_PATTERNS)


def _newest_mtime(path: Path) -> float | None:
    """Return the newest timestamp anywhere under ``path``.

    A directory mtime changes when entries are added or removed, not when an
    existing child is updated. Judging a tree by that one timestamp can erase
    fresh work. Any unreadable descendant fails closed by returning ``None``.
    """
    try:
        newest = path.stat().st_mtime
        if not path.is_dir() or path.is_symlink():
            return newest
        for descendant in path.rglob("*"):
            try:
                newest = max(newest, descendant.stat().st_mtime)
            except OSError:
                return None
        return newest
    except OSError:
        return None


def _scan(days: int) -> tuple[list[Path], list[Path]]:
    if not TMP_DIR.exists():
        return [], []
    cutoff = time.time() - (days * 86400)
    to_delete: list[Path] = []
    kept: list[Path] = []
    for entry in TMP_DIR.iterdir():
        if entry.name == "":
            continue
        if _is_allowlisted(entry.name):
            kept.append(entry)
            continue
        if entry.name.startswith("."):
            continue
        mtime = _newest_mtime(entry)
        if mtime is None:
            kept.append(entry)
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


def _quarantine_dir() -> Path:
    return TMP_DIR / QUARANTINE_DIR_NAME


def _quarantine(path: Path, *, stale_cutoff: float | None = None) -> Path | None:
    """Atomically move a still-stale candidate aside for recoverable cleanup.

    ``_scan`` is discovery, not authority to delete later. Rechecking before
    and immediately after the rename closes the practical scan/action race: if
    fresh work appeared, the tree is restored instead of entering retention.
    """
    if stale_cutoff is not None:
        newest = _newest_mtime(path)
        if newest is None or newest >= stale_cutoff:
            return None
    quarantine = _quarantine_dir()
    quarantine.mkdir(parents=True, exist_ok=True)
    destination = quarantine / f"{time.time_ns()}--{path.name}"
    path.replace(destination)
    if stale_cutoff is not None:
        newest = _newest_mtime(destination)
        if newest is None or newest >= stale_cutoff:
            if not path.exists():
                destination.replace(path)
                return None
            # A path-based writer recreated the original while an old handle
            # updated the detached tree. Preserve both: the detached copy gets
            # a full quarantine grace period and the new live path is untouched.
    # Retention is based on when the item entered quarantine, not on the stale
    # payload timestamp that made it eligible in the first place.
    try:
        os.utime(destination, None)
    except OSError:
        # Without a fresh quarantine timestamp the next sweep could purge the
        # item immediately. Roll back instead of pretending it received a
        # recovery window.
        destination.replace(path)
        raise
    return destination


def _purge_quarantine(days: int, apply: bool) -> tuple[list[str], list[str], int]:
    """Purge items only after they have spent ``days`` in quarantine."""
    quarantine = _quarantine_dir()
    if not quarantine.is_dir():
        return [], [], 0
    cutoff = time.time() - (days * 86400)
    purged: list[str] = []
    failed: list[str] = []
    bytes_total = 0
    for entry in quarantine.iterdir():
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
        except OSError:
            failed.append(entry.name)
            continue
        size = _bytes_for(entry)
        if apply and not _delete(entry):
            failed.append(entry.name)
            continue
        purged.append(entry.name)
        bytes_total += size
    return purged, failed, bytes_total


# Failure logs are evidence, so they outlive ordinary tmp/ scratch by a wide
# margin — long enough to still be there when the same job breaks again.
CRON_FAILURE_RETENTION_DAYS = 90


def _prune_cron_failures(days: int, apply: bool) -> tuple[list[str], int]:
    """Age individual files INSIDE tmp/cron_failures/.

    _scan() above is top-level only, so it can see the directory but never its
    contents — which meant the "keep ~90 days" retention policy was never
    actually implemented for the one place it was written down. The directory
    itself is allowlisted (deleting the whole archive during a quiet stretch is
    the failure mode); this ages what is inside it.
    """
    d = TMP_DIR / "cron_failures"
    if not d.is_dir():
        return [], 0
    cutoff = time.time() - (days * 86400)
    removed: list[str] = []
    freed = 0
    for f in d.iterdir():
        if not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_mtime >= cutoff:
            continue
        if apply:
            try:
                held = _quarantine(f, stale_cutoff=cutoff)
            except OSError:
                continue
            if held is None:
                continue
        freed += st.st_size
        removed.append(f.name)
    return removed, freed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--days", type=int, default=30, help="Max age in days (default 30)")
    p.add_argument("--apply", action="store_true", help="Actually delete (default dry-run)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--failure-days", type=int, default=CRON_FAILURE_RETENTION_DAYS,
                   help=f"Age for tmp/cron_failures/ contents "
                        f"(default {CRON_FAILURE_RETENTION_DAYS})")
    args = p.parse_args()

    quarantine_purged, quarantine_purge_failed, quarantine_bytes = _purge_quarantine(
        QUARANTINE_RETENTION_DAYS,
        args.apply,
    )
    to_delete, kept = _scan(args.days)
    stale_failures, failure_bytes = _prune_cron_failures(args.failure_days, args.apply)
    bytes_total = sum(_bytes_for(p) for p in to_delete)

    quarantined: list[str] = []
    skipped_fresh: list[str] = []
    failed: list[str] = list(quarantine_purge_failed)
    if args.apply:
        cutoff = time.time() - (args.days * 86400)
        for path in to_delete:
            try:
                held = _quarantine(path, stale_cutoff=cutoff)
                if held is None:
                    skipped_fresh.append(path.name)
                else:
                    quarantined.append(path.name)
            except OSError:
                failed.append(path.name)

    result = {
        "tmp_dir": str(TMP_DIR),
        "cutoff_days": args.days,
        "applied": args.apply,
        "candidates": [p.name for p in to_delete],
        "candidate_count": len(to_delete),
        "bytes_recoverable": bytes_total,
        "kept_count": len(kept),
        "quarantined": quarantined,
        "skipped_became_fresh": skipped_fresh,
        "deleted": quarantine_purged if args.apply else [],
        "quarantine_purge_candidates": quarantine_purged,
        "quarantine_bytes_purged": quarantine_bytes,
        "quarantine_retention_days": QUARANTINE_RETENTION_DAYS,
        "failed": failed,
        "cron_failures_pruned": len(stale_failures),
        "cron_failures_bytes": failure_bytes,
        "cron_failures_cutoff_days": args.failure_days,
    }

    if args.json:
        # ONE compact line, deliberately. scheduler.py USED TO store
        # out[-1][:200] as last_result, so pretty JSON ended in a lone bracket
        # and the run read as OPAQUE ("verdict unknowable"). That slice is gone
        # (scheduler.summarize_stdout, 2026-08-29) and a pretty payload would
        # now be summarized correctly — so this is no longer load-bearing for
        # legibility. Keep it compact anyway: one line is what the downstream
        # parsers expect and what a log is readable as. Do not "improve" this
        # back to indent=2.
        print(json.dumps(result, separators=(",", ":")))
        return 0

    verb = "Quarantined" if args.apply else "Would quarantine"
    mb = bytes_total / (1024 * 1024)
    print(f"{verb} {len(to_delete)} entries ({mb:.1f} MB) older than {args.days} days from {TMP_DIR}")
    if to_delete:
        for path in to_delete[:20]:
            print(f"  - {path.name}")
        if len(to_delete) > 20:
            print(f"  ... and {len(to_delete) - 20} more")
    if failed:
        print(f"FAILED cleanup actions {len(failed)}: {', '.join(failed[:5])}", file=sys.stderr)
    if quarantine_purged:
        purge_verb = "Purged" if args.apply else "Would purge"
        print(f"{purge_verb} {len(quarantine_purged)} expired quarantine item(s).")
    print(f"Kept {len(kept)} entries (allowlist + fresh).")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
