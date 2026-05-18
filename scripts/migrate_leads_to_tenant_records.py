"""
migrate_leads_to_tenant_records.py
==================================

One-time back-population of `public.leads` → `public.tenant_records`
(entity_type='lead'). Round 3 R3-2 of the SunBiz CRM build.

Why this exists
---------------
Pre-2026-05-15 the bulk lead import wrote to a dedicated `public.leads`
table. On 2026-05-15 the import was migrated to `tenant_records` so the
SunBiz Kanban (which reads from `tenant_records`) could see imports.
Today (2026-05-16) the 6 lead READERS were also migrated to read from
`tenant_records` — `recentLeads`, `pipelineBreakdown`, `getLeadById`,
`topOpenLead`, `topClientConcentration`, `activePipeline`.

Pre-existing rows in `public.leads` would now be invisible to the dashboard.
This script copies them into `tenant_records` so OASIS HQ keeps its
historical lead data + the SunBiz tenant keeps anything it had pre-cutover.

Idempotent
----------
Already-copied leads are skipped (dedup by source `id` matching
`tenant_records.id`). Re-running the script after a fresh import is safe
— it adds new rows but doesn't duplicate existing ones.

Dry-run by default
------------------
Pass --apply to actually write rows. Default mode prints the proposed
inserts + counts so you can review before committing.

Usage
-----
    python scripts/migrate_leads_to_tenant_records.py             # dry-run
    python scripts/migrate_leads_to_tenant_records.py --apply     # write rows
    python scripts/migrate_leads_to_tenant_records.py --apply \\
        --tenant <uuid>                                            # one tenant only
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib import secret_loader  # noqa: E402
from supabase import create_client  # noqa: E402


def load_client():
    env = secret_loader.load_env(
        ["BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_SERVICE_ROLE_KEY"]
    )
    return create_client(
        env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"]
    )


# The Lead row columns we copy into tenant_records.data. Keep this list
# stable — the dashboard's tenantRecordToLead() mapper in
# lib/queries.ts (oasis-command-center repo) reads exactly these keys back out.
COPY_FIELDS = [
    "name",
    "email",
    "phone",
    "company",
    "status",
    "score",
    "source",
    "notes",
    "tags",
    "last_contacted_at",
    "next_followup_at",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write rows. Default is dry-run.",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Restrict to a single tenant_id. Default: all tenants.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per insert batch. Default 500.",
    )
    args = parser.parse_args()

    db = load_client()

    # 1. Find every lead in the legacy public.leads table.
    src = db.table("leads").select("*")
    if args.tenant:
        src = src.eq("tenant_id", args.tenant)
    src_rows = src.execute().data or []
    print(f"Source: {len(src_rows)} legacy leads (filter tenant={args.tenant or 'ALL'})")
    if not src_rows:
        print("Nothing to migrate.")
        return 0

    # 2. Look up which ids already exist in tenant_records so we don't
    #    re-copy. tenant_records.id is generated server-side, so the
    #    dedup key is the original lead's id stored in data._legacy_id
    #    (a marker we set on write).
    existing_ids = set()
    page = 0
    while True:
        q = (
            db.table("tenant_records")
            .select("data->>_legacy_id", count="exact")
            .eq("entity_type", "lead")
            .range(page * 1000, page * 1000 + 999)
        )
        res = q.execute()
        rows = res.data or []
        if not rows:
            break
        for row in rows:
            # supabase-py returns the aliased column under the path-string key.
            legacy = row.get("_legacy_id") or row.get("data->>_legacy_id")
            if legacy:
                existing_ids.add(legacy)
        if len(rows) < 1000:
            break
        page += 1
    print(f"Already migrated: {len(existing_ids)} leads")

    # 3. Build the tenant_records insert rows.
    to_insert = []
    skipped_no_tenant = 0
    for lead in src_rows:
        if lead.get("id") in existing_ids:
            continue
        if not lead.get("tenant_id"):
            # Legacy rows without a tenant_id can't be migrated cleanly —
            # they predate the multi-tenant fan-out. Log and skip.
            skipped_no_tenant += 1
            continue
        data = {k: lead.get(k) for k in COPY_FIELDS if lead.get(k) is not None}
        # Add the legacy id as a marker so future re-runs don't duplicate.
        data["_legacy_id"] = lead["id"]
        # Stamp a stage value so the Kanban (which groups by 'stage') has
        # somewhere to put the row. Use the existing status as the stage
        # if no stage was already set — these will mostly be the legacy
        # values (new / contacted / qualified / proposal / won / lost /
        # archived) which the operator can re-map as needed.
        if "stage" not in data:
            data["stage"] = data.get("status") or "new"
        to_insert.append(
            {
                "tenant_id": lead["tenant_id"],
                "entity_type": "lead",
                "data": data,
                # Preserve the original timestamps if they exist; otherwise
                # let Postgres default to now(). Keeping the original
                # created_at lets historical sort orders reflect reality.
                "created_at": lead.get("created_at"),
                "updated_at": lead.get("updated_at") or lead.get("created_at"),
            }
        )
    print(f"To migrate: {len(to_insert)} rows")
    if skipped_no_tenant:
        print(f"Skipped (no tenant_id): {skipped_no_tenant} rows")
    if not to_insert:
        print("Everything already migrated.")
        return 0

    if not args.apply:
        # Dry-run summary — show first 5 row shapes + per-tenant counts.
        print("\nDRY-RUN: first 5 proposed rows:")
        for r in to_insert[:5]:
            print(f"  tenant={r['tenant_id'][:8]}.. data={r['data']}")
        tenant_counts: dict[str, int] = {}
        for r in to_insert:
            tenant_counts[r["tenant_id"]] = tenant_counts.get(r["tenant_id"], 0) + 1
        print("\nPer-tenant counts:")
        for t, c in sorted(tenant_counts.items(), key=lambda x: -x[1]):
            print(f"  {t}: {c} rows")
        print("\nRe-run with --apply to write.")
        return 0

    # 4. Batch insert. tenant_records' RLS bypasses for service role so
    #    we don't need to set any extra headers.
    inserted = 0
    for i in range(0, len(to_insert), args.batch_size):
        batch = to_insert[i : i + args.batch_size]
        res = db.table("tenant_records").insert(batch).execute()
        inserted += len(res.data or [])
        print(f"  ...inserted {inserted}/{len(to_insert)}")

    print(f"\nDone. Migrated {inserted} legacy leads into tenant_records.")
    print(
        "Verify: open the dashboard /leads page or /t/<slug>/leads kanban — "
        "row count should match the legacy table plus any post-migration imports."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
