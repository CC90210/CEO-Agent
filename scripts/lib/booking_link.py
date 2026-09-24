"""booking_link.py — the one place the Python side resolves the "pick a time" link.

Python twin of oasis-command-center `lib/booking-link.ts`. One list per stack,
parity asserted by tests/test_booking_link.py (same pattern as tenant_brand).

WHAT WENT WRONG (2026-09-24, a real Instagram prospect)
-------------------------------------------------------
The command center retired this link on 2026-09-09:

    https://calendar.app.google/tpfvJYBGircnGu8G8

That appointment schedule was deleted; Google renders "Appointment not found".
The TypeScript side stopped shipping it. The Python side never did: it lived on
as `email_playbook.BOOKING_LINK`, a module constant frozen at import, and it
was inlined into every Instagram DM system prompt as "the ONLY booking
mechanism". On 2026-09-24T16:24:35Z the DM bot told a prospect who said "next
week" to "grab whatever slot fits you here:" and handed over the dead page.

WHY A RESOLVER AND NOT A NEW CONSTANT
------------------------------------
A default URL is a promise that some address always works, and no code can keep
that promise about a page owned by a calendar UI one click away from deletion.
So absent is representable: `resolve_booking_url()` answers "" when nothing
usable is configured, and every caller decides what to do without a link. It is
read at CALL time, never frozen at import, so fixing the env fixes every caller
on its next run.

The retired value is refused BY NAME, even when explicitly configured, because
it is still in git history, old emails and env backups — the single most likely
value for someone to "restore". Delete an entry only when that link is verified
working again, and delete it from lib/booking-link.ts in the same change.

Shape only, no network: this cannot tell a live schedule from a deleted one.
"""

from __future__ import annotations

import os
import sys
from typing import Mapping, Optional
from urllib.parse import urlsplit

# Checked in order; the first USABLE one wins. A superset of the TypeScript
# list: BOOKING_LINK / BOOKING_MEET_LINK are the names the Python scripts have
# always read, so they lead.
BOOKING_URL_ENV_KEYS: tuple[str, ...] = (
    "BOOKING_LINK",
    "BOOKING_MEET_LINK",
    "NEXT_PUBLIC_BOOKING_URL",
    "NEXT_PUBLIC_FOUNDER_BOOKING_URL",
    "OASIS_FOUNDER_BOOKING_URL",
)

# Known-dead links, compared lowercased with trailing slashes stripped. MUST
# equal RETIRED_BOOKING_URLS in oasis-command-center lib/booking-link.ts.
RETIRED_BOOKING_URLS: frozenset[str] = frozenset({
    "https://calendar.app.google/tpfvjybgircngu8g8",
})


def _normalise(raw: str) -> str:
    return (raw or "").strip().lower().rstrip("/")


def is_retired_booking_url(raw: Optional[str]) -> bool:
    """True when `raw` is a retired link (case and trailing slash ignored)."""
    return _normalise(raw or "") in RETIRED_BOOKING_URLS


def is_usable_booking_url(raw: Optional[str]) -> bool:
    """https, has a hostname, and not retired. Shape only — no network."""
    url = (raw or "").strip()
    if not url or is_retired_booking_url(url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:  # malformed (e.g. an unclosed IPv6 bracket): not usable
        return False
    # https only: this link is handed to strangers.
    return parts.scheme == "https" and bool(host)


def contains_retired_booking_url(text: Optional[str]) -> bool:
    """True when `text` mentions a retired link anywhere, with or without scheme.

    For copy linters: a model that learned the dead link from an old prompt or
    thread can write it back out as "calendar.app.google/..." with no https.
    """
    lowered = (text or "").lower()
    return any(url.split("://", 1)[-1] in lowered for url in RETIRED_BOOKING_URLS)


def _first_usable(env: Mapping[str, str]) -> str:
    for key in BOOKING_URL_ENV_KEYS:
        value = (env.get(key) or "").strip()
        if value and is_usable_booking_url(value):
            return value
    return ""


def _env_file_values() -> dict[str, str]:
    """The booking keys as the audited secret loader sees them (.env.agents).

    A seam: tests replace it so no test depends on the machine's env file.
    Values are returned to the caller, never printed.
    """
    from lib.secret_loader import SecretLoaderRefused, get  # noqa: PLC0415

    out: dict[str, str] = {}
    for key in BOOKING_URL_ENV_KEYS:
        try:
            value = get(key)
        except SecretLoaderRefused as exc:
            # Interactive shell: the loader refuses by policy. Say so rather
            # than pretending the file had nothing; os.environ was still read.
            print(f"[booking_link] env-file fallback refused ({exc}); "
                  "resolved from os.environ only", file=sys.stderr)
            return {}
        if value:
            out[key] = value
    return out


def _sources(env: Optional[Mapping[str, str]]) -> list[Mapping[str, str]]:
    if env is not None:
        return [env]
    return [os.environ, _env_file_values()]


def resolve_booking_url(env: Optional[Mapping[str, str]] = None) -> str:
    """The configured booking link, or "" when there is not a usable one.

    "" is a real answer, not a failure; callers MUST handle it. With env=None,
    os.environ is checked first and the env file only when os.environ has
    nothing usable.
    """
    if env is not None:
        return _first_usable(env)
    found = _first_usable(os.environ)
    if found:
        return found
    return _first_usable(_env_file_values())


def booking_url_misconfigured(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when a value was configured but every configured value is refused.

    Tells "nobody set it" apart from "somebody set the dead one again".
    """
    configured = [
        (src.get(key) or "").strip()
        for src in _sources(env)
        for key in BOOKING_URL_ENV_KEYS
    ]
    configured = [v for v in configured if v]
    if not configured:
        return False
    return not any(is_usable_booking_url(v) for v in configured)
