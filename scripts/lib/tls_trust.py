"""tls_trust.py — one-call Windows/OS TLS trust setup for every network tool.

The 2026-07-17 CA-bundle lesson: on this Windows fleet, Python's bundled
certifi roots miss what the OS store has, so direct HTTPS calls die with
CERTIFICATE_VERIFY_FAILED (hit Supabase cron/heartbeat first, then
vercel_env_tool). The fix is the OS trust store via `truststore`, with a
certifi env-var fallback — but as of extraction it existed as four separate
inline copies (agent_heartbeat, cron_engine, email_validate_tool,
vercel_env_tool) while 30+ other HTTPS-calling scripts had none.

CANONICAL PATTERN for any script that talks HTTPS (requests/httpx/urllib):

    from lib.tls_trust import ensure_os_trust
    ensure_os_trust()   # call once, before the first network call

Behavior (mirrors agent_heartbeat._configure_ca_bundle, the fullest copy):
- Respects an operator override: if SSL_CERT_FILE or REQUESTS_CA_BUNDLE is
  already set, does nothing.
- Prefers `truststore.inject_into_ssl()` (OS store — the real fix).
- Falls back to pointing SSL_CERT_FILE/REQUESTS_CA_BUNDLE at certifi.
- Never raises; safe to call multiple times.
"""
from __future__ import annotations

import os

_done = False


def _genuine_override() -> str | None:
    """Return an operator-supplied CA bundle path worth honouring, else None.

    The plain "is SSL_CERT_FILE set?" test was too permissive (2026-07-28
    incident). Two paths do NOT represent operator intent and must not
    suppress the OS-store fix:

    * a path that no longer exists — a stale value inherited from a
      long-running parent, not a live choice;
    * certifi's own bundle — that is merely Python's default written out
      explicitly, and on this fleet it is exactly what CANNOT verify the
      AV-scanner-MITM'd chain.

    A real corporate bundle (exists, and isn't certifi's) still wins.

    Both vars are inspected INDEPENDENTLY. An earlier draft used
    `SSL_CERT_FILE or REQUESTS_CA_BUNDLE`, which read only the first non-empty
    one — so a stale SSL_CERT_FILE alongside a valid REQUESTS_CA_BUNDLE was
    judged "not genuine" and the caller then deleted BOTH, destroying a real
    corporate bundle. Either var holding a real bundle now protects both.
    """
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        raw = os.environ.get(var)
        if not raw:
            continue
        try:
            candidate = os.path.realpath(raw)
            if not os.path.isfile(candidate):
                continue
            try:
                import certifi  # type: ignore

                if candidate == os.path.realpath(certifi.where()):
                    continue
            except ImportError:
                pass
            return raw
        except OSError:
            continue
    return None


def ensure_os_trust() -> str:
    """Idempotent. Returns which path was taken: 'env-override' | 'truststore'
    | 'certifi' | 'none' (nothing available — system defaults apply)."""
    global _done
    if _genuine_override():
        return "env-override"
    try:
        import truststore  # type: ignore

        if not _done:
            # Drop the ineffective bundle vars before injecting. requests/httpx
            # read REQUESTS_CA_BUNDLE/SSL_CERT_FILE and pass the path down as an
            # explicit verify= target, which would re-pin the very certifi store
            # we just established cannot verify this box's chain — the OS-store
            # injection alone would be silently overridden.
            for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
                os.environ.pop(var, None)
            truststore.inject_into_ssl()
            _done = True
        return "truststore"
    except Exception:  # noqa: BLE001 — ImportError or injection failure
        pass
    try:
        import certifi  # type: ignore

        ca_path = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
        return "certifi"
    except ImportError:
        return "none"
