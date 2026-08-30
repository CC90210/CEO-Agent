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
import re
import time
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
DEFAULT_BUSINESS_ADDRESS = "OASIS AI Solutions, Montreal, QC, Canada"
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
    """E.164-friendly normalization for SUPPRESSION-LIST MATCHING.

    Strips formatting, drops a leading US/Canada country code, and returns
    DIGITS ONLY (e.g. "7634218229"). Empty/None returns an empty string.

    NOTE: this is the canonical comparison form for STOP/DNC matching.
    For the WIRE format that SMS providers (TextTorrent / Twilio / Kixie)
    require, use `to_e164()` below.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def to_e164(phone: str | None) -> str | None:
    """Normalize to E.164 wire format for SMS providers (+1NXXXXXXXXX).

    TextTorrent / Twilio / Kixie all require E.164. SunBiz dashboard
    captures bare 10-digit phones in lead.data.phone (e.g. "7634218229")
    and historic imports came in formatted as "(763) 421-8229". Without
    upstream normalization every SMS send hit the strict E.164 gate in
    send_gateway and was rejected — discovered 2026-06-09 (VPS health
    audit): 408/408 SunBiz leads had non-E.164 phones, 2 welcome
    sequences had been stuck failed for 152h.

    Returns None when the input can't be confidently normalized so the
    caller fails closed rather than ships to a bad number.

    Codex audit 2026-06-09 round-5 [medium]: round-4 was too permissive.
    "+1" / "+12345" passed through because the plus-prefix branch only
    stripped non-digits without validating E.164 shape. Round-5 adds a
    strict ITU E.164 regex: ^\\+[1-9]\\d{7,14}$ (country code starts
    1-9, total 8-15 digits including country code).

    Accepts:
      - "+17634218229"            -> "+17634218229"  (already E.164)
      - "+447946112233"           -> "+447946112233" (UK, passes E.164 regex)
      - "7634218229"              -> "+17634218229"  (10-digit US/CA, default)
      - "17634218229"             -> "+17634218229"  (11-digit with leading 1)
      - "(763) 421-8229"          -> "+17634218229"  (formatted 10-digit)
      - "1-763-421-8229"          -> "+17634218229"  (formatted 11-digit)
      - " +1 763 421 8229 "       -> "+17634218229"  (whitespace tolerant)

    Rejects (returns None):
      - "" / None                 — empty
      - "+1"                      — plus prefix but too short
      - "+12345"                  — plus prefix below 8-digit minimum
      - "+0123456789"             — country code starts with 0 (invalid)
      - "12345"                   — bare digits too short for NANP
      - "1234567890123"           — too long for NANP (US/CA = 10 digits)
      - "abc"                     — no digits

    NOTE: bare 10/11-digit input is assumed US/CA (NANP) and gets
    "+1" prepended. If SunBiz ever takes non-NANP leads, callers MUST
    pre-format with the correct country code as a "+..." string. The
    helper has no way to distinguish a bare French mobile from a US
    one if both are 10 digits.
    """
    if not phone:
        return None
    raw = phone.strip()
    # ASCII-ONLY digit handling (Codex round-6 [medium]). str.isdigit()
    # returns True for Unicode decimal digits — Arabic-Indic (٠-٩),
    # fullwidth (０-９), Devanagari (०-९), etc. A normalized number
    # containing those bytes is not E.164 and SMS providers reject it
    # silently or with confusing errors. Restrict to ASCII 0-9 so the
    # final string is byte-valid for the wire.
    if raw.startswith("+"):
        digits = "".join(ch for ch in raw[1:] if ch in _ASCII_DIGITS)
        candidate = "+" + digits
        if _E164_REGEX.fullmatch(candidate):
            return candidate
        return None
    # Bare digits — assume NANP (US/CA), prepend +1 for 10-digit,
    # prepend + for 11-digit starting with 1. Anything else is
    # ambiguous and rejected.
    digits = "".join(ch for ch in raw if ch in _ASCII_DIGITS)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


# ASCII 0-9. Used by to_e164 to reject Unicode digit imposters that
# str.isdigit() / \d would otherwise accept.
_ASCII_DIGITS = frozenset("0123456789")

# Strict E.164 shape: leading '+', country code 1-9, 7-14 more digits
# (8-15 total). re.ASCII flag so \d only matches [0-9], never Unicode
# decimal digits. https://en.wikipedia.org/wiki/E.164
_E164_REGEX = re.compile(r"^\+[1-9][0-9]{7,14}$", re.ASCII)


# ----------------------------------------------------------------------------
# Suppression read path (2026-06-06 — closes the /unsubscribe loop)
# ----------------------------------------------------------------------------
#
# Before 2026-06-06 should_suppress() only checked data/email_suppressions.csv.
# After shipping /unsubscribe on the agent-dashboard the new
# email_suppressions table became the authoritative store for
# web-form unsubscribes (per-tenant, per-brand, CASL s. 6 scoped). The
# CSV stays in place for legacy inbound STOP detection on email/SMS;
# should_suppress now consults BOTH so a web unsub silences future
# sends even when the operator hasn't replicated the row into the CSV.
#
# 2026-08-08 — moved off raw Supabase REST onto the data-backend switch.
# This used to hand-build a PostgREST URL and fetch it with urllib, which
# pinned the legal check to Supabase no matter what EMPIRE_DATA_BACKEND
# said. Once the web app started recording unsubscribes into Turso that
# meant an unsubscribed person kept getting mailed — the suppression row
# existed, just not in the store this file was reading. It now goes through
# supabase.create_client + the builder dialect, which sitecustomize swaps
# for the Turso compat client when EMPIRE_DATA_BACKEND=turso_cloud. Same
# filters, same limit, same returned shape, same fail-open posture.
#
# In-process cache: 60s TTL keyed on (email, tenant_id, brand). Drip
# runners call should_suppress() hundreds of times per minute during a
# campaign; without caching the per-check round trip would dominate latency
# and burn through the Vercel-side rate limit on the service role key.
#
# Fail-open on backend errors: if the query fails (network blip, bad
# credentials, table missing), we fall through to the CSV check.
# CSV-read errors still fail-CLOSED per the existing behaviour — that
# path is local-disk and "we lost our suppression list" is a serious
# CASL hazard, while a transient backend outage isn't.

_SUPPRESSION_CACHE: dict[str, tuple[bool, float]] = {}
_SUPPRESSION_CACHE_TTL = 60.0  # seconds

# The client is memoized because constructing one is NOT free on the Turso
# side: TursoDB.__init__ introspects the live schema (one PRAGMA per table)
# to build its tenant-scope registry. Rebuilding that per should_suppress()
# call would put a few hundred round trips in front of every send. Keyed on
# the resolved (backend, url, key) so flipping EMPIRE_DATA_BACKEND — or
# rotating credentials — rebuilds instead of serving a stale connection.
_DB_CLIENT: object | None = None
_DB_CLIENT_KEY: Optional[tuple[str, str, str]] = None


def _cache_key(email: str, tenant_id: Optional[str], brand: Optional[str]) -> str:
    return f"{email}|{tenant_id or ''}|{brand or ''}"


def _suppression_client():
    """Return a client for email_suppressions, or None if unconfigured.

    Follows EMPIRE_DATA_BACKEND: sitecustomize swaps create_client for the
    Turso compat client when the flag is turso_cloud, so this one call site
    serves both backends.
    """
    global _DB_CLIENT, _DB_CLIENT_KEY
    backend = os.environ.get("EMPIRE_DATA_BACKEND", "").strip().lower()
    url = os.environ.get("BRAVO_SUPABASE_URL") or ""
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or ""
    # On the Turso backend create_client ignores url/key entirely (it resolves
    # TURSO_* through lib.db_turso), so demanding Supabase credentials there
    # would silently disable the suppression check the day CC cancels the
    # subscription and removes those keys — precisely the CASL hazard this
    # module exists to prevent.
    if backend != "turso_cloud" and (not url or not key):
        return None
    ck = (backend, url, key)
    if _DB_CLIENT is not None and _DB_CLIENT_KEY == ck:
        return _DB_CLIENT
    from supabase import ClientOptions, create_client
    # 4s ceiling preserves the urllib timeout this path used to carry.
    # postgrest-py's default is 120s, which would stall a drip run behind a
    # single hung legal check. Ignored (harmlessly) by the compat client.
    _DB_CLIENT = create_client(
        url, key, options=ClientOptions(postgrest_client_timeout=4)
    )
    _DB_CLIENT_KEY = ck
    return _DB_CLIENT


def _check_db_suppression(
    email: str,
    tenant_id: Optional[str],
    brand: Optional[str],
) -> Optional[bool]:
    """Query the email_suppressions table on the active data backend.

    Returns True if a matching row is found, False if the table has no
    match, or None when the query couldn't run (credentials missing,
    network error, etc.). Callers treat None as "fall through to CSV."
    """
    try:
        client = _suppression_client()
        if client is None:
            return None
        # Match rows where email matches AND tenant_id matches (or is global
        # NULL) AND brand matches (or is global NULL). NULL on either column
        # is the "global" suppression — always wins. Two or_() calls are
        # AND-ed together by PostgREST and by the compat client alike, which
        # is exactly what the two `or=` query params did before.
        q = (
            client.table("email_suppressions")
            .select("tenant_id,brand")
            .eq("email", email)
        )
        if tenant_id:
            q = q.or_(f"tenant_id.is.null,tenant_id.eq.{tenant_id}")
        else:
            q = q.is_("tenant_id", "null")
        # When no brand supplied, we accept any brand-scope match (existing
        # callers don't know the sender brand yet — they're legacy paths
        # from before the per-brand schema), so no brand filter is added.
        if brand:
            q = q.or_(f"brand.is.null,brand.eq.{brand}")
        return bool(q.limit(1).execute().data)
    except Exception as exc:  # noqa: BLE001
        # Fail OPEN to the CSV check, as the urllib version did. Deliberately
        # broad: the exception surface moved with the backend (postgrest
        # APIError, httpx timeouts, libsql errors, CompatError, ImportError)
        # and a transient data-plane fault must not crash the send path.
        # Logged rather than swallowed — a silent fail-open here means
        # unsubscribed people get mailed, so it must leave a trail.
        try:
            from lib.structured_log import get_logger  # noqa: PLC0415
            get_logger("casl_compliance").error(
                "email_suppressions lookup failed — falling back to CSV",
                error=str(exc), error_type=type(exc).__name__,
                backend=os.environ.get("EMPIRE_DATA_BACKEND", "supabase"),
            )
        except Exception:  # noqa: BLE001 - logging must never break the send path
            pass
        return None


def should_suppress(
    email: str,
    tenant_id: Optional[str] = None,
    brand: Optional[str] = None,
) -> bool:
    """Return True if the email is on the suppression list.

    Sources, in order: in-process cache → the email_suppressions table on
    the active data backend (Supabase or Turso, per EMPIRE_DATA_BACKEND)
    → data/email_suppressions.csv. The table check fail-opens to CSV;
    CSV read errors still fail-CLOSED (we suppress, since losing the
    list is the worse CASL hazard).

    Args:
        email: The recipient address (case-insensitive).
        tenant_id: Optional tenant UUID. If supplied, the table check
            matches global (tenant_id IS NULL) OR same-tenant rows.
            When omitted, only global suppressions match — preserves
            backward compat with existing callers like email_engine.
        brand: Optional brand label (e.g. "OASIS AI", "SunBiz"). When
            supplied, the table check narrows to rows whose `brand`
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

    # 1. Backend check (authoritative for web unsubs; fail-open).
    sb = _check_db_suppression(normalized, tenant_id, brand)
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
