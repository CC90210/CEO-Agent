"""enrich_oasis_leads.py — fill missing phone + first name on OASIS leads.

Walks tenant_records for the OASIS tenant looking for active leads
(non-archived, non-lost) where data.name is empty OR data.phone is null,
scrapes the lead's website via Firecrawl, and asks Claude Haiku to pull
out a primary contact + phone. Writes back to tenant_records.data.

Idempotent: each enriched lead gets data.enrichment_run_at stamped so
a second pass skips already-touched rows unless --force.

Usage:
    python scripts/enrich_oasis_leads.py audit            # count, no writes
    python scripts/enrich_oasis_leads.py run --limit 5    # smoke test
    python scripts/enrich_oasis_leads.py run --limit 100  # full pass
    python scripts/enrich_oasis_leads.py run --id <uuid>  # one lead
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "lib"))

from secret_loader import load_env  # type: ignore  # noqa: E402

OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
SKIP_STAGES = {"archived", "lost"}

EXTRACTION_PROMPT = """\
You are looking at a single page of a small business's website. Find the
primary contact's first name + last name + title, plus the main phone
number to reach them.

Return STRICT JSON only, matching this schema:
{
  "first_name": string | null,
  "last_name": string | null,
  "title": string | null,
  "phone": string | null,
  "confidence": "high" | "medium" | "low",
  "notes": string
}

Rules:
- first_name MUST be a real person's first name. NEVER use "info", "team",
  "contact", "support", "admin", "hello" or other mailbox handles.
