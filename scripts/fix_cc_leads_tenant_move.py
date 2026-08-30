"""One-off repair (2026-08-29): move mis-seeded CC Leads from the CRM tenant to webdev.

seed_cc_leads_turso.py wrote 52 leads + 15 territory sheets under the OASIS AI
CRM tenant ('ef8d389e…') instead of Oasis Web Studio ('42423fde…') — Codex audit
P1. This script:
1. Moves seeder-stamped leads (created_from='seed_cc_leads_turso') whose company
   is NOT already present in webdev → webdev tenant. Redundant copies are left
   in place and reported (deletion is CC's call).
2. Moves the vertical='CC Leads' territory sheets to webdev.
3. Recomputes each moved sheet's leads_total/leads_callable from actual webdev rows.

Idempotent; prints a summary, never values. Verify after with a separate-process
count (Turso writes must be confirmed out-of-process).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from supabase_tool import get_client, load_env  # noqa: E402

CRM_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"     # OASIS AI (wrong)
WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"  # Oasis Web Studio


def _company(d: dict[str, Any]) -> str:
    return (d.get("company") or d.get("business_name") or d.get("name") or "").lower().strip()


def _fetch_all_leads(db: Any, tenant_id: str, cols: str) -> list[dict[str, Any]]:
    """Paginate to exhaustion — a capped page is not a search: the CRM tenant
    holds >2000 lead rows and the 52 seeder rows were beyond the first page."""
    out: list[dict[str, Any]] = []
    page = 1000
    offset = 0
    while True:
        res = db.from_("tenant_records").select(cols).eq(
            "tenant_id", tenant_id).eq("entity_type", "lead").order(
            "id").range(offset, offset + page - 1).execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < page:
            return out
        offset += page


def main() -> int:
    db = get_client(load_env())

    webdev_rows = _fetch_all_leads(db, WEBDEV_TENANT_ID, "data")
    webdev_companies = {_company(r.get("data") or {}) for r in webdev_rows}
    webdev_companies.discard("")

    crm_rows = _fetch_all_leads(db, CRM_TENANT_ID, "id,data")
    print(f"scanned webdev={len(webdev_rows)} crm={len(crm_rows)} lead rows")
    moved, redundant = 0, 0
    for row in crm_rows:
        d = row.get("data") or {}
        if d.get("created_from") != "seed_cc_leads_turso":
            continue
        comp = _company(d)
        if comp and comp in webdev_companies:
            redundant += 1
            continue
        db.from_("tenant_records").update({"tenant_id": WEBDEV_TENANT_ID}).eq(
            "id", row["id"]).execute()
        webdev_companies.add(comp)
        moved += 1
        print(f"  [moved] {d.get('company') or d.get('business_name')}")

    sheets = db.from_("leadgen_territories").select("id").eq(
        "tenant_id", CRM_TENANT_ID).eq("vertical", "CC Leads").limit(200).execute()
    crm_sheet_ids = [r["id"] for r in (sheets.data or [])]
    for sid in crm_sheet_ids:
        db.from_("leadgen_territories").update({"tenant_id": WEBDEV_TENANT_ID}).eq(
            "id", sid).execute()
    print(f"moved {len(crm_sheet_ids)} territory sheets to webdev")

    # Recompute over ALL webdev CC Leads sheets, not just ones moved this run —
    # a rerun after a partial failure must still repair the counts.
    all_sheets = db.from_("leadgen_territories").select("id").eq(
        "tenant_id", WEBDEV_TENANT_ID).eq("vertical", "CC Leads").limit(200).execute()
    sheet_ids = [r["id"] for r in (all_sheets.data or [])]

    # Recompute sheet counts from actual webdev rows.
    counts: dict[str, int] = {}
    for r in _fetch_all_leads(db, WEBDEV_TENANT_ID, "data"):
        sid = (r.get("data") or {}).get("webdev_territory_id")
        if sid:
            counts[sid] = counts.get(sid, 0) + 1
    for sid in sheet_ids:
        n = counts.get(sid, 0)
        db.from_("leadgen_territories").update(
            {"leads_total": n, "leads_callable": n}).eq("id", sid).execute()
        print(f"  [sheet] {sid}: leads_total={n}")

    print(f"\nSUMMARY: moved={moved} leads, redundant_left_in_crm={redundant}, "
          f"sheets_moved={len(crm_sheet_ids)}, sheets_recounted={len(sheet_ids)}")
    print("Redundant CRM copies + 20 unstamped CRM rows left untouched — deletion is CC's call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
