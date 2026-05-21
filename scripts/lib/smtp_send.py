"""Shared SMTP transport — single source of truth for all Gmail sends.

All outbound email MUST go through this module. This closes the V5.6
outbound chokepoint: no other file should import smtplib directly.

Usage:
    from lib.smtp_send import smtp_send
    ok, err = smtp_send(gmail_user, gmail_pass, mime_message, to_email)

Canonical: send_gateway.py _send_email_smtp() → extracted here 2026-05-21.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from typing import Optional


def smtp_send(
    gmail_user: str,
    gmail_pass: str,
    mime: MIMEMultipart,
    to_email: str,
    timeout: int = 30,
) -> tuple[bool, Optional[str]]:
    """Send an email via Gmail SMTP SSL.

    Returns (success, error_message). error_message is None on success.
    """
    if not gmail_user or not gmail_pass:
        return False, "GMAIL_USER/GMAIL_APP_PASSWORD missing"
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=timeout) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, to_email, mime.as_bytes())
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed — rotate GMAIL_APP_PASSWORD"
    except smtplib.SMTPRecipientsRefused:
        return False, f"recipient refused by server: {to_email}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected send error: {e}"
