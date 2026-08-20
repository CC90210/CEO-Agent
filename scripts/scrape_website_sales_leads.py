"""Website-sales lead scraper — fills the oasis-webdev pipeline at stage 'researched'.

Interim leadgen layer for the OASIS Website Sales Engine (Bravo runs this
until APEX ships the upstream leadgen_* system — see brain/DEAL_ARCHITECTURE.md).
Unlike scrape_firecrawl_leads.py (which feeds the `leads` table for the email
motion), this writes tenant_records rows the /pipeline UI actually renders,
with the full promoted-lead contract: website_condition, audit_findings,
icp_track, pitch_angle — everything a sales rep needs to open a cold call.

Pipeline per lead:
  1. Firecrawl search "{niche} {city} {province} small business" -> business URLs
  2. Firecrawl extract -> {owner name, business_name, email, phone, role}
  3. research_fetch ladder scrapes the site -> Claude audits it:
     website_condition, audit_findings[], pitch_angle, recommended_tier,
     automation_openings[] (upsell menu), conversion_score
  4. Keep if email OR phone (reps CALL first; email is secondary here)
  5. Dedupe vs existing tenant_records (oasis-webdev + OASIS CRM) by email + domain
  6. Insert tenant_records row immediately (tenant oasis-webdev, entity_type='lead',
     data.stage='researched', sales_program='website_sales_v1') — progressive fill,
     a crash loses nothing.

Usage:
  python scripts/scrape_website_sales_leads.py --target 100
  python scripts/scrape_website_sales_leads.py --target 4 --cities "Hamilton:Ontario" --dry-run
  python scripts/scrape_website_sales_leads.py --target 20 --niches "HVAC,med spa" --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
# supabase_tool lives in scripts/integrations/ — scrape_firecrawl_leads.py
# imports it bare, so integrations/ must be on the path BEFORE that import.
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from supabase_tool import get_client, load_env  # noqa: E402
from scrape_firecrawl_leads import (  # noqa: E402
    EXTRACT_SCHEMA, _is_skippable, _run_firecrawl, _valid_email, _is_real_first,
)
from name_utils import strip_honorifics  # noqa: E402
from lib.lead_contract import enrich_lead_defaults, should_create_lead  # noqa: E402

WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"  # oasis-webdev (Oasis Web Studio)
OASIS_CRM_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"  # dedupe against main CRM too

OUT_JSON = PROJECT_ROOT / "tmp" / "website_sales_leads.json"

# (city, province) — province feeds the search query so Montreal doesn't
# return Ontario results. Default mix: existing Ontario list + Montreal metro.
DEFAULT_CITIES: list[tuple[str, str]] = [
    ("Montreal", "Quebec"), ("Laval", "Quebec"),
    ("Hamilton", "Ontario"), ("London", "Ontario"), ("Burlington", "Ontario"),
    ("Oakville", "Ontario"), ("Mississauga", "Ontario"), ("Brampton", "Ontario"),
    ("Kitchener", "Ontario"), ("Guelph", "Ontario"), ("Waterloo", "Ontario"),
    ("Cambridge", "Ontario"), ("Markham", "Ontario"), ("Vaughan", "Ontario"),
    ("Richmond Hill", "Ontario"),
]

# niche -> icp_track (the 4 tracks in brain/CLIENT_PLAYBOOK.md). Deterministic
# mapping; the site audit can refine but never invent a fifth track.
NICHE_TRACKS: dict[str, str] = {
    "HVAC": "trades", "plumbing": "trades", "electrician": "trades",
    "roofing": "trades",
    "landscaping": "home_services", "cleaning service": "home_services",
    "painting contractor": "home_services", "garage door repair": "home_services",
    "med spa": "wellness_beauty", "massage therapy": "wellness_beauty",
    "chiropractic": "wellness_beauty", "physiotherapy": "wellness_beauty",
    "hair salon": "wellness_beauty",
    "dentist": "professional_services", "accounting firm": "professional_services",
    "law firm": "professional_services", "veterinary clinic": "professional_services",
}
VALID_TRACKS = set(NICHE_TRACKS.values())

TIER_VALUE = {"essential": 2000, "growth": 3500, "authority": 5000}
VALID_CONDITIONS = {
    "broken", "outdated", "weak_mobile", "unclear_cta", "no_online_booking",
    "thin_content", "decent", "strong", "unreachable",
}
# Must mirror AUTOMATION_ADD_ONS in oasis-command-center/lib/website-sales.ts.
# document_generation and local_seo were retired from the sell sheet on
# 2026-08-20 — suggesting them here would hand a rep an upsell the playbook
# no longer prices.
AUTOMATION_MENU = {
    "google_reviews", "lead_routing", "gmail_classifier", "missed_call_recovery",
    "quote_followup", "appointment_reminders", "lead_reactivation",
}

# Geo gate: Firecrawl search for "Hamilton Ontario" happily returns Hamilton,
# Michigan (found live 2026-08-19: mastheating.com, area code 616). Two layers:
# a deterministic area-code check + the audit's location_check. A rep must
# never cold-call the wrong country.
TOLL_FREE_CODES = {"800", "833", "844", "855", "866", "877", "888"}
PROVINCE_AREA_CODES: dict[str, set[str]] = {
    "Ontario": {"416", "647", "437", "905", "289", "365", "742", "519", "226",
                "548", "613", "343", "753", "705", "249", "683", "807", "382", "942"},
    "Quebec": {"514", "438", "263", "450", "579", "354", "418", "581", "367",
               "819", "873", "468"},
}
_ALL_TARGET_CODES = set().union(*PROVINCE_AREA_CODES.values())


def _phone_geo_ok(phone: Optional[str], province: str) -> bool:
    """True unless the area code proves the business is outside our territory.
    Toll-free and unparseable numbers pass (the audit layer still checks)."""
    if not phone or province not in PROVINCE_AREA_CODES:
        return True
    m = re.match(r"^(\d{3})-", phone)
    if not m:
        return True
    code = m.group(1)
    if code in TOLL_FREE_CODES:
        return True
    # Any ON/QC code passes (border-town leads are fine); anything else —
    # a US or other-region code — is a hard drop.
    return code in _ALL_TARGET_CODES

AUDIT_PROMPT = """\
You are a website-conversion auditor for a web design agency that sells
conversion-focused websites ($2,000-$5,000 setup) plus back-office automations
to owner-operated local businesses. A sales rep will cold-call this business
owner and needs concrete, specific ammunition.

