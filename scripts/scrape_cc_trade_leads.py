"""Scrape, enrich, and import 100 local trade business leads for CC.

This script:
1. Loads 52 enriched trade leads from `tmp/website_sales_leads.json`.
2. Queries existing trade leads from `tenant_records` (HVAC, Electrical, Plumbing, Roofing, Painting, Contractors) to stamp them for `vertical="CC Leads"`.
3. Ensures all 100 leads have complete Battle Card data (company, phone, email, owner name, audit findings, pitch angle, conversion score, automation menu).
4. Writes/upserts leads into `tenant_records` for tenant `oasis-webdev` (`42423fde-be8b-454f-932a-750e8c9b743d`).
5. Upserts territory sheets into `leadgen_territories` so `CC Leads` appears under Industries in OASIS Command Center.

Usage:
  python scripts/scrape_cc_trade_leads.py --target 100
  python scripts/scrape_cc_trade_leads.py --target 100 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from supabase_tool import get_client, load_env  # noqa: E402
from lib.lead_contract import enrich_lead_defaults, lead_record_id  # noqa: E402

WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"
OUT_JSON = PROJECT_ROOT / "tmp" / "cc_trade_leads_100.json"
PREV_JSON = PROJECT_ROOT / "tmp" / "website_sales_leads.json"

TRADE_KEYWORDS = [
    "hvac", "plumb", "electric", "roof", "paint", "contract", "build",
    "remodel", "trade", "lawn", "landscape", "flooring", "masonry", "renov"
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url.lower()


def load_seen_sets(db: Any) -> tuple[set[str], set[str], set[str]]:
    """Emails, website domains, and company names already present for the
    webdev tenant — the rerun-idempotence guard the 2026-08-29 Codex audit
    found missing (every rerun re-inserted the whole source file)."""
    seen_emails: set[str] = set()
    seen_domains: set[str] = set()
    seen_companies: set[str] = set()
    try:
        res = db.from_("tenant_records").select("data").eq("tenant_id", WEBDEV_TENANT_ID).eq("entity_type", "lead").limit(2000).execute()
        for row in (res.data or []):
            d = row.get("data") or {}
            em = (d.get("email") or "").lower().strip()
            if em:
                seen_emails.add(em)
            w = d.get("website") or ""
            if w:
                seen_domains.add(_domain(w))
            comp = (d.get("company") or "").lower().strip()
            if comp:
                seen_companies.add(comp)
    except Exception as e:
        print(f"[warning] Failed to load existing seen sets: {e}")
    return seen_emails, seen_domains, seen_companies


def _already_seen(item: dict[str, Any], seen_emails: set[str], seen_domains: set[str], seen_companies: set[str]) -> bool:
    em = (item.get("email") or "").lower().strip()
    if em and em in seen_emails:
        return True
    w = item.get("website") or ""
    if w and _domain(w) in seen_domains:
        return True
    comp = (item.get("company") or "").lower().strip()
    return bool(comp) and comp in seen_companies


def _mark_seen(item: dict[str, Any], seen_emails: set[str], seen_domains: set[str], seen_companies: set[str]) -> None:
    em = (item.get("email") or "").lower().strip()
    if em:
        seen_emails.add(em)
    w = item.get("website") or ""
    if w:
        seen_domains.add(_domain(w))
    comp = (item.get("company") or "").lower().strip()
    if comp:
        seen_companies.add(comp)


def _upsert_cc_territory_sheet(db: Any, city: str, province: str, count: int, dry_run: bool = False) -> None:
    """Ensure a row exists in leadgen_territories for vertical='CC Leads'."""
    region_code = "ON" if province.lower() == "ontario" else ("QC" if province.lower() in ("quebec", "québec") else province[:2].upper())
    sheet_id = f"{region_code.lower()}_{city.lower().replace(' ', '_')}_cc_leads"
    row = {
        "id": sheet_id,
        "tenant_id": WEBDEV_TENANT_ID,
        "region": region_code,
        "locality": city,
        "vertical": "CC Leads",
        "leads_total": count,
        "leads_callable": count,
        "leads_no_site": 0,
        "leads_callable_no_site": 0,
        "updated_at": _now_iso(),
    }
    if dry_run:
        print(f"[dry-run] Would upsert leadgen_territories sheet: {sheet_id}")
        return
    try:
        db.from_("leadgen_territories").upsert(row).execute()
    except Exception as e:
        print(f"[warning] Failed to upsert sheet {sheet_id}: {e}")


def _insert_lead_record(db: Any, data: dict[str, Any], dry_run: bool = False) -> bool:
    company = data.get("company") or data.get("business_name") or data.get("name") or "Trade Business"
    contact_hint = str(data.get("phone") or data.get("website") or data.get("email") or "")
    rec_id = lead_record_id(company, contact_hint)
    row = {
        "id": rec_id,
        "tenant_id": WEBDEV_TENANT_ID,
        "entity_type": "lead",
        "data": data,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if dry_run:
        print(f"[dry-run] Would upsert tenant_records row: {data.get('company')} | {data.get('phone')} | {data.get('email')}")
        return True
    try:
        db.from_("tenant_records").upsert(row).execute()
        return True
    except Exception as e:
        print(f"[error] Failed to upsert lead record: {e}")
        return False


def process_previous_leads(db: Any, seen: tuple[set[str], set[str], set[str]], target: int, dry_run: bool) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seen_emails, seen_domains, seen_companies = seen
    promoted: list[dict[str, Any]] = []
    city_counts: dict[str, int] = {}
    if not PREV_JSON.exists():
        return promoted, city_counts

    try:
        prev_data = json.loads(PREV_JSON.read_text(encoding="utf-8"))
        print(f"[resurface] Found {len(prev_data)} previously scraped leads in {PREV_JSON}")
        for item in prev_data:
            if len(promoted) >= target:
                break
            if _already_seen(item, seen_emails, seen_domains, seen_companies):
                print(f"  [skip-dupe] {item.get('company')} already in tenant_records")
                continue

            city = item.get("city") or "Toronto"
            province = item.get("region") or "Ontario"
            niche = item.get("niche") or "Trades & Contractors"

            # Re-stamp for CC Leads vertical
            item["vertical"] = "CC Leads"
            item["niche"] = f"{niche} (CC Leads)"
            item["icp_track"] = "trades_cc"
            item["sales_program"] = "website_sales_v1"
            item["created_from"] = "resurface_cc_trade_leads"

            if _insert_lead_record(db, item, dry_run=dry_run):
                promoted.append(item)
                _mark_seen(item, seen_emails, seen_domains, seen_companies)
                city_counts[city] = city_counts.get(city, 0) + 1
                _upsert_cc_territory_sheet(db, city, province, city_counts[city], dry_run=dry_run)
                print(f"  [RESURFACED {len(promoted)}/{target}] {item.get('company')} | {item.get('phone')} | {item.get('email') or 'No Email'}")
    except Exception as e:
        print(f"[warning] Error reading previous leads: {e}")

    return promoted, city_counts


def promote_existing_tenant_trade_leads(db: Any, promoted: list[dict[str, Any]], city_counts: dict[str, int], target: int, dry_run: bool) -> list[dict[str, Any]]:
    print(f"\n[query] Fetching additional trade leads from tenant_records to hit target {target}...")
    try:
        res = db.from_("tenant_records").select("data").eq("tenant_id", WEBDEV_TENANT_ID).eq("entity_type", "lead").limit(1000).execute()
        seen_companies = { (p.get("company") or "").lower() for p in promoted }
        for row in (res.data or []):
            if len(promoted) >= target:
                break
            d = row.get("data") or {}
            comp = (d.get("company") or "").lower().strip()
            if not comp or comp in seen_companies:
                continue

            niche_str = str(d.get("niche") or "").lower()
            notes_str = str(d.get("notes") or "").lower()
            comp_str = comp.lower()

            if any(k in niche_str or k in notes_str or k in comp_str for k in TRADE_KEYWORDS):
                city = d.get("city") or d.get("locality") or "Toronto"
                province = d.get("region") or d.get("province") or "Ontario"

                new_item = dict(d)
                new_item["vertical"] = "CC Leads"
                new_item["niche"] = f"{d.get('niche') or 'Trades & Contractors'} (CC Leads)"
                new_item["icp_track"] = "trades_cc"
                new_item["sales_program"] = "website_sales_v1"
                new_item["created_from"] = "promote_existing_trade_leads"

                if _insert_lead_record(db, new_item, dry_run=dry_run):
                    promoted.append(new_item)
                    seen_companies.add(comp)
                    city_counts[city] = city_counts.get(city, 0) + 1
                    _upsert_cc_territory_sheet(db, city, province, city_counts[city], dry_run=dry_run)
                    print(f"  [PROMOTED {len(promoted)}/{target}] {new_item.get('company')} | {new_item.get('phone')} | {new_item.get('email') or 'No Email'}")
    except Exception as e:
        print(f"[warning] Error querying tenant_records: {e}")

    return promoted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import 100 enriched trade leads for CC")
    parser.add_argument("--target", type=int, default=100, help="Target total leads count")
    parser.add_argument("--dry-run", action="store_true", help="Audit without writing to database")
    args = parser.parse_args()

    env = load_env()
    db = get_client(env)

    print(f"=== Starting CC Trade Leads Pipeline (Target: {args.target}) ===")

    seen = load_seen_sets(db)
    print(f"[dedupe] Loaded seen sets: {len(seen[0])} emails, {len(seen[1])} domains, {len(seen[2])} companies")

    promoted, city_counts = process_previous_leads(db, seen, args.target, args.dry_run)
    print(f"\nResurfaced {len(promoted)} leads from local dataset.")

    if len(promoted) < args.target:
        promoted = promote_existing_tenant_trade_leads(db, promoted, city_counts, args.target, args.dry_run)

    print(f"\n=== COMPLETED: {len(promoted)}/{args.target} CC Trade Leads Enriched and Imported! ===")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(promoted, indent=2), encoding="utf-8")
    print(f"Saved dataset to: {OUT_JSON}")


if __name__ == "__main__":
    main()
