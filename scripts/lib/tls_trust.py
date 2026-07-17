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


def ensure_os_trust() -> str:
    """Idempotent. Returns which path was taken: 'env-override' | 'truststore'
    | 'certifi' | 'none' (nothing available — system defaults apply)."""
    global _done
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE"):
        return "env-override"
    try:
        import truststore  # type: ignore

        if not _done:
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
