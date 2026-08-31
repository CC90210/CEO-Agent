"""One way to ask "what answered, and who served it?"

Three tools grew their own version of this during the Cloudflare migration and
each made its own call about redirects. That decision is not a detail — getting
it wrong is what let the Vercel-exit gate report two remaining hostnames when
there were five:

  * `www.breezeadvance.credit` 307s to an apex that IS on Workers. Follow the
    hop and you measure the destination; the 307 itself is served by Vercel, and
    cancelling the account kills it.
  * A hostname proxied through Cloudflare resolves to 172.x whatever sits
    behind it, so resolved IPs cannot answer "who serves this" at all. Only the
    response headers can.

So: redirects are NOT followed by default here, and origin is read from the
response rather than inferred from which hostname you chose to probe.

    from lib.http_probe import probe, origin_of
    r = probe("https://example.com/")          # first response only
    r = probe("https://example.com/", follow=True)   # end of the redirect chain
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field

__all__ = ["probe", "origin_of", "Probe", "VERCEL", "WORKERS", "UNKNOWN", "UNREACHABLE"]

VERCEL = "vercel"
WORKERS = "workers"
UNKNOWN = "unknown"
UNREACHABLE = "unreachable"

UA = "bravo-http-probe/1.0"
_CTX = ssl.create_default_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


@dataclass
class Probe:
    url: str
    status: int | None = None
    headers: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None

    @property
    def location(self) -> str | None:
        return self.headers.get("location")

    @property
    def origin(self) -> str:
        return UNREACHABLE if self.error else origin_of(self.headers)


def origin_of(headers: dict) -> str:
    """Who generated this response body?

    `x-vercel-id` is emitted by Vercel's own infrastructure and survives being
    proxied, which is exactly why it is checked FIRST: a response can carry both
    `cf-ray` (Cloudflare fronted it) and `x-vercel-id` (Vercel produced it), and
    reading `cf-ray` alone would call that a Worker. `server:` is checked last
    because a proxy rewrites it.
    """
    h = {k.lower(): v for k, v in (headers or {}).items()}
    if h.get("x-vercel-id") or (h.get("server", "").lower() == "vercel"):
        return VERCEL
    if h.get("cf-ray"):
        return WORKERS
    return UNKNOWN


def probe(url: str, follow: bool = False, timeout: int = 20) -> Probe:
    """Fetch `url` and report status + headers. Never raises.

    `follow` defaults to FALSE on purpose. A redirect is a response somebody
    serves; following it silently attributes the hop to the destination's host.
    Pass follow=True only when the question is "does a user eventually get a
    working page", which is a health question, not an ownership question.
    """
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    opener = (urllib.request.build_opener() if follow
              else urllib.request.build_opener(_NoRedirect))
    try:
        with opener.open(req, timeout=timeout) as r:
            return Probe(url, r.status, dict(r.headers))
    except urllib.error.HTTPError as e:
        # A 4xx/5xx is an ANSWER, not a failure to reach the host — the headers
        # still identify who served it, which is the whole question here.
        return Probe(url, e.code, dict(e.headers))
    except Exception as e:                       # noqa: BLE001 — reported, never raised
        return Probe(url, None, {}, error=f"{type(e).__name__}: {e}")
