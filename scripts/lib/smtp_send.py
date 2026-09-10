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

import html as _html
import os
import re
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


# ---- Identity guard: the message must be sent by the company it claims -----
#
# WHY HERE AND NOWHERE ELSE. On 2026-09-09 a client saw OASIS-branded mail from
# their own mailbox. A brand/mailbox guard was added to send_gateway.send() —
# and did not fire, because dashboard_email_consumer does NOT call send_gateway.
# Its own header says so: "queues operator-composed lead emails straight to
# lib.smtp_send, bypassing send_gateway". Six OASIS-tenant rows had already gone
# out from the client's mailbox on that path, the last two being the messages
# the client screenshotted.
#
# This module is the ONLY thing both paths share, so a guard anywhere else is a
# guard with a door beside it.
#
# THE DISCRIMINATOR IS THE POSTAL ADDRESS, not the company name. A street
# address appears only inside a CASL/CAN-SPAM identification block — the part
# of a message that asserts "this is who sent it". A company NAME can appear in
# ordinary prose ("we also work with Bluerise"), so matching on names would
# refuse legitimate mail. Matching on the identification address does not.
#
# EMAIL_REQUIRE_FROM_DOMAIN cannot do this job: it asserts the mailbox is on a
# domain, which an OASIS-branded message from the client's mailbox trivially
# satisfies. It checks the envelope; this checks the claim.
_IDENTITY_ADDRESSES: tuple[tuple[str, frozenset[str]], ...] = (
    # OASIS AI Solutions, Montreal.
    ("6993 decarie blvd", frozenset({"oasisai.work"})),
    # SunBiz Funding LLC and Bluerise Business Capital share premises by
    # agreement (Adon, 2026-08-05), so either domain may carry this address.
    ("221 w hallandale beach blvd", frozenset({"sunbizfunding.com", "bluerisebusinesscapital.com"})),
)


_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def _message_text(mime: MIMEMultipart) -> str:
    """Every text part of the message, lowercased, for identity inspection.

    Walks the MIME tree rather than reading a single payload: the identification
    block lives in the text/plain part on some paths and only in the HTML on
    others, and a guard that inspects one of them is blind on the other.
    """
    chunks: list[str] = []
    try:
        for part in mime.walk():
            if part.get_content_maintype() != "text":
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:  # noqa: BLE001
                payload = None
            if payload is None:
                raw = part.get_payload()
                if isinstance(raw, str):
                    chunks.append(raw)
                continue
            charset = part.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    except Exception:  # noqa: BLE001
        # An unwalkable message is not evidence of innocence, but it is also not
        # evidence of a mismatch. Fall back to the raw bytes so the check still
        # sees the identification block if one is present.
        try:
            chunks.append(mime.as_bytes().decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return ""
    return "\n".join(chunks).lower()


def _normalised_variants(raw: str) -> tuple[str, ...]:
    """The message text as a matcher should see it, in both tag-strip flavours.

    A raw substring match over HTML is trivially defeated by ordinary markup:
    "6993&nbsp;Decarie Blvd" and "6993 <span>Decarie</span> Blvd" both render as
    the identification a human reads, and neither contains the literal
    "6993 decarie blvd". A guard that can be stepped around by a template change
    is not a guard. (CodeRabbit, PR #72.)

    Two variants because neither tag replacement is safe alone:
      - tags -> ""   joins "6993<br>Decarie" correctly, but welds "Deca<b>rie</b>"
      - tags -> " "  splits "Deca<b>rie</b>" correctly, but breaks the <br> case
    Checking both means markup cannot hide an identification either way. Entity
    decoding and whitespace collapsing apply to both.
    """
    text = _html.unescape(raw)
    out = []
    for filler in ("", " "):
        stripped = _TAG_RE.sub(filler, text)
        out.append(_WS_RE.sub(" ", stripped).strip())
    return tuple(out)


def _identity_conflict(mime: MIMEMultipart, gmail_user: str) -> Optional[str]:
    """The message identifies as a company this mailbox may not send for.

    Returns an explanation, or None when there is no conflict — including when
    the message carries no identification block at all, which is the case for
    internal and transactional mail that never claims a company.
    """
    addr = (gmail_user or "").strip().lower()
    if addr.count("@") != 1:
        return None  # the credential guard above already owns malformed addresses
    domain = addr.rsplit("@", 1)[1]
    raw = _message_text(mime)
    if not raw:
        return None
    variants = _normalised_variants(raw)
    for street, entitled in _IDENTITY_ADDRESSES:
        if not any(street in v for v in variants):
            continue
        if domain in entitled or any(domain.endswith("." + d) for d in entitled):
            continue
        return (
            f"this message carries the legal identification of a company at "
            f"'{street}', which only {' or '.join(sorted(entitled))} may send for — "
            f"but it is authenticated as {addr}. Refusing: a commercial email may "
            f"not claim one company's identity while being sent from another's mailbox."
        )
    return None


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
    # The message must be sent by the company it identifies as. Runs AFTER the
    # domain guard because that one answers a simpler question ("is this mailbox
    # allowed here at all"), and its message is clearer when it applies.
    #
    # Unconditional — no env var, no opt-in. The 2026-09-09 leak ran for months
    # through a path where the opt-in guard was set and satisfied. A guard that
    # has to be switched on is off wherever nobody remembered.
    _conflict = _identity_conflict(mime, gmail_user)
    if _conflict:
        _log.error("identity_claim_block", from_=gmail_user, to=",".join(recipients),
                   reason=_conflict[:200])
        return False, f"sender-identity guard: {_conflict}"

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
