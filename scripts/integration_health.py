"""integration_health.py — shared utility for bumping the OASIS Command Center
integrations_health row from any background worker.

Why this exists: the Settings → Integrations page on the Command Center shows
a green dot per service. That dot is honest only if every worker that touches
that service pings the integrations_health row. This module is the one-liner
helper that does it.

Usage from any script:
    from integration_health import ping
    ping("gws", status="healthy")  # Google Workspace (covers Gmail/Calendar/Drive/Docs)
    ping("stripe", status="degraded", error="balance API timed out", metadata={"latency_ms": 4200})

Tenant safety:
- Calls the ping_integration RPC which resolves tenant_id server-side from
  the profile row. Workers don't need to know their tenant_id.

Best-effort by design:
- Never raises. Failures are logged to stderr and swallowed.
- Resolves the operator profile by OPERATOR_EMAIL env var; falls back to the
  canonical CC profile if unset.
- Skips silently if Supabase env vars aren't loaded (e.g. during tests).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _env_fallback(name: str) -> str | None:
    """When os.environ doesn't have the value, scan .env.agents directly.
    Several CLI tools (stripe_tool, supabase_tool, email_engine) read
    .env.agents into a dict but don't push to os.environ — meaning their
    later ping() call would silently fail. Reading the file ourselves
    closes the gap so callers don't need to remember to export.
    """
    candidates = [
        Path.cwd() / ".env.agents",
        Path(__file__).resolve().parent.parent / ".env.agents",
        # Common Bravo-repo home-relative layouts. The pre-rename path
        # ('Business-Empire-Agent') and the legacy Mac landing zone
        # ('Downloads/business-empire-agent') stay in the list so this
        # helper still finds .env.agents on machines that haven't moved
        # to the renamed layout yet.
        Path.home() / "CEO-Agent" / ".env.agents",
        Path.home() / "Business-Empire-Agent" / ".env.agents",
        Path.home() / "Downloads" / "business-empire-agent" / ".env.agents",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
        except Exception:
            continue
    return None

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
        url = os.environ.get("BRAVO_SUPABASE_URL") or _env_fallback("BRAVO_SUPABASE_URL")
        key = (
            os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
            or _env_fallback("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        )
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
