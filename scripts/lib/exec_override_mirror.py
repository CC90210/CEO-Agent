"""Supabase mirror for the V6 dashboard-driven override approval flow.

The local SQLite `override_request` table is the source of truth for the
agent's at-runtime block/allow decision. This module mirrors pending +
approved/denied/consumed/expired status to the Supabase `exec_overrides`
table so the operator can see + act on pending requests from the Vercel
dashboard.

Design rules:
  - EVERY call is best-effort. Network down / Supabase unauthenticated /
    service-role key absent — none of those are allowed to break exec_guard
    or the operator CLI. We log a one-line debug breadcrumb and return.
  - We import lazily so importing this module never costs anything when the
    mirror isn't reachable.
  - We never read secrets via Read tool calls — `lib.secret_loader.load_env`
    is the canonical in-process loader and respects secret_guard.

Functions:
  mirror_pending(row)   — upsert a freshly-created request as pending
  mirror_status(row)    — push a status update (approved/denied/consumed/expired)
  fetch_pending_intents() — read rows the dashboard has decided but the
                            local consumer hasn't synced yet
  mark_synced(...)      — confirm the consumer applied the dashboard decision
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def _client():
    """Build a Supabase service-role client. Returns None on any failure
    (missing env, missing package, network) — caller treats None as 'mirror
    disabled' and silently no-ops."""
    try:
        from lib.secret_loader import load_env  # noqa: E402
    except Exception:
        return None
    try:
        env = load_env()
    except Exception:
        return None
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def _row_to_pending_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a SQLite override_request row → Supabase exec_overrides row.
    Only fields that exist on the Supabase schema; SQLite-only fields are dropped."""
    return {
        "request_id":   row["id"],
        "ts":           row["ts"],
        "expires_at":   row["expires_at"],
        "command":      (row.get("command") or "")[:2000],
        "command_hash": row["command_hash"],
        "layer":        row.get("layer") or "?",
        "reason":       row.get("reason"),
        "caller_pid":   row.get("caller_pid"),
        "status":       row.get("status") or "pending",
        "approved_at":  row.get("approved_at"),
        "approved_by":  row.get("approved_by"),
        "consumed_at":  row.get("consumed_at"),
        "hmac_sig":     row.get("hmac_sig"),
    }


def mirror_pending(row: dict[str, Any]) -> bool:
    """Best-effort upsert of a pending override_request to Supabase.

    Returns True on success, False on any failure. Never raises.
    """
    client = _client()
    if client is None:
        return False
    try:
        payload = _row_to_pending_payload(row)
        client.table("exec_overrides").upsert(payload, on_conflict="request_id").execute()
        return True
    except Exception:
        return False


def mirror_status(row: dict[str, Any]) -> bool:
    """Best-effort push of a status update (approved / denied / consumed / expired).

    Uses the mark_exec_override_synced_v1 RPC so the row reflects the new
    state AND the consumer_synced_at timestamp gets stamped — preventing the
    local poller from re-applying the same dashboard intent.

    Returns True on success, False otherwise. Never raises.
    """
    client = _client()
    if client is None:
        return False
    try:
        client.rpc(
            "mark_exec_override_synced_v1",
            {
                "p_request_id":   row["id"],
                "p_final_status": row.get("status") or "approved",
                "p_hmac_sig":     row.get("hmac_sig"),
                "p_approved_at":  row.get("approved_at"),
                "p_approved_by":  row.get("approved_by"),
                "p_consumed_at":  row.get("consumed_at"),
            },
        ).execute()
        return True
    except Exception:
        return False


def fetch_pending_intents(limit: int = 25) -> list[dict[str, Any]]:
    """Return rows the dashboard has decided but the local consumer hasn't
    applied yet. Empty list on any failure.

    Filter: dashboard_decision IS NOT NULL AND consumer_synced_at IS NULL
            AND expires_at > now()
    """
    client = _client()
    if client is None:
        return []
    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        res = (
            client.table("exec_overrides")
            .select(
                "request_id, command, command_hash, layer, expires_at, "
                "dashboard_decision, dashboard_decided_at, "
                "dashboard_decided_by, dashboard_reason"
            )
            .not_.is_("dashboard_decision", "null")
            .is_("consumer_synced_at", "null")
            .gt("expires_at", now_iso)
            .order("dashboard_decided_at", desc=False)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
    except Exception:
        return []


def mark_synced(request_id: str, final_status: str, *,
                hmac_sig: str | None = None,
                approved_at: str | None = None,
                approved_by: str | None = None,
                consumed_at: str | None = None) -> bool:
    """Tell Supabase the consumer applied the dashboard decision locally.

    Stamps consumer_synced_at + mirrors the final local status (approved /
    consumed / denied / expired) back to the mirror row. Never raises.
    """
    client = _client()
    if client is None:
        return False
    try:
        client.rpc(
            "mark_exec_override_synced_v1",
            {
                "p_request_id":   request_id,
                "p_final_status": final_status,
                "p_hmac_sig":     hmac_sig,
                "p_approved_at":  approved_at,
                "p_approved_by":  approved_by,
                "p_consumed_at":  consumed_at,
            },
        ).execute()
        return True
    except Exception:
        return False
