"""Fill in the owner's name on board leads that have a website but nobody named.

WHY THIS IS EXTRACT-ONLY, AND WHY THAT MATTERS
----------------------------------------------
Discovering a NEW lead needs search (find the business) plus extract (read its
site). Enriching one we ALREADY hold needs only the second half: the website is
already on the row. That distinction is what makes this runnable today.

Measured 2026-09-08 against the OASIS board (tenant ef8d389e-…): 1,982 leads,
of which 121 carry a website and a phone but no owner_name. Those 121 are the
entire addressable set, and every one of them needs exactly one extract call.

PROVIDER, AND THE HONEST STATE OF EACH
--------------------------------------
  ScrapeGraph  extract WORKS. Probed live on a real business site and it
               returned "Peter Jamieson / Founder and President / 705-888-3050".
               Its `search` is unreliable on the current plan — the same query
               returned 2 results, then 0, then 0, while still consuming credit
               — but this script never calls search.
  Firecrawl    out of credits: both verbs answer "Payment Required". Kept as the
               fallback so this starts working again by itself when topped up.

The provider descends on ANY failure, not on a matched error string. A fallback
that only fires for the one error message somebody thought of is not a fallback
— the free tier here was once unreachable for exactly that reason.

CREDITS ARE FINITE AND THE RUN SAYS SO. The plan reports remaining credit; this
checks before starting and again as it goes, stops with a reserve intact, and
prints how many leads were left untouched. A run that silently stops early reads
as "there was nothing more to find", which is the failure this whole feature
exists to correct.

WHAT IT WILL NOT WRITE
----------------------
`_clean_owner_name` (shared with owner_operator_scraper.py, imported rather than
copied) rejects a business name echoed back, a bare first name, a title with no
person, and the extractor artifacts already seen in production —
"Administration <Name>", "Principal <Name>", "Province Postal Code". A lead
keeps NO owner rather than gaining a fake one: an empty field reads "find out on
the call", while a wrong name is said out loud to a stranger.

Every write records owner_evidence_url (the page that proved it) and
owner_verification_state='self_reported' — the company's own page saying so.
NOT 'confirmed', which this board reserves for an independent source publishing
the same number, and which nothing here establishes.

Usage:
  python scripts/lead_generation/enrich_owner_names.py --plan
  python scripts/lead_generation/enrich_owner_names.py --dry-run --limit 3
  python scripts/lead_generation/enrich_owner_names.py --limit 100
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "lead_generation"))

from integrations.supabase_tool import get_client, load_env  # noqa: E402
from lib.subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# Shared with the discovery scraper so the two cannot drift into different ideas
# of what a person's name looks like.
from owner_operator_scraper import _clean_owner_name, _norm_phone  # noqa: E402

OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

EXTRACT_PROMPT = (
    "Extract the business name and the full name of the OWNER, founder, principal, "
    "or named practitioner, exactly as this page writes it. Return an empty string "
    "for owner_full_name if the page names no specific person. Never infer a name "
    "from the business name. Never use a name from a testimonial, a review, or a "
    "staff member who is not presented as an owner or principal. Do not include a "
    "job title or a section heading such as 'Administration' or 'Principal' as part "
    "of the name."
)

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_name": {"type": "string"},
        "owner_full_name": {"type": "string"},
        "owner_title": {"type": "string"},
        "phone": {"type": "string"},
        "email": {"type": "string"},
    },
}

# Leave this much credit unspent. A provider that hits zero mid-run starts
# failing every call, and those failures get recorded against leads as though we
# had looked at them and found nobody.
CREDIT_RESERVE = 5


class ProviderExhausted(RuntimeError):
    """A provider refused us for credit/auth reasons — not a fact about a lead.

    Raised rather than returned so it cannot be mistaken for "this one site did
    not load". Every candidate processed after that point would be journalled as
    a business we looked at and found nothing on, which is untrue and which a
    later run then has to unpick.
    """


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(tool: str, args: list[str], timeout: int = 180) -> dict[str, Any] | None:
    """Invoke an integration CLI and return parsed JSON, or None on any failure."""
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "integrations" / tool)] + args + ["--json"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=str(PROJECT_ROOT), creationflags=WINDOWLESS_FLAGS,
        )
    except subprocess.TimeoutExpired:
        print(f"[warn] {tool} timed out after {timeout}s", file=sys.stderr)
        return None
    out = (proc.stdout or "").strip()
    start = out.find("{")
    payload: dict[str, Any] | None = None
    if start >= 0:
        try:
            payload = json.loads(out[start:])
        except json.JSONDecodeError:
            payload = None
    # Parse stdout BEFORE judging the exit code: these CLIs report quota and
    # billing refusals as {"error": ...} on stdout, sometimes with exit 1 and an
    # empty stderr. Judging the code first turns a specific, actionable message
    # into a blank warning.
    if payload is None:
        detail = (proc.stderr or "").strip() or out[:200] or "(no output)"
        print(f"[warn] {tool} exit {proc.returncode}: {detail[:200]}", file=sys.stderr)
        return None
    if payload.get("error") or payload.get("ok") is False:
        err = str(payload.get("error") or "")
        # OUT OF CREDIT / UNAUTHORISED is terminal for that provider, and it is
        # NOT a fact about the lead. The first run here kept going after
        # ScrapeGraph started answering 402 and recorded `fetch_failed` against
        # businesses it was never allowed to read — a judgement we did not make,
        # written to rows a rerun would then have to reconsider. Raised so the
        # caller can stop instead of manufacturing outcomes.
        low = err.lower()
        if "insufficient credits" in low or "payment required" in low or "unauthorized" in low or "402" in low:
            raise ProviderExhausted(f"{tool}: {err[:200]}")
        print(f"[warn] {tool}: {err[:200]}", file=sys.stderr)
        return None
    return payload


def scrapegraph_credits() -> int | None:
    res = _run("scrapegraph_tool.py", ["credits"], timeout=60)
    if not res:
        return None
    remaining = res.get("remaining")
    return int(remaining) if isinstance(remaining, (int, float)) else None


def extract_owner(url: str) -> tuple[dict[str, Any] | None, str]:
    """Read the owner off `url`. Returns (fields, provider) — provider "" on failure.

    ScrapeGraph first because it is the one with credit today; Firecrawl behind
    it so this recovers by itself when that account is topped up. The descent is
    on ANY failure, deliberately: a fallback gated on one recognised error
    message is not a fallback.
    """
    dead: list[str] = []
    try:
        res = _run(
            "scrapegraph_tool.py",
            ["extract", url, "--prompt", EXTRACT_PROMPT, "--schema", json.dumps(EXTRACT_SCHEMA)],
            timeout=240,
        )
        if res:
            fields = res.get("json") or res.get("result")
            if isinstance(fields, dict):
                return fields, "scrapegraph"
    except ProviderExhausted as e:
        dead.append(str(e))

    try:
        res = _run(
            "firecrawl_tool.py",
            ["extract", url, "--schema", json.dumps(EXTRACT_SCHEMA)],
            timeout=240,
        )
        if res:
            fields = res.get("data") or res.get("extract")
            if isinstance(fields, dict):
                return fields, "firecrawl"
    except ProviderExhausted as e:
        dead.append(str(e))

    # EVERY provider refused us on billing/auth. There is nothing left that can
    # read a page, so the run must stop rather than journal outcomes it did not
    # observe. One provider down is fine — that is what the descent is for.
    if len(dead) == 2:
        raise ProviderExhausted(" | ".join(dead))
    return None, ""


def load_candidates(db: Any, limit: int) -> list[dict[str, Any]]:
    """Board leads with a website and a phone but nobody named.

    Filtered in Python rather than SQL because the fields live inside a JSON blob
    and the compat client has no json_extract predicate; the row count here is
    ~2,000, so this costs nothing.
    """
    res = (
        db.from_("tenant_records")
        .select("id,data")
        .eq("tenant_id", OASIS_TENANT_ID)
        .eq("entity_type", "lead")
        .limit(50000)
        .execute()
    )
    out: list[dict[str, Any]] = []
    for row in (res.data or []):
        d = row.get("data") or {}
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                continue
        if str(d.get("owner_name") or "").strip():
            continue
        website = str(d.get("website") or "").strip()
        if not website:
            continue
        if not str(d.get("phone") or "").strip():
            continue
        # `no_owner_found` is a JUDGEMENT — we read the page and it named
        # nobody — so it is terminal and we do not pay for it twice.
        #
        # `fetch_failed` is NOT a judgement. It means we never got to look, and
        # the cause is usually transient or ours: a 502, a timeout, or the
        # provider refusing us because credit ran out mid-run. Treating it as
        # terminal is how a billing outage turns into a permanent hole in the
        # inventory — 25 leads were marked that way on the first run here, most
        # of them for exactly that reason. Retryable, deliberately.
        if str(d.get("owner_lookup_outcome") or "").strip() == "no_owner_found":
            continue
        out.append({"id": row["id"], "data": d, "website": website})
        if len(out) >= limit:
            break
    return out


def write_owner(db: Any, lead_id: str, data: dict[str, Any], patch: dict[str, Any], dry: bool) -> bool:
    if dry:
        return True
    merged = dict(data)
    merged.update(patch)
    try:
        db.from_("tenant_records").update(
            {"data": json.dumps(merged), "updated_at": _now_iso()}
        ).eq("tenant_id", OASIS_TENANT_ID).eq("id", lead_id).execute()
        return True
    except Exception as e:
        print(f"[error] write failed for {lead_id}: {e}", file=sys.stderr)
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=200, help="Maximum leads to attempt this run")
    ap.add_argument("--dry-run", action="store_true", help="Do everything except write")
    ap.add_argument("--plan", action="store_true", help="Report what would run, then exit")
    ap.add_argument("--json", action="store_true", help="Emit a JSON summary")
    args = ap.parse_args()

    db = get_client(load_env(), "bravo")
    candidates = load_candidates(db, args.limit)
    credits = scrapegraph_credits()

    if args.plan:
        payload = {
            "candidates": len(candidates),
            "scrapegraph_credits_remaining": credits,
            "reserve": CREDIT_RESERVE,
            "affordable_now": None if credits is None else max(0, credits - CREDIT_RESERVE),
        }
        print(json.dumps(payload, indent=2) if args.json else
              f"{payload['candidates']} leads have a website and a phone but no owner name.\n"
              f"ScrapeGraph credits remaining: {credits}  (reserve {CREDIT_RESERVE})\n"
              f"Affordable this run: {payload['affordable_now']}")
        return

    print(f"[start] {len(candidates)} candidate(s); scrapegraph credits: {credits}")
    stats = {"attempted": 0, "named": 0, "no_owner": 0, "fetch_failed": 0,
             "stopped_low_credit": False, "by_provider": {}}
    named: list[dict[str, str]] = []

    for lead in candidates:
        if credits is not None and credits <= CREDIT_RESERVE:
            stats["stopped_low_credit"] = True
            print(f"[stop] credit reserve reached ({credits} left).", file=sys.stderr)
            break

        stats["attempted"] += 1
        fields, provider = extract_owner(lead["website"])
        if credits is not None:
            credits -= 1

        if not fields:
            stats["fetch_failed"] += 1
            write_owner(db, lead["id"], lead["data"], {
                "owner_lookup_at": _now_iso(),
                "owner_lookup_outcome": "fetch_failed",
            }, args.dry_run)
            continue

        stats["by_provider"][provider] = stats["by_provider"].get(provider, 0) + 1
        business = str(fields.get("business_name") or lead["data"].get("company") or "")
        owner = _clean_owner_name(str(fields.get("owner_full_name") or ""), business)

        if not owner:
            stats["no_owner"] += 1
            write_owner(db, lead["id"], lead["data"], {
                "owner_lookup_at": _now_iso(),
                "owner_lookup_outcome": "no_owner_found",
            }, args.dry_run)
            continue

        patch: dict[str, Any] = {
            "owner_name": owner,
            "owner_title": (str(fields.get("owner_title") or "").strip() or None),
            # The company's own page saying so. NOT 'confirmed' — this board
            # reserves that for an independent source publishing the same
            # number, which nothing here establishes.
            "owner_verification_state": "self_reported",
            "owner_evidence_url": lead["website"],
            "owner_source_method": f"{provider}_extract:owner_full_name",
            "owner_enriched_at": _now_iso(),
            "owner_lookup_at": _now_iso(),
            "owner_lookup_outcome": "found",
        }
        # A phone the page publishes, only when the lead has none. Never
        # overwrite the number a rep may already have dialled.
        page_phone = _norm_phone(str(fields.get("phone") or ""))
        if page_phone and not str(lead["data"].get("phone") or "").strip():
            patch["phone"] = f"({page_phone[:3]}) {page_phone[3:6]}-{page_phone[6:]}"

        if write_owner(db, lead["id"], lead["data"], patch, args.dry_run):
            stats["named"] += 1
            named.append({
                "id": lead["id"],
                "company": str(lead["data"].get("company") or ""),
                "owner": owner,
                "title": str(patch.get("owner_title") or ""),
                "provider": provider,
            })
            print(f"  + {business[:40]:42} -> {owner} ({provider})")

    remaining = len(candidates) - stats["attempted"]
    summary = {"ok": True, "stats": stats, "named": named,
               "credits_left": credits, "candidates_untouched": remaining,
               "dry_run": args.dry_run}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n{'DRY RUN — nothing written' if args.dry_run else 'WROTE ' + str(stats['named']) + ' owner names'}")
        print(f"  attempted={stats['attempted']} named={stats['named']} "
              f"no_owner={stats['no_owner']} fetch_failed={stats['fetch_failed']}")
        print(f"  providers: {stats['by_provider'] or '(none)'}   credits left: {credits}")
        # NEVER let a capped run read as a finished one.
        if remaining > 0:
            why = "credit reserve" if stats["stopped_low_credit"] else "--limit"
            print(f"  {remaining} candidate(s) NOT attempted (stopped by {why}) — rerun to continue.")


if __name__ == "__main__":
    try:
        main()
    except ProviderExhausted as e:
        print(
            "\n[STOPPED] Every fetch provider refused us, so nothing further could be read.\n"
            f"  {e}\n"
            "  Leads after this point were NOT marked — an outcome we did not observe is\n"
            "  not recorded. Top up and re-run; `fetch_failed` rows are retried, only\n"
            "  `no_owner_found` (a page we read that named nobody) is skipped.",
            file=sys.stderr,
        )
        sys.exit(2)
