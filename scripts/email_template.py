"""email_template.py — single canonical OASIS AI branded HTML email.

Used by:
  - scripts/google_tool.py gmail send --branded
  - scripts/send_gateway.py for outreach + transactional sends
  - any other script that needs to send a branded email

Why a Python module not an HTML file: every send picks the operator's
display name + email + brand from .env.agents at runtime, and the body
is the per-message text. A static template doesn't help. This is the
canonical layout — change it here, every email surface picks it up.

Design notes:
  - Single column, 600px max width — works in every client incl. Gmail
    mobile, Outlook, Apple Mail.
  - Inline styles only (Gmail strips <style> blocks in some surfaces).
  - Dark theme accent color matches the OASIS AI brand teal (#00d4ff).
  - Plain-text version sent alongside (multipart/alternative) so clients
    that strip HTML still see something readable.
"""
from __future__ import annotations

import html as _html
import os
from typing import Optional


_BRAND_TEAL = "#00d4ff"
_BG_DEEP = "#0a0e16"
_FG = "#f5f7fa"
_FG_MUTED = "#9ba3b4"
_FG_DIM = "#6b7280"
_ACCENT_FADE = "#1a1f2e"


def _from_display() -> str:
    """The operator's display name. Falls back to OASIS AI default."""
    return (
        os.environ.get("BRAVO_FROM_DISPLAY")
        or os.environ.get("USER_FULL_NAME")
        or "Conaugh McKenna"
    )


def _from_email() -> str:
    return (
        os.environ.get("GMAIL_USER")
        or os.environ.get("BRAVO_FROM_EMAIL")
        or "conaugh@oasisai.work"
    )


def _signature_block() -> str:
    return os.environ.get("BRAVO_SIGNATURE_TAGLINE") or "Founder, OASIS AI Solutions"


def _booking_link() -> Optional[str]:
    """If set, included as a soft CTA below the body."""
    return os.environ.get("BOOKING_LINK") or None


def _website() -> str:
    return os.environ.get("BRAVO_WEBSITE_URL") or "https://oasisai.work"


def render_branded_html(
    body: str,
    *,
    subject: Optional[str] = None,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    show_booking: bool = False,
) -> str:
    """Wrap a plain-text body in the OASIS AI branded HTML shell.

    `body` may contain newlines — they're converted to <br/>. Markdown
    is NOT processed; if the caller wants formatting they should pass
    a pre-rendered HTML fragment via `html_body` (separate function
    below). The simple-string path keeps the agent's life easy: pass
    the message it would have written in plaintext, get a branded
    email out.
    """
    safe_body = _html.escape(body).replace("\n", "<br/>\n")
    name = _html.escape(_from_display())
    sig = _html.escape(_signature_block())
    site = _html.escape(_website())
    booking = _booking_link()

    cta_block = ""
    if cta_label and cta_url:
        cta_block = (
            f'<div style="margin:28px 0 20px 0;text-align:left">'
            f'<a href="{_html.escape(cta_url)}" '
            f'style="display:inline-block;padding:12px 22px;'
            f'background:{_BRAND_TEAL};color:{_BG_DEEP};text-decoration:none;'
            f'border-radius:6px;font-weight:600;font-size:14px;'
            f'letter-spacing:0.01em">{_html.escape(cta_label)}</a>'
            f"</div>"
        )

    booking_block = ""
    if show_booking and booking:
        booking_block = (
            f'<div style="margin:24px 0 8px 0;font-size:13px;color:{_FG_MUTED}">'
            f'Want to talk live? '
            f'<a href="{_html.escape(booking)}" '
            f'style="color:{_BRAND_TEAL};text-decoration:underline">'
            f"Grab a 30-minute slot</a>."
            f"</div>"
        )

    title = _html.escape(subject or "OASIS AI")

    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1" />\n'
        f'<title>{title}</title>\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background:{_BG_DEEP};color:{_FG};'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',system-ui,sans-serif;'
        'line-height:1.6;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="background:{_BG_DEEP}">\n'
        '<tr><td align="center" style="padding:32px 16px">\n'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'border="0" style="max-width:600px;width:100%;background:{_ACCENT_FADE};'
        f'border:1px solid rgba(0,212,255,0.2);border-radius:12px;overflow:hidden">\n'
        # Header bar
        f'<tr><td style="padding:22px 28px 18px 28px;border-bottom:1px solid rgba(0,212,255,0.15)">\n'
        f'<div style="display:flex;align-items:center;gap:10px">\n'
        f'<div style="width:32px;height:32px;border-radius:6px;'
        f'background:linear-gradient(135deg,{_BRAND_TEAL},#3b82f6);'
        f'display:inline-block;vertical-align:middle"></div>\n'
        f'<span style="font-weight:800;font-size:14px;letter-spacing:0.06em;'
        f'color:{_FG};text-transform:uppercase;margin-left:8px">OASIS AI</span>\n'
        f"</div></td></tr>\n"
        # Body
        f'<tr><td style="padding:28px 28px 8px 28px;color:{_FG};font-size:15px;'
        f'line-height:1.65">{safe_body}</td></tr>\n'
        # CTA (optional)
        + (
            f'<tr><td style="padding:0 28px">{cta_block}</td></tr>\n'
            if cta_block else ""
        )
        # Booking (optional)
        + (
            f'<tr><td style="padding:0 28px">{booking_block}</td></tr>\n'
            if booking_block else ""
        )
        # Signature
        + f'<tr><td style="padding:24px 28px 22px 28px;border-top:1px solid rgba(255,255,255,0.06);margin-top:20px">\n'
        f'<div style="font-size:14px;color:{_FG};font-weight:600">— {name}</div>\n'
        f'<div style="font-size:12px;color:{_FG_MUTED};margin-top:2px">{sig}</div>\n'
        f'<div style="font-size:11px;color:{_FG_DIM};margin-top:12px">'
        f'<a href="{site}" style="color:{_FG_DIM};text-decoration:none">{site}</a>'
        f'</div>\n'
        f"</td></tr>\n"
        # Footer
        f'<tr><td style="padding:14px 28px;background:{_BG_DEEP};'
        f'font-size:10px;color:{_FG_DIM};text-align:center">'
        f'You\'re receiving this because {name} sent it personally. '
        f'Reply to this email and it lands in their inbox.'
        f"</td></tr>\n"
        "</table>\n"
        "</td></tr>\n"
        "</table>\n"
        "</body></html>"
    )


def render_branded_plaintext(body: str) -> str:
    """The plaintext alternative shipped alongside the HTML. Mirrors the
    structure so HTML-stripped clients see the same message + signature.
    """
    name = _from_display()
    sig = _signature_block()
    site = _website()
    booking = _booking_link()
    parts = [body.strip(), "", f"— {name}", sig, site]
    if booking:
        parts.append(f"Book a call: {booking}")
    return "\n".join(parts) + "\n"
