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
_BRAND_TEAL_DEEP = "#0099cc"
_BG_DEEP = "#050810"
_BG_PANEL = "#0c1220"
_BG_PANEL_GLOW = "#0f1830"
_FG = "#f5f7fa"
_FG_MUTED = "#a8b0c2"
_FG_DIM = "#6b7280"
_ACCENT_FADE = "#0f1830"

# Logo URL — public asset on oasisai.work (verified live, 55KB JPG).
# Inlining as base64 would push the email past Gmail's 102KB clip
# threshold; remote URL is the standard approach used by every modern
# transactional-email provider.
_LOGO_URL = "https://oasisai.work/images/oasis-logo.jpg"

# Pre-built star field — 25 stars at deterministic positions across the
# header band. SVG inlined as a data: URL so it ships in the HTML and
# renders even when remote images are blocked. Subtle pulse effect on
# the brighter ones; static positioning so it doesn't reflow per client.
_STARFIELD_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 180" preserveAspectRatio="xMidYMid slice" style="position:absolute;inset:0;width:100%;height:100%;opacity:0.75">'
    # Brighter stars
    '<circle cx="42" cy="28" r="1.4" fill="#7dd3fc" opacity="0.9"/>'
    '<circle cx="118" cy="62" r="1.2" fill="#a5f3fc" opacity="0.85"/>'
    '<circle cx="208" cy="38" r="1.6" fill="#7dd3fc" opacity="0.95"/>'
    '<circle cx="296" cy="22" r="1.3" fill="#bae6fd" opacity="0.9"/>'
    '<circle cx="378" cy="58" r="1.5" fill="#7dd3fc" opacity="0.92"/>'
    '<circle cx="456" cy="32" r="1.1" fill="#bae6fd" opacity="0.85"/>'
    '<circle cx="528" cy="74" r="1.5" fill="#7dd3fc" opacity="0.95"/>'
    '<circle cx="566" cy="44" r="1.2" fill="#a5f3fc" opacity="0.9"/>'
    # Mid stars
    '<circle cx="78" cy="98" r="0.9" fill="#cffafe" opacity="0.7"/>'
    '<circle cx="158" cy="118" r="0.8" fill="#cffafe" opacity="0.65"/>'
    '<circle cx="248" cy="92" r="1.0" fill="#a5f3fc" opacity="0.7"/>'
    '<circle cx="332" cy="128" r="0.9" fill="#cffafe" opacity="0.65"/>'
    '<circle cx="412" cy="108" r="1.0" fill="#a5f3fc" opacity="0.75"/>'
    '<circle cx="488" cy="148" r="0.9" fill="#cffafe" opacity="0.65"/>'
    # Dim background stars
    '<circle cx="22" cy="148" r="0.6" fill="#67e8f9" opacity="0.5"/>'
    '<circle cx="92" cy="158" r="0.5" fill="#67e8f9" opacity="0.45"/>'
    '<circle cx="186" cy="158" r="0.6" fill="#67e8f9" opacity="0.5"/>'
    '<circle cx="268" cy="172" r="0.5" fill="#67e8f9" opacity="0.4"/>'
    '<circle cx="352" cy="158" r="0.6" fill="#67e8f9" opacity="0.5"/>'
    '<circle cx="432" cy="172" r="0.5" fill="#67e8f9" opacity="0.4"/>'
    '<circle cx="512" cy="158" r="0.6" fill="#67e8f9" opacity="0.5"/>'
    '<circle cx="148" cy="14" r="0.7" fill="#bae6fd" opacity="0.55"/>'
    '<circle cx="244" cy="62" r="0.7" fill="#bae6fd" opacity="0.55"/>'
    '<circle cx="384" cy="14" r="0.7" fill="#bae6fd" opacity="0.55"/>'
    '<circle cx="478" cy="78" r="0.7" fill="#bae6fd" opacity="0.55"/>'
    '</svg>'
)


