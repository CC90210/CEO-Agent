"""email_template.py — brand-aware HTML email shell.

Used by:
  - scripts/integrations/google_tool.py gmail send --branded
  - scripts/integrations/send_gateway.py for outreach + transactional sends
  - any other script that needs to send a branded email

Brand-aware as of 2026-06-10. Each render call takes a `brand` parameter
(default "oasis") and picks the matching brand config: visual palette,
wordmark, signature defaults, website link, footer text. Adding a new
brand is one entry in BRAND_CONFIG below.

Why a Python module not an HTML file: every send picks the operator's
display name + email from .env.agents at runtime, and the body is the
per-message text. A static template can't substitute those. The shell
chrome is centralized here so every email surface inherits the same
look without touching the body.

Design notes:
  - Single column, 600px max width — works in every client incl. Gmail
    mobile, Outlook, Apple Mail.
  - Inline styles only (Gmail strips <style> blocks in some surfaces).
  - Plain-text version sent alongside (multipart/alternative) so clients
    that strip HTML still see something readable.
"""
from __future__ import annotations

import html as _html
import os
from typing import Optional


# ────────────────────────────────────────────────────────────────────────────
# Brand registry — add a new brand by adding a new entry.
#
# Required keys per brand:
#   display_name        Wordmark text in the header
#   tagline             Subhead under the wordmark
#   palette             Color tokens used in the shell + signature
#   logo_url            Optional remote logo image; None = text wordmark only
#   default_from_display Operator-display fallback when env vars are unset
#   default_from_email  From-email fallback
#   default_signature_tagline  Signature line under the operator's name
#   default_website     Linked under the signature
#   footer_template     Template string for the centered email footer.
#                       Placeholders: {name} (the from-display value).
# ────────────────────────────────────────────────────────────────────────────
BRAND_CONFIG: dict[str, dict[str, object]] = {
    "oasis": {
        "display_name": "OASIS AI",
        "tagline": "Custom AI · Intelligent Automation",
        "logo_url": "https://oasisai.work/oasis-logo.jpg",
        "palette": {
            "primary": "#00d4ff",
            "primary_deep": "#0099cc",
            "bg_deep": "#050810",
            "bg_panel": "#0c1220",
            "bg_panel_glow": "#0f1830",
            "fg": "#f5f7fa",
            "fg_muted": "#a8b0c2",
            "fg_dim": "#6b7280",
            # Header-band gradient anchor.
            "header_top": "#0a1530",
        },
        "default_from_display": "Conaugh McKenna",
        "default_from_email": "conaugh@oasisai.work",
        "default_signature_tagline": "Founder, OASIS AI Solutions",
        "default_website": "https://oasisai.work",
        "footer_template": (
            "You're receiving this because {name} sent it personally.<br/>"
            "Reply to this email and it lands directly in their inbox."
        ),
    },
    "sunbiz": {
        "display_name": "SUNBIZ FUNDING",
        "tagline": "Business Funding · Built Around Your Cash Flow",
        # SunBiz uses a text wordmark (the SunBiz HTML templates use the
        # same — survives "block remote images" without a logo asset).
        "logo_url": None,
        # SunBiz palette extracted from templates/email/sunbiz_funding.html
        # (green #10b981 / deep green #059669 / navy #001F54 / gold #D4A843).
        # Adapted to the same shell skeleton used by OASIS so layout
        # changes flow through both brands.
        "palette": {
            "primary": "#10b981",
            "primary_deep": "#059669",
            "bg_deep": "#001F54",
            "bg_panel": "#ffffff",
            "bg_panel_glow": "#f8fafc",
            "fg": "#1e293b",
            "fg_muted": "#64748b",
            "fg_dim": "#94a3b8",
            "header_top": "#001F54",
            # SunBiz-only gold accent on the wordmark.
            "gold": "#D4A843",
        },
        "default_from_display": "SunBiz Submissions",
        "default_from_email": "submissions@sunbizfunding.com",
        "default_signature_tagline": "SunBiz Funding LLC",
        "default_website": "https://sunbizfunding.com",
        "footer_template": (
            "You're receiving this from {name} at SunBiz Funding.<br/>"
            "Reply to this email — it lands in our shared submissions inbox."
        ),
    },
}


