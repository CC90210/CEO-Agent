"""Scrape, enrich, and import 100 local trade business leads for CC.

This script:
1. Loads existing 52 trade leads from `tmp/website_sales_leads.json`.
2. Scrapes fresh local trade leads across Ontario & Quebec (HVAC, Electricians, Plumbers, Roofers, Contractors) using Firecrawl + Claude Audit.
3. Stamps all leads with `vertical="CC Leads"` and `icp_track="trades_cc"`.
4. Writes leads directly into `tenant_records` for tenant `oasis-webdev` (`42423fde-be8b-454f-932a-750e8c9b743d`).
5. Upserts territory sheets into `leadgen_territories` so `CC Leads` appears under Industries in OASIS Command Center.

Usage:
  python scripts/scrape_cc_trade_leads.py --target 100
  python scripts/scrape_cc_trade_leads.py --target 100 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from supabase_tool import get_client, load_env  # noqa: E402
from scrape_firecrawl_leads import (  # noqa: E402
    EXTRACT_SCHEMA, _is_skippable, _run_firecrawl, _valid_email, _is_real_first,
)
from name_utils import strip_honorifics  # noqa: E402
from lib.lead_contract import enrich_lead_defaults, should_create_lead  # noqa: E402
from scrape_website_sales_leads import (  # noqa: E402
    _fetch_site, _audit_site, _fmt_phone, _phone_geo_ok, TIER_VALUE,
)

WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"
OASIS_CRM_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

TARGET_CITIES: list[tuple[str, str]] = [
    ("Toronto", "Ontario"),
    ("Montreal", "Quebec"),
    ("Ottawa", "Ontario"),
    ("Hamilton", "Ontario"),
    ("Mississauga", "Ontario"),
    ("Laval", "Quebec"),
    ("Brampton", "Ontario"),
    ("Markham", "Ontario"),
    ("Vaughan", "Ontario"),
    ("London", "Ontario"),
    ("Kitchener", "Ontario"),
    ("Windsor", "Ontario"),
]

TARGET_NICHES = [
    "HVAC",
    "Electrician",
    "Plumber",
    "Roofer",
    "General Contractor",
    "Painter",
    "Flooring Contractor",
    "Landscaper",
    "Masonry",
]

OUT_JSON = PROJECT_ROOT / "tmp" / "cc_trade_leads_100.json"
PREV_JSON = PROJECT_ROOT / "tmp" / "website_sales_leads.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url.lower()


def load_seen_sets(db: Any) -> tuple[set[str], set[str]]:
    seen_emails: set[str] = set()
    seen_domains: set[str] = set()
    try:
        res = db.from_("tenant_records").select("data").eq("tenant_id", WEBDEV_TENANT_ID).eq("entity_type", "lead").limit(1000).execute()
        for row in (res.data or []):
            d = row.get("data") or {}
            em = (d.get("email") or "").lower().strip()
            if em:
                seen_emails.add(em)
            w = d.get("website") or ""
            if w:
                seen_domains.add(_domain(w))
    except Exception as e:
        print(f"[warning] Failed to load existing seen sets: {e}")
    return seen_emails, seen_domains


def _upsert_cc_territory_sheet(db: Any, city: str, province: str, count: int, dry_run: bool = False) -> None:
    """Ensure a row exists in leadgen_territories for vertical='CC Leads'."""
    region_code = "ON" if province.lower() == "ontario" else ("QC" if province.lower() in ("quebec", "québec") else province[:2].upper())
    sheet_id = f"{region_code.lower()}_{city.lower().replace(' ', '_')}_cc_leads"
    row = {
        "id": sheet_id,
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
    rec_id = str(uuid.uuid4())
    row = {
        "id": rec_id,
        "tenant_id": WEBDEV_TENANT_ID,
        "entity_type": "lead",
        "data": data,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if dry_run:
        print(f"[dry-run] Would insert tenant_records row: {data.get('company')} | {data.get('phone')} | {data.get('email')}")
        return True
    try:
        res = db.from_("tenant_records").insert(row).execute()
        return bool(res.data)
    except Exception as e:
        print(f"[error] Failed to insert lead record: {e}")
        return False


def process_previous_leads(db: Any, seen_emails: set[str], seen_domains: set[str], target: int, dry_run: bool) -> tuple[list[dict[str, Any]], dict[str, int]]:
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
            email = (item.get("email") or "").lower().strip()
            website = item.get("website") or ""
            dom = _domain(website) if website else ""

            if email and email in seen_emails:
                continue
            if dom and dom in seen_domains:
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
                if email:
                    seen_emails.add(email)
                if dom:
                    seen_domains.add(dom)
                city_counts[city] = city_counts.get(city, 0) + 1
                _upsert_cc_territory_sheet(db, city, province, city_counts[city], dry_run=dry_run)
                print(f"  [RESURFACED {len(promoted)}/{target}] {item.get('company')} | {item.get('phone')} | {item.get('email') or 'No Email'}")
    except Exception as e:
        print(f"[warning] Error reading previous leads: {e}")

    return promoted, city_counts


def scrape_fresh_leads(db: Any, seen_emails: set[str], seen_domains: set[str], promoted: list[dict[str, Any]], city_counts: dict[str, int], target: int, dry_run: bool, delay: float = 1.0) -> list[dict[str, Any]]:
    print(f"\n[scraping] Starting Firecrawl + Claude audit scrape for remaining {target - len(promoted)} leads...")
    stats = {"queries": 0, "urls_found": 0, "extracts": 0, "dropped_dup": 0, "dropped_no_contact": 0, "dropped_geo": 0}

    for city, province in TARGET_CITIES:
        if len(promoted) >= target:
            break
        for niche in TARGET_NICHES:
            if len(promoted) >= target:
                break
            query = f"{niche} {city} {province} small business"
            print(f"\n--- Query [{len(promoted)}/{target}]: '{query}' ---")
            stats["queries"] += 1

            s_res = _run_firecrawl(["search", query])
            urls: list[str] = []
            if isinstance(s_res, list):
                urls = [u.get("url") for u in s_res if isinstance(u, dict) and u.get("url")]
            elif isinstance(s_res, dict):
                raw = s_res.get("data") or s_res.get("results") or []
                urls = [u.get("url") for u in raw if isinstance(u, dict) and u.get("url")]

            for url in urls:
                if len(promoted) >= target:
                    break
                if not url or _is_skippable(url):
                    continue
                dom = _domain(url)
                if dom in seen_domains:
                    stats["dropped_dup"] += 1
                    continue

                print(f"  Extracting: {url[:75]}...")
                stats["extracts"] += 1
                ex_res = _run_firecrawl(["extract", url, "--schema", json.dumps(EXTRACT_SCHEMA)])
                ex = (ex_res or {}).get("data") or (ex_res or {}).get("extract") or ex_res or {}
                if not isinstance(ex, dict):
                    continue

                business = (ex.get("business_name") or "").strip()
                if not business:
                    continue

                email = (ex.get("email") or "").lower().strip()
                if email and not _valid_email(email):
                    email = ""
                if email and email in seen_emails:
                    stats["dropped_dup"] += 1
                    continue

                site_md = _fetch_site(url)
                phone = _fmt_phone(ex.get("phone"), site_md)
                if not email and not phone:
                    stats["dropped_no_contact"] += 1
                    continue

                if not _phone_geo_ok(phone, province):
                    stats["dropped_geo"] += 1
                    continue

                raw_first = strip_honorifics((ex.get("owner_first_name") or "").strip())
                first = raw_first.split()[0] if raw_first else ""
                full_name = (ex.get("owner_full_name") or "").strip()
                name = full_name or (first if _is_real_first(first) else "")

                audit = _audit_site(business, niche, city, province, url, site_md)
                if audit.get("location_check") == "mismatch":
                    stats["dropped_geo"] += 1
                    continue

                score = max(10, min(95, (10 - audit.get("conversion_score", 5)) * 10))
                tier = audit.get("recommended_tier", "growth")
                value_est = TIER_VALUE.get(tier, 3500)

                contract_row = {
                    "name": name,
                    "company": business,
                    "email": email or None,
                    "phone": phone,
                    "source": "bravo_firecrawl_scrape",
                    "stage": "researched",
                    "score": score,
                    "value_estimate": value_est,
                    "notes": f"{city}, {province} | {niche} | site: {audit.get('website_condition')} | {audit.get('pitch_angle')}",
                }
                enriched = enrich_lead_defaults(contract_row)
                data = {
                    **enriched,
                    "website": url,
                    "city": city,
                    "region": province,
                    "niche": f"{niche} (CC Leads)",
                    "vertical": "CC Leads",
                    "icp_track": "trades_cc",
                    "sales_program": "website_sales_v1",
                    "website_condition": audit.get("website_condition", "outdated"),
                    "audit_findings": audit.get("audit_findings", []),
                    "pitch_angle": audit.get("pitch_angle", ""),
                    "recommended_tier": tier,
                    "automation_openings": audit.get("automation_openings", []),
                    "conversion_score": audit.get("conversion_score", 4),
                    "location_check": audit.get("location_check", "confirmed"),
                    "location_evidence": audit.get("location_evidence", ""),
                    "audit_source": audit.get("audit_source", "claude_haiku"),
                    "role": (ex.get("role") or "").strip() or "Owner",
                    "stage_entered_at": _now_iso(),
                    "scraped_at": _now_iso(),
                    "created_from": "scrape_cc_trade_leads",
                }

                if _insert_lead_record(db, data, dry_run=dry_run):
                    promoted.append(data)
                    if email:
                        seen_emails.add(email)
                    seen_domains.add(dom)
                    city_counts[city] = city_counts.get(city, 0) + 1
                    _upsert_cc_territory_sheet(db, city, province, city_counts[city], dry_run=dry_run)
                    print(f"    [FRESH {len(promoted)}/{target}] {(name or '(owner)')[:16]:16} | {(business)[:26]:26} | {phone} | {email or 'No Email'}")

                OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
                OUT_JSON.write_text(json.dumps(promoted, indent=2), encoding="utf-8")
                time.sleep(delay)

    return promoted


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape and import 100 trade leads for CC")
    parser.add_argument("--target", type=int, default=100, help="Target total leads count")
    parser.add_argument("--dry-run", action="store_true", help="Audit without writing to database")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between Firecrawl requests")
    args = parser.parse_args()

    env = load_env()
    db = get_client(env)

    print(f"=== Starting CC Trade Leads Pipeline (Target: {args.target}) ===")
    seen_emails, seen_domains = load_seen_sets(db)
    print(f"Loaded {len(seen_emails)} existing emails and {len(seen_domains)} existing domains for dedup.")

    promoted, city_counts = process_previous_leads(db, seen_emails, seen_domains, args.target, args.dry_run)
    print(f"\nResurfaced {len(promoted)} leads from local dataset.")

    if len(promoted) < args.target:
        promoted = scrape_fresh_leads(db, seen_emails, seen_domains, promoted, city_counts, args.target, args.dry_run, args.delay)

    print(f"\n=== COMPLETED: {len(promoted)}/{args.target} CC Trade Leads Enriched and Imported! ===")
    print(f"Saved dataset to: {OUT_JSON}")


if __name__ == "__main__":
    main()