Business: {business} ({niche}, {city})
Website: {url}

Return STRICT JSON only:
{{
  "website_condition": one of ["broken","outdated","weak_mobile","unclear_cta","no_online_booking","thin_content","decent","strong"],
  "audit_findings": [3-6 short strings, each ONE concrete observed deficiency or
                     opportunity, specific to THIS site — name the missing CTA,
                     the year in the footer, the absent booking widget. Never generic.],
  "pitch_angle": "1-2 plain-English sentences the rep can open the call with,
                  referencing the single most compelling finding.",
  "recommended_tier": one of ["essential","growth","authority"],
  "conversion_score": 0-10 (how well the CURRENT site converts visitors: 10 = excellent),
  "automation_openings": [0-3 items from: "google_reviews","lead_routing","gmail_classifier",
                          "missed_call_recovery","quote_followup","appointment_reminders",
                          "lead_reactivation" — only ones this business plausibly needs
                          based on what you saw. These are text/email automations only;
                          nothing here answers a phone call.],
  "location_check": one of ["confirmed","mismatch","unclear"] — does the page show this
                    business operating in or near {city}, {province} (street address,
                    service-area list, city names)? "mismatch" ONLY when the page clearly
                    places the business somewhere else (different state/province/country).
  "location_evidence": "short string: the address or service-area text you saw, or ''"
}}

Rules:
- audit_findings must be verifiable from the page content below. If you can't
  see it, don't claim it.
- pitch_angle is spoken aloud on a cold call: no jargon, no hedging.
- A beautiful site that already converts well = "strong", conversion_score 8-10,
  and findings shift to automation gaps instead of design flaws.