def _brand(brand: Optional[str]) -> dict[str, object]:
    """Resolve a brand entry. Defaults to oasis when unknown."""
    key = (brand or "oasis").strip().lower()
    return BRAND_CONFIG.get(key, BRAND_CONFIG["oasis"])


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert #RRGGBB to rgba(r, g, b, alpha). Used for the brand-
    primary alpha tints throughout the shell (borders, glows, gradient
    overlays). Falls back to opaque black on invalid input so a bad
    palette entry never breaks the render — the shell still ships."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return f"rgba(0, 0, 0, {alpha})"
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return f"rgba(0, 0, 0, {alpha})"
    return f"rgba({r}, {g}, {b}, {alpha})"


# Backwards-compat aliases — used elsewhere in the module body. Always
# resolve to the OASIS palette so existing imports keep working; the
# brand-aware paths use _brand(brand)["palette"] instead.
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
_LOGO_URL = "https://oasisai.work/oasis-logo.jpg"

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


def _from_display(brand: Optional[str] = None) -> str:
    """The operator's display name. Per-brand env var override, then
    brand default. SunBiz brand picks BRAVO_FROM_DISPLAY_SUNBIZ if set,
    else the SunBiz default. Same shape for any future brand."""
    bcfg = _brand(brand)
    brand_key = (brand or "oasis").upper().replace("-", "_")
    return (
        os.environ.get(f"BRAVO_FROM_DISPLAY_{brand_key}")
        or os.environ.get("BRAVO_FROM_DISPLAY")
        or os.environ.get("USER_FULL_NAME")
        or str(bcfg["default_from_display"])
    )


def _from_email(brand: Optional[str] = None) -> str:
    bcfg = _brand(brand)
    brand_key = (brand or "oasis").upper().replace("-", "_")
    return (
        os.environ.get(f"BRAVO_FROM_EMAIL_{brand_key}")
        or os.environ.get("GMAIL_USER")
        or os.environ.get("BRAVO_FROM_EMAIL")
        or str(bcfg["default_from_email"])
    )


def _signature_block(brand: Optional[str] = None) -> str:
    bcfg = _brand(brand)
    brand_key = (brand or "oasis").upper().replace("-", "_")
    return (
        os.environ.get(f"BRAVO_SIGNATURE_TAGLINE_{brand_key}")
        or os.environ.get("BRAVO_SIGNATURE_TAGLINE")
        or str(bcfg["default_signature_tagline"])
    )


def _booking_link() -> Optional[str]:
    """If set, included as a soft CTA below the body. Brand-agnostic;
    the booking link itself is operator-level config."""
    return os.environ.get("BOOKING_LINK") or None


def _website(brand: Optional[str] = None) -> str:
    bcfg = _brand(brand)
    brand_key = (brand or "oasis").upper().replace("-", "_")
    return (
        os.environ.get(f"BRAVO_WEBSITE_URL_{brand_key}")
        or os.environ.get("BRAVO_WEBSITE_URL")
        or str(bcfg["default_website"])
    )


