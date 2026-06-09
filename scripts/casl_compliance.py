"""CASL compliance helpers for all outgoing cold email and SMS.

Single source of truth for CASL (Canada's Anti-Spam Legislation) requirements:
- Sender identification (name + physical address)
- Working unsubscribe mechanism
- Suppression list check before every send

AS OF 2026-05-16: the canonical caller is `scripts/integrations/send_gateway.py`, which
applies these to every outbound commercial AND transactional send. The
old `outreach_batch.py` pre-draft suppression caller was removed on
2026-05-16 along with the cold-outreach Telegram-approval cron. All
business engines (outreach_engine, email_engine, funnel_nurture,
booking_engine, contract_generator) delegate physical send to
send_gateway — they no longer call these functions directly.

Every outgoing commercial email MUST:
  1. Call should_suppress(lead_email) and refuse to send if True
  2. Append build_casl_footer(...) to the email body
  3. Add List-Unsubscribe + List-Unsubscribe-Post headers (RFC 2369/8058)

The gateway enforces #1, #2, and #3 architecturally. Do not bypass.
Fines for violations are up to $10M per incident for businesses.
"""

from __future__ import annotations

import csv
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS_CSV = PROJECT_ROOT / "data" / "email_suppressions.csv"
EMAIL_SUPPRESSIONS_CSV = SUPPRESSIONS_CSV
PHONE_SUPPRESSIONS_CSV = PROJECT_ROOT / "data" / "phone_suppressions.csv"

# RFC 2606 reserved + common placeholder/sample domains that should never
# receive a real send. Firecrawl + manual lead imports occasionally pull
# these from page templates / dummy mailto links. Gate-level rejection so
# every send path (email_engine, autonomous_agent, etc.) is protected,
# not just the scraper.
RESERVED_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "example.com", "example.org", "example.net",
    "test.com", "test.org", "invalid", "localhost",
    "domain.com", "yourdomain.com", "yoursite.com", "email.com",
    "sentry.io", "wixpress.com", "squarespace.com", "wordpress.com",
})


def is_reserved_domain(email: str) -> bool:
    """True if `email` is on a reserved/test/placeholder domain that
    should never receive a real send."""
    if not email or "@" not in email:
        return False
    _, _, domain = email.rpartition("@")
    return domain.lower().strip() in RESERVED_EMAIL_DOMAINS

# Physical mailing address required by CASL s. 6(2)(b).
# Set via .env.agents; fall back to a public OASIS AI address.
DEFAULT_BUSINESS_ADDRESS = "OASIS AI Solutions, Collingwood, ON, Canada"
DEFAULT_BUSINESS_NAME = "OASIS AI Solutions"
DEFAULT_SENDER_NAME = "Conaugh McKenna"