WEBSITE CONTENT (markdown)
==========================
{markdown}
"""

PHONE_RE = re.compile(r"(?:\+?1[\s\-\.])?\(?(\d{3})\)?[\s\-\.](\d{3})[\s\-\.](\d{4})")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_phone(raw: Optional[str], site_md: Optional[str] = None) -> Optional[str]:
    """Normalize extracted phone; fall back to first phone-looking string on the site."""
    for source in (raw or "", site_md or ""):
        if not source:
            continue
        m = PHONE_RE.search(source)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return (raw or "").strip() or None


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return url.lower()


def _fetch_site(url: str) -> Optional[str]:
    """research_fetch ladder (Firecrawl -> CloakBrowser -> urllib)."""
    try:
        from research_fetch import fetch
        res = fetch(url)
        if res.get("ok") and (res.get("text") or "").strip():
            return res["text"]
    except Exception as exc:  # noqa: BLE001
        print(f"    [site-fetch] {url} failed: {exc}", file=sys.stderr)
    return None


def _audit_site(business: str, niche: str, city: str, province: str, url: str,
                markdown: Optional[str]) -> dict[str, Any]:
    """Claude-audit the site. Returns a dict that always has the audit keys —
    fail-soft to 'unreachable' so a model outage never blocks the fill."""
    fallback = {
        "website_condition": "unreachable",
        "audit_findings": [
            "Site could not be fetched or audited - may be down, blocking, or JS-only",
            "Opener: reliability and a rebuilt fast-loading site",
        ],
        "pitch_angle": (
            f"When I tried to look at {business}'s website it wouldn't even load "
            "properly for me - if that's what your customers hit, you're losing "
            "jobs before the phone ever rings."
        ),
        "recommended_tier": "essential",
        "conversion_score": 0,
        "automation_openings": ["missed_call_recovery", "lead_routing"],
        "location_check": "unclear",
        "location_evidence": "",
        "audit_source": "fallback",
    }
    if not markdown:
        return fallback
    try:
        from lib.claude_cli import run_claude_cli
        prompt = AUDIT_PROMPT.format(
            business=business or "(unknown)", niche=niche, city=city,
            province=province, url=url, markdown=markdown[:10000],
        )
        text = run_claude_cli(prompt, model="haiku", timeout=120)
        if not text:
            return fallback
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return fallback
        audit = json.loads(m.group(0))
    except Exception as exc:  # noqa: BLE001
        print(f"    [audit] claude call failed: {exc}", file=sys.stderr)
        return fallback

    cond = str(audit.get("website_condition") or "").strip()
    if cond not in VALID_CONDITIONS:
        cond = "outdated"
    findings = [str(f).strip() for f in (audit.get("audit_findings") or []) if str(f).strip()][:6]
    tier = str(audit.get("recommended_tier") or "essential").strip()
    if tier not in TIER_VALUE:
        tier = "essential"
    try:
        conv = max(0, min(10, int(audit.get("conversion_score", 0))))
    except (TypeError, ValueError):
        conv = 0
    autos = [a for a in (audit.get("automation_openings") or []) if a in AUTOMATION_MENU][:3]
    loc = str(audit.get("location_check") or "unclear").strip()
    if loc not in {"confirmed", "mismatch", "unclear"}:
        loc = "unclear"
    return {
        "website_condition": cond,
        "audit_findings": findings or fallback["audit_findings"],
        "pitch_angle": str(audit.get("pitch_angle") or "").strip() or fallback["pitch_angle"],
        "recommended_tier": tier,
        "conversion_score": conv,
        "automation_openings": autos,
        "location_check": loc,
        "location_evidence": str(audit.get("location_evidence") or "").strip()[:200],
        "audit_source": "claude_haiku",
    }


def _existing_dedupe_sets(db) -> tuple[set[str], set[str]]:
    """Emails + website domains already in the pipeline (both tenants)."""
    emails: set[str] = set()
    domains: set[str] = set()
    for tenant in (WEBDEV_TENANT_ID, OASIS_CRM_TENANT_ID):
        try:
            rows = (db.table("tenant_records").select("id,data")
                    .eq("tenant_id", tenant).eq("entity_type", "lead")
                    .limit(2000).execute()).data or []
        except Exception as exc:  # noqa: BLE001
            print(f"  [dedupe] tenant {tenant[:8]} read failed: {exc}", file=sys.stderr)
            continue
        for row in rows:
            d = row.get("data") or {}
            if isinstance(d, str):
                try:
                    d = json.loads(d)
                except json.JSONDecodeError:
                    continue
            e = (d.get("email") or "").lower().strip()
            if e:
                emails.add(e)
            w = d.get("website") or ""
            if w:
                domains.add(_domain(str(w)))
    return emails, domains


def _insert_lead(db, payload: dict[str, Any], dry_run: bool) -> bool:
    if dry_run:
        return True
    row = {
        "id": str(uuid.uuid4()),
        "tenant_id": WEBDEV_TENANT_ID,
        "entity_type": "lead",
        "data": payload,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        db.table("tenant_records").insert(row).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"    [insert] FAILED for {payload.get('email') or payload.get('company')}: {exc}",
              file=sys.stderr)
        return False


def _audit_fields(audit: dict[str, Any]) -> dict[str, Any]:
    """The audit's contribution to a lead row. One definition, used by both the
    insert path and the re-audit path so a new audit field can never land on
    freshly scraped leads while silently skipping re-audited ones."""
    conv = audit["conversion_score"]
    return {
        "website_condition": audit["website_condition"],
        "audit_findings": audit["audit_findings"],
        "pitch_angle": audit["pitch_angle"],
        "recommended_tier": audit["recommended_tier"],
        "automation_openings": audit["automation_openings"],
        "conversion_score": conv,
        "location_check": audit["location_check"],
        "location_evidence": audit["location_evidence"],
        "audit_source": audit["audit_source"],
        "value_estimate": TIER_VALUE[audit["recommended_tier"]],
        # Opportunity score: the worse the site converts, the hotter the lead.
        # A fallback audit saw nothing, so it earns no confidence-weighted score.
        "score": max(10, min(95, (10 - conv) * 10)) if audit["audit_source"] == "claude_haiku" else 85,
    }


def cmd_reaudit(db, limit: int, delay: float, dry_run: bool) -> int:
    """Re-run the site audit on leads whose audit fell back.

    The first bulk run burned through the Claude CLI's session limit partway,
    so 46 of 53 leads landed with audit_source='fallback' — a generic pitch
    angle and no real findings, which is precisely the ammunition a rep opens
    the call with. This re-audits exactly those rows once the limit resets.
    Idempotent: a row that upgrades to a real audit no longer matches.
    """
    rows = (db.table("tenant_records").select("id,data")
            .eq("tenant_id", WEBDEV_TENANT_ID).eq("entity_type", "lead")
            .limit(2000).execute()).data or []
    targets = []
    for row in rows:
        d = row.get("data") or {}
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except json.JSONDecodeError:
                continue
        if d.get("sales_program") != "website_sales_v1":
            continue
        if d.get("audit_source") == "fallback" and d.get("website"):
            targets.append((row["id"], d))
    if limit:
        targets = targets[:limit]
    print(f"re-auditing {len(targets)} lead(s) with fallback audits"
          f"{' (DRY RUN)' if dry_run else ''}")
    fixed = still_failing = 0
    for i, (rid, d) in enumerate(targets, 1):
        url = str(d.get("website") or "")
        site_md = _fetch_site(url)
        audit = _audit_site(str(d.get("company") or ""), str(d.get("niche") or ""),
                            str(d.get("city") or ""), str(d.get("region") or "Ontario"),
                            url, site_md)
        if audit["audit_source"] == "fallback":
            still_failing += 1
            print(f"[{i}/{len(targets)}] {rid[:8]} still unreachable: {url}")
        else:
            if audit.get("location_check") == "mismatch":
                print(f"[{i}/{len(targets)}] {rid[:8]} GEO MISMATCH on re-audit "
                      f"({audit.get('location_evidence') or 'no evidence'}) — flagging")
            new = dict(d)
            new.update(_audit_fields(audit))
            new["reaudited_at"] = _now_iso()
            if not dry_run:
                db.table("tenant_records").update(
                    {"data": new, "updated_at": _now_iso()}
                ).eq("id", rid).eq("tenant_id", WEBDEV_TENANT_ID).execute()
            fixed += 1
            print(f"[{i}/{len(targets)}] {rid[:8]} {audit['website_condition']:14} "
                  f"score={audit['conversion_score']} | {(d.get('company') or '')[:32]}")
        if i < len(targets):
            time.sleep(delay)
    print(json.dumps({"reaudited": fixed, "still_unreachable": still_failing,
                      "dry_run": dry_run}, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reaudit", action="store_true",
                   help="Re-audit existing leads whose audit fell back, then exit")
    p.add_argument("--target", type=int, default=None,
                   help="Scrape mode: stop after this many promoted leads (default 100). "
                        "With --reaudit: cap how many leads to re-audit (default: all)")
    p.add_argument("--cities", default=None,
                   help='Comma list of "City:Province" (default: Ontario 13 + Montreal metro)')
    p.add_argument("--niches", default=",".join(NICHE_TRACKS.keys()))
    p.add_argument("--dry-run", action="store_true", help="No DB writes")
    p.add_argument("--json", action="store_true", help="JSON summary to stdout")
    p.add_argument("--delay", type=float, default=2.0,
                   help="Seconds between leads (Firecrawl rate courtesy)")
    args = p.parse_args()

    if args.cities:
        cities: list[tuple[str, str]] = []
        for chunk in args.cities.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            city, _, prov = chunk.partition(":")
            cities.append((city.strip(), (prov or "Ontario").strip()))
    else:
        cities = DEFAULT_CITIES

    niches = [n.strip() for n in args.niches.split(",") if n.strip()]
    unknown = [n for n in niches if n not in NICHE_TRACKS]
    if unknown:
        print(f"WARNING: niches without a track map (default trades): {unknown}",
              file=sys.stderr)

    db = get_client(load_env())

    if args.reaudit:
        # No --target in re-audit mode means "every fallback lead", not "100".
        return cmd_reaudit(db, limit=args.target or 0,
                           delay=args.delay, dry_run=args.dry_run)

    target = args.target if args.target is not None else 100

    seen_emails, seen_domains = _existing_dedupe_sets(db)
    print(f"Dedupe baseline: {len(seen_emails)} emails, {len(seen_domains)} domains already in CRM")

    promoted: list[dict] = []
    seen_urls: set[str] = set()
    per_track: dict[str, int] = {t: 0 for t in VALID_TRACKS}
    stats = {"searches": 0, "extracts": 0, "dropped_no_contact": 0,
             "dropped_dup": 0, "dropped_machine_email": 0, "dropped_geo": 0,
             "insert_failures": 0}

    print(f"Target: {target} promoted leads | tenant oasis-webdev | "
          f"{'DRY RUN' if args.dry_run else 'LIVE'}\n")

    # Round-robin cities x niches so no single city/niche dominates the fill.
    pairs = [(c, p_, n) for (c, p_) in cities for n in niches]
    # Interleave: sort by (niche_index, city_index) round-robin
    pairs.sort(key=lambda x: (niches.index(x[2]), cities.index((x[0], x[1]))))

    for city, province, niche in pairs:
        if len(promoted) >= target:
            break
        track = NICHE_TRACKS.get(niche, "trades")
        query = f"{niche} {city} {province} small business"
        print(f"\n[{city}, {province} / {niche} -> {track}] search: {query!r}")
        stats["searches"] += 1
        result = _run_firecrawl(["search", query])
        items = ((result or {}).get("web") or (result or {}).get("data")
                 or (result or {}).get("results") or [])
        urls: list[str] = []
        for item in items[:12]:
            u = item.get("url") if isinstance(item, dict) else None
            if not u or not u.startswith("http") or _is_skippable(u):
                continue
            urls.append(u)
            if len(urls) >= 5:
                break

        for url in urls:
            if len(promoted) >= target:
                break
            dom = _domain(url)
            if url in seen_urls or dom in seen_domains:
                stats["dropped_dup"] += 1
                continue
            seen_urls.add(url)
            print(f"  extract: {url}")
            stats["extracts"] += 1
            ex_res = _run_firecrawl(["extract", url, "--schema", json.dumps(EXTRACT_SCHEMA)])
            ex = (ex_res or {}).get("data") or (ex_res or {}).get("extract") or ex_res or {}
            if not isinstance(ex, dict):
                continue

            business = (ex.get("business_name") or "").strip()
            email = (ex.get("email") or "").lower().strip()
            if email and not _valid_email(email):
                email = ""
            if email:
                ok, reason = should_create_lead(email)
                if not ok:
                    print(f"    drop ({reason})")
                    stats["dropped_machine_email"] += 1
                    email = ""  # keep the lead if phone exists; just drop the address
            if email and email in seen_emails:
                stats["dropped_dup"] += 1
                continue

            site_md = _fetch_site(url)
            phone = _fmt_phone(ex.get("phone"), site_md)
            if not email and not phone:
                print("    drop (no email AND no phone - rep can't act)")
                stats["dropped_no_contact"] += 1
                continue
            if not _phone_geo_ok(phone, province):
                print(f"    drop (geo: area code {phone[:3]} outside ON/QC - "
                      f"wrong-region search hit)")
                stats["dropped_geo"] += 1
                continue

            raw_first = strip_honorifics((ex.get("owner_first_name") or "").strip())
            first = raw_first.split()[0] if raw_first else ""
            full_name = (ex.get("owner_full_name") or "").strip()
            name = full_name or (first if _is_real_first(first) else "")

            audit = _audit_site(business, niche, city, province, url, site_md)
            if audit.get("location_check") == "mismatch":
                print(f"    drop (geo: audit places business elsewhere - "
                      f"{audit.get('location_evidence') or 'no evidence text'})")
                stats["dropped_geo"] += 1
                continue
            # Opportunity score: the worse their site converts, the hotter the lead.
            score = max(10, min(95, (10 - audit["conversion_score"]) * 10)) \
                if audit["audit_source"] == "claude_haiku" else 85

            contract_row = {
                "name": name, "company": business, "email": email or None,
                "phone": phone, "source": "bravo_firecrawl_scrape",
                "stage": "researched", "score": score,
                "value_estimate": TIER_VALUE[audit["recommended_tier"]],
                "notes": (f"{city}, {province} | {niche} | site: {audit['website_condition']} | "
                          f"{audit['pitch_angle']}"),
            }
            enriched = enrich_lead_defaults(contract_row)
            data = {
                **enriched,
                "website": url,
                "city": city, "region": province, "niche": niche,
                "icp_track": track,
                "sales_program": "website_sales_v1",
                "website_condition": audit["website_condition"],
                "audit_findings": audit["audit_findings"],
                "pitch_angle": audit["pitch_angle"],
                "recommended_tier": audit["recommended_tier"],
                "automation_openings": audit["automation_openings"],
                "conversion_score": audit["conversion_score"],
                "location_check": audit["location_check"],
                "location_evidence": audit["location_evidence"],
                "audit_source": audit["audit_source"],
                "role": (ex.get("role") or "").strip() or None,
                "stage_entered_at": _now_iso(),
                "scraped_at": _now_iso(),
                "created_from": "scrape_website_sales_leads",
            }
            if _insert_lead(db, data, args.dry_run):
                promoted.append(data)
                per_track[track] = per_track.get(track, 0) + 1
                if email:
                    seen_emails.add(email)
                seen_domains.add(dom)
                print(f"    [PROMOTED {len(promoted)}/{target}] "
                      f"{(name or '(no name)')[:18]:18} | {(business or '(unknown)')[:28]:28} | "
                      f"{audit['website_condition']:16} | {email or phone}")
            else:
                stats["insert_failures"] += 1

            # Persist progress after every lead — crash-safe.
            OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
            OUT_JSON.write_text(json.dumps(promoted, indent=2), encoding="utf-8")
            time.sleep(args.delay)

    summary = {
        "promoted": len(promoted),
        "per_track": per_track,
        **stats,
        "tenant": "oasis-webdev",
        "stage": "researched",
        "dry_run": args.dry_run,
        "json_path": str(OUT_JSON),
    }
    print()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("=== Website-Sales Scrape Summary ===")
        for k, v in summary.items():
            print(f"  {k:22} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
