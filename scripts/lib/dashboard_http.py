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
    user_agent: str | None = None,
) -> urllib.request.Request:
    """Build a urllib Request to the dashboard with the User-Agent forced on.

    The UA is applied LAST and unconditionally. A caller that passes its own
    user-agent HEADER does not get to reinstate the banned default by accident,
    and a caller that forgets one cannot ship a request the edge will drop.

    `user_agent` is the one deliberate exception, and it exists for exactly one
    caller: the canary that checks whether the Cloudflare skip rule still works.
    That check is only meaningful when it sends the User-Agent Cloudflare BANS -
    our own would sail through with or without the rule, making it a test that
    can never fail. Naming the parameter is the point: an override has to be
    asked for in writing, while the accident this module exists to prevent
    remains impossible.
    """
    hdrs = dict(headers or {})
    # Header names are case-insensitive over the wire but not in this dict, so
    # drop any caller-supplied spelling before setting ours.
    for k in [k for k in hdrs if k.lower() == "user-agent"]:
        hdrs.pop(k)
    hdrs["User-Agent"] = user_agent or OASIS_UA
    return urllib.request.Request(url, data=data, headers=hdrs, method=method)


# The User-Agent Cloudflare bans by signature. Named so the canary reads as what
# it is, and so nobody has to rediscover which string triggers a 1010.
BANNED_PROBE_UA = "Python-urllib/3.12"


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


def _looks_like_cloudflare(text: str) -> bool:
    return any(marker in text for marker in _CF_BODY_MARKERS)


# Cloudflare answers these when it is busy or briefly down, not when it has
# decided something about us. They clear on their own, so they must stay
# retryable - treating them as terminal would throw away a finished extraction
# over a thirty-second throttle (Codex review, 2026-09-15).
_TRANSIENT_EDGE_STATUSES = (429, 503)
_TERMINAL_EDGE_STATUSES = (403,)


def classify_edge_block(status: int, body: str | None) -> str | None:
    """Return a stable edge-block reason, or None if our app actually answered.

    None does NOT mean success - it means the response came from the dashboard
    and the caller's normal status handling applies.

    Pair every use with edge_block_is_transient(): a policy ban needs a human, a
    throttle needs another attempt, and collapsing the two loses jobs in one
    direction or hammers a ban in the other.
    """
    if status not in _TRANSIENT_EDGE_STATUSES + _TERMINAL_EDGE_STATUSES:
        return None
    text = (body or "").lower()

    if status in _TRANSIENT_EDGE_STATUSES:
        # Still confirm the EDGE answered rather than our app: our routes can
        # legitimately return 429 from their own rate limiter, and that is the
        # dashboard talking, not Cloudflare.
        if _looks_like_cloudflare(text) or not text.lstrip().startswith("{"):
            return f"edge_transient_{status}"
        return None

    m = re.search(r"error code:\s*(\d{3,4})", text)
    if m:
        return f"cloudflare_{m.group(1)}"
    if _looks_like_cloudflare(text):
        return "cloudflare_challenge"
    # Our routes answer JSON, always. A 403 that is not JSON did not come from us.
    if not text.lstrip().startswith("{"):
        return "edge_non_json_403"
    return None


def edge_block_is_transient(reason: str | None) -> bool:
    """True when the edge was busy rather than when it decided something.

    Callers use this to choose between a bounded retry and going terminal. It
    reads the reason string alone so the decision travels with the reason
    through a database column and a log line.
    """
    return bool(reason) and reason.startswith("edge_transient_")


def edge_block_help(reason: str) -> str:
    """Operator-facing sentence for an edge block. Names the action, not the code."""
    if reason.startswith("edge_transient_"):
        return (
            f"Cloudflare was busy or briefly down ({reason}); the dashboard never saw "
            "the request. This clears by itself - the job stays queued and retries."
        )
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