- phone format: digits + dashes (e.g. 905-528-9167). Strip extensions.
- If multiple people are listed, prefer the owner / founder / president.
- confidence "high" only when both name AND phone come from clearly
  labelled contact text (not OCR'd from an image, not guessed).
- confidence "low" when only one field is filled or the source is
  ambiguous. Return all-nulls + confidence "low" rather than guessing.
- "notes" is one short sentence: where on the page you found the info.

WEBSITE CONTENT BELOW
=====================
{markdown}
"""


def _supabase():
    env = load_env()
    from supabase import create_client
    url = env.get("BRAVO_SUPABASE_URL")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("missing BRAVO_SUPABASE_URL / BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def _research_fetcher():
    """Use the canonical research_fetch ladder (Firecrawl → CloakBrowser
    with auto-escalation + site-reputation memory). When Firecrawl is
    out of credits or hit by Cloudflare, it falls through to stealth
    Chromium without the caller having to know."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from research_fetch import fetch  # type: ignore
    return fetch


def _anthropic():
    env = load_env()
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("missing ANTHROPIC_API_KEY")
    from anthropic import Anthropic  # type: ignore
    return Anthropic(api_key=key)


def _domain_from_lead(data: dict) -> Optional[str]:
    """Pick the best URL to scrape. Notes sometimes carry a Website: line
    from the original Firecrawl scrape; prefer that over the email domain."""
    notes = (data.get("notes") or "")
    m = re.search(r"Website:\s*(https?://\S+)", notes, re.IGNORECASE)
    if m:
        return m.group(1).rstrip(" ,;|")
    if data.get("website"):
        url = str(data["website"]).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url
    email = data.get("email") or ""
    if "@" in email:
        domain = email.split("@", 1)[1].strip()
        if domain and "." in domain:
            return f"https://{domain}"
    return None


def _looks_like_real_first_name(value: Optional[str]) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    if not v:
        return False
    bad = {"info", "team", "contact", "support", "admin", "hello", "office",
           "sales", "service", "the", "thank", "we", "our"}
    if v in bad:
        return False
    return bool(re.match(r"^[a-z][a-z'\-]+$", v))


def _format_phone(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return value.strip() or None
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def _list_candidates(client, only_id: Optional[str]) -> list[dict]:
    q = client.table("tenant_records").select("id,data,updated_at,created_at")
    q = q.eq("tenant_id", OASIS_TENANT_ID).eq("entity_type", "lead").limit(500)
    rows = q.execute().data or []
    out: list[dict] = []
    for row in rows:
        if only_id and row["id"] != only_id:
            continue
        d = row.get("data") or {}
        if d.get("stage") in SKIP_STAGES:
            continue
        has_phone = bool(d.get("phone"))
        has_name = _looks_like_real_first_name(d.get("name"))
        if has_phone and has_name:
            continue
        out.append(row)
    return out


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)


def _scrape_plain(url: str) -> Optional[str]:
    """Last-ditch fallback when research_fetch tiers are unavailable.
    A UA-spoofed urllib GET + naive HTML→text strip. Won't bypass
    Cloudflare but works for the small-business sites that make up
    the OASIS cold-list."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(2_000_000)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"  [scrape-plain] {url}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"  [scrape-plain] {url}: {exc}", file=sys.stderr)
        return None
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) > 200 else None


def _scrape(fetch_fn, url: str) -> Optional[str]:
    # Tier 1: canonical research_fetch ladder (Firecrawl → CloakBrowser).
    try:
        res = fetch_fn(url)
        if res.get("ok"):
            text = res.get("text") or ""
            if text.strip():
                return text
    except Exception as exc:  # noqa: BLE001
        print(f"  [scrape] {url} ladder threw: {exc}", file=sys.stderr)
        res = {}
    # Tier 2: plain UA-spoofed urllib for sites the ladder can't hit
    # (Firecrawl out-of-credits / Cloak not installed locally).
    if not res.get("ok"):
        tiers = res.get("tiers_tried") or []
        errs = res.get("errors") or {}
        last_err = next(iter(errs.values()), "unknown") if errs else "ladder unavailable"
        print(
            f"  [scrape] {url} ladder ({','.join(tiers) or 'none'}) failed: {last_err.strip()[:120]}",
            file=sys.stderr,
        )
    return _scrape_plain(url)


def _ask_claude(client, markdown: str) -> Optional[dict]:
    if len(markdown) > 12000:
        markdown = markdown[:12000]
    prompt = EXTRACTION_PROMPT.replace("{markdown}", markdown)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  [claude] call failed: {exc}", file=sys.stderr)
        return None
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _merge(existing: dict, extracted: dict) -> tuple[dict, list[str]]:
    """Build the new data dict; return (new_data, changed_fields)."""
    new_data = dict(existing)
    changed: list[str] = []
    fn = (extracted.get("first_name") or "").strip() if extracted else ""
    ln = (extracted.get("last_name") or "").strip() if extracted else ""
    phone = _format_phone(extracted.get("phone") if extracted else None)

    if _looks_like_real_first_name(fn) and not _looks_like_real_first_name(existing.get("name")):
        full = f"{fn} {ln}".strip() if ln else fn
        new_data["name"] = full
        changed.append(f"name={full}")
    if phone and not existing.get("phone"):
        new_data["phone"] = phone
        changed.append(f"phone={phone}")
    title = (extracted.get("title") or "").strip() if extracted else ""
    if title and not existing.get("title"):
        new_data["title"] = title
        changed.append(f"title={title}")
    confidence = (extracted.get("confidence") if extracted else None) or "low"
    new_data["enrichment_confidence"] = confidence
    new_data["enrichment_run_at"] = _now_iso()
    return new_data, changed


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def cmd_audit(args: argparse.Namespace) -> int:
    sb = _supabase()
    cands = _list_candidates(sb, args.id)
    print(f"OASIS leads needing enrichment: {len(cands)}")
    from collections import Counter
    by_stage = Counter((c["data"] or {}).get("stage", "?") for c in cands)
    for stage, n in by_stage.most_common():
        print(f"  {stage:<14} {n:>4}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    sb = _supabase()
    fetch_fn = _research_fetcher()
    cl = _anthropic()
    cands = _list_candidates(sb, args.id)
    if args.limit:
        cands = cands[: args.limit]
    if not cands:
        print("nothing to enrich.")
        return 0
    print(f"enriching {len(cands)} lead(s) ...")
    summary = {"updated": 0, "skipped_no_url": 0, "skipped_no_md": 0,
               "skipped_no_extract": 0, "no_change": 0}
    for i, row in enumerate(cands, 1):
        rid = row["id"]
        d = row.get("data") or {}
        # Honor a prior pass unless --force
        if not args.force and d.get("enrichment_run_at"):
            print(f"[{i}/{len(cands)}] {rid[:8]} skip — already enriched (--force to retry)")
            continue
        url = _domain_from_lead(d)
        if not url:
            print(f"[{i}/{len(cands)}] {rid[:8]} skip — no URL resolvable")
            summary["skipped_no_url"] += 1
            continue
        print(f"[{i}/{len(cands)}] {rid[:8]} -> {url}")
        md = _scrape(fetch_fn, url)
        if not md:
            summary["skipped_no_md"] += 1
            continue
        extracted = _ask_claude(cl, md)
        if not extracted:
            summary["skipped_no_extract"] += 1
            continue
        new_data, changed = _merge(d, extracted)
        if not changed:
            # Still stamp enrichment_run_at so we don't re-fetch next pass.
            summary["no_change"] += 1
            print(f"   no new fields (conf={new_data.get('enrichment_confidence')})")
        else:
            print(f"   {' '.join(changed)} (conf={new_data.get('enrichment_confidence')})")
            summary["updated"] += 1
        if not args.dry_run:
            sb.table("tenant_records").update({"data": new_data}).eq("id", rid).execute()
        if i < len(cands):
            time.sleep(args.delay)
    print()
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="OASIS lead enrichment via Firecrawl + Claude")
    sub = p.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("audit", help="count candidates, no writes")
    pa.add_argument("--id", help="single lead UUID")
    pa.set_defaults(func=cmd_audit)
    pr = sub.add_parser("run", help="scrape + enrich")
    pr.add_argument("--limit", type=int, help="cap N leads")
    pr.add_argument("--id", help="single lead UUID")
    pr.add_argument("--delay", type=float, default=1.5, help="seconds between leads")
    pr.add_argument("--dry-run", action="store_true", help="don't write")
    pr.add_argument("--force", action="store_true", help="re-enrich previously enriched")
    pr.set_defaults(func=cmd_run)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
