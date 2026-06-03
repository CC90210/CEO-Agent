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

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from typing import Optional, Sequence, Union

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
    to_email: Union[str, Sequence[str]],
    timeout: int = 30,
    require_from_domain: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Send an email via Gmail SMTP SSL.

    Returns (success, error_message). error_message is None on success.
    Every call emits one structured-log line tagged with the outcome class
    (`sent` | `auth_failed` | `recipient_refused` | `smtp_error` |
    `unexpected_error`) so daemons that drive this function can be
    investigated post-hoc from `state/logs/smtp_send.log`.
    """
    recipients = [to_email] if isinstance(to_email, str) else list(to_email)
    if not gmail_user or not gmail_pass:
        _log.error("missing_credentials", to=",".join(recipients))
        return False, "GMAIL_USER/GMAIL_APP_PASSWORD missing"
    # Opt-in sender-identity guard — the single chokepoint for EVERY SMTP caller
    # (send_gateway, dashboard_email_consumer, …). When EMAIL_REQUIRE_FROM_DOMAIN
    # is set (single-tenant deploy, e.g. SunBiz VPS = "sunbizfunding.com"), refuse
    # to authenticate as any account not on that EXACT domain, so a misconfigured
    # bridge can never send as the operator's personal address. Unset → no-op.
    _rd = (require_from_domain if require_from_domain is not None
           else os.getenv("EMAIL_REQUIRE_FROM_DOMAIN", "")).strip().lower()
    if _rd:
        _addr = (gmail_user or "").strip().lower()
        _domain = _addr.rsplit("@", 1)[1] if "@" in _addr else ""
        if _addr.count("@") != 1 or _domain != _rd:
            _log.error("identity_guard_block", from_=gmail_user, require_domain=_rd)
            return False, (
                f"sender-identity guard: '{gmail_user}' is not on the required domain "
                f"@{_rd}; refusing to send. Set the tenant's own Gmail (e.g. "
                f"submissions@{_rd}) or unset EMAIL_REQUIRE_FROM_DOMAIN."
            )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=timeout) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, recipients, mime.as_bytes())
        _log.info("sent", to=",".join(recipients), from_=gmail_user)
        return True, None
    except smtplib.SMTPAuthenticationError:
        _log.error("auth_failed", to=",".join(recipients), from_=gmail_user)
        return False, "SMTP authentication failed — rotate GMAIL_APP_PASSWORD"
    except smtplib.SMTPRecipientsRefused:
        _log.warn("recipient_refused", to=",".join(recipients))
        return False, f"recipient refused by server: {', '.join(recipients)}"
    except smtplib.SMTPException as e:
        _log.error("smtp_error", to=",".join(recipients), error=str(e)[:200])
        return False, f"SMTP error: {e}"
    except Exception as e:  # noqa: BLE001
        _log.error("unexpected_error", to=",".join(recipients), error_type=type(e).__name__,
                   error=str(e)[:200])
        return False, f"unexpected send error: {e}"
