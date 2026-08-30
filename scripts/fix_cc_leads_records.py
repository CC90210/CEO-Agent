"""Fix and update existing tenant_records for CC Trade Leads.

Updates data -> webdev_territory_id and data -> vertical for all trade leads in tenant_records
so they match leadgen_territories sheets and pass fetchLeads filtering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from supabase_tool import get_client, load_env

# 2026-08-29: was 'ef8d389e…' (OASIS AI CRM tenant) — same wrong-tenant bug as
# seed_cc_leads_turso.py. The website-sales pipeline reads Oasis Web Studio.
WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"
PREV_JSON = PROJECT_ROOT / "tmp" / "website_sales_leads.json"


def fix_tenant_records() -> None:
    env = load_env()
    db = get_client(env)

    if not PREV_JSON.exists():
        print(f"Error: {PREV_JSON} not found.")
        return

    prev_leads = json.loads(PREV_JSON.read_text(encoding="utf-8"))
    company_to_lead = { (item.get("company") or "").lower().strip(): item for item in prev_leads if item.get("company") }
    phone_to_lead = { (item.get("phone") or "").strip(): item for item in prev_leads if item.get("phone") }

    print(f"Loaded {len(prev_leads)} reference trade leads.")

    # Fetch all lead rows from tenant_records
    res = db.from_("tenant_records").select("id,data").eq("tenant_id", WEBDEV_TENANT_ID).eq("entity_type", "lead").limit(2000).execute()
    rows = res.data or []
    print(f"Queried {len(rows)} tenant_records rows.")

    updated_count = 0

    for r in rows:
        row_id = r.get("id")
        d = r.get("data") or {}
        comp = (d.get("company") or d.get("business_name") or d.get("name") or "").lower().strip()
        phone = (d.get("phone") or "").strip()

        matched_ref = company_to_lead.get(comp) or phone_to_lead.get(phone)

        # Also check if niche or company contains trade keywords
        is_trade = matched_ref or any(k in comp or k in str(d.get("niche") or "").lower() for k in ["hvac", "plumb", "electric", "roof", "paint", "contract", "build", "lawn", "landscape"])

        if is_trade:
            city = (matched_ref and matched_ref.get("city")) or d.get("city") or d.get("business_city") or d.get("locality") or "Toronto"
            province = (matched_ref and matched_ref.get("region")) or d.get("region") or d.get("state") or "Ontario"
            region_code = "ON" if province.lower() == "ontario" else ("QC" if province.lower() in ("quebec", "québec") else province[:2].upper())
            sheet_id = f"{region_code.lower()}_{city.lower().replace(' ', '_')}_cc_leads"

            new_data = dict(d)
            if matched_ref:
                new_data.update(matched_ref)

            new_data["business_name"] = d.get("company") or matched_ref.get("company") if matched_ref else d.get("name") or "Trade Business"
            new_data["name"] = new_data["business_name"]
            new_data["webdev_territory_id"] = sheet_id
            new_data["vertical"] = "CC Leads"
            new_data["state"] = region_code
            new_data["business_city"] = city
            new_data["niche"] = f"{d.get('niche') or 'Trades & Contractors'} (CC Leads)"

            try:
                db.from_("tenant_records").update({"data": new_data}).eq("id", row_id).execute()
                updated_count += 1
                print(f"  [{updated_count}] Updated {new_data.get('business_name')} -> sheet_id: {sheet_id}")
            except Exception as e:
                print(f"  [Error] Failed to update row {row_id}: {e}")

    print(f"\n=== SUCCESS: Updated {updated_count} tenant_records rows with webdev_territory_id and vertical='CC Leads' ===")


if __name__ == "__main__":
    fix_tenant_records()
