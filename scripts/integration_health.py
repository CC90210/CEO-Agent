"""integration_health.py — shared utility for bumping the OASIS Command Center
integrations_health row from any background worker.

Why this exists: the Settings → Integrations page on the Command Center shows
a green dot per service. That dot is honest only if every worker that touches
that service pings the integrations_health row. This module is the one-liner
helper that does it.

Usage from any script:
    from integration_health import ping
    ping("gmail", status="healthy")
    ping("stripe", status="degraded", error="balance API timed out", metadata={"latency_ms": 4200})

Best-effort by design:
- Never raises. Failures are logged to stderr and swallowed.
- Resolves the operator profile by OPERATOR_EMAIL env var; falls back to the
  canonical CC profile if unset.
- Skips silently if Supabase env vars aren't loaded (e.g. during tests).
"""
from __future__ import annotations

import os
import sys
from typing import Any

# Single source of truth for the canonical operator email
DEFAULT_OPERATOR_EMAIL = "conaugh@oasisai.work"

# Cache the profile_id lookup per process — saves a round-trip on every ping
_cached_profile_id: str | None = None


def _resolve_profile_id(client: Any) -> str | None:
    """Resolve the profile_id for the active operator, cached per process."""
    global _cached_profile_id
    if _cached_profile_id:
        return _cached_profile_id
    email = os.environ.get("OPERATOR_EMAIL", DEFAULT_OPERATOR_EMAIL)
    try:
        r = client.table("user_profiles").select("id").eq("email", email).limit(1).execute()
        if r.data:
            _cached_profile_id = r.data[0]["id"]
            return _cached_profile_id
    except Exception as exc:  # noqa: BLE001
        print(f"[integration_health] profile lookup warning: {exc}", file=sys.stderr)
    return None


def ping(
    service: str,
    *,
    status: str = "healthy",
    error: str | None = None,
    metadata: dict | None = None,
    client: Any = None,
) -> bool:
    """Bump integrations_health for the named service. Returns True on success.

    Args:
        service: e.g. 'gmail' | 'stripe' | 'n8n_inbound' | 'telegram' | 'browser_harness' | 'supabase'
        status:  'healthy' | 'degraded' | 'down' | 'unconfigured'
        error:   optional error string (sets last_error column)
        metadata: optional jsonb payload for context (latency, version, etc.)
        client:   pre-built Supabase client; if None, a fresh one is created from env

    Best-effort — never raises. Returns False if anything failed.
    """
    if metadata is None:
        metadata = {}

    if client is None:
        url = os.environ.get("BRAVO_SUPABASE_URL")
        key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return False  # Tests / unconfigured environments — silently skip
        try:
            from supabase import create_client  # type: ignore

            client = create_client(url, key)
        except Exception as exc:  # noqa: BLE001
            print(f"[integration_health] client init warning: {exc}", file=sys.stderr)
            return False

    profile_id = _resolve_profile_id(client)
    if not profile_id:
        return False

    try:
        client.rpc(
            "ping_integration",
            {
                "p_profile_id": profile_id,
                "p_service": service,
                "p_status": status,
                "p_error": error,
                "p_metadata": metadata,
            },
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        # Best-effort: log + return False, never raise
        print(f"[integration_health] ping {service} warning: {exc}", file=sys.stderr)
        return False
