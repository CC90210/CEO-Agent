"""migrate_lender_industry_restrictions_key.py — one-shot key rename across lender rows.

Background: oasis-command-center 2026-06-11 (commits 44baf13 + c4b9e48)
renamed the SunBiz lender catalog field `industry_restrictions` →
`restricted_industries` so it matches what the SOP §4 match-fitness
scoring code reads. Both the schema (seeds.ts) and the UI write path
(LendersDirectoryClient.tsx) now use the canonical name.

But existing lender rows still carry data under the OLD key from before
the rename. The VPS audit on 2026-06-11 found:
  - All 46 SunBiz lenders carry the legacy industry_restrictions key
    (44 as empty []; 2 with real data)
  - 2 rows have real orphaned data:
      Maison Capital Group: ["trucking","staffing","auto"]
      Olympus Lending:      ["auto","real_estate","transportation",
                             "trucking","childcare"]
  - 0 rows have restricted_industries set

The defensive read in lib/lenders/shop-out.ts catches this so the SOP §4
filter still works correctly during transition. But carrying duplicated
keys forever creates a drift surface. This script does the one-shot:

  FOR EACH SunBiz lender row WHERE data.industry_restrictions IS NOT NULL:
    IF data.restricted_industries IS NULL OR EMPTY:
       data.restricted_industries := data.industry_restrictions
    REMOVE data.industry_restrictions

Tenant-scoped (only touches SunBiz tenant_id). Idempotent: re-runs are
no-ops since the old key gets cleared. --dry-run prints what would
change without writing. --json prints the planned migration as JSON
so you can review the exact diff before confirming.

The 4 off-vocabulary slugs the migration preserves ("auto",
"transportation", "staffing", "childcare") are already in
seed_sunbiz_application_form_fields.py SUNBIZ_INDUSTRIES so the form
collection vocabulary aligns. match-fitness uses exact lowercase slug
compare; a deal with industry="trucking" gets blocked by Olympus
(which has "trucking" in its restricted_industries). Maison blocks
"trucking" or "staffing" deals; Olympus blocks five categories.

Usage:
    python3 scripts/migrate_lender_industry_restrictions_key.py --dry-run
    python3 scripts/migrate_lender_industry_restrictions_key.py --json
    python3 scripts/migrate_lender_industry_restrictions_key.py  # apply
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SUNBIZ_TENANT_ID = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"


def _supabase():
    from lib.secret_loader import load_env  # type: ignore
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Supabase URL or service role key missing from .env.agents")
    from supabase import create_client  # type: ignore
    return create_client(url, key)


def _plan_migration(rows: list[dict]) -> list[dict]:
    """Build the migration plan. Each entry:
      {
        id: <row_id>,
        name: <lender name>,
        action: "preserve" | "clear_empty" | "skip_collision",
        before: { industry_restrictions, restricted_industries },
        after:  { restricted_industries }
      }
    """
    plan: list[dict] = []
    for row in rows:
        data = row.get("data") or {}
        old = data.get("industry_restrictions")
        new = data.get("restricted_industries")

        if old is None:
            # Old key absent — nothing to migrate.
            continue

        old_list = old if isinstance(old, list) else []
        new_list = new if isinstance(new, list) else []

        if old_list and not new_list:
            # Real data to preserve.
            action = "preserve"
            after = old_list
        elif old_list and new_list:
            # Both populated — refuse to overwrite. Operator decides.
            action = "skip_collision"
            after = new_list
        else:
            # Old is empty list, new is null/empty — just drop the dead key.
            action = "clear_empty"
            after = new_list

        plan.append({
            "id": row["id"],
            "name": (data.get("name") or row["id"])[:80],
            "action": action,
            "before": {
                "industry_restrictions": old,
                "restricted_industries": new,
            },
            "after": {
                "restricted_industries": after,
            },
        })
    return plan


def _apply_one(sb, row: dict, target_entry: dict) -> bool:
    """Write the migration for one row. Returns True on success."""
    data = copy.deepcopy(row.get("data") or {})
    if target_entry["action"] == "preserve":
        data["restricted_industries"] = target_entry["after"]["restricted_industries"]
    data.pop("industry_restrictions", None)
    res = (
        sb.table("tenant_records")
        .update({"data": data})
        .eq("id", row["id"])
        .eq("tenant_id", SUNBIZ_TENANT_ID)
        .eq("entity_type", "lender")
        .execute()
    )
    return bool(res.data)


def main() -> int:
    p = argparse.ArgumentParser(prog="migrate_lender_industry_restrictions_key")
    p.add_argument("--dry-run", action="store_true", help="Print plan, do not write")
    p.add_argument("--json", action="store_true", help="Emit plan as JSON")
    args = p.parse_args()

    sb = _supabase()

    rows = (
        sb.table("tenant_records")
        .select("id, data")
        .eq("tenant_id", SUNBIZ_TENANT_ID)
        .eq("entity_type", "lender")
        .execute()
        .data
        or []
    )

    plan = _plan_migration(rows)
    rows_by_id = {r["id"]: r for r in rows}

    if args.json:
        print(json.dumps(plan, indent=2, default=str))
        if args.dry_run:
            return 0
    else:
        if not plan:
            print("No rows carry industry_restrictions — nothing to migrate.")
            return 0
        print(f"Migration plan: {len(plan)} row(s)\n")
        by_action: dict[str, int] = {}
        for e in plan:
            by_action[e["action"]] = by_action.get(e["action"], 0) + 1
        for action, count in by_action.items():
            print(f"  {action}: {count}")
        print()
        for e in plan:
            print(f"  [{e['action']}] {e['name']}")
            if e["action"] == "preserve":
                print(f"    old: {e['before']['industry_restrictions']}")
                print(f"    new: {e['after']['restricted_industries']}")
            elif e["action"] == "skip_collision":
                print(f"    BOTH keys carry data — manual review:")
                print(f"    old: {e['before']['industry_restrictions']}")
                print(f"    new: {e['before']['restricted_industries']}")

    if args.dry_run:
        print("\n--dry-run set, NOT writing.")
        return 0

    print("\nApplying migration...")
    succeeded = 0
    failed: list[str] = []
    for e in plan:
        if e["action"] == "skip_collision":
            print(f"  SKIP  {e['name']}  (collision — needs manual review)")
            continue
        ok = _apply_one(sb, rows_by_id[e["id"]], e)
        if ok:
            succeeded += 1
            print(f"  ok    {e['name']}")
        else:
            failed.append(e["name"])
            print(f"  FAIL  {e['name']}")

    print(f"\nDone. Migrated: {succeeded}. Failed: {len(failed)}. Collisions skipped: {sum(1 for e in plan if e['action']=='skip_collision')}.")
    if failed:
        print("Failed rows:", failed[:10])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
