#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Find addresses suppressed on ONE tenant that another tenant can still mail.

WHY THIS EXISTS
---------------
2026-09-07. checkEmailSuppressed() enforces on (tenant_id, email), and that is
DELIBERATE: a merchant who unsubscribes from one brand must not be silently
unsubscribed from another, which is the correct CASL reading and is documented
in lib/email/sending-identity.ts.

But the same design makes a STANDING ORDER silently tenant-local. The operator's
"never email this address, suppress on sight" order for a test account was filed
against SunBiz only. Two live OASIS leads carried that exact address, both at
stage founder_meeting_booked -- a stage whose automation sends confirmations and
reminders. Every guardrail read as passing, because the query found no row for
the OASIS tenant and correctly returned suppressed=false.

The fix for that instance was the missing row. This is the guard for the CLASS:
it asks the question nobody was asking -- "is any address we promised never to
mail reachable from a different tenant?" -- and it fails loudly with the exact
rows to add.

READ-ONLY. It reports; it never writes a suppression. Deciding that an opt-out
on one brand should bind another is a consent judgement, and it belongs to the
operator, not to a script run at 3am.

Usage:
    python scripts/audit_suppression_coverage.py            # human-readable
    python scripts/audit_suppression_coverage.py --json     # machine-readable
    python scripts/audit_suppression_coverage.py --strict   # exit 1 on any gap
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.db_turso import get_db  # noqa: E402

CAPABILITY_META = {
    "category": "communication.email",
    "lifecycle": "active",
    # Reads two tables and writes nothing. The read-only guarantee is enforced
    # by a test that walks the AST, not just asserted here.
    "risk": "read_only",
    "triggers": [
        "audit email suppression coverage",
        "is a suppressed address mailable from another tenant",
        "check standing never-email orders",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": True},
}

REASON = "cross-tenant suppression coverage audit"


def find_gaps(db) -> list[dict]:
    """Every (address, other_tenant) pair where the address is suppressed
    somewhere else and is a live lead on that other tenant."""
    suppressed = db.query(
        "select distinct lower(trim(email)) email, tenant_id from email_suppressions "
        "where email is not null and trim(email) <> ''",
        allow_unscoped=True,
        reason=REASON,
    )
    # Normalised in Python as well as in the SQL above. The SQL lower()/trim()
    # is what runs in production, but a defence that lives only inside a query
    # string evaporates the moment someone edits the query -- and the failure
    # mode is silent under-reporting, which is exactly the shape of the bug this
    # script exists to catch. Cheap to do twice.
    by_addr: dict[str, set[str]] = {}
    for row in suppressed:
        r = dict(row)
        addr = str(r.get("email") or "").strip().lower()
        if not addr:
            continue
        by_addr.setdefault(addr, set()).add(r.get("tenant_id") or "")
    if not by_addr:
        return []

    # One scan of the lead corpus, not one query per address: at 84 suppressions
    # the per-address version would be 84 round trips against a ~145ms floor.
    leads = db.query(
        "select tenant_id, id, lower(trim(json_extract(data,'$.email'))) email, "
        "json_extract(data,'$.stage') stage from tenant_records "
        "where entity_type = 'lead' and json_extract(data,'$.email') is not null",
        allow_unscoped=True,
        reason=REASON,
    )

    gaps: list[dict] = []
    for row in leads:
        lead = dict(row)
        addr = str(lead.get("email") or "").strip().lower()
        if not addr or addr not in by_addr:
            continue
        holder = lead.get("tenant_id") or ""
        if holder in by_addr[addr]:
            continue  # already suppressed on the tenant that holds this lead
        gaps.append({
            "email": addr,
            "mailable_from_tenant": holder,
            "suppressed_on": sorted(t for t in by_addr[addr] if t),
            "lead_id": lead.get("id"),
            "stage": lead.get("stage"),
        })
    gaps.sort(key=lambda g: (g["email"], g["mailable_from_tenant"]))
    return gaps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any gap is found")
    args = ap.parse_args()

    gaps = find_gaps(get_db())

    if args.json:
        print(json.dumps({"gaps": len(gaps), "items": gaps}, separators=(",", ":")))
    elif not gaps:
        print("No cross-tenant suppression gaps: every suppressed address is "
              "either suppressed on, or absent from, every other tenant.")
    else:
        print(f"{len(gaps)} address/tenant pair(s) suppressed elsewhere but "
              f"MAILABLE here:\n")
        for g in gaps:
            print(f"  {g['email']}")
            print(f"    mailable from : {g['mailable_from_tenant']}")
            print(f"    suppressed on : {', '.join(g['suppressed_on']) or '(none)'}")
            print(f"    lead          : {g['lead_id']}  stage={g['stage']}")
        print("\nAdd the missing row per tenant if the order is meant to be "
              "standing. Do NOT make suppression global: an opt-out from one "
              "brand binding another is a consent decision, not a bug fix.")

    return 1 if (gaps and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