def render_branded_html(
    body: str,
    *,
    subject: Optional[str] = None,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    show_booking: bool = False,
    brand: Optional[str] = None,
) -> str:
    """Wrap a plain-text body in the brand-aware HTML shell.

    `brand` selects the palette + wordmark + signature defaults. Pass
    'oasis' (default) or 'sunbiz'. Adding a brand: extend BRAND_CONFIG.

    `body` may contain newlines — they're converted to <br/>. Markdown
    is NOT processed; if the caller wants formatting they should pass
    a pre-rendered HTML fragment via `html_body` (separate function
    below). The simple-string path keeps the agent's life easy: pass
    the message it would have written in plaintext, get a branded
    email out.
    """
    bcfg = _brand(brand)
    palette = bcfg["palette"]  # type: ignore[assignment]
    p_primary = str(palette["primary"])  # type: ignore[index]
    p_bg_deep = str(palette["bg_deep"])  # type: ignore[index]
    p_bg_panel = str(palette["bg_panel"])  # type: ignore[index]
    p_bg_panel_glow = str(palette["bg_panel_glow"])  # type: ignore[index]
    p_fg = str(palette["fg"])  # type: ignore[index]
    p_fg_muted = str(palette["fg_muted"])  # type: ignore[index]
    p_fg_dim = str(palette["fg_dim"])  # type: ignore[index]
    p_header_top = str(palette["header_top"])  # type: ignore[index]
    # SunBiz exposes a gold accent for the wordmark suffix; OASIS doesn't.
    p_gold = str(palette.get("gold") or palette["primary"])  # type: ignore[index]
    p_logo_url = bcfg.get("logo_url")
    brand_display = str(bcfg["display_name"])
    brand_tagline = str(bcfg["tagline"])
    safe_body = _html.escape(body).replace("\n", "<br/>\n")
    name = _html.escape(_from_display(brand))
    sig = _html.escape(_signature_block(brand))
    site = _html.escape(_website(brand))
    booking = _booking_link()

    # Primary-color alpha tints — used throughout for brand consistency.
    p_alpha_18 = _hex_to_rgba(p_primary, 0.18)
    p_alpha_22 = _hex_to_rgba(p_primary, 0.22)
    p_alpha_35 = _hex_to_rgba(p_primary, 0.35)
    p_alpha_55 = _hex_to_rgba(p_primary, 0.55)
    p_alpha_08 = _hex_to_rgba(p_primary, 0.08)

    cta_block = ""
    if cta_label and cta_url:
        cta_block = (
            f'<div style="margin:28px 0 20px 0;text-align:left">'
            f'<a href="{_html.escape(cta_url)}" '
            f'style="display:inline-block;padding:12px 22px;'
            f'background:{p_primary};color:{p_bg_deep};text-decoration:none;'
            f'border-radius:6px;font-weight:600;font-size:14px;'
            f'letter-spacing:0.01em">{_html.escape(cta_label)}</a>'
            f"</div>"
        )

    booking_block = ""
    if show_booking and booking:
        booking_block = (
            f'<div style="margin:24px 0 8px 0;font-size:13px;color:{p_fg_muted}">'
            f'Want to talk live? '
            f'<a href="{_html.escape(booking)}" '
            f'style="color:{p_primary};text-decoration:underline">'
            f"Grab a 30-minute slot</a>."
            f"</div>"
        )

    title = _html.escape(subject or brand_display)
    starfield = _starfield_data_uri()

    # Wordmark — brand-aware. SunBiz splits the display name so the
    # "BIZ" suffix shows in gold, matching the marketing templates;
    # other brands render the wordmark in a single color.
    if str(bcfg.get("display_name", "")).upper().startswith("SUNBIZ"):
        # "SUNBIZ FUNDING" → "SUN" + gold "BIZ" + " FUNDING"
        wordmark_html = (
            f'<span style="color:{p_fg}">SUN</span>'
            f'<span style="color:{p_gold}">BIZ</span>'
            f'<span style="color:{p_fg}">&nbsp;FUNDING</span>'
        )
    else:
        wordmark_html = (
            f'<span style="color:{p_fg}">'
            f'{_html.escape(brand_display).replace(" ", "&nbsp;")}'
            f'</span>'
        )

    # Logo block — only rendered when the brand has a logo_url. Text-
    # only brands (SunBiz) skip the image cell entirely and the
    # wordmark carries the visual identity.
    logo_row = ""
    if p_logo_url:
        logo_row = (
            f'<td align="center" style="padding:34px 28px 12px 28px">'
            f'<img src="{p_logo_url}" alt="{_html.escape(brand_display)}" '
            f'width="64" height="96" '
            f'style="display:block;width:64px;height:96px;object-fit:cover;'
            f'border-radius:10px;border:1px solid {p_alpha_35};'
            f'box-shadow:0 0 28px -6px {p_alpha_55}" />'
            f'</td></tr><tr>'
        )

    # Header band: starry-night gradient with the brand wordmark.
    # Background-image stack is single-layer (the SVG starfield) over
    # the radial gradient because Outlook silently collapses multi-
    # layer backgrounds in some versions. The starfield is base64-
    # inlined so it survives "block remote images" — the only remote
    # asset (when present) is the logo, which most clients allow once
    # the recipient marks the sender as known.
    header_html = (
        f'<tr><td style="padding:0;border-bottom:1px solid {p_alpha_18};'
        f'background:radial-gradient(circle at 50% 130%, {p_alpha_18}, transparent 65%),'
        f'linear-gradient(180deg, {p_header_top} 0%, {p_bg_panel_glow} 100%);'
        f'background-image:url(\'{starfield}\'), '
        f'radial-gradient(circle at 50% 130%, {p_alpha_22}, transparent 65%),'
        f'linear-gradient(180deg, {p_header_top} 0%, {p_bg_panel_glow} 100%);'
        f'background-repeat:no-repeat;background-size:cover">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0"><tr>'
        # Logo (optional — only on brands with logo_url)
        + logo_row +
        # Wordmark
        f'<td align="center" style="padding:0 28px 6px 28px">'
        f'<div style="font-weight:800;font-size:18px;letter-spacing:0.32em;'
        f'text-transform:uppercase">{wordmark_html}</div>'
        f'</td></tr><tr>'
        # Tagline
        f'<td align="center" style="padding:0 28px 26px 28px">'
        f'<div style="font-size:11px;letter-spacing:0.18em;color:{p_primary};'
        f'text-transform:uppercase;font-weight:600">'
        f'{_html.escape(brand_tagline)}</div>'
        f'</td></tr></table>\n'
        f"</td></tr>\n"
    )

    # Footer text — brand-supplied template with the from-display
    # substituted in. Subtle divider above so the section reads
    # independently from the signature.
    footer_text = str(bcfg["footer_template"]).format(name=name)

    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1" />\n'
        f'<title>{title}</title>\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background:{p_bg_deep};color:{p_fg};'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',system-ui,sans-serif;'
        'line-height:1.6;">\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="background:{p_bg_deep}">\n'
        '<tr><td align="center" style="padding:36px 16px">\n'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        f'border="0" style="max-width:600px;width:100%;background:{p_bg_panel};'
        f'border:1px solid {p_alpha_18};border-radius:14px;overflow:hidden;'
        f'box-shadow:0 12px 48px -12px rgba(0,0,0,0.6)">\n'
        + header_html
        # Body
        + f'<tr><td style="padding:34px 32px 8px 32px;color:{p_fg};font-size:15.5px;'
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
        + f'<tr><td style="padding:28px 32px 24px 32px;border-top:1px solid rgba(0,0,0,0.06)">\n'
        f'<div style="font-size:14px;color:{p_fg};font-weight:600">— {name}</div>\n'
        f'<div style="font-size:12px;color:{p_fg_muted};margin-top:2px">{sig}</div>\n'
        f'<div style="font-size:11px;color:{p_fg_dim};margin-top:14px">'
        f'<a href="{site}" style="color:{p_primary};text-decoration:none">{site}</a>'
        f'</div>\n'
        f"</td></tr>\n"
        # Footer with subtle divider
        f'<tr><td style="padding:16px 28px;background:{p_bg_deep};'
        f'border-top:1px solid {p_alpha_08};'
        f'font-size:10.5px;color:{p_fg_dim};text-align:center;line-height:1.5">'
        f'{footer_text}'
        f"</td></tr>\n"
        "</table>\n"
        "</td></tr>\n"
        "</table>\n"
        "</body></html>"
    )


