"""exec_override_expire.py — auto-mark expired override requests.

Runs every 10 minutes via the SEED_JOBS cron. Sweeps `exec_overrides`
for any `status='pending'` row whose `expires_at` is past, sets
`status='expired'`.

Why this exists: the exec_guard creates a `pending` override row every
time it blocks a hard-blocklisted command. Each row carries a 5-minute
approval window. Without cleanup, the dashboard's "pending count" badge
balloons over time — CC saw 284 pending on 2026-05-22 because every
prior block (incl. all the test_exec_override.py test runs) had never
been transitioned out of `pending`.

The correct UX: pending count = real requests waiting for human input.
Expired requests are settled state, not work queue. This script enforces
that invariant.

Flags:
  --json    machine-readable summary
  --dry-run scan + count, no DB writes

Exit code:
  0 = sweep succeeded (even if 0 rows expired)
  1 = sweep errored (DB unreachable etc.)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib.secret_loader import bootstrap  # noqa: E402
bootstrap()

from supabase_tool import get_client, load_env  # noqa: E402


def sweep(dry_run: bool = False) -> dict:
    db = get_client(load_env())
    r = (
        db.table("exec_overrides")
        .select("command_hash,expires_at")
        .eq("status", "pending")
        .execute()
    )
    rows = r.data or []
    now = datetime.now(timezone.utc)
    expired_hashes: list[str] = []
    for row in rows:
        exp = row.get("expires_at")
        if not exp:
            expired_hashes.append(row["command_hash"])
            continue
        try:
            if datetime.fromisoformat(exp.replace("Z", "+00:00")) < now:
                expired_hashes.append(row["command_hash"])
        except Exception:
            expired_hashes.append(row["command_hash"])

    if dry_run or not expired_hashes:
        return {
            "scanned": len(rows),
            "expired_count": len(expired_hashes),
            "applied": False if dry_run else len(expired_hashes) == 0,
        }

    now_iso = now.isoformat()
    BATCH = 50
    total_updated = 0
    for i in range(0, len(expired_hashes), BATCH):
        chunk = expired_hashes[i : i + BATCH]
        u = (
            db.table("exec_overrides")
            .update({"status": "expired", "updated_at": now_iso})
            .in_("command_hash", chunk)
            .execute()
        )
        total_updated += len(u.data or [])

    return {
        "scanned": len(rows),
        "expired_count": len(expired_hashes),
        "rows_updated": total_updated,
        "applied": True,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--dry-run", action="store_true", help="Scan + count, no DB writes")
    args = p.parse_args()

    try:
        summary = sweep(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: sweep failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary))
    elif summary["expired_count"] == 0:
        print(f"ok: {summary['scanned']} pending rows scanned, none expired")
    elif args.dry_run:
        print(f"dry-run: would expire {summary['expired_count']} of {summary['scanned']} pending rows")
    else:
        print(f"expired {summary['expired_count']} stale override request(s) "
              f"({summary['scanned']} pending scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
