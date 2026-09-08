"""Owner-operator lead scraper — small-town service businesses where the phone
reaches the person who can say yes.

WHY THIS EXISTS, AND WHY IT IS NOT THE OSM PIPELINE
---------------------------------------------------
The web-leads board is sourced from OpenStreetMap (133,904 businesses). OSM maps
PREMISES, so it is excellent for restaurants, salons and retail and close to
useless for the businesses CC actually wants to call: a mobile detailer, a window
washer or a two-truck moving company frequently has no mapped premises at all.
Measured against live inventory on 2026-09-08, the whole corpus held 28 detailers,
4 window cleaners and 40 movers across all of Canada — and in ON+BC together only
140 rows of that ICP, 59 with a phone. There is nothing to promote. New leads have
to be discovered, not filtered.

The discovery source here is web search (Firecrawl), which surfaces exactly the
businesses OSM misses — the Google Business Profile, the one-page site, the
local directory listing. A probe for "car detailing Orillia Ontario" returned
mobile detailers with phone numbers and owner first names in the result text,
which is the shape this pipeline is built to harvest.

THE SELECTION THESIS (Adon's, and it is the whole point)
--------------------------------------------------------
In a town of 5,000-60,000 the business IS the owner, so the published number
reaches a decision maker. In Toronto the same listing reaches a receptionist. So
geography and industry do the qualification work that a personal-mobile lookup
otherwise would — and personal mobiles are NOT on the public web (APEX tested it:
DuckDuckGo returns the business line from directories, and LinkedIn scraping is a
ToS violation we do not commit). Every town below is chosen for size, and every
ICP below is chosen because the trade is overwhelmingly owner-operated.

WHAT THIS WRITES, AND THE GATE IT WRITES BEHIND
-----------------------------------------------
Two destinations, deliberately:

  leadgen_businesses   every candidate we discovered, promoted or not. This is
                       inventory, and holding the misses is what stops the next
                       run re-crawling them.
  tenant_records       the rep-facing board — ONLY rows that clear the gate.

The gate is `phone AND owner_name`, which is exactly the "Owner named" tier the
board filters on. Two independent reasons it is not negotiable:

  1. It is what CC asked for — a number that reaches the owner.
  2. APEX's purge deletes owner-less leads at stage='researched'. A row promoted
     without an owner name is deleted on their next sweep, so promoting one is
     not merely low-value, it is work that erases itself.

A candidate that fails the gate stays in leadgen_businesses with its
`owner_lookup_outcome` recorded, so it is inventory for a later enrichment pass
rather than a hole this scraper digs again next week.

IDEMPOTENCE — ATTEMPTS, NOT JUST SUCCESSES
------------------------------------------
APEX lost real time to a scraper that recorded only successful enrichments and
therefore re-crawled its own failures on every restart (25 owners in 925 leads,
then 2 in the next 900). Every (province, town, icp) cell is journalled to
state/owner_operator_attempts.json the moment it is ATTEMPTED, with its outcome.
A rerun skips cells attempted inside --retry-after-days regardless of whether
they produced anything.

Usage:
  python scripts/lead_generation/owner_operator_scraper.py --plan
  python scripts/lead_generation/owner_operator_scraper.py --dry-run --limit 3
  python scripts/lead_generation/owner_operator_scraper.py --provinces ON --target 100
  python scripts/lead_generation/owner_operator_scraper.py --icp detailing,moving --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from integrations.supabase_tool import get_client, load_env  # noqa: E402
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# The OASIS command-center tenant — the same one lib/web-leads/tenant.ts pins.
# Rows written without it land NULL and are invisible to every tenant-scoped read.
OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

# Distinct from `oasis_webdev_leadgen:osm` ON PURPOSE. APEX purges and promotes
# against the same board; a source value only this pipeline writes lets either
# side scope a sweep to its own rows instead of guessing.
SOURCE = "oasis_webdev_leadgen:gbp_owner_operator"

ATTEMPTS_PATH = PROJECT_ROOT / "state" / "owner_operator_attempts.json"

# ---------------------------------------------------------------------------
# THE ICP CATALOG
# ---------------------------------------------------------------------------
# `industry` is the label a rep sees in the filter rail, and it is also written
# to leadgen_territories.vertical — the rail is built from territory sheets, not
# from the leads, so an industry with no sheet is invisible however many leads
# carry it.
#
# `queries` are search phrasings, plural because one phrasing systematically
# misses part of a trade: "car detailing" and "mobile detailing" are different
# businesses in the results, and a mobile operator is the MORE owner-operated of
# the two. Precision tokens can also empty a search outright, so the phrasings
# stay deliberately short.
ICP_CATALOG: dict[str, dict[str, Any]] = {
    "detailing": {
        "industry": "Auto Detailing",
        "queries": ["car detailing", "mobile car detailing", "auto detailing"],
        "why": "Almost always one or two operators; the phone on the listing is the owner's.",
    },
    "window": {
        "industry": "Window Cleaning",
        "queries": ["window cleaning", "window washing"],
        "why": "Owner-operated by default; no premises, so OSM never had them.",
    },
    "moving": {
        "industry": "Moving & Storage",
        "queries": ["moving company", "movers"],
        "why": "Small fleets are owner-run; dispatch and ownership are the same phone.",
    },
    "renovation": {
        "industry": "Home Renovation",
        "queries": ["home renovation", "home remodeling contractor", "kitchen renovation"],
        "why": "Trade contractors answer their own phone between jobs.",
    },
    "chiro": {
        "industry": "Chiropractic",
        "queries": ["chiropractor", "chiropractic clinic"],
        "why": "Practitioner-owned clinics; the named DC on the site is the owner.",
    },
    "medspa": {
        "industry": "Med Spa & Aesthetics",
        "queries": ["med spa", "medical aesthetics clinic"],
        "why": "Owner-operator clinics, and they buy marketing.",
    },
    "homecare": {
        "industry": "Nursing & Home Care",
        "queries": ["home care nursing", "private nursing services"],
        "why": "Nurse-founded agencies; the founder is the intake line.",
    },
    # Adjacent trades that satisfy the SAME thesis (no premises, owner answers).
    # They cost nothing extra to search and they widen a thin town.
    "pressure": {
        "industry": "Pressure Washing",
        "queries": ["pressure washing", "power washing"],
        "why": "Single-truck operators.",
    },
    "landscaping": {
        "industry": "Landscaping & Lawn Care",
        "queries": ["landscaping company", "lawn care service"],
        "why": "Seasonal owner-operators.",
    },
    "junk": {
        "industry": "Junk Removal",
        "queries": ["junk removal", "waste removal service"],
        "why": "Owner-driven; competes on local visibility.",
    },
    "painting": {
        "industry": "Painting Contractors",
        "queries": ["painting contractor", "house painters"],
        "why": "Owner quotes every job personally.",
    },
    "pool": {
        "industry": "Pool & Spa Service",
        "queries": ["pool service", "hot tub service"],
        "why": "Route-based owner-operators.",
    },
}

# ---------------------------------------------------------------------------
# GEOGRAPHY
# ---------------------------------------------------------------------------
# English-speaking small towns, per CC. Roughly 5k-60k population: big enough to
# support the trade, small enough that the listed number is the owner's. QC is
# deliberately ABSENT — CC asked for English markets, and a French-first town
# changes both the script and the compliance posture.
TOWNS: dict[str, list[str]] = {
    "ON": [
        "Orillia", "Collingwood", "Wasaga Beach", "Midland", "Bracebridge",
        "Huntsville", "Gravenhurst", "Stratford", "St. Marys", "Goderich",
        "Owen Sound", "Meaford", "Port Elgin", "Kincardine", "Elora",
        "Fergus", "Paris", "Simcoe", "Tillsonburg", "Ingersoll",
        "Napanee", "Picton", "Cobourg", "Port Hope", "Brockville",
        "Perth", "Smiths Falls", "Renfrew", "Pembroke", "Arnprior",
        "Bancroft", "Haliburton", "Parry Sound", "Espanola", "Kenora",
        "Dryden", "Fort Frances", "Elliot Lake", "Hanover", "Listowel",
    ],
    "BC": [
        "Vernon", "Penticton", "Salmon Arm", "Cranbrook", "Nelson",
        "Castlegar", "Trail", "Revelstoke", "Golden", "Kimberley",
        "Squamish", "Powell River", "Courtenay", "Comox", "Parksville",
        "Qualicum Beach", "Duncan", "Ladysmith", "Port Alberni", "Campbell River",
        "Williams Lake", "Quesnel", "Terrace", "Smithers", "Prince Rupert",
        "Fort St. John", "Dawson Creek", "Merritt", "Kamloops", "Sechelt",
        "Gibsons", "Creston", "Grand Forks", "Oliver", "Osoyoos",
        "Summerland", "Sicamous", "Chase", "Hope", "Lillooet",
    ],
}

PROVINCE_NAMES = {"ON": "Ontario", "BC": "British Columbia"}

# ---------------------------------------------------------------------------
# Directory / aggregator hosts.
#
# These are NOT businesses, and treating one as a lead produces a call to Yelp's
# support line. They are still useful as CORROBORATION for a phone number, so
# they are excluded from candidacy rather than dropped from the result set.
# ---------------------------------------------------------------------------
AGGREGATOR_HOSTS = {
    "yelp.com", "yelp.ca", "yellowpages.ca", "yellowpages.com", "ypnext.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "tiktok.com", "youtube.com", "pinterest.com", "nextdoor.com",
    "reddit.com", "kijiji.ca", "craigslist.org", "indeed.com", "glassdoor.com",
    "google.com", "maps.google.com", "bing.com", "duckduckgo.com",
    "tripadvisor.com", "tripadvisor.ca", "bbb.org", "homestars.com",
    "houzz.com", "thumbtack.com", "angi.com", "yellowpagesdirectory.com",
    "canada411.ca", "411.ca", "cylex-canada.ca", "opendi.ca", "bizapedia.com",
    "wikipedia.org", "amazon.com", "ebay.com", "groupon.com", "wayfair.com",
    "trustpilot.com", "birdeye.com", "chatterblock.com", "profilecanada.com",
    # Added after the first live run put each of these forward as a "business".
    "mapquest.com", "pandahub.com", "foursquare.com", "yellowpages.net",
    "storeboard.com", "manta.com", "hotfrog.ca", "hotfrog.com", "brownbook.net",
    "cybo.com", "tupalo.com", "n49.com", "goldenpages.ca", "biztoc.com",
    "expertise.com", "threebestrated.com", "trustanalytica.com", "yably.com",
    "bark.com", "checkatrade.com", "porch.com", "networx.com", "yelp.co.uk",
}

# Non-ICP business types that search returns for these queries but that we must
# never call. Dealerships in particular were explicitly purged from this board
# once already (APEX, 2026-09-02, 208 rows) — a dealership answering a
# detailing search is a receptionist at a franchise, which is the exact
# opposite of the owner-operator thesis this pipeline is built on.
NON_ICP_NAME_TOKENS = (
    "nissan", "toyota", "honda", "ford", "chevrolet", "chevy", "hyundai", "kia",
    "mazda", "subaru", "volkswagen", "audi", "bmw", "mercedes", "lexus", "acura",
    "chrysler", "dodge", "jeep", "ram trucks", "gmc", "buick", "cadillac",
    "dealership", "auto group", "autogroup", "car dealer",
    "university", "college", "municipality", "city of ", "town of ",
    "canadian tire", "walmart", "costco", "home depot", "lowes",
)


def _is_non_icp(name: str, host: str) -> bool:
    """True for businesses this pipeline must not put in front of a rep."""
    hay = f"{name} {host}".lower()
    return any(tok in hay for tok in NON_ICP_NAME_TOKENS)

# Ten digits in the shapes a Canadian listing actually uses. Deliberately NOT
# anchored, because it runs against prose ("call us at ...") as well as markup.
PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?([2-9]\d{2})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})(?!\d)")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Area codes by province. A number whose area code belongs to another province is
# not proof of anything on its own (toll-free, ported cells, an owner who moved),
# so this DOWNGRADES confidence — it never rejects.
AREA_CODES = {
    "ON": {"226", "249", "289", "343", "365", "382", "387", "416", "437", "519",
           "548", "613", "647", "683", "705", "742", "753", "807", "905", "942"},
    "BC": {"236", "250", "257", "604", "672", "778"},
}
# Never a person: toll-free reaches a call centre or an answering service, which
# is the exact opposite of what this pipeline is for.
TOLL_FREE = {"800", "833", "844", "855", "866", "877", "888"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host(url: str) -> str:
    try:
        h = (urlparse(url).netloc or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _registrable(host: str) -> str:
    """Good-enough eTLD+1 for dedupe. Handles the .co.uk / .on.ca shapes we meet."""
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    if parts[-2] in {"co", "com", "net", "org", "gov", "edu"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_aggregator(url: str) -> bool:
    h = _host(url)
    if not h:
        return True
    return _registrable(h) in AGGREGATOR_HOSTS or h in AGGREGATOR_HOSTS


def _norm_phone(raw: str) -> str | None:
    """Ten digits, or nothing. A 'phone' we cannot normalise is not a phone."""
    m = PHONE_RE.search(raw or "")
    if not m:
        return None
    npa, nxx, line = m.groups()
    if npa in TOLL_FREE:
        return None
    return f"{npa}{nxx}{line}"


def _pretty_phone(ten: str) -> str:
    return f"({ten[:3]}) {ten[3:6]}-{ten[6:]}"


def _phone_confidence(ten: str, province: str) -> tuple[int, str, list[str]]:
    """Confidence, tier and the reasons — the same vocabulary the board renders.

    Returns a TIER a rep can act on, never a bare number, because the tier is
    what the card shows and an unexplained score is not reviewable.
    """
    reasons: list[str] = []
    npa = ten[:3]
    if npa in AREA_CODES.get(province, set()):
        reasons.append("The area code matches the province this business is listed in.")
        return 70, "probable", reasons
    other = [p for p, codes in AREA_CODES.items() if npa in codes]
    if other:
        reasons.append(
            f"The area code belongs to {other[0]}, not {province} — could be a ported "
            "cell or a recent move. Confirm on the call."
        )
        return 40, "possible", reasons
    reasons.append("The area code is not one we recognise for this province. Confirm on the call.")
    return 30, "possible", reasons


# ---------------------------------------------------------------------------
# Attempt journal
# ---------------------------------------------------------------------------
def _load_attempts() -> dict[str, Any]:
    if not ATTEMPTS_PATH.exists():
        return {}
    try:
        with open(ATTEMPTS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        # A corrupt journal must not stop a run; it must not silently look empty
        # either, or the next run re-crawls everything believing it is fresh.
        print(f"[warn] attempts journal unreadable at {ATTEMPTS_PATH}; treating as empty", file=sys.stderr)
        return {}


def _save_attempts(state: dict[str, Any]) -> None:
    ATTEMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ATTEMPTS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    tmp.replace(ATTEMPTS_PATH)


def _cell_key(province: str, town: str, icp: str) -> str:
    return f"{province}|{town}|{icp}"


def _recently_attempted(state: dict, key: str, days: int) -> bool:
    rec = state.get(key)
    if not rec:
        return False
    try:
        when = datetime.fromisoformat(rec["at"])
    except Exception:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when < timedelta(days=days)


# ---------------------------------------------------------------------------
# Firecrawl
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# RATE LIMITING
#
# Measured against the live account 2026-09-08: 6 requests/minute, and the API
# says so in the response body rather than in the exit code —
#   "Rate Limit Exceeded ... Consumed (req/min): 6, Remaining (req/min): 0 ...
#    please retry after 19s"
# — delivered with EXIT STATUS 0. So a throttled call and a town with no
# businesses in it are byte-identical to any caller that only checks the exit
# code, which is how a scraper comes to report "0 candidates" for forty towns in
# a row and looks like it merely found nothing. `_run_firecrawl` therefore treats
# an `error` key as failure regardless of exit status, and this bucket keeps us
# under the ceiling instead of discovering it 2,000 times.
# ---------------------------------------------------------------------------
class FirecrawlUnavailable(RuntimeError):
    """The account cannot fetch at all — out of credits, or the key is refused.

    Raised rather than returned so it cannot be mistaken for "this one site did
    not load". It aborts the run at the top level with the provider's own
    sentence, because every candidate processed after it would be recorded as a
    business we looked at and rejected, which is a lie.
    """


_RATE_MIN_INTERVAL = 11.0  # seconds between calls ≈ 5.5/min, just under the cap
_last_call_at = 0.0


def _throttle() -> None:
    global _last_call_at
    wait = _RATE_MIN_INTERVAL - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


_RETRY_AFTER_RE = re.compile(r"retry after (\d+)s", re.I)


def _run_firecrawl(args: list[str], timeout: int = 180, attempts: int = 3) -> dict | None:
    """Invoke the Firecrawl CLI. Returns parsed JSON, or None on any failure.

    Failures are printed, never swallowed — a scraper that silently returns
    nothing looks identical to a town with no businesses in it, and that
    ambiguity is exactly what produces a confident, empty result set.
    """
    import subprocess

    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "integrations" / "firecrawl_tool.py")] + args + ["--json"]
    for attempt in range(1, attempts + 1):
        _throttle()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
                cwd=str(PROJECT_ROOT), creationflags=WINDOWLESS_FLAGS,
            )
        except subprocess.TimeoutExpired:
            print(f"[warn] firecrawl timed out after {timeout}s: {' '.join(args[:2])}", file=sys.stderr)
            return None
        # PARSE STDOUT BEFORE JUDGING THE EXIT CODE. The CLI reports quota and
        # billing failures as {"error": "..."} on STDOUT — sometimes with exit 1
        # and an EMPTY stderr. The original order here printed that empty stderr
        # and returned None, so "Payment Required: Insufficient credits" reached
        # the operator as a blank warning and 29 perfectly good businesses were
        # journalled as `fetch_failed`. A diagnosis this specific must never be
        # thrown away because it arrived on the wrong stream.
        out = (proc.stdout or "").strip()
        payload: dict | None = None
        start = out.find("{")
        if start >= 0:
            try:
                payload = json.loads(out[start:])
            except json.JSONDecodeError:
                payload = None

        err = payload.get("error") if isinstance(payload, dict) else None

        if err is None and proc.returncode != 0:
            detail = (proc.stderr or "").strip() or out[:200] or "(no output)"
            print(f"[warn] firecrawl exit {proc.returncode}: {detail[:200]}", file=sys.stderr)
            return None
        if payload is None:
            return None
        if not err:
            return payload

        # OUT OF CREDITS / UNAUTHORISED is terminal, not retryable. Grinding on
        # would spend hours turning every remaining candidate into a
        # `fetch_failed` row — inventory poisoned with a judgement we never
        # made, and a run that reports "found nothing" when the truth is "was
        # never allowed to look".
        low = str(err).lower()
        if "insufficient credits" in low or "payment required" in low or "unauthorized" in low:
            raise FirecrawlUnavailable(str(err)[:300])

        # An error IN THE BODY, delivered with exit 0. Retry only the throttle;
        # anything else is a real failure and retrying it just burns quota.
        if "rate limit" in str(err).lower():
            m = _RETRY_AFTER_RE.search(str(err))
            backoff = int(m.group(1)) + 2 if m else 30 * attempt
            if attempt < attempts:
                print(f"  [throttled] waiting {backoff}s (attempt {attempt}/{attempts})", file=sys.stderr)
                time.sleep(backoff)
                continue
            print(f"  [throttled] giving up after {attempts} attempts", file=sys.stderr)
            return None
        print(f"[warn] firecrawl error: {str(err)[:200]}", file=sys.stderr)
        return None
    return None


def search_candidates(icp_key: str, town: str, province: str, per_query: int) -> list[dict[str, Any]]:
    """Search every phrasing for this ICP and merge the results by host.

    Merging matters: the same business often appears once as its own site and
    once as a directory listing, and the directory listing frequently carries the
    phone number the site buries in an image.
    """
    icp = ICP_CATALOG[icp_key]
    by_host: dict[str, dict[str, Any]] = {}
    corroborating_phones: dict[str, set[str]] = {}

    for phrasing in icp["queries"]:
        query = f"{phrasing} {town} {PROVINCE_NAMES[province]}"
        # The search verb takes no result-count flag (checked against
        # firecrawl_tool.py's argparse, not assumed) — it returns what it
        # returns and we cap it here. NOTE: a result set arriving exactly at
        # `per_query` is a CEILING, not a count of what exists; nothing below
        # treats it as a measurement of the town.
        res = _run_firecrawl(["search", query])
        if not res:
            continue
        for item in (res.get("web") or res.get("data") or [])[:per_query]:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            title = (item.get("title") or "").strip()
            desc = (item.get("description") or "").strip()
            blob = f"{title} {desc}"

            # Harvest phones from EVERY result, aggregator or not. A number that
            # shows up on both the business's own site and an independent
            # directory is corroborated, which is the difference between the
            # `named` and `verified` tiers on the board.
            ten = _norm_phone(blob)
            if ten:
                for token in re.findall(r"[a-z0-9\-]+", (title + " " + desc).lower()):
                    if len(token) > 3:
                        corroborating_phones.setdefault(token, set()).add(ten)

            if _is_aggregator(url):
                continue
            host = _host(url)
            if not host:
                continue
            if _is_non_icp(title, host):
                continue
            reg = _registrable(host)
            entry = by_host.setdefault(reg, {
                # FETCH THE URL THE SEARCH ENGINE ACTUALLY RETURNED. This used
                # to rebuild it as f"https://{host}" from _host(), which strips
                # a leading "www." — correct for a dedupe key, wrong for a
                # request, because plenty of small-business sites serve only the
                # www host and answer nothing on the bare domain. Measured on
                # the first live run: 29 of 51 candidates (57%) died at
                # fetch_failed, and the rebuilt URL is why. The registrable
                # domain below still does the deduping; these are two different
                # jobs and one string cannot do both.
                "url": url, "host": host, "registrable": reg,
                "title": title, "snippets": [], "search_phone": None,
            })
            entry["snippets"].append(blob[:400])
            if ten and not entry["search_phone"]:
                entry["search_phone"] = ten

    return list(by_host.values())


OWNER_SCHEMA = {
    "type": "object",
    "properties": {
        "business_name": {"type": "string", "description": "The trading name of the business."},
        "owner_full_name": {
            "type": "string",
            "description": (
                "Full name of the owner, founder, principal or named practitioner, "
                "EXACTLY as the page writes it. Empty string if the page names no "
                "specific person. Never infer a name from the business name, never "
                "use a first name from a testimonial or a review, and never use a "
                "staff member who is not presented as an owner or principal."
            ),
        },
        "owner_title": {
            "type": "string",
            "description": "Their stated title, e.g. Owner, Founder, President, Dr. Empty if none.",
        },
        "phone": {"type": "string", "description": "Primary phone number shown on the page."},
        "email": {"type": "string", "description": "Primary contact email if shown."},
        "city": {"type": "string"},
        "province": {"type": "string", "description": "Two-letter code, e.g. ON or BC."},
        "street_address": {"type": "string"},
        "services_summary": {
            "type": "string",
            "description": "One sentence on what they actually do, in the site's own terms.",
        },
        "has_own_website": {
            "type": "boolean",
            "description": "True if this looks like the business's own site rather than a directory listing.",
        },
    },
    "required": ["business_name"],
}


def extract_business(url: str) -> dict[str, Any] | None:
    """Pull owner + contact facts off the business's own site.

    The evidence URL is recorded alongside every owner name so the claim is
    re-checkable later. An owner name with no page that proves it is a guess with
    good posture, and the board's `named` tier is supposed to mean somebody
    verified a human.
    """
    res = _run_firecrawl(["extract", url, "--schema", json.dumps(OWNER_SCHEMA)], timeout=240)
    if not res:
        return None
    data = res.get("data") or res.get("extract") or res
    if not isinstance(data, dict):
        return None
    return data


# Rejected owner-name shapes. The extractor is instructed not to produce these,
# but an instruction is not a gate — a business name landing in owner_name is the
# single most common way this kind of pipeline manufactures a fake person.
_BAD_OWNER_TOKENS = {
    "owner", "founder", "team", "staff", "management", "admin", "info",
    "contact", "office", "reception", "sales", "service", "support",
    "customer", "manager", "director", "n/a", "na", "none", "unknown",
    "the team", "our team", "llc", "inc", "ltd", "company", "corp",
}


def _clean_owner_name(raw: str, business_name: str) -> str | None:
    """Return a plausible PERSON name, or None. Conservative on purpose."""
    name = re.sub(r"\s+", " ", (raw or "")).strip().strip(".,;:-–—")
    if not name:
        return None
    low = name.lower()
    if low in _BAD_OWNER_TOKENS:
        return None
    # A business name echoed back is not an owner. Compared on letters only so
    # "Coastline Auto Detailing Ltd." and "coastline auto detailing" collide.
    def letters(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower())
    if letters(name) and letters(name) == letters(business_name or ""):
        return None
    # Strip a leading honorific but KEEP Dr., which is load-bearing for the
    # chiro / med-spa ICPs where the practitioner is the owner.
    name = re.sub(r"^(?:Mr|Mrs|Ms|Miss)\.?\s+", "", name, flags=re.I).strip()
    parts = [p for p in name.split(" ") if p]
    if not (2 <= len(parts) <= 4):
        return None  # a lone first name cannot be asked for at a switchboard
    if any(p.lower().strip(".") in _BAD_OWNER_TOKENS for p in parts):
        return None
    if not re.match(r"^[A-Za-zÀ-ÿ'’.\- ]+$", name):
        return None
    # Require real capitalisation. NOTE: this is a Python `re` with no
    # IGNORECASE — the JS version of this check silently matched lowercase when
    # /i and /u were combined, which cost APEX a capitalisation anchor.
    if not any(re.match(r"^[A-ZÀ-Þ]", p) for p in parts):
        return None
    return name


def build_lead(
    cand: dict[str, Any],
    extracted: dict[str, Any],
    icp_key: str,
    town: str,
    province: str,
    territory_id: str,
) -> dict[str, Any] | None:
    """Assemble the board row. Returns None when the gate is not cleared."""
    icp = ICP_CATALOG[icp_key]
    business_name = (extracted.get("business_name") or cand.get("title") or "").strip()
    if not business_name:
        return None

    ten = _norm_phone(str(extracted.get("phone") or "")) or cand.get("search_phone")
    if not ten:
        return None  # GATE 1: unreachable is not a lead

    owner = _clean_owner_name(str(extracted.get("owner_full_name") or ""), business_name)
    if not owner:
        return None  # GATE 2: no named owner — stays inventory, see module docstring

    conf, tier, reasons = _phone_confidence(ten, province)
    website = cand["url"]
    email = (extracted.get("email") or "").strip()
    if email and not EMAIL_RE.match(email):
        email = ""

    dedupe = hashlib.md5(
        f"{_registrable(cand['host'])}|{ten}".encode("utf-8")
    ).hexdigest()

    return {
        "name": business_name,
        "business_name": business_name,
        "company": business_name,
        "email": email or None,
        "phone": _pretty_phone(ten),
        "business_address": (extracted.get("street_address") or "").strip() or None,
        "business_city": (extracted.get("city") or town).strip() or town,
        "state": province,
        "business_zip": None,
        "industry": icp["industry"],
        "source": SOURCE,
        "website": website,
        # VERBATIM HONESTY, same contract as the OSM rows: nothing here has run a
        # website audit, so neither field may imply one happened. The rep reads
        # these aloud on a live call.
        "website_condition": "Has a site, not yet reviewed",
        "audit_findings": "Not audited yet - confirm on the call",
        "icp_track": icp["industry"],
        "stage": "researched",
        "status": "researched",
        "tags": ["webdev-outbound", "owner-identified", "small-town-icp", f"icp-{icp_key}"],
        "webdev_opportunity_score": 0,
        "webdev_quality_score": 0,
        "webdev_website_state": "unknown",
        "webdev_reason_codes": [],
        "webdev_email_confidence": 60 if email else 0,
        "webdev_phone_confidence": conf,
        "webdev_consent_basis": None,
        "webdev_consent_evidence_url": None,
        "webdev_dedupe_key": dedupe,
        "webdev_territory_id": territory_id,
        "webdev_territory": f"{town}, {province} - {icp['industry']}",
        "webdev_industry": icp["industry"],
        "webdev_osm_no_website_tag": False,
        "sales_motion": "cold_outbound",
        "webdev_phone_tier": tier,
        "webdev_phone_reasons": reasons,
        "webdev_phone_ext": None,
        "webdev_phone_alternates": [],
        # OWNER EVIDENCE. `self_reported` is the honest state: the name came off
        # the company's own page, which is the company saying so. Only an
        # INDEPENDENT source publishing the same number earns `confirmed`, and
        # nothing in this pipeline does that yet — claiming it here would put
        # leads in the board's top tier on no evidence.
        "owner_name": owner,
        "owner_title": (extracted.get("owner_title") or "").strip() or None,
        "owner_phone": None,
        "owner_source_method": "site_extract:owner_full_name",
        "owner_evidence_url": website,
        "owner_verification_state": "self_reported",
        "owner_enriched_at": _now_iso(),
        "webdev_icp_key": icp_key,
        "webdev_icp_rationale": icp["why"],
        "webdev_services_summary": (extracted.get("services_summary") or "").strip() or None,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def load_seen(db: Any) -> tuple[set[str], set[str]]:
    """Phones and registrable domains already on the board or in inventory.

    Both dimensions, because either one alone lets a duplicate through: two
    listings of the same business under different domains share the phone, and a
    business that changed its number keeps its domain.
    """
    phones: set[str] = set()
    domains: set[str] = set()

    try:
        res = (
            db.from_("tenant_records")
            .select("data")
            .eq("tenant_id", OASIS_TENANT_ID)
            .eq("entity_type", "lead")
            .limit(50000)
            .execute()
        )
        for row in (res.data or []):
            d = row.get("data") or {}
            if isinstance(d, str):
                try:
                    d = json.loads(d)
                except Exception:
                    continue
            ten = _norm_phone(str(d.get("phone") or ""))
            if ten:
                phones.add(ten)
            host = _host(str(d.get("website") or ""))
            if host:
                domains.add(_registrable(host))
    except Exception as e:
        # FAIL LOUD. An empty seen-set silently re-inserts the whole board.
        raise RuntimeError(f"could not load existing leads for dedupe: {e}") from e

    try:
        res = (
            db.from_("leadgen_businesses")
            .select("phone_raw,registrable_domain,source,crm_record_id,owner_lookup_outcome")
            .eq("tenant_id", OASIS_TENANT_ID)
            .limit(200000)
            .execute()
        )
        for row in (res.data or []):
            ten = _norm_phone(str(row.get("phone_raw") or ""))
            if ten:
                phones.add(ten)
            reg = (row.get("registrable_domain") or "").strip().lower()
            if not reg:
                continue
            # A candidate OF OURS that we simply could not fetch is not a
            # business we have judged — it is one we never saw. Excluding it
            # forever turns a transient network failure into a permanent hole in
            # the inventory, which is what the first live run created for 29
            # sites whose URLs we had rebuilt wrongly. `no_owner_found` and
            # `no_phone_found` ARE judgements and stay excluded; so does
            # anything already promoted, and every row from another pipeline.
            if (
                row.get("source") == SOURCE
                and not row.get("crm_record_id")
                and row.get("owner_lookup_outcome") in ("fetch_failed", "provider_unavailable")
            ):
                continue
            domains.add(reg)
    except Exception as e:
        raise RuntimeError(f"could not load existing inventory for dedupe: {e}") from e

    return phones, domains


def ensure_territory(db: Any, town: str, province: str, industry: str, dry: bool) -> str:
    """Find or create the leadgen_territories sheet for this cell.

    THE RAIL IS BUILT FROM THESE SHEETS, NOT FROM THE LEADS (see
    lib/web-leads/queries.ts). An industry with leads but no sheet does not
    appear in the filter rail at all, so this is not bookkeeping — it is the
    difference between a rep being able to select "Auto Detailing" and not.
    """
    import uuid

    if db is not None:
        try:
            res = (
                db.from_("leadgen_territories")
                .select("id")
                .eq("tenant_id", OASIS_TENANT_ID)
                .eq("region", province)
                .eq("locality", town)
                .eq("vertical", industry)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]["id"]
        except Exception as e:
            print(f"[warn] territory lookup failed for {town}/{industry}: {e}", file=sys.stderr)

    tid = str(uuid.uuid4())
    if dry or db is None:
        return tid
    try:
        db.from_("leadgen_territories").insert({
            "id": tid,
            "tenant_id": OASIS_TENANT_ID,
            "country": "CA",
            "region": province,
            "locality": town,
            "vertical": industry,
            # NOT NULL, and the label a rep actually reads on the sheet. Omitting
            # it fails the insert with SQLITE_CONSTRAINT, which this function
            # only warns about — so the sheet is missing, the industry never
            # reaches the filter rail, and the leads underneath it are
            # unreachable through the UI while looking fine in the table.
            # Same shape as the lead's own webdev_territory string.
            "name": f"{town}, {province} - {industry}",
            # It has leads the moment we write one; 'pending' would describe a
            # sheet nobody has scraped yet.
            "status": "ready",
            "leads_total": 0,
            "leads_callable": 0,
            "leads_no_site": 0,
            "leads_callable_no_site": 0,
            "leads_worked": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }).execute()
    except Exception as e:
        print(f"[warn] could not create territory {town}/{industry}: {e}", file=sys.stderr)
    return tid


def bump_territory(db: Any, territory_id: str, added: int, callable_added: int, dry: bool) -> None:
    """Keep the rail's counts in step with what we just wrote.

    Read-modify-write rather than a bare increment because the compat layer has
    no atomic add. This runs once per cell from a single writer, so the race
    window is not real here — if it ever runs concurrently it needs a real
    UPDATE ... SET x = x + n.
    """
    if dry or db is None or added <= 0:
        return
    try:
        res = (
            db.from_("leadgen_territories")
            .select("leads_total,leads_callable")
            .eq("tenant_id", OASIS_TENANT_ID)
            .eq("id", territory_id)
            .limit(1)
            .execute()
        )
        cur = (res.data or [{}])[0]
        db.from_("leadgen_territories").update({
            "leads_total": int(cur.get("leads_total") or 0) + added,
            "leads_callable": int(cur.get("leads_callable") or 0) + callable_added,
            "updated_at": _now_iso(),
        }).eq("tenant_id", OASIS_TENANT_ID).eq("id", territory_id).execute()
    except Exception as e:
        print(f"[warn] territory count bump failed ({territory_id}): {e}", file=sys.stderr)


def write_lead(db: Any, lead: dict[str, Any], cand: dict[str, Any], dry: bool) -> str | None:
    """Write the inventory row and the board row. Returns the board id, or None."""
    import uuid

    business_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())
    if dry or db is None:
        return record_id

    try:
        db.from_("leadgen_businesses").insert({
            "id": business_id,
            "tenant_id": OASIS_TENANT_ID,
            "dedupe_key": lead["webdev_dedupe_key"],
            "name": lead["business_name"],
            "website_url": lead["website"],
            "registrable_domain": _registrable(cand["host"]),
            "phone_raw": lead["phone"],
            "address_line": lead.get("business_address"),
            "locality": lead["business_city"],
            "region": lead["state"],
            "country": "CA",
            "category": lead["webdev_industry"],
            "source": SOURCE,
            "source_ref": cand["url"],
            "website_state": "unknown",
            "crm_record_id": record_id,
            "first_seen_at": _now_iso(),
            "last_seen_at": _now_iso(),
            "updated_at": _now_iso(),
            "territory_id": lead["webdev_territory_id"],
            "owner_name": lead["owner_name"],
            "owner_title": lead.get("owner_title"),
            "owner_evidence_url": lead["owner_evidence_url"],
            "owner_lookup_at": _now_iso(),
            "owner_lookup_outcome": "found",
            "owner_verification_state": lead["owner_verification_state"],
        }).execute()
    except Exception as e:
        print(f"[warn] inventory insert failed for {lead['business_name']}: {e}", file=sys.stderr)

    lead = dict(lead)
    lead["webdev_source_business_id"] = business_id
    try:
        db.from_("tenant_records").insert({
            "id": record_id,
            "tenant_id": OASIS_TENANT_ID,
            "entity_type": "lead",
            "data": json.dumps(lead),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }).execute()
    except Exception as e:
        print(f"[error] board insert FAILED for {lead['business_name']}: {e}", file=sys.stderr)
        return None
    return record_id


def record_miss(db: Any, cand: dict[str, Any], town: str, province: str,
                industry: str, outcome: str, dry: bool) -> None:
    """Hold a candidate that failed the gate, WITH the reason it failed.

    This is 'mark attempted work, not just successful work' at the row level.
    Without it the next run rediscovers the same unreachable business, pays for
    the same extract, and fails the same gate.
    """
    if dry or db is None:
        return
    import uuid
    dedupe = hashlib.md5(cand["registrable"].encode("utf-8")).hexdigest()
    try:
        db.from_("leadgen_businesses").insert({
            "id": str(uuid.uuid4()),
            "tenant_id": OASIS_TENANT_ID,
            "dedupe_key": dedupe,
            "name": (cand.get("title") or cand["host"])[:200],
            "website_url": cand["url"],
            "registrable_domain": cand["registrable"],
            "locality": town,
            "region": province,
            "country": "CA",
            "category": industry,
            "source": SOURCE,
            "source_ref": cand["url"],
            "crm_record_id": None,
            "first_seen_at": _now_iso(),
            "last_seen_at": _now_iso(),
            "updated_at": _now_iso(),
            "owner_lookup_at": _now_iso(),
            "owner_lookup_outcome": outcome,
        }).execute()
    except Exception as e:
        # A domain we have already journalled (this run or a previous one) hits
        # UNIQUE(tenant_id, dedupe_key). That is not an error — the row exists,
        # which is the whole point — but leaving it as a bare warn meant the
        # attempt was NOT re-dated, so a domain seen every week looked freshly
        # attempted only the first time. Refresh it instead.
        if "UNIQUE constraint failed" in str(e):
            try:
                db.from_("leadgen_businesses").update({
                    "last_seen_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "owner_lookup_at": _now_iso(),
                    "owner_lookup_outcome": outcome,
                }).eq("tenant_id", OASIS_TENANT_ID).eq("dedupe_key", dedupe).execute()
            except Exception as e2:
                print(f"[warn] miss refresh failed ({cand['registrable']}): {e2}", file=sys.stderr)
            return
        print(f"[warn] miss record failed ({cand['registrable']}): {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--provinces", default="ON,BC", help="Comma-separated province codes (default ON,BC)")
    ap.add_argument("--towns", default="", help="Restrict to these towns (default: the full small-town list)")
    ap.add_argument("--icp", default="", help=f"Restrict to these ICP keys. Available: {','.join(ICP_CATALOG)}")
    ap.add_argument("--target", type=int, default=200, help="Stop after this many leads clear the gate")
    ap.add_argument("--limit", type=int, default=0, help="Stop after this many (town,icp) cells — for smoke runs")
    ap.add_argument("--per-query", type=int, default=10, help="Search results per phrasing")
    ap.add_argument("--retry-after-days", type=int, default=30, help="Re-attempt a cell only after this many days")
    ap.add_argument("--dry-run", action="store_true", help="Do everything except write to the database")
    ap.add_argument("--plan", action="store_true", help="Print the cells that WOULD run, then exit")
    ap.add_argument("--json", action="store_true", help="Emit a JSON summary")
    args = ap.parse_args()

    provinces = [p.strip().upper() for p in args.provinces.split(",") if p.strip()]
    for p in provinces:
        if p not in TOWNS:
            ap.error(f"unknown province '{p}'. Known: {','.join(TOWNS)}")

    icp_keys = [k.strip() for k in args.icp.split(",") if k.strip()] or list(ICP_CATALOG)
    for k in icp_keys:
        if k not in ICP_CATALOG:
            ap.error(f"unknown icp '{k}'. Known: {','.join(ICP_CATALOG)}")

    town_filter = {t.strip().lower() for t in args.towns.split(",") if t.strip()}

    attempts = _load_attempts()
    cells: list[tuple[str, str, str]] = []
    skipped_recent = 0
    for province in provinces:
        for town in TOWNS[province]:
            if town_filter and town.lower() not in town_filter:
                continue
            for icp_key in icp_keys:
                key = _cell_key(province, town, icp_key)
                if _recently_attempted(attempts, key, args.retry_after_days):
                    skipped_recent += 1
                    continue
                cells.append((province, town, icp_key))

    if args.limit:
        cells = cells[: args.limit]

    if args.plan:
        searches = sum(len(ICP_CATALOG[k]["queries"]) for _, _, k in cells)
        payload = {
            "cells": len(cells),
            "skipped_recently_attempted": skipped_recent,
            "provinces": provinces,
            "icps": [{"key": k, "industry": ICP_CATALOG[k]["industry"]} for k in icp_keys],
            "towns": {
                p: len([t for t in TOWNS[p] if not town_filter or t.lower() in town_filter])
                for p in provinces
            },
            "searches": searches,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"{payload['cells']} cells to run "
                f"({payload['skipped_recently_attempted']} skipped as recently attempted)\n"
                f"provinces={','.join(provinces)}  icps={','.join(icp_keys)}\n"
                f"~{searches} searches"
            )
        return

    # load_env() returns the credential dict WITHOUT pushing it to os.environ,
    # and get_client takes it as its first argument. Nothing here reads, logs or
    # echoes a value out of it.
    db = None if args.dry_run else get_client(load_env(), "bravo")
    seen_phones: set[str] = set()
    seen_domains: set[str] = set()
    if db is not None:
        seen_phones, seen_domains = load_seen(db)
        print(f"[dedupe] {len(seen_phones)} phones / {len(seen_domains)} domains already held")

    written: list[dict[str, Any]] = []
    stats = {"cells": 0, "candidates": 0, "extracted": 0, "gate_no_phone": 0,
             "gate_no_owner": 0, "dupe": 0, "written": 0, "extract_failed": 0}

    for province, town, icp_key in cells:
        if len(written) >= args.target:
            break
        industry = ICP_CATALOG[icp_key]["industry"]
        stats["cells"] += 1
        cell_written = 0
        print(f"\n[{stats['cells']}/{len(cells)}] {town}, {province} — {industry}")

        try:
            candidates = search_candidates(icp_key, town, province, args.per_query)
        except FirecrawlUnavailable:
            raise
        except Exception as e:
            print(f"  [error] search failed: {e}", file=sys.stderr)
            candidates = []
        stats["candidates"] += len(candidates)
        print(f"  {len(candidates)} candidate site(s)")

        territory_id = ensure_territory(db, town, province, industry, args.dry_run)

        for cand in candidates:
            if len(written) >= args.target:
                break
            if cand["registrable"] in seen_domains:
                stats["dupe"] += 1
                continue

            # Whatever happens to this candidate below, we are not paying for it
            # twice in one run. Directory hosts in particular resurface in every
            # ICP for the same town.
            seen_domains.add(cand["registrable"])

            extracted = extract_business(cand["url"])
            if not extracted:
                stats["extract_failed"] += 1
                record_miss(db, cand, town, province, industry, "fetch_failed", args.dry_run)
                continue
            stats["extracted"] += 1

            lead = build_lead(cand, extracted, icp_key, town, province, territory_id)
            if not lead:
                has_phone = bool(_norm_phone(str(extracted.get("phone") or "")) or cand.get("search_phone"))
                if has_phone:
                    stats["gate_no_owner"] += 1
                    record_miss(db, cand, town, province, industry, "no_owner_found", args.dry_run)
                else:
                    stats["gate_no_phone"] += 1
                    record_miss(db, cand, town, province, industry, "no_phone_found", args.dry_run)
                continue

            ten = _norm_phone(lead["phone"]) or ""
            if ten in seen_phones:
                stats["dupe"] += 1
                continue

            rid = write_lead(db, lead, cand, args.dry_run)
            if not rid:
                continue
            seen_phones.add(ten)
            seen_domains.add(cand["registrable"])
            written.append({
                "id": rid, "name": lead["business_name"], "phone": lead["phone"],
                "owner": lead["owner_name"], "city": lead["business_city"],
                "province": province, "industry": industry, "website": lead["website"],
            })
            cell_written += 1
            stats["written"] += 1
            print(f"  + {lead['business_name']} — {lead['owner_name']} — {lead['phone']}")

        bump_territory(db, territory_id, cell_written, cell_written, args.dry_run)

        # JOURNAL THE CELL WHETHER OR NOT IT PRODUCED ANYTHING. A cell that found
        # nothing is a fact worth keeping; re-running it next week costs the same
        # searches and returns the same nothing.
        attempts[_cell_key(province, town, icp_key)] = {
            "at": _now_iso(), "written": cell_written, "candidates": len(candidates),
        }
        if not args.dry_run:
            _save_attempts(attempts)

    summary = {"ok": True, "stats": stats, "leads": written, "dry_run": args.dry_run}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n{'DRY RUN — nothing written' if args.dry_run else 'WROTE ' + str(stats['written']) + ' leads'}")
        print(f"  cells={stats['cells']} candidates={stats['candidates']} extracted={stats['extracted']}")
        print(f"  rejected: no_phone={stats['gate_no_phone']} no_owner={stats['gate_no_owner']} "
              f"dupe={stats['dupe']} extract_failed={stats['extract_failed']}")


if __name__ == "__main__":
    try:
        main()
    except FirecrawlUnavailable as e:
        # Exit LOUD and specific. Every cell completed before this point is
        # already journalled (state/owner_operator_attempts.json is written per
        # cell), so a re-run after the account is topped up resumes rather than
        # restarts.
        print(
            "\n[STOPPED] The fetch provider refused the request, so no further "
            "candidates can be looked at.\n"
            f"  Provider said: {e}\n"
            "  Nothing after this point was judged — the run stopped instead of "
            "recording businesses it never managed to read.\n"
            "  Re-run the same command once credits are restored; completed "
            "cells are skipped automatically.",
            file=sys.stderr,
        )
        sys.exit(2)
