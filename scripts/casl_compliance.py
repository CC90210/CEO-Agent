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

# Unsubscribe endpoint — the cc-funnel app handles GET/POST here and writes to
# the suppression list + email_suppressions Supabase table.
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


def _suppression_enforced() -> bool:
    """True on hosts that MUST treat suppression as authoritative (prod / the
    SunBiz VPS set CASL_FAIL_CLOSED=1). When True, Supabase is consulted as the
    source of truth and a host with NO reachable suppression source fails CLOSED.
    Default False preserves the fast CSV-only dev/test path (no per-send DB call,
    no behavior change for the existing suite)."""
    return (os.environ.get("CASL_FAIL_CLOSED", "") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


_SUPPRESSION_CLIENT = None
_SUPPRESSION_CLIENT_INIT = False


def _suppression_client():
    """Cached service-role Supabase client for suppression lookups. Built once
    from os.environ (the daemon's secret_loader populates BRAVO_SUPABASE_* there,
    same pattern as send_gateway.get_supabase / funnel_nurture.get_supabase).
    create_client is offline (no network until a query), so caching is safe.
    Returns None if creds are absent (dev) — caller falls back to the CSV."""
    global _SUPPRESSION_CLIENT, _SUPPRESSION_CLIENT_INIT
    if not _SUPPRESSION_CLIENT_INIT:
        _SUPPRESSION_CLIENT_INIT = True
        url = os.environ.get("BRAVO_SUPABASE_URL", "")
        key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
        if url and key:
            try:
                from supabase import create_client
                _SUPPRESSION_CLIENT = create_client(url, key)
            except Exception:
                _SUPPRESSION_CLIENT = None
    return _SUPPRESSION_CLIENT


def _db_suppressed(table: str, column: str, value: str) -> Optional[bool]:
    """Supabase suppression lookup. Returns True/False when the table is
    reachable, or None when Supabase is unavailable (caller falls back to the
    CSV). The web unsubscribe endpoint writes to these tables, so on production
    Supabase — not the local CSV — is the source of truth."""
    client = _suppression_client()
    if client is None:
        return None
    try:
        resp = client.table(table).select(column).eq(column, value).limit(1).execute()
        return bool(getattr(resp, "data", None))
    except Exception:
        return None


def _csv_contains(csv_path: Path, column: str, value: str, normalize) -> bool:
    """True only if `value` is actually present in the CSV. NO fail-closed —
    this is for the WRITE paths' idempotency check, NOT send-time suppression.
    (should_suppress fail-closes to True on no-source; using it for the add_*
    dedup would make an unsubscribe during a DB/CSV outage report 'already
    suppressed' and silently skip persisting the opt-out.)"""
    if not csv_path.exists():
        return False
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if normalize(row.get(column, "")) == value:
                    return True
    except Exception:
        return False
    return False


def should_suppress(email: str) -> bool:
    """Return True if the email must NOT be sent to.

    On production hosts (CASL_FAIL_CLOSED=1) the Supabase ``email_suppressions``
    table is the source of truth — that's where the web unsubscribe endpoint
    records opt-outs the local CSV can't see. The CSV is a cache/fallback. On
    dev hosts the fast CSV-only path is kept.

    Fail-CLOSED: empty recipient, a read error, OR (on production) no reachable
    suppression source at all → suppress. The prior version returned False
    (fail-OPEN) when the CSV was merely missing — a CASL exposure.
    """
    normalized = _normalize_email(email)
    if not normalized:
        return True  # empty email = suppress

    enforced = _suppression_enforced()

    # 1. Supabase source of truth (production only — avoids a per-send DB call
    #    on dev/test where CASL_FAIL_CLOSED is unset).
    db_state: Optional[bool] = (
        _db_suppressed("email_suppressions", "email", normalized) if enforced else None
    )
    if db_state is True:
        return True

    # 2. Local CSV cache / fallback.
    if SUPPRESSIONS_CSV.exists():
        try:
            with open(SUPPRESSIONS_CSV, "r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if _normalize_email(row.get("email", "")) == normalized:
                        return True
        except Exception:
            return True  # fail CLOSED on read error
        return False

    # 3. No CSV. On a production host with no reachable DB either, fail CLOSED.
    if enforced and db_state is None:
        return True
    return False  # dev fast-path: no suppression source materialized yet


def add_suppression(email: str, reason: str = "unsubscribe") -> bool:
    """Append an email to the suppression list. Idempotent."""
    from datetime import datetime, timezone
    normalized = _normalize_email(email)
    if not normalized:
        return False
    if _csv_contains(SUPPRESSIONS_CSV, "email", normalized, _normalize_email):
        return True  # already in the local list — idempotent no-op
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

    enforced = _suppression_enforced()

    # 1. Supabase source of truth (production only).
    db_state: Optional[bool] = (
        _db_suppressed("phone_suppressions", "phone", normalized) if enforced else None
    )
    if db_state is True:
        return True

    # 2. Local CSV cache / fallback.
    if PHONE_SUPPRESSIONS_CSV.exists():
        try:
            with open(PHONE_SUPPRESSIONS_CSV, "r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if normalize_phone(row.get("phone", "")) == normalized:
                        return True
        except Exception:
            return True  # fail CLOSED on read error
        return False

    # 3. No CSV. On a production host with no reachable DB either, fail CLOSED.
    if enforced and db_state is None:
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
    if _csv_contains(PHONE_SUPPRESSIONS_CSV, "phone", normalized, normalize_phone):
        return  # already in the local DNC list — idempotent no-op
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
    business_address = business_address or os.environ.get("CASL_BUSINESS_ADDRESS", DEFAULT_BUSINESS_ADDRESS)
    sender_name = sender_name or os.environ.get("CASL_SENDER_NAME", DEFAULT_SENDER_NAME)

    # 2026-04-27: dropped the visible "reply STOP" line at CC's direction —
    # the spammy phrasing was hurting deliverability and brand perception on
    # cold B2B outreach. Opt-out still works via the List-Unsubscribe header
    # (Gmail/Outlook native one-click button → unsubscribe@oasisai.work →
    # email_engine.check-inbox auto-suppresses). Visible footer retains
    # sender name, business name, and physical address per CASL s. 6(2)(a-b).
    footer = (
        "\n\n---\n"
        f"{sender_name} — {business_name}\n"
        f"{business_address}\n"
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
    business_address = business_address or os.environ.get("CASL_BUSINESS_ADDRESS", DEFAULT_BUSINESS_ADDRESS)
    sender_name = sender_name or os.environ.get("CASL_SENDER_NAME", DEFAULT_SENDER_NAME)

    from html import escape

    return (
        '<hr style="margin-top:24px;border:none;border-top:1px solid #ddd"/>'
        '<div style="font-size:11px;color:#888;font-family:sans-serif;line-height:1.5">'
        f'{escape(sender_name)} — {escape(business_name)}<br/>'
        f'{escape(business_address)}'
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
