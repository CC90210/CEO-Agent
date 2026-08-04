#!/usr/bin/env python3
"""Retire CRM rows that were never leads.

CAPABILITY_META = see bottom.

Two auto-create paths wrote a `leads` row for every inbound sender and every
outbound recipient, with no check on whether they should be in the CRM at all
(fixed 2026-08-04 in lib/lead_contract.should_create_lead). The residue on
2026-08-04 was 37 of 63 rows: Google/Stripe/Vercel/LinkedIn notifications,
vendor newsletters, and one send-path probe to an RFC-2606 reserved domain.
Lead counts and pipeline metrics were reading 2.4x reality.

This retires them by setting status='dead' — NOT DELETE. The rows keep their
lead_interactions history, the change is one UPDATE away from being reversed,
and anything that was misjudged can be resurrected. Deleting CRM rows to fix a
counting bug trades one irreversible mistake for another.

Selection is deliberately narrow: a row is only touched if it is BOTH
tenantless AND fails should_create_lead(). A tenant-owned row is never
eligible, whatever it looks like.

    python scripts/purge_junk_leads.py              # dry run, writes nothing
    python scripts/purge_junk_leads.py --apply      # perform the update
    python scripts/purge_junk_leads.py --undo       # restore status='new'
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.lead_contract import should_create_lead  # noqa: E402

RETIRED_STATUS = "dead"
MARKER = "retired-2026-08-04-junk-autocreate"


def _client():
    from integrations.supabase_tool import get_client, load_env  # noqa: E402
    return get_client(load_env(), project="bravo")


def _fetch(db, limit: int = 2000) -> list[dict]:
    return (db.table("leads")
            .select("id,email,name,source,status,tenant_id,notes")
            .limit(limit).execute().data or [])


def select_junk(rows: list[dict]) -> list[tuple[dict, str]]:
    """Tenantless AND ineligible. Both conditions, always."""
    out = []
    for r in rows:
        if r.get("tenant_id"):
            continue                      # tenant-owned: never touched
        if str(r.get("status") or "").lower() == RETIRED_STATUS:
            continue                      # already retired
        create, why = should_create_lead(r.get("email") or "",
                                         {"category": "low_priority"})
        if not create:
            out.append((r, why))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Retire junk auto-created leads.")
    ap.add_argument("--apply", action="store_true", help="Perform the update")
    ap.add_argument("--undo", action="store_true",
                    help="Restore rows this script retired back to status='new'")
    args = ap.parse_args(argv)

    db = _client()
    rows = _fetch(db)

    if args.undo:
        targets = [r for r in rows if MARKER in str(r.get("notes") or "")]
        print(f"rows to restore: {len(targets)}")
        for r in targets:
            if args.apply:
                db.table("leads").update({"status": "new"}).eq("id", r["id"]).execute()
            print(f"  {'restored' if args.apply else 'would restore'}  {r.get('email')}")
        if not args.apply:
            print("\n(dry run — pass --apply to write)")
        return 0

    junk = select_junk(rows)
    kept = len(rows) - len(junk)
    print(f"leads scanned      : {len(rows)}")
    print(f"tenant-owned/valid : {kept}  (never touched)")
    print(f"to retire          : {len(junk)}\n")
    for r, why in junk:
        print(f"  {str(r.get('email'))[:44]:46} {why}")

    if not args.apply:
        print("\n(dry run — nothing written. Pass --apply to retire these.)")
        return 0

    done = 0
    for r, why in junk:
        note = f"{(r.get('notes') or '').strip()}\n{MARKER}: {why}".strip()
        db.table("leads").update({"status": RETIRED_STATUS, "notes": note}) \
          .eq("id", r["id"]).execute()
        done += 1
    print(f"\nretired {done} row(s) to status='{RETIRED_STATUS}' "
          f"(reverse with --undo --apply)")
    return 0


CAPABILITY_META = {
    "category": "lead.data_operations",
    "lifecycle": "one_off",
    "risk": "external_write",
    "triggers": ["purge junk leads", "retire junk leads", "clean the crm"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
