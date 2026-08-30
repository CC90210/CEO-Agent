"""Age out agent_events rows that will never be consumed.

WHY THIS EXISTS
---------------
Measured 2026-08-28: every one of the first 5,000 agent_events rows had
status='pending'. Nothing in the fleet ever moves an event to a terminal state,
so the queue is append-only in practice and grows without bound. 4,734 of those
5,000 — 95% of the bus — were TEXTTORRENT_UNMAPPED_DID: one row per inbound SMS
to a phone number with no tenant mapping, emitted by a producer OUTSIDE this
repo (SunBiz/TextTorrent), for which no consumer is registered anywhere.

The router is not at fault and is deliberately not the fix. event_router.py:21-23
documents it as cursor-based, read-only and lossless — claiming is the per-agent
consumer path, by design. The problem is that for these event types there is no
consumer and never will be, so "pending" is a permanent lie about work that is
waiting to happen.

WHY 'dead' AND NOT DELETE
-------------------------
015_v6_event_bus_extensions.sql constrains status to
('pending','processing','done','failed','dead'). 'dead' is exactly this case: an
event nobody will process. Marking preserves the row — agent_events is also the
Bravo<->APEX coordination channel and a shared audit trail, so deleting rows out
of it is not ours to do unilaterally. Marking unblocks the queue and keeps the
history.

SAFETY
------
Dry-run by default; --apply is required to write. Only rows OLDER than --days
are touched, so nothing in the live coordination window is affected. --type
restricts to one event type when you want to clear a known-unactionable producer
without touching anything else.

CLI:
  python scripts/core/event_retention.py                       # dry run, 30d
  python scripts/core/event_retention.py --type TEXTTORRENT_UNMAPPED_DID
  python scripts/core/event_retention.py --apply --days 30
  python scripts/core/event_retention.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

DEFAULT_DAYS = 30
TERMINAL = "dead"


def _client():
    from integrations.supabase_tool import get_client  # noqa: PLC0415
    from lib.secret_loader import load_env  # noqa: PLC0415
    return get_client(dict(load_env()))


def _as_dt(raw) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def find_stale(db, days: int, event_type: str | None, limit: int) -> list[dict]:
    """Pending rows older than `days`. Age is computed client-side because
    published_at and created_at are populated inconsistently across producers —
    an external producer may set only one of them."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.table("agent_events").select(
        "id,event_type,status,published_at,created_at").eq("status", "pending")
    if event_type:
        q = q.eq("event_type", event_type)
    rows = q.limit(limit).execute().data or []
    stale = []
    for r in rows:
        ts = _as_dt(r.get("published_at")) or _as_dt(r.get("created_at"))
        if ts is None:
            continue  # undateable: leave it alone rather than guess it is old
        if ts < cutoff:
            stale.append(r)
    return stale


def sweep(days: int = DEFAULT_DAYS, event_type: str | None = None,
          apply: bool = False, limit: int = 20000) -> dict:
    db = _client()
    stale = find_stale(db, days, event_type, limit)
    by_type = Counter(r.get("event_type") for r in stale)

    marked, failed = 0, 0
    if apply:
        for r in stale:
            try:
                db.table("agent_events").update({
                    "status": TERMINAL,
                    "last_error": "aged out by event_retention: no consumer "
                                  f"claimed it within {days}d",
                }).eq("id", r["id"]).eq("status", "pending").execute()
                marked += 1
            except Exception:  # noqa: BLE001
                failed += 1

    return {
        "cutoff_days": days,
        "event_type": event_type,
        "applied": apply,
        "stale_found": len(stale),
        "by_type": dict(by_type.most_common(10)),
        "marked": marked,
        "failed": failed,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--days", type=int, default=DEFAULT_DAYS)
    p.add_argument("--type", dest="event_type", help="restrict to one event_type")
    p.add_argument("--apply", action="store_true", help="write (default: dry run)")
    p.add_argument("--limit", type=int, default=20000)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = sweep(args.days, args.event_type, args.apply, args.limit)

    if args.json:
        # ONE compact line — scheduler.py keeps only the last stdout line.
        print(json.dumps(result, separators=(",", ":"), default=str))
        return 0

    verb = "Marked" if args.apply else "Would mark"
    print(f"{verb} {result['stale_found']} pending event(s) older than "
          f"{result['cutoff_days']}d as '{TERMINAL}'")
    for t, n in result["by_type"].items():
        print(f"  {n:>6}  {t}")
    if args.apply:
        print(f"marked={result['marked']} failed={result['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
