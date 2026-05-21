"""_outbound_log_post.py — single-source helper for write-back to the dashboard.

send_gateway.py used to write directly to lead_interactions via the Supabase
client, but it never set tenant_id on the row. The dashboard's Pipeline +
Activity Tape filter by tenant_id, so recent sends were invisible — the UI
fell back to older gmail_historical_backfill rows that DID carry the tenant.
"Recent Outbound" lied with 8d-old data while real sends happened hours ago.

This module routes send-confirmations through /api/outbound/log instead. The
route validates HMAC, resolves tenant from the profile, and atomically writes
lead_interactions + agent_events. One call, both surfaces light up.

Auth env vars (read from .env.agents):
    OASIS_DASHBOARD_URL          — e.g. https://agent-dashboard-cc90210.vercel.app
    OASIS_PROFILE_ID             — operator's user_profiles.id (uuid)
    OASIS_OUTBOUND_HMAC_SECRET   — raw secret issued by n8n_webhook_secret.py

If any of those are missing, post_outbound_log() returns (False, None,
"missing_env") WITHOUT raising — send_gateway should not crash because the
operator hasn't configured write-back yet. It logs a one-time hint to stderr.

Issuance one-liner:
    python scripts/integrations/n8n_webhook_secret.py issue \\
        --profile-email <operator_email> \\
        --label "outbound-engine"
Then save secret + profile_id to .env.agents under the names above.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

DEFAULT_DASHBOARD_URL = "https://agent-dashboard-cc90210.vercel.app"
TIMEOUT_SECONDS = 8

_warned_missing_env = False


def _hint_once(reason: str) -> None:
    """Print the missing-env hint exactly once per process so a high-volume
    send loop doesn't flood stderr."""
    global _warned_missing_env
    if _warned_missing_env:
        return
    _warned_missing_env = True
    print(
        f"[outbound_log] write-back disabled ({reason}). To enable:\n"
        f"  1. python scripts/integrations/n8n_webhook_secret.py issue --profile-email <you> --label outbound\n"
        f"  2. Add to .env.agents:\n"
        f"     OASIS_DASHBOARD_URL=https://agent-dashboard-cc90210.vercel.app\n"
        f"     OASIS_PROFILE_ID=<from issue output>\n"
        f"     OASIS_OUTBOUND_HMAC_SECRET=<raw secret from issue output>",
        file=sys.stderr,
    )


def post_outbound_log(
    *,
    to_email: str,
    subject: str,
    body_preview: str = "",
    lead_id: Optional[str] = None,
    status: str = "sent",
    channel: str = "email",
    agent_source: str = "send_gateway",
    sent_at: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    existing_interaction_id: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[str]]:
    """POST a send-confirmation to /api/outbound/log.

    Returns (ok, interaction_id, error). Never raises — caller is the
    send-loop and should not crash on a write-back failure.
    """
    profile_id = (os.environ.get("OASIS_PROFILE_ID") or "").strip()
    secret = (os.environ.get("OASIS_OUTBOUND_HMAC_SECRET") or "").strip()
    base_url = (os.environ.get("OASIS_DASHBOARD_URL") or DEFAULT_DASHBOARD_URL).rstrip("/")

    if not profile_id or not secret:
        _hint_once("OASIS_PROFILE_ID or OASIS_OUTBOUND_HMAC_SECRET not set")
        return False, None, "missing_env"

    payload: dict[str, Any] = {
        "to_email": to_email,
        "subject": subject[:500] if subject else "",
        "body_preview": (body_preview or "")[:1000],
        "status": status,
        "channel": channel,
        "agent_source": agent_source,
    }
    if lead_id:
        payload["lead_id"] = lead_id
    if sent_at:
        payload["sent_at"] = sent_at
    if metadata:
        payload["metadata"] = metadata
    if existing_interaction_id:
        # Dedup signal — RPC will UPDATE this row's tenant_id + publish
        # agent_events, but won't INSERT a duplicate lead_interactions row.
        payload["existing_interaction_id"] = existing_interaction_id

    url = f"{base_url}/api/outbound/log"
    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-oasis-profile-id": profile_id,
            "x-oasis-secret": secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
            if data.get("ok"):
                return True, data.get("interaction_id"), None
            return False, None, str(data.get("error") or f"http_{resp.status}")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8") or ""
        except Exception:
            err_body = ""
        msg = f"http_{e.code}"
        if err_body:
            msg = f"{msg}: {err_body[:200]}"
        return False, None, msg
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, None, f"network: {e}"
    except Exception as e:  # noqa: BLE001
        return False, None, f"unexpected: {e}"
