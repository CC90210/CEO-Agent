"""Seed CC Leads into leadgen_territories and tenant_records for the webdev tenant.

Ensures:
1. `leadgen_territories` rows have tenant_id = WEBDEV_TENANT_ID (Oasis Web Studio), vertical = 'CC Leads', leads_callable > 0.
2. `tenant_records` rows have tenant_id = WEBDEV_TENANT_ID, entity_type = 'lead', data.webdev_territory_id = sheet_id, data.vertical = 'CC Leads'.

Idempotent: record ids are uuid5 of (tenant, company, phone/website/email), and
rows are upserted — a rerun updates in place instead of duplicating.
2026-08-29: previously wrote to 'ef8d389e…' (the OASIS AI CRM tenant) — that id
belongs to the CRM, not webdev; the website-sales pipeline reads '42423fde…'.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from supabase_tool import get_client, load_env

WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"  # Oasis Web Studio
CC_LEADS_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "cc-leads.oasis-webdev")
PREV_JSON = PROJECT_ROOT / "tmp" / "website_sales_leads.json"


def lead_record_id(company: str, contact_hint: str) -> str:
    """Deterministic id: same lead -> same row across reruns (and across the
    scrape_cc_trade_leads resurface path, which uses the same scheme)."""
    return str(uuid.uuid5(CC_LEADS_NS, f"{company.lower().strip()}|{contact_hint.lower().strip()}"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_cc_leads() -> None:
    env = load_env()
    db = get_client(env)

    if not PREV_JSON.exists():
        print(f"Error: {PREV_JSON} does not exist.")
        sys.exit(1)

    leads_data = json.loads(PREV_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(leads_data)} trade leads from {PREV_JSON}.")

    # Group leads by (locality, region)
    by_city: dict[str, list[dict[str, Any]]] = {}
    for item in leads_data:
        city = item.get("city") or "Toronto"
        province = item.get("region") or "Ontario"
        key = f"{city}||{province}"
        by_city.setdefault(key, []).append(item)

    print(f"Grouped into {len(by_city)} territory cities.")

    total_sheets = 0
    total_inserted = 0

    for key, items in by_city.items():
        city, province = key.split("||")
        region_code = "ON" if province.lower() == "ontario" else ("QC" if province.lower() in ("quebec", "québec") else province[:2].upper())
        sheet_id = f"{region_code.lower()}_{city.lower().replace(' ', '_')}_cc_leads"
        count = len(items)

        sheet_row = {
            "id": sheet_id,
            "tenant_id": WEBDEV_TENANT_ID,
            "name": f"CC Leads — {city}, {region_code}",
            "region": region_code,
            "locality": city,
            "vertical": "CC Leads",
            "leads_total": count,
            "leads_callable": count,
            "leads_no_site": 0,
            "leads_callable_no_site": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        try:
            db.from_("leadgen_territories").upsert(sheet_row).execute()
            total_sheets += 1
            print(f"  [Sheet] Upserted {sheet_id} (count: {count})")
        except Exception as e:
            print(f"  [Sheet Error] Failed to upsert sheet {sheet_id}: {e}")

        for item in items:
            data_blob = dict(item)
            company_name = item.get("company") or item.get("business_name") or item.get("name") or "Trade Business"
            contact_hint = item.get("phone") or item.get("website") or item.get("email") or ""
            rec_id = lead_record_id(company_name, str(contact_hint))
            data_blob["business_name"] = company_name
            data_blob["name"] = company_name
            data_blob["phone"] = item.get("phone")
            data_blob["website"] = item.get("website")
            data_blob["business_city"] = city
            data_blob["state"] = region_code
            data_blob["webdev_territory_id"] = sheet_id
            data_blob["vertical"] = "CC Leads"
            data_blob["niche"] = f"{item.get('niche') or 'Trades & Contractors'} (CC Leads)"
            data_blob["icp_track"] = "trades_cc"
            data_blob["sales_program"] = "website_sales_v1"
            data_blob["created_from"] = "seed_cc_leads_turso"

            record_row = {
                "id": rec_id,
                "tenant_id": WEBDEV_TENANT_ID,
                "entity_type": "lead",
                "data": data_blob,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
            try:
                db.from_("tenant_records").upsert(record_row).execute()
                total_inserted += 1
                print(f"    [Lead] Upserted {company_name} ({data_blob.get('phone')})")
            except Exception as e:
                print(f"    [Lead Error] Failed to upsert lead {company_name}: {e}")

    print(f"\n=== SUCCESS: Upserted {total_sheets} sheets and {total_inserted} CC trade leads into tenant_records for {WEBDEV_TENANT_ID} (Oasis Web Studio) ===")


if __name__ == "__main__":
    seed_cc_leads()
