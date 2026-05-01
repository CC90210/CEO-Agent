#!/usr/bin/env python3
"""crm_reset.py — archive cold/dead leads from the bravo Supabase CRM.

CC's directive (2026-04-30 PM): the CRM has accumulated cold-outreach noise.
Only keep ACTUAL warm leads + ACTUAL clients. Everything else gets archived
(soft-deleted: status='archived' + tag 'auto_archived_2026-04-30'). Lead
interactions are preserved so we can resurrect anyone if needed.

KEEP rules (any one match keeps a lead):
  - status = 'won' (paying clients)
  - primary retainer (name OR company contains 'primary_retainer' OR 'agency-accelerance')
  - Jonathan Hutton / Basque Landscaping (name='Jonathan Hutton' OR company ILIKE '%basque%')
  - Alejandro Andrade / Alondra (name ILIKE '%alejandro%' OR '%alondra%' OR '%andrade%')
  - Tremont (name ILIKE '%tremont%')

Everything else: archived. NO 14-day grace window — true cold noise must go.

Default mode: dry-run (prints would-be archives).
--apply: commit changes.
--json: machine-readable summary.

Usage:
  python scripts/crm_reset.py                  # dry-run
  python scripts/crm_reset.py --apply          # commit
  python scripts/crm_reset.py --apply --json   # for CI/agents
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # type: ignore

load_dotenv(ROOT / ".env.agents")

try:
    from supabase import create_client, Client  # type: ignore
except ImportError:
    print("ERROR: pip install supabase", file=sys.stderr)
    sys.exit(2)


ARCHIVE_TAG = "auto_archived_2026-04-30"

# Patterns that match warm leads / clients. Any match = keep.
# Lowercase comparisons throughout.
KEEP_NAME_PATTERNS = [
    "primary_retainer",
    "spooner",        # the prior client
    "jonathan hutton",
    "alejandro",
    "alondra",
    "andrade",
    "tremont",
]

KEEP_COMPANY_PATTERNS = [
    "primary_retainer",
    "agency-accelerance",
    "agency accelerance",
    "basque",        # Basque Landscaping
]


def matches_keep(lead: dict) -> tuple[bool, str]:
    """Return (kept, reason). Reason is a short string for the audit log."""
    name = (lead.get("name") or "").lower()
    company = (lead.get("company") or "").lower()
    email = (lead.get("email") or "").lower()
    status = (lead.get("status") or "").lower()

    if status == "won":
        return True, "status=won"

    for p in KEEP_NAME_PATTERNS:
        if p in name or p in email:
            return True, f"name~{p}"
    for p in KEEP_COMPANY_PATTERNS:
        if p in company:
            return True, f"company~{p}"
    return False, ""


def operator_tenant_id(client: "Client") -> str:
    """Find the canonical operator's tenant_id (single-operator-per-server)."""
    r = (
        client.table("user_profiles")
        .select("id, email, tenant_id")
        .eq("role", "operator")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not r.data:
        raise RuntimeError("no operator profile found in user_profiles")
    if not r.data[0].get("tenant_id"):
        raise RuntimeError("operator profile has no tenant_id (apply migration 018+019 first)")
    return r.data[0]["tenant_id"]


def db() -> "Client":
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing BRAVO_SUPABASE_URL / BRAVO_SUPABASE_SERVICE_ROLE_KEY in environment")
    return create_client(url, key)


def main() -> int:
    p = argparse.ArgumentParser(description="Archive cold leads from the bravo CRM")
    p.add_argument("--apply", action="store_true", help="commit changes (default: dry-run)")
    p.add_argument("--json", action="store_true", help="machine-readable summary")
    p.add_argument("--limit", type=int, default=10000, help="max leads to scan")
    args = p.parse_args()

    client = db()
    tenant_id = operator_tenant_id(client)

    leads_resp = (
        client.table("leads")
        .select("id, name, email, company, status, score, source, tags, last_contacted_at, created_at")
        .eq("tenant_id", tenant_id)
        .neq("status", "archived")
        .limit(args.limit)
        .execute()
    )
    leads = leads_resp.data or []

    keep: list[dict] = []
    archive: list[dict] = []
    reasons: dict[str, str] = {}

    for lead in leads:
        ok, reason = matches_keep(lead)
        if ok:
            keep.append(lead)
            reasons[lead["id"]] = reason
        else:
            archive.append(lead)

    archived_ids = [lead["id"] for lead in archive]

    summary: dict = {
        "tenant_id": tenant_id,
        "total_scanned": len(leads),
        "kept": len(keep),
        "to_archive": len(archive),
        "kept_breakdown": {},
        "applied": False,
        "archive_tag": ARCHIVE_TAG,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    for lead in keep:
        r = reasons.get(lead["id"], "?")
        summary["kept_breakdown"][r] = summary["kept_breakdown"].get(r, 0) + 1

    if args.apply and archived_ids:
        # Soft-archive in batches of 500 to stay under PostgREST URL limits
        BATCH = 500
        archived_count = 0
        for i in range(0, len(archived_ids), BATCH):
            batch_ids = archived_ids[i : i + BATCH]
            # Update each row, appending the archive tag without clobbering existing tags.
            # We do this row-by-row to preserve per-row tag arrays correctly.
            for lid in batch_ids:
                lead = next(x for x in archive if x["id"] == lid)
                existing_tags = lead.get("tags") or []
                new_tags = list(existing_tags)
                if ARCHIVE_TAG not in new_tags:
                    new_tags.append(ARCHIVE_TAG)
                client.table("leads").update(
                    {"status": "archived", "tags": new_tags}
                ).eq("id", lid).execute()
                archived_count += 1
        summary["applied"] = True
        summary["archived_count_actual"] = archived_count

    # Count preserved interactions (just for the report — never modified)
    if archived_ids:
        chunks = [archived_ids[i : i + 100] for i in range(0, len(archived_ids), 100)]
        total_interactions = 0
        for chunk in chunks:
            r = (
                client.table("lead_interactions")
                .select("id", count="exact", head=True)
                .in_("lead_id", chunk)
                .execute()
            )
            total_interactions += r.count or 0
        summary["preserved_interactions_for_archived"] = total_interactions

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        mode = "APPLIED" if args.apply else "DRY-RUN (use --apply to commit)"
        print(f"\n=== CRM RESET — {mode} ===\n")
        print(f"Tenant: {tenant_id}")
        print(f"Scanned: {len(leads)} active leads")
        print(f"Keeping: {len(keep)}  ({summary['kept_breakdown']})")
        print(f"Archiving: {len(archive)}")
        print()
        if keep:
            print("KEEP:")
            for lead in keep:
                r = reasons.get(lead["id"], "?")
                disp = (
                    lead.get("name")
                    or lead.get("email")
                    or lead.get("company")
                    or lead["id"][:8]
                )
                print(f"  + {disp:<40} status={lead.get('status'):<12} reason={r}")
            print()
        if archive and not args.apply:
            print(f"WOULD ARCHIVE (showing first 30 of {len(archive)}):")
            for lead in archive[:30]:
                disp = (
                    lead.get("name")
                    or lead.get("email")
                    or lead.get("company")
                    or lead["id"][:8]
                )
                print(f"  - {disp:<40} status={lead.get('status') or 'new':<12} email={lead.get('email') or '-'}")
            if len(archive) > 30:
                print(f"  ... and {len(archive) - 30} more")
            print()
            print("Re-run with --apply to commit. Lead rows + interactions are preserved (soft delete).")
        if args.apply:
            print(f"Done. {summary.get('archived_count_actual', 0)} leads archived.")
            print(f"Preserved {summary.get('preserved_interactions_for_archived', 0)} interaction rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
