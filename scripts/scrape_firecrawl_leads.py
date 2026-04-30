"""Lead scraper using Firecrawl API (replaces slow Playwright + Google Maps flow).

Pipeline:
  1. Search Firecrawl for "{niche} {city} Ontario" -> list of business URLs
  2. For each URL, run Firecrawl extract with a structured schema:
       {owner_first_name, owner_full_name, business_name, email, phone, role}
  3. Filter for valid email + real first name (drops business-only contacts)
  4. Dedup against existing Supabase leads
  5. Insert to Supabase as status='new', source='cold_outreach_firecrawl'

This is the canonical lead scraper (replaced the Playwright Google-Maps
flow on 2026-04-27 — that path produced placeholder names and was slow).
Firecrawl's structured extract delivers real first names directly.

Usage:
  python scripts/scrape_firecrawl_leads.py --target 50
  python scripts/scrape_firecrawl_leads.py --target 20 --cities "Hamilton,London" --niches "HVAC,Roofing"
  python scripts/scrape_firecrawl_leads.py --dry-run --json
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from supabase_tool import get_client, load_env  # noqa: E402
from name_utils import _is_placeholder, strip_honorifics  # noqa: E402
from casl_compliance import is_reserved_domain  # noqa: E402

# Schema Firecrawl uses to pull structured contact info from each website
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "owner_first_name": {
            "type": "string",
            "description": "Owner / founder / primary contact's first name "
                           "(e.g. 'Jane', 'Mike'). Empty string if only a "
                           "business name is shown, no real person."
        },
        "owner_full_name": {
            "type": "string",
            "description": "Full name of the owner / founder / primary contact."
        },
        "business_name": {"type": "string"},
        "email": {
            "type": "string",
            "description": "Contact / info / sales email shown on page."
        },
        "phone": {"type": "string"},
        "role": {
            "type": "string",
            "description": "Owner's role/title if shown (e.g. 'Owner', 'Founder', 'CEO')."
        },
    },
    "required": ["business_name"],
}

DEFAULT_CITIES = [
    "Hamilton", "London", "Burlington", "Oakville", "Mississauga",
    "Brampton", "Kitchener", "Guelph", "Waterloo", "Cambridge",
    "Markham", "Vaughan", "Richmond Hill",
]
DEFAULT_NICHES = [
    "HVAC", "plumbing", "roofing", "physiotherapy", "chiropractic",
    "dentist", "landscaping", "med spa", "electrician",
]

OUT_JSON = PROJECT_ROOT / "tmp" / "scraped_leads_firecrawl.json"


def _run_firecrawl(args: list[str]) -> dict | None:
    try:
        r = subprocess.run(
            ["python", "scripts/firecrawl_tool.py", *args, "--json"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        if r.returncode != 0:
            print(f"  [firecrawl error rc={r.returncode}] {r.stderr.strip()[:200]}",
                  file=sys.stderr)
            return None
        return json.loads(r.stdout) if r.stdout.strip() else None
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"  [firecrawl exception] {exc}", file=sys.stderr)
        return None


# Skip directory / aggregator / national-chain domains — no individual
# small-business owner contact info worth extracting.
DIRECTORY_DOMAINS = {
    "yelp.com", "reddit.com", "homestars.com", "yellowpages.ca",
    "yellowpages.com", "kijiji.ca", "google.com", "facebook.com",
    "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "indeed.com", "glassdoor.com",
    "bbb.org", "tripadvisor.com", "opentable.com", "houzz.com",
    "thumbtack.com", "wikipedia.org", "trustpilot.com",
    "reliancehomecomfort.com", "directenergy.com",  # national chains
    "enercare.ca", "enbridgegas.com",
}


def _is_skippable(url: str) -> bool:
    lower = url.lower()
    return any(d in lower for d in DIRECTORY_DOMAINS)


def _search_one(niche: str, city: str) -> list[str]:
    """Return up to ~6 small-business URLs for a niche+city query."""
    query = f"{niche} {city} Ontario small business"
    print(f"  search: {query!r}")
    result = _run_firecrawl(["search", query])
    if not result:
        return []
    # Firecrawl search returns {web: [...], data: [...], or results: [...]}
    items = (result.get("web") or result.get("data") or
             result.get("results") or [])
    urls = []
    for item in items[:12]:  # check more results, then filter directories
        u = item.get("url") if isinstance(item, dict) else None
        if not u or not u.startswith("http"):
            continue
        if _is_skippable(u):
            print(f"    skip directory: {u}")
            continue
        urls.append(u)
        if len(urls) >= 6:
            break
    return urls


def _extract_one(url: str) -> dict[str, Any] | None:
    print(f"  extract: {url}")
    result = _run_firecrawl(["extract", url, "--schema", json.dumps(EXTRACT_SCHEMA)])
    if not result:
        return None
    # Firecrawl extract returns {data: {...schema fields...}, ...}
    data = result.get("data") or result.get("extract") or result
    if isinstance(data, dict):
        return data
    return None


def _is_real_first(name: str) -> bool:
    if not name:
        return False
    cleaned = strip_honorifics(name.strip())
    s = cleaned.split()[0] if cleaned else ""
    if not s or _is_placeholder(s.lower()):
        return False
    return any(c.isalpha() for c in s)


def _valid_email(email: str) -> bool:
    """Surface-level structural check + reserved-domain rejection.
    Reserved-domain list is canonical in casl_compliance.RESERVED_EMAIL_DOMAINS
    and the gateway re-checks at send time as belt-and-suspenders."""
    if not email or "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        return False
    return not is_reserved_domain(email)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=int, default=50,
                   help="Stop scraping after this many qualified leads (default 50)")
    p.add_argument("--cities", default=",".join(DEFAULT_CITIES))
    p.add_argument("--niches", default=",".join(DEFAULT_NICHES))
    p.add_argument("--dry-run", action="store_true",
                   help="Don't write to Supabase, just produce the JSON")
    p.add_argument("--json", action="store_true", help="Output JSON summary")
    args = p.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    niches = [n.strip() for n in args.niches.split(",") if n.strip()]

    db = get_client(load_env())
    existing = {(L.get("email") or "").lower().strip()
                for L in (db.table("leads")
                          .select("email")
                          .limit(2000)
                          .execute()).data or []
                if L.get("email")}

    leads: list[dict] = []
    seen_urls: set[str] = set()
    extracted = 0
    qualified = 0

    print(f"Target: {args.target} qualified leads")
    print(f"Cities: {cities}")
    print(f"Niches: {niches}\n")

    for city in cities:
        if qualified >= args.target:
            break
        for niche in niches:
            if qualified >= args.target:
                break
            print(f"\n[{city} / {niche}]")
            urls = _search_one(niche, city)
            for url in urls:
                if qualified >= args.target:
                    break
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                extracted += 1
                ex = _extract_one(url)
                if not ex:
                    continue
                email = (ex.get("email") or "").lower().strip()
                # Strip honorifics so "Dr. Micah" stored as "Micah" and
                # downstream rendering says "Hi Micah," not "Hi Dr.,"
                raw_first = (ex.get("owner_first_name") or "").strip()
                first = strip_honorifics(raw_first).split()[0] if raw_first else ""
                business = (ex.get("business_name") or "").strip()
                if not _valid_email(email):
                    continue
                if email in existing:
                    print(f"    skip (dup): {email}")
                    continue
                if not _is_real_first(first):
                    # Keep but flag — name enrichment can fix later
                    flag = "no_first_name"
                else:
                    flag = "ready_to_send"
                lead = {
                    "first_name": first if _is_real_first(first) else None,
                    "full_name": (ex.get("owner_full_name") or "").strip() or None,
                    "company": business or None,
                    "email": email,
                    "phone": (ex.get("phone") or "").strip() or None,
                    "role": (ex.get("role") or "").strip() or None,
                    "city": city,
                    "niche": niche,
                    "website": url,
                    "flag": flag,
                }
                leads.append(lead)
                existing.add(email)
                if flag == "ready_to_send":
                    qualified += 1
                print(f"    [{flag}] {first or '(no name)':12} | "
                      f"{(business or '(unknown)')[:30]:30} | {email}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(leads, indent=2), encoding="utf-8")

    inserted = 0
    if leads and not args.dry_run:
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for L in leads:
            notes_parts = [
                f"City: {L['city']}", f"Niche: {L['niche']}",
                f"Website: {L['website']}",
                f"Source: Firecrawl scrape on {now[:10]}",
            ]
            if L.get("role"):
                notes_parts.append(f"Role: {L['role']}")
            if L.get("flag") == "no_first_name":
                notes_parts.append("FLAG: no_first_name (needs enrichment before send)")
            # leads.name is NOT NULL — use empty string when no real name was
            # extracted. The placeholder sanitizer + eligibility filter both
            # treat "" as "no usable first name" and skip these leads from
            # auto-send until enriched.
            rows.append({
                "name": L["full_name"] or L["first_name"] or "",
                "company": L["company"],
                "email": L["email"],
                "phone": L["phone"],
                "source": "cold_outreach",
                "status": "new",
                "score": 0,
                "tags": [L["niche"], "firecrawl"],
                "notes": " | ".join(notes_parts),
                "assigned_to": "bravo",
                "created_at": now,
                "updated_at": now,
            })
        for i in range(0, len(rows), 25):
            chunk = rows[i:i + 25]
            try:
                res = db.table("leads").insert(chunk).execute()
                inserted += len(res.data or [])
            except Exception as exc:  # noqa: BLE001
                print(f"  insert error chunk {i}: {exc}", file=sys.stderr)

    summary = {
        "extracted_pages": extracted,
        "leads_found": len(leads),
        "ready_to_send": sum(1 for L in leads if L["flag"] == "ready_to_send"),
        "needs_enrichment": sum(1 for L in leads if L["flag"] == "no_first_name"),
        "inserted_to_supabase": inserted,
        "json_path": str(OUT_JSON),
        "dry_run": args.dry_run,
    }
    print()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("=== Firecrawl Scrape Summary ===")
        for k, v in summary.items():
            print(f"  {k:25} {v}")


if __name__ == "__main__":
    main()