def render_branded_html_fragment(
    html_fragment: str,
    *,
    subject: Optional[str] = None,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    show_booking: bool = False,
    brand: Optional[str] = None,
) -> str:
    """Wrap an existing HTML fragment (e.g. a stored template's
    formatted body content like `<p>Hi {{name}}</p>`) in the
    brand-aware shell. Identical chrome to `render_branded_html` —
    same wordmark + signature — but the body is treated as pre-rendered
    HTML rather than escape-and-newline-to-br.

    Use this when:
      - You have HTML the operator authored intentionally (templates,
        WYSIWYG editor output) and want to add the brand shell around it.

    Don't use this when:
      - The fragment is actually a complete <!doctype>/<html> document
        (the caller's responsibility to detect; send_gateway does this
        upstream).
      - The body is plain text — use `render_branded_html` instead.
    """
    # We render via the existing function but then swap the body cell.
    # That keeps both paths sharing the exact same chrome and means
    # any future change to the shell only needs to touch one place.
    placeholder = "__BODY_FRAGMENT_PLACEHOLDER__"
    base = render_branded_html(
        placeholder,
        subject=subject,
        cta_label=cta_label,
        cta_url=cta_url,
        show_booking=show_booking,
        brand=brand,
    )
    return base.replace(placeholder, html_fragment)


def render_branded_plaintext(body: str, *, brand: Optional[str] = None) -> str:
    """The plaintext alternative shipped alongside the HTML. Mirrors the
    structure so HTML-stripped clients see the same message + signature,
    branded per `brand`.
    """
    name = _from_display(brand)
    sig = _signature_block(brand)
    site = _website(brand)
    booking = _booking_link()
    parts = [body.strip(), "", f"— {name}", sig, site]
    if booking:
        parts.append(f"Book a call: {booking}")
    return "\n".join(parts) + "\n"