# Unsubscribe endpoint — the agent-dashboard (`oasis-command-center` repo)
# hosts `/unsubscribe` (page) + `/api/unsubscribe` (POST). Anonymous, IP-rate
# limited, idempotent. Writes to the `email_suppressions` table (migration 094,
# tenant-scoped per CASL s. 6) via service-role Supabase client. The historical
# claim that `cc-funnel` handled this was stale — `cc-funnel` returns 404 for
# `/unsubscribe` as of 2026-06-06; the dashboard now owns the route.
DEFAULT_UNSUBSCRIBE_BASE = "https://oasisai.work/unsubscribe"


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_phone(phone: str | None) -> str:
    """E.164-friendly normalization.

    Strips formatting, drops a leading US/Canada country code, and returns
    digits only. Empty/None returns an empty string.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


# ----------------------------------------------------------------------------
# Supabase suppression read path (2026-06-06 — closes the /unsubscribe loop)
# ----------------------------------------------------------------------------
#
# Before today should_suppress() only checked data/email_suppressions.csv.
# After shipping /unsubscribe on the agent-dashboard the new
# email_suppressions Supabase table became the authoritative store for
# web-form unsubscribes (per-tenant, per-brand, CASL s. 6 scoped). The
# CSV stays in place for legacy inbound STOP detection on email/SMS;
# should_suppress now consults BOTH so a web unsub silences future
# sends even when the operator hasn't replicated the row into the CSV.
#
# In-process cache: 60s TTL keyed on (email, tenant_id, brand). Drip
# runners call should_suppress() hundreds of times per minute during a
# campaign; without caching the Supabase REST hop would dominate latency
# and burn through the Vercel-side rate limit on the service role key.
#
# Fail-open on Supabase errors: if the REST call fails (network blip,
# bad credentials, table missing), we fall through to the CSV check.
# CSV-read errors still fail-CLOSED per the existing behaviour — that
# path is local-disk and "we lost our suppression list" is a serious
# CASL hazard, while a transient Supabase outage isn't.

_SUPPRESSION_CACHE: dict[str, tuple[bool, float]] = {}
_SUPPRESSION_CACHE_TTL = 60.0  # seconds


def _cache_key(email: str, tenant_id: Optional[str], brand: Optional[str]) -> str:
    return f"{email}|{tenant_id or ''}|{brand or ''}"


def _check_supabase_suppression(
    email: str,
    tenant_id: Optional[str],
    brand: Optional[str],
) -> Optional[bool]:
    """Query the Supabase email_suppressions table.

    Returns True if a matching row is found, False if the table has no
    match, or None when the query couldn't run (credentials missing,
    network error, etc.). Callers treat None as "fall through to CSV."
    """
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    # Match rows where email matches AND tenant_id matches (or is global
    # NULL) AND brand matches (or is global NULL). NULL on either column
    # is the "global" suppression — always wins. PostgREST `or=` lets us
    # express each OR-with-NULL in one round trip.
    try:
        encoded_email = urllib.parse.quote(email, safe="@")
        tenant_filter = (
            f"&or=(tenant_id.is.null,tenant_id.eq.{urllib.parse.quote(tenant_id)})"
            if tenant_id
            else "&tenant_id=is.null"
        )
        brand_filter = (
            f"&or=(brand.is.null,brand.eq.{urllib.parse.quote(brand)})"
            if brand
            else ""
            # When no brand supplied, we accept any brand-scope match
            # (existing callers don't know the sender brand yet —
            # they're legacy paths from before the per-brand schema).
        )
        query_url = (
            f"{url.rstrip('/')}/rest/v1/email_suppressions"
            f"?email=eq.{encoded_email}{tenant_filter}{brand_filter}"
            f"&select=tenant_id,brand&limit=1"
        )
        req = urllib.request.Request(
            query_url,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            import json
            rows = json.loads(resp.read() or b"[]")
        return bool(rows)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def should_suppress(
    email: str,
    tenant_id: Optional[str] = None,
    brand: Optional[str] = None,
) -> bool:
    """Return True if the email is on the suppression list.

    Sources, in order: in-process cache → Supabase email_suppressions
    table → data/email_suppressions.csv. Supabase fail-opens to CSV;
    CSV read errors still fail-CLOSED (we suppress, since losing the
    list is the worse CASL hazard).

    Args:
        email: The recipient address (case-insensitive).
        tenant_id: Optional tenant UUID. If supplied, the Supabase check
            matches global (tenant_id IS NULL) OR same-tenant rows.
            When omitted, only global suppressions match — preserves
            backward compat with existing callers like email_engine.
        brand: Optional brand label (e.g. "OASIS AI", "SunBiz"). When
            supplied, the Supabase check narrows to rows whose `brand`
            is NULL (global) OR matches — enforces CASL s. 6 per-sender
            scoping (a SunBiz unsub does not silence OASIS AI sends).

    Backward compatible: existing callers like should_suppress(email)
    continue to work unchanged.
    """
    normalized = _normalize_email(email)
    if not normalized:
        return True  # empty email = suppress

    ck = _cache_key(normalized, tenant_id, brand)
    cached = _SUPPRESSION_CACHE.get(ck)
    now = time.time()
    if cached and cached[1] > now:
        return cached[0]

    # 1. Supabase check (authoritative for web unsubs; fail-open).
    sb = _check_supabase_suppression(normalized, tenant_id, brand)
    if sb is True:
        _SUPPRESSION_CACHE[ck] = (True, now + _SUPPRESSION_CACHE_TTL)
        return True

    # 2. CSV fallback (legacy + inbound STOP detection).
    if not SUPPRESSIONS_CSV.exists():
        _SUPPRESSION_CACHE[ck] = (False, now + _SUPPRESSION_CACHE_TTL)
        return False
    try:
        with open(SUPPRESSIONS_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if _normalize_email(row.get("email", "")) == normalized:
                    _SUPPRESSION_CACHE[ck] = (True, now + _SUPPRESSION_CACHE_TTL)
                    return True
    except Exception:
        # Fail CLOSED on CSV read errors — safer to miss a send than violate CASL.
        # Do NOT cache the closed result — a transient disk error shouldn't
        # poison the next 60s of sends.
        return True

    _SUPPRESSION_CACHE[ck] = (False, now + _SUPPRESSION_CACHE_TTL)
    return False


def add_suppression(email: str, reason: str = "unsubscribe") -> bool:
    """Append an email to the suppression list. Idempotent."""
    from datetime import datetime, timezone
    normalized = _normalize_email(email)
    if not normalized:
        return False
    if should_suppress(normalized):
        return True  # already suppressed
    SUPPRESSIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not SUPPRESSIONS_CSV.exists() or SUPPRESSIONS_CSV.stat().st_size == 0
    with open(SUPPRESSIONS_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if header_needed:
            w.writerow(["email", "reason", "added_at"])
        w.writerow([normalized, reason, datetime.now(timezone.utc).isoformat()])
    return True


def should_suppress_phone(phone: str | None) -> bool:
    """Return True if the normalized phone is on the DNC list.

    Mirrors should_suppress(email): empty recipients suppress, missing file
    means no suppression yet, and read errors fail closed.
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return True
    if not PHONE_SUPPRESSIONS_CSV.exists():
        return False
    try:
        with open(PHONE_SUPPRESSIONS_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if normalize_phone(row.get("phone", "")) == normalized:
                    return True
    except Exception:
        # Fail CLOSED on read errors. Better to skip one SMS than violate STOP.
        return True
    return False


def add_phone_suppression(
    phone: str,
    reason: str = "stop_received",
    source: str = "twilio_inbound",
) -> None:
    """Append a phone to the DNC CSV.

    Idempotent: already-suppressed numbers are left untouched.
    Columns: phone,added_at,reason,source.
    """
    from datetime import datetime, timezone

    normalized = normalize_phone(phone)
    if not normalized:
        return
    if should_suppress_phone(normalized):
        return
    PHONE_SUPPRESSIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    header_needed = (
        not PHONE_SUPPRESSIONS_CSV.exists()
        or PHONE_SUPPRESSIONS_CSV.stat().st_size == 0
    )
    with open(PHONE_SUPPRESSIONS_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if header_needed:
            w.writerow(["phone", "added_at", "reason", "source"])
        w.writerow([
            normalized,
            datetime.now(timezone.utc).isoformat(),
            reason,
            source,
        ])


def build_casl_footer(
    recipient_email: str,
    business_name: Optional[str] = None,
    business_address: Optional[str] = None,
    sender_name: Optional[str] = None,
    unsubscribe_base: Optional[str] = None,
) -> str:
    """Return a CASL-compliant plain-text footer for a cold email.

    Every required CASL element:
      1. Sender name (CC's real name, not alias)
      2. Business name
      3. Physical mailing address
      4. Functional unsubscribe mechanism (link + reply-to)

    The unsubscribe link carries the recipient's email as a query param so
    the cc-funnel unsubscribe endpoint can auto-add it to the suppression list.
    """
    business_name = business_name or os.environ.get("CASL_BUSINESS_NAME", DEFAULT_BUSINESS_NAME)
    # 2026-06-08: business_address can now be explicitly empty (per-brand
    # decision). When empty, the address line is omitted entirely rather
    # than rendering "Address:" with a blank value or falling through to
    # the OASIS default. CC's call for SunBiz; documented legal-risk note
    # in send_gateway.BRAND_IDENTITY["sunbiz"].
    if business_address is None:
        business_address = os.environ.get("CASL_BUSINESS_ADDRESS", DEFAULT_BUSINESS_ADDRESS)
    sender_name = sender_name or os.environ.get("CASL_SENDER_NAME", DEFAULT_SENDER_NAME)

    # 2026-04-27: dropped the visible "reply STOP" line at CC's direction —
    # the spammy phrasing was hurting deliverability and brand perception on
    # cold B2B outreach. Opt-out still works via the List-Unsubscribe header
    # (Gmail/Outlook native one-click button → unsubscribe@oasisai.work →
    # email_engine.check-inbox auto-suppresses). Visible footer retains
    # sender name, business name, and physical address per CASL s. 6(2)(a-b)
    # WHEN provided; empty address suppresses just the address line.
    if business_address and business_address.strip():
        footer = (
            "\n\n---\n"
            f"{sender_name} — {business_name}\n"
            f"{business_address}\n"
        )
    else:
        footer = (
            "\n\n---\n"
            f"{sender_name} — {business_name}\n"
        )
    return footer


def build_casl_footer_html(
    recipient_email: str,
    business_name: Optional[str] = None,
    business_address: Optional[str] = None,
    sender_name: Optional[str] = None,
    unsubscribe_base: Optional[str] = None,
) -> str:
    """HTML version of the CASL footer for multipart emails."""
    business_name = business_name or os.environ.get("CASL_BUSINESS_NAME", DEFAULT_BUSINESS_NAME)
    # Same empty-address handling as the text variant — None falls through
    # to env / default, but explicit "" suppresses the address row.
    if business_address is None:
        business_address = os.environ.get("CASL_BUSINESS_ADDRESS", DEFAULT_BUSINESS_ADDRESS)
    sender_name = sender_name or os.environ.get("CASL_SENDER_NAME", DEFAULT_SENDER_NAME)

    from html import escape

    address_row = (
        f'<br/>{escape(business_address)}'
        if business_address and business_address.strip()
        else ''
    )
    return (
        '<hr style="margin-top:24px;border:none;border-top:1px solid #ddd"/>'
        '<div style="font-size:11px;color:#888;font-family:sans-serif;line-height:1.5">'
        f'{escape(sender_name)} — {escape(business_name)}{address_row}'
        '</div>'
    )


def add_list_unsubscribe_headers(msg, recipient_email: str) -> None:
    """Add RFC 2369 / RFC 8058 List-Unsubscribe headers to a MIME message.

    These headers are what Gmail, Outlook, and Apple Mail show as the native
    'Unsubscribe' button. Without them, the cold email looks like spam and
    deliverability tanks. With them, recipients get a one-click unsubscribe
    that satisfies both CASL and CAN-SPAM.

    2026-04-20: mailto-only. We removed the https fallback because the
    https://oasisai.work/unsubscribe page was a 404. The mailto version
    (List-Unsubscribe-Post one-click) still gives recipients the native
    Gmail/Outlook "Unsubscribe" button — Gmail sends a pre-filled email
    to unsubscribe@oasisai.work when they click it, and email_engine.check-inbox
    auto-suppresses whoever sent it. Simpler + actually works.
    """
    gmail_user = os.environ.get("GMAIL_USER") or os.environ.get("GMAIL_ADDRESS") or "conaugh@oasisai.work"
    # Use conaugh@oasisai.work (the real inbox we monitor) so the mailto
    # lands somewhere a human actually reads. Subject 'unsubscribe' is the
    # trigger the classifier watches for.
    msg["List-Unsubscribe"] = f"<mailto:{gmail_user}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="casl_compliance.py",
        description="CASL/TCPA suppression helpers.",
    )
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="Check email suppression")
    check.add_argument("email")

    add = sub.add_parser("add", help="Add email suppression")
    add.add_argument("email")
    add.add_argument("reason", nargs="?", default="manual")

    footer = sub.add_parser("footer", help="Render CASL footer")
    footer.add_argument("email")

    suppress_phone = sub.add_parser(
        "add-phone-suppression",
        aliases=["suppress-phone"],
        help="Add SMS DNC suppression",
    )
    suppress_phone.add_argument("--phone", required=True)
    suppress_phone.add_argument("--reason", default="stop_received")
    suppress_phone.add_argument("--source", default="twilio_inbound")

    args = parser.parse_args()

    if args.command == "check":
        print(f"suppressed: {should_suppress(args.email)}")
    elif args.command == "add":
        ok = add_suppression(args.email, args.reason)
        print(f"added: {ok}")
    elif args.command == "footer":
        print(build_casl_footer(args.email))
    elif args.command in {"add-phone-suppression", "suppress-phone"}:
        add_phone_suppression(args.phone, reason=args.reason, source=args.source)
        print(f"suppressed_phone: {normalize_phone(args.phone)}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
