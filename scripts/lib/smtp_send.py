"""Shared SMTP transport — single source of truth for all Gmail sends.

All outbound email MUST go through this module. This closes the V5.6
outbound chokepoint: no other file should import smtplib directly.

V6.8.3: every send emits one structured-log line (success or failure type)
so the dashboard's "Recent Outbound" + the audit trail share a queryable
JSON ledger. Falls back to silent on import error so this module never
fails just because logging isn't wired up.

Usage:
    from lib.smtp_send import smtp_send
    ok, err = smtp_send(gmail_user, gmail_pass, mime_message, to_email)

Canonical: send_gateway.py _send_email_smtp() → extracted here 2026-05-21.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from typing import Optional

try:  # pragma: no cover — optional dep
    from lib.structured_log import get_logger  # type: ignore
    _log = get_logger("smtp_send")
except Exception:
    class _StubLog:
        def info(self, *_a, **_k): pass
        def warn(self, *_a, **_k): pass
        def error(self, *_a, **_k): pass
    _log = _StubLog()


def smtp_send(
    gmail_user: str,
    gmail_pass: str,
    mime: MIMEMultipart,
    to_email: str,
    timeout: int = 30,
) -> tuple[bool, Optional[str]]:
    """Send an email via Gmail SMTP SSL.

    Returns (success, error_message). error_message is None on success.
    Every call emits one structured-log line tagged with the outcome class
    (`sent` | `auth_failed` | `recipient_refused` | `smtp_error` |
    `unexpected_error`) so daemons that drive this function can be
    investigated post-hoc from `state/logs/smtp_send.log`.
    """
    if not gmail_user or not gmail_pass:
        _log.error("missing_credentials", to=to_email)
        return False, "GMAIL_USER/GMAIL_APP_PASSWORD missing"
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=timeout) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, to_email, mime.as_bytes())
        _log.info("sent", to=to_email, from_=gmail_user)
        return True, None
    except smtplib.SMTPAuthenticationError:
        _log.error("auth_failed", to=to_email, from_=gmail_user)
        return False, "SMTP authentication failed — rotate GMAIL_APP_PASSWORD"
    except smtplib.SMTPRecipientsRefused:
        _log.warn("recipient_refused", to=to_email)
        return False, f"recipient refused by server: {to_email}"
    except smtplib.SMTPException as e:
        _log.error("smtp_error", to=to_email, error=str(e)[:200])
        return False, f"SMTP error: {e}"
    except Exception as e:  # noqa: BLE001
        _log.error("unexpected_error", to=to_email, error_type=type(e).__name__,
                   error=str(e)[:200])
        return False, f"unexpected send error: {e}"
