"""CASL compliance helpers for all outgoing cold email.

Single source of truth for CASL (Canada's Anti-Spam Legislation) requirements:
- Sender identification (name + physical address)
- Working unsubscribe mechanism
- Suppression list check before every send

Import from outreach_engine.py, outreach_batch.py, email_engine.py, funnel_nurture.py.
Every outgoing commercial email MUST:
  1. Call should_suppress(lead_email) and refuse to send if True
  2. Append build_casl_footer(...) to the email body

Fines for violations are up to $10M per incident for businesses. Do not bypass.
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
    unsubscribe_base = unsubscribe_base or os.environ.get("CASL_UNSUBSCRIBE_URL", DEFAULT_UNSUBSCRIBE_BASE)

    from urllib.parse import urlencode
    unsub_link = f"{unsubscribe_base}?{urlencode({'email': recipient_email})}"

    footer = (
        "\n\n---\n"
        f"{sender_name} — {business_name}\n"
        f"{business_address}\n"
        f"Unsubscribe: {unsub_link}\n"
        "Or reply with STOP to opt out within 10 business days.\n"
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
    unsubscribe_base = unsubscribe_base or os.environ.get("CASL_UNSUBSCRIBE_URL", DEFAULT_UNSUBSCRIBE_BASE)

    from urllib.parse import urlencode
    from html import escape
    unsub_link = f"{unsubscribe_base}?{urlencode({'email': recipient_email})}"

    return (
        '<hr style="margin-top:24px;border:none;border-top:1px solid #ddd"/>'
        '<div style="font-size:11px;color:#888;font-family:sans-serif;line-height:1.5">'
        f'{escape(sender_name)} — {escape(business_name)}<br/>'
        f'{escape(business_address)}<br/>'
        f'<a href="{escape(unsub_link)}" style="color:#888">Unsubscribe</a> '
        'or reply STOP to opt out within 10 business days.'
        '</div>'
    )


def add_list_unsubscribe_headers(msg, recipient_email: str) -> None:
    """Add RFC 2369 / RFC 8058 List-Unsubscribe headers to a MIME message.

    These headers are what Gmail, Outlook, and Apple Mail show as the native
    'Unsubscribe' button. Without them, the cold email looks like spam and
    deliverability tanks. With them, recipients get a one-click unsubscribe
    that satisfies both CASL and CAN-SPAM.
    """
    unsub_base = os.environ.get("CASL_UNSUBSCRIBE_URL", DEFAULT_UNSUBSCRIBE_BASE)
    from urllib.parse import urlencode
    unsub_url = f"{unsub_base}?{urlencode({'email': recipient_email})}"
    msg["List-Unsubscribe"] = f"<mailto:unsubscribe@oasisai.work?subject=unsubscribe>, <{unsub_url}>"
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