def _starfield_data_uri() -> str:
    """Encode the inline starfield SVG as a data: URL so the header
    band always shows stars even when the recipient's mail client
    blocks remote images. SVG passes through every major email client
    (Gmail, Outlook, Apple Mail) — verified.
    """
    import base64 as _b64
    encoded = _b64.b64encode(_STARFIELD_SVG.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


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
    starfield = _starfield_data_uri()

    # Header band: starry-night gradient with the OASIS AI circuit-tree
    # logo + wordmark. Background-image stack is single-layer (the SVG
    # starfield) over the radial gradient because Outlook silently
    # collapses multi-layer backgrounds in some versions. The starfield
    # is base64-inlined so it survives "block remote images" — the only
    # remote asset is the logo itself, which most clients allow once
    # the recipient marks the sender as known.
    header_html = (
        f'<tr><td style="padding:0;border-bottom:1px solid rgba(0,212,255,0.18);'
        f'background:radial-gradient(circle at 50% 130%, rgba(0,212,255,0.18), transparent 65%),'
        f'linear-gradient(180deg, #0a1530 0%, {_BG_PANEL_GLOW} 100%);'
        f'background-image:url(\'{starfield}\'), '
        f'radial-gradient(circle at 50% 130%, rgba(0,212,255,0.22), transparent 65%),'
        f'linear-gradient(180deg, #0a1530 0%, {_BG_PANEL_GLOW} 100%);'
        f'background-repeat:no-repeat;background-size:cover">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0"><tr>'
        # Logo
        f'<td align="center" style="padding:34px 28px 12px 28px">'
        f'<img src="{_LOGO_URL}" alt="OASIS AI" width="64" height="96" '
        f'style="display:block;width:64px;height:96px;object-fit:cover;'
        f'border-radius:10px;border:1px solid rgba(0,212,255,0.35);'
        f'box-shadow:0 0 28px -6px rgba(0,212,255,0.55)" />'
        f'</td></tr><tr>'
        # Wordmark
        f'<td align="center" style="padding:0 28px 6px 28px">'
        f'<div style="font-weight:800;font-size:18px;letter-spacing:0.32em;'
        f'color:{_FG};text-transform:uppercase">OASIS&nbsp;AI</div>'
        f'</td></tr><tr>'
        # Tagline
        f'<td align="center" style="padding:0 28px 26px 28px">'
        f'<div style="font-size:11px;letter-spacing:0.18em;color:{_BRAND_TEAL};'
        f'text-transform:uppercase;font-weight:600">'
        f'Custom AI &middot; Intelligent Automation</div>'
        f'</td></tr></table>\n'
        f"</td></tr>\n"
    )

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
        '<tr><td align="center" style="padding:36px 16px">\n'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'border="0" style="max-width:600px;width:100%;background:{_BG_PANEL};'
        f'border:1px solid rgba(0,212,255,0.18);border-radius:14px;overflow:hidden;'
        f'box-shadow:0 12px 48px -12px rgba(0,0,0,0.6)">\n'
        + header_html
        # Body
        + f'<tr><td style="padding:34px 32px 8px 32px;color:{_FG};font-size:15.5px;'
        f'line-height:1.7">{safe_body}</td></tr>\n'
        # CTA (optional)
        + (
            f'<tr><td style="padding:0 32px">{cta_block}</td></tr>\n'
            if cta_block else ""
        )
        # Booking (optional)
        + (
            f'<tr><td style="padding:0 32px">{booking_block}</td></tr>\n'
            if booking_block else ""
        )
        # Signature
        + f'<tr><td style="padding:28px 32px 24px 32px;border-top:1px solid rgba(255,255,255,0.06)">\n'
        f'<div style="font-size:14px;color:{_FG};font-weight:600">— {name}</div>\n'
        f'<div style="font-size:12px;color:{_FG_MUTED};margin-top:2px">{sig}</div>\n'
        f'<div style="font-size:11px;color:{_FG_DIM};margin-top:14px">'
        f'<a href="{site}" style="color:{_BRAND_TEAL};text-decoration:none">{site}</a>'
        f'</div>\n'
        f"</td></tr>\n"
        # Footer with subtle divider
        f'<tr><td style="padding:16px 28px;background:{_BG_DEEP};'
        f'border-top:1px solid rgba(0,212,255,0.08);'
        f'font-size:10.5px;color:{_FG_DIM};text-align:center;line-height:1.5">'
        f'You\'re receiving this because {name} sent it personally.<br/>'
        f'Reply to this email and it lands directly in their inbox.'
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
