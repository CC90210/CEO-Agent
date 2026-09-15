"""The ONE way VPS code talks to the OASIS dashboard over HTTP.

oasisai.work sits behind Cloudflare. Cloudflare's Browser Integrity Check bans
Python's DEFAULT urllib User-Agent ("Python-urllib/3.x") by signature: it
answers 403 with the body "error code: 1010" BEFORE the request ever reaches
Next.js. No amount of correct HMAC helps, because nothing of ours runs.

That is exactly how the application-drop feature broke on 2026-09-15. Every
extraction finished correctly and every callback was refused at the edge. Worse,
the daemon recorded it as `dashboard_rejected_signature_403` - which is false,
the signature was never evaluated - and that wrong label is what made an
infrastructure block look like an application bug. Reproduced from the VPS
itself, same second, same URL:

    curl -A 'curl/8.5.0'           -> 401 {"ok":false,"error":"bad_signature"}
    curl -A 'python-requests/2.31' -> 401 {"ok":false,"error":"bad_signature"}
    curl -A 'Python-urllib/3.12'   -> 403 error code: 1010

Two rules, both enforced HERE instead of at ~40 call sites:

  1. Every dashboard request carries an explicit, identifying User-Agent. Any
     value but the urllib default survives the check; an identifying one also
     means the Cloudflare logs name us instead of showing an anonymous bot.

  2. An edge rejection is classified as an EDGE rejection and never as an
     application-level auth failure. `classify_edge_block()` is the single place
     that knows what a Cloudflare denial looks like, so no caller has to guess.

Do not build a urllib Request to the dashboard anywhere else.
`tests/test_dashboard_ua.py` fails the build if you do, and that test plants a
violation of its own to prove it still fires.
"""

from __future__ import annotations

import re
import urllib.request

# Identifying, stable, and - the whole point - not the urllib default.
# Bumping this string is safe. Removing it is not.
OASIS_UA = "oasis-vps-agent/1.0 (+https://oasisai.work; internal-hmac)"


def dashboard_request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str = "POST",
) -> urllib.request.Request:
    """Build a urllib Request to the dashboard with the User-Agent forced on.

    The UA is applied LAST and unconditionally. A caller that passes its own
    user-agent header does not get to reinstate the banned default by accident,
    and a caller that forgets one cannot ship a request the edge will drop.
    """
    hdrs = dict(headers or {})
    # Header names are case-insensitive over the wire but not in this dict, so
    # drop any caller-supplied spelling before setting ours.
    for k in [k for k in hdrs if k.lower() == "user-agent"]:
        hdrs.pop(k)
    hdrs["User-Agent"] = OASIS_UA
    return urllib.request.Request(url, data=data, headers=hdrs, method=method)


# Markers that mean "Cloudflare answered, our app did not". Checked against the
# BODY, not just the status: a 403 from our own code is JSON we emitted, while
# an edge denial is Cloudflare's HTML error page. Status alone cannot tell them
# apart, and conflating them is the mislabel this module exists to prevent.
_CF_BODY_MARKERS = (
    "cloudflare",
    "attention required",
    "cf-error-details",
    "__cf_chl",
    "ray id",
)


def classify_edge_block(status: int, body: str | None) -> str | None:
    """Return a stable edge-block reason, or None if our app actually answered.

    None does NOT mean success - it means the response came from the dashboard
    and the caller's normal status handling applies.
    """
    if status not in (403, 429, 503):
        return None
    text = (body or "").lower()

    m = re.search(r"error code:\s*(\d{3,4})", text)
    if m:
        return f"cloudflare_{m.group(1)}"
    if any(marker in text for marker in _CF_BODY_MARKERS):
        return "cloudflare_challenge"
    # Our routes answer JSON, always. A 403 that is not JSON did not come from us.
    if status == 403 and not text.lstrip().startswith("{"):
        return "edge_non_json_403"
    return None


def edge_block_help(reason: str) -> str:
    """Operator-facing sentence for an edge block. Names the action, not the code."""
    if reason == "cloudflare_1010":
        return (
            "Cloudflare banned this request by browser signature (1010). Something is "
            "sending the default Python urllib User-Agent again - route it through "
            "scripts/lib/dashboard_http.dashboard_request()."
        )
    return (
        f"Cloudflare refused the request at the edge ({reason}); the dashboard never saw it. "
        "Check the WAF skip rule for /api/internal/* from this server's IP."
    )
