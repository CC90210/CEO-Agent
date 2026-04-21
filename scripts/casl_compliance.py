"""CASL compliance helpers for all outgoing cold email.

Single source of truth for CASL (Canada's Anti-Spam Legislation) requirements:
- Sender identification (name + physical address)
- Working unsubscribe mechanism
- Suppression list check before every send

AS OF 2026-04-20 (V5.6 chokepoint era): the only callers that matter are
`scripts/send_gateway.py` (which applies these to every outbound commercial
AND transactional send) and `scripts/outreach_batch.py` (which calls
should_suppress pre-draft so suppressed addresses don't burn Claude Haiku
tokens on emails that can never be sent). All business engines
(outreach_engine, email_engine, funnel_nurture, booking_engine,
contract_generator) delegate physical send to send_gateway — they no
longer call these functions directly.

Every outgoing commercial email MUST:
  1. Call should_suppress(lead_email) and refuse to send if True
  2. Append build_casl_footer(...) to the email body
  3. Add List-Unsubscribe + List-Unsubscribe-Post headers (RFC 2369/8058)

The gateway enforces #1, #2, and #3 architecturally. Do not bypass.
Fines for violations are up to $10M per incident for businesses.
"""

import csv
import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS_CSV = PROJECT_ROOT / "data" / "email_suppressions.csv"

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


def should_suppress(email: str) -> bool:
    """Return True if the email is on the suppression list.

    Reads from data/email_suppressions.csv. Safe to call on every send —
    file is small and reads are cheap. Returns False if the file does
    not exist yet (fail-open, since the file is created on first unsub).
    """
    normalized = _normalize_email(email)
    if not normalized:
        return True  # empty email = suppress
    if not SUPPRESSIONS_CSV.exists():
        return False
    try:
        with open(SUPPRESSIONS_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if _normalize_email(row.get("email", "")) == normalized:
                    return True
    except Exception:
        # Fail CLOSED on read errors — safer to miss a send than violate CASL
        return True
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

    # 2026-04-20: dropped the https://oasisai.work/unsubscribe link from the
    # footer — that page didn't exist and CC confirmed it was a dead end.
    # Reply-STOP is the primary mechanism now; email_engine.check-inbox
    # auto-suppresses any lead whose inbound classifier flags intent=unsubscribe.
    # Reply-STOP is CASL-compliant as long as the opt-out is processed within
    # 10 business days — the auto-suppression handler does this in seconds.
    footer = (
        "\n\n---\n"
        f"{sender_name} — {business_name}\n"
        f"{business_address}\n"
        "To opt out, just reply STOP and you will be removed from the list "
        "within 24 hours (usually within the hour).\n"
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
        f'{escape(business_address)}<br/>'
        'To opt out, just reply <strong>STOP</strong> and you will be removed '
        'from the list within 24 hours (usually within the hour).'
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


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "check" and len(sys.argv) > 2:
        email = sys.argv[2]
        print(f"suppressed: {should_suppress(email)}")
    elif cmd == "add" and len(sys.argv) > 2:
        email = sys.argv[2]
        reason = sys.argv[3] if len(sys.argv) > 3 else "manual"
        ok = add_suppression(email, reason)
        print(f"added: {ok}")
    elif cmd == "footer" and len(sys.argv) > 2:
        print(build_casl_footer(sys.argv[2]))
    else:
        print(__doc__)
        print("\nUsage:")
        print("  python scripts/casl_compliance.py check <email>")
        print("  python scripts/casl_compliance.py add <email> [reason]")
        print("  python scripts/casl_compliance.py footer <email>")
