"""pause_controller.py — operator kill switches + operating mode toggles
for the SunBiz outbound infrastructure.

Phase 1 deliverable from Adon's MCA brief §4.9 + §9. Operator needs
a panic button when something looks wrong:
  - /pause all                — halt every automated outbound for a tenant
  - /pause agent <name>       — halt one agent (e.g. sequence_runner)
  - /pause lead <uuid>        — manual takeover for one merchant
  - /resume * / agent / lead  — clear the pause
  - /status                   — list active pauses
  - /set-mode <mode>          — operating mode toggle

State is persisted in tenant_records with entity_type='kill_switch' or
entity_type='operating_mode' so the existing tenant-scoped query path
just works and the kill switch survives daemon restarts.

INTEGRATION
-----------
send_gateway.py reads kill switches + operating mode on every can_act()
call. Operating modes adjust per-channel caps and gate which agents
are allowed to send:
  - silent       : block everything (no automated outbound)
  - conservative : only agents that move money (status reporter, offer
                   presenter, funding concierge, sentinel — see brief §9)
  - standard     : default — all agents active with normal cadences
  - aggressive   : doubled caps, no cadence slow-down

KILL SWITCHES vs LEAD.DATA.MANUAL_PAUSED
----------------------------------------
The per-merchant pause set by `/pause lead <uuid>` writes to
lead.data.manual_paused (existing field used by Phase 1
_check_manual_pause). NOT a separate kill_switch row — Adon's brief
treats this as the same primitive. The two scopes that DO use
kill_switch rows: global (no target) and per-agent (target=agent_source).

CLI
---
  python scripts/pause_controller.py pause global \\
      --tenant <uuid> --reason "investigating sentiment regression"
  python scripts/pause_controller.py pause agent sequence_runner --tenant <uuid>
  python scripts/pause_controller.py pause lead <lead_uuid> --tenant <uuid>
  python scripts/pause_controller.py resume global --tenant <uuid>
  python scripts/pause_controller.py status --tenant <uuid>
  python scripts/pause_controller.py set-mode standard --tenant <uuid>
  python scripts/pause_controller.py get-mode --tenant <uuid>

Telegram bridge integration: add a router in telegram_agent.js that
parses /pause /resume /status /set-mode messages and subprocesses out
to this script. Same pattern as every other Bravo CLI tool.

EXIT CODES
----------
0 = success
1 = invalid scope / target
2 = supabase unreachable
3 = pause did not exist (for resume)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

CAPABILITY_META = {
    "category": "outbound.safety",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": ["pause outbound", "resume outbound", "outbound status", "set operating mode"],
    "owner": "bravo",
    "project": "sunbiz",
    "bridge": {
        "visible": True,
        "confirm": True,
        "subcommands": {
            "pause": {"visible": True, "confirm": True},
            "resume": {"visible": True, "confirm": True},
            "status": {"visible": True, "confirm": False},
            "set-mode": {"visible": True, "confirm": True},
            "get-mode": {"visible": True, "confirm": False},
        },
    },
}


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


VALID_MODES = ("silent", "conservative", "standard", "aggressive")
DEFAULT_MODE = "standard"

# Conservative mode allows only these agents per Adon §9. Everything else
# is blocked at the send_gateway gate when mode == "conservative".
CONSERVATIVE_ALLOWED_AGENTS = frozenset({
    "underwriting_status_reporter",  # Adon's Agent 4
    "offer_presenter",                # Adon's Agent 5
    "funding_day_concierge",          # Adon's Agent 7
    "sentinel",                       # Adon's Agent 12
    "manual_cc",                      # operator-driven sends always allowed
})

# Operating mode -> cap multipliers applied on top of DAILY_CAPS / HOURLY_CAPS
# in send_gateway. silent = 0 (block); conservative = 0.5; standard = 1.0;
# aggressive = 2.0. send_gateway floor()s the result to int.
MODE_CAP_MULTIPLIERS: dict[str, float] = {
    "silent": 0.0,
    "conservative": 0.5,
    "standard": 1.0,
    "aggressive": 2.0,
}


# ─────────────────────────────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────────────────────────────


def _supabase():
    try:
        from lib.secret_loader import load_env  # type: ignore
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
    return create_client(url, key)


# ─────────────────────────────────────────────────────────────────────
# Kill switch primitives
# ─────────────────────────────────────────────────────────────────────


def _safe_upsert_kill_switch(sb, tenant_id: str, scope: str,
                              target: Optional[str], payload: dict) -> dict[str, Any]:
    """Atomic upsert that never leaves a pause-window gap. Codex audit
    finding #3: the OLD delete-then-insert pattern could clear an active
    pause mid-incident if the follow-up insert failed. New pattern:
    INSERT the new row first; if it succeeds, delete the OLDER rows
    matching the same (scope, target) tuple. If insert fails, the
    previous row stays — caller sees an error, no panic-control gap.
    """
    try:
        ins = sb.table("tenant_records").insert(payload).execute()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "scope": scope, "target": target,
                "error": "insert_failed", "detail": str(exc)}
    new_id = ins.data[0]["id"] if ins.data else None
    # Now sweep older duplicates (every row with this scope+target except
    # the one we just inserted). Best-effort — failure here just leaves
    # extra audit history, doesn't break the pause itself.
    try:
        q = sb.table("tenant_records").delete().eq(
            "tenant_id", tenant_id
        ).eq("entity_type", "kill_switch").filter(
            "data->>scope", "eq", scope
        )
        if target is not None:
            q = q.filter("data->>target", "eq", target)
        if new_id:
            q = q.neq("id", new_id)
        q.execute()
    except Exception as exc:  # noqa: BLE001
        # Audit cleanup failed — surface in the result so the operator
        # knows but don't reverse the pause.
        return {"ok": True, "scope": scope, "id": new_id,
                "cleanup_warning": f"sweep failed: {exc}"}
    return {"ok": True, "scope": scope, "id": new_id}


def pause_global(sb, tenant_id: str, reason: str = "", actor: str = "operator") -> dict[str, Any]:
    """Halt every automated outbound for this tenant. Uses safe-upsert
    so a failed retry can't clear an existing pause."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "tenant_id": tenant_id,
        "entity_type": "kill_switch",
        "data": {
            "scope": "global",
            "target": None,
            "reason": reason or "manual pause",
            "set_at": now,
            "set_by": actor,
        },
    }
    return _safe_upsert_kill_switch(sb, tenant_id, "global", None, payload)


def pause_agent(sb, tenant_id: str, agent_source: str, reason: str = "",
                actor: str = "operator") -> dict[str, Any]:
    """Halt a single agent. Safe-upsert — see _safe_upsert_kill_switch."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "tenant_id": tenant_id,
        "entity_type": "kill_switch",
        "data": {
            "scope": "agent",
            "target": agent_source,
            "reason": reason or f"manual pause: {agent_source}",
            "set_at": now,
            "set_by": actor,
        },
    }
    result = _safe_upsert_kill_switch(sb, tenant_id, "agent", agent_source, payload)
    if result.get("ok"):
        result["agent"] = agent_source
    return result


def pause_lead(sb, tenant_id: str, lead_id: str, reason: str = "",
               actor: str = "operator") -> dict[str, Any]:
    """Manual takeover for one merchant. Writes lead.data.manual_paused
    (read by send_gateway _check_manual_pause), NOT a kill_switch row.
    Adon's brief treats per-merchant pauses as the same primitive."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        sb.rpc("patch_tenant_record_data", {
            "p_tenant_id": tenant_id,
            "p_id": lead_id,
            "p_patch": {
                "manual_paused": True,
                "manual_paused_reason": reason or "manual takeover",
                "manual_paused_at": now,
                "manual_paused_by": actor,
            },
        }).execute()
    except Exception as exc:
        # Fallback RMW for tenants without the RPC
        rows = (
            sb.table("tenant_records")
            .select("data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        if not rows.data:
            return {"ok": False, "error": "lead_not_found", "lead_id": lead_id, "detail": str(exc)}
        d = rows.data[0].get("data") or {}
        d.update({
            "manual_paused": True,
            "manual_paused_reason": reason or "manual takeover",
            "manual_paused_at": now,
            "manual_paused_by": actor,
        })
        sb.table("tenant_records").update({"data": d}).eq("id", lead_id).execute()
    return {"ok": True, "scope": "lead", "lead_id": lead_id}


def resume_global(sb, tenant_id: str) -> dict[str, Any]:
    r = sb.table("tenant_records").delete().eq("tenant_id", tenant_id).eq(
        "entity_type", "kill_switch"
    ).filter("data->>scope", "eq", "global").execute()
    return {"ok": True, "scope": "global", "deleted": len(r.data or [])}


def resume_agent(sb, tenant_id: str, agent_source: str) -> dict[str, Any]:
    r = sb.table("tenant_records").delete().eq("tenant_id", tenant_id).eq(
        "entity_type", "kill_switch"
    ).filter("data->>scope", "eq", "agent").filter(
        "data->>target", "eq", agent_source
    ).execute()
    return {"ok": True, "scope": "agent", "agent": agent_source,
            "deleted": len(r.data or [])}


def resume_lead(sb, tenant_id: str, lead_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    try:
        sb.rpc("patch_tenant_record_data", {
            "p_tenant_id": tenant_id,
            "p_id": lead_id,
            "p_patch": {
                "manual_paused": False,
                "manual_paused_cleared_at": now,
            },
        }).execute()
        return {"ok": True, "scope": "lead", "lead_id": lead_id}
    except Exception as exc:
        return {"ok": False, "error": "rpc_failed", "detail": str(exc)}


def list_active_pauses(sb, tenant_id: str) -> dict[str, Any]:
    """Return every active kill switch + count of per-merchant pauses."""
    try:
        kill_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "kill_switch")
            .execute()
        )
    except Exception as exc:
        return {"ok": False, "error": "supabase_unreachable", "detail": str(exc)}

    global_active = []
    agent_active = []
    for r in kill_rows.data or []:
        d = r.get("data") or {}
        scope = d.get("scope")
        if scope == "global":
            global_active.append(d)
        elif scope == "agent":
            agent_active.append(d)

    # Count merchants currently flagged manual_paused=true
    try:
        manual_count_res = (
            sb.table("tenant_records")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .filter("data->>manual_paused", "eq", "true")
            .execute()
        )
        manual_count = manual_count_res.count or 0
    except Exception:
        manual_count = -1

    mode = get_operating_mode(sb, tenant_id)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "operating_mode": mode,
        "global": global_active,
        "agents": agent_active,
        "lead_pauses_count": manual_count,
    }


# ─────────────────────────────────────────────────────────────────────
# Operating mode
# ─────────────────────────────────────────────────────────────────────


def set_operating_mode(sb, tenant_id: str, mode: str,
                       actor: str = "operator") -> dict[str, Any]:
    if mode not in VALID_MODES:
        return {"ok": False, "error": "invalid_mode",
                "valid": list(VALID_MODES)}
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "tenant_id": tenant_id,
        "entity_type": "operating_mode",
        "data": {
            "mode": mode,
            "set_at": now,
            "set_by": actor,
            "cap_multiplier": MODE_CAP_MULTIPLIERS[mode],
        },
    }
    # Safe-upsert (insert first, then sweep older rows). Same pattern as
    # _safe_upsert_kill_switch — protects against a failed mode change
    # accidentally clearing an existing mode (Codex finding #3).
    try:
        ins = sb.table("tenant_records").insert(payload).execute()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "insert_failed", "detail": str(exc)}
    new_id = ins.data[0]["id"] if ins.data else None
    try:
        q = sb.table("tenant_records").delete().eq(
            "tenant_id", tenant_id
        ).eq("entity_type", "operating_mode")
        if new_id:
            q = q.neq("id", new_id)
        q.execute()
    except Exception:  # noqa: BLE001
        pass  # cleanup best-effort
    return {"ok": True, "mode": mode, "cap_multiplier": MODE_CAP_MULTIPLIERS[mode],
            "id": new_id}


def get_operating_mode(sb, tenant_id: str) -> dict[str, Any]:
    """Return the active operating mode + cap multiplier. Defaults to
    'standard' (1.0x) when no row exists."""
    try:
        r = (
            sb.table("tenant_records")
            .select("data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "operating_mode")
            .limit(1)
            .execute()
        )
    except Exception:
        return {"mode": DEFAULT_MODE, "cap_multiplier": 1.0, "source": "default_on_error"}
    if r.data:
        d = r.data[0].get("data") or {}
        mode = d.get("mode") if d.get("mode") in VALID_MODES else DEFAULT_MODE
        return {
            "mode": mode,
            "cap_multiplier": MODE_CAP_MULTIPLIERS.get(mode, 1.0),
            "set_at": d.get("set_at"),
            "set_by": d.get("set_by"),
            "source": "stored",
        }
    return {"mode": DEFAULT_MODE, "cap_multiplier": 1.0, "source": "default"}


# ─────────────────────────────────────────────────────────────────────
# Gates used by send_gateway
# ─────────────────────────────────────────────────────────────────────


def check_kill_switches(sb, tenant_id: Optional[str], agent_source: str) -> Optional[str]:
    """send_gateway helper. Returns a string reason if the send should
    be blocked, None to allow. Fail-closed on DB error (refuse send)."""
    if not tenant_id:
        return None  # cross-tenant or system sends not gated by kill switches
    try:
        rows = (
            sb.table("tenant_records")
            .select("data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "kill_switch")
            .execute()
        ).data or []
    except Exception as exc:
        return f"kill_switch ledger unavailable: {exc}"
    for r in rows:
        d = r.get("data") or {}
        scope = d.get("scope")
        if scope == "global":
            return f"global pause active (set by {d.get('set_by','?')} at {d.get('set_at','?')}: {d.get('reason','')})"
        if scope == "agent" and d.get("target") == agent_source:
            return f"agent pause active for {agent_source} (set by {d.get('set_by','?')} at {d.get('set_at','?')}: {d.get('reason','')})"
    return None


def check_operating_mode(sb, tenant_id: Optional[str], agent_source: str) -> tuple[Optional[str], float]:
    """Returns (block_reason_or_None, cap_multiplier).
      - silent       -> block all, multiplier irrelevant
      - conservative -> block if agent not in CONSERVATIVE_ALLOWED_AGENTS;
                         multiplier 0.5 for allowed agents
      - standard     -> no block, multiplier 1.0
      - aggressive   -> no block, multiplier 2.0
    """
    if not tenant_id:
        return None, 1.0
    info = get_operating_mode(sb, tenant_id)
    mode = info["mode"]
    if mode == "silent":
        return f"operating mode = silent (all automated outbound paused; set at {info.get('set_at','?')})", 0.0
    if mode == "conservative" and agent_source not in CONSERVATIVE_ALLOWED_AGENTS:
        return f"operating mode = conservative — agent {agent_source} not in allowlist", info["cap_multiplier"]
    return None, info["cap_multiplier"]


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Operator pause controller")
    parser.add_argument("--tenant", required=False,
                        help="tenant_id (defaults to SUNBIZ_TENANT_ID env or hard-coded SunBiz)")
    parser.add_argument("--actor", default="operator")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pause = sub.add_parser("pause", help="halt automated outbound")
    p_pause.add_argument("scope", choices=["global", "agent", "lead"])
    p_pause.add_argument("target", nargs="?", default=None,
                         help="agent_source for scope=agent, lead_id for scope=lead, ignored for global")
    p_pause.add_argument("--reason", default="")

    p_resume = sub.add_parser("resume", help="clear an active pause")
    p_resume.add_argument("scope", choices=["global", "agent", "lead"])
    p_resume.add_argument("target", nargs="?", default=None)

    sub.add_parser("status", help="list active pauses + operating mode")

    p_setmode = sub.add_parser("set-mode", help="change operating mode")
    p_setmode.add_argument("mode", choices=list(VALID_MODES))

    sub.add_parser("get-mode", help="print current operating mode")

    args = parser.parse_args(argv)

    sb = _supabase()
    if sb is None:
        print(json.dumps({"ok": False, "error": "supabase_unreachable"}))
        return 2

    sunbiz_default = os.environ.get(
        "SUNBIZ_TENANT_ID", "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
    )
    tenant = args.tenant or sunbiz_default

    if args.cmd == "pause":
        if args.scope == "global":
            _emit(pause_global(sb, tenant, args.reason, args.actor), args.json)
        elif args.scope == "agent":
            if not args.target:
                print(json.dumps({"ok": False, "error": "agent name required"}))
                return 1
            _emit(pause_agent(sb, tenant, args.target, args.reason, args.actor), args.json)
        elif args.scope == "lead":
            if not args.target:
                print(json.dumps({"ok": False, "error": "lead_id required"}))
                return 1
            _emit(pause_lead(sb, tenant, args.target, args.reason, args.actor), args.json)
        return 0

    if args.cmd == "resume":
        if args.scope == "global":
            _emit(resume_global(sb, tenant), args.json)
        elif args.scope == "agent":
            if not args.target:
                print(json.dumps({"ok": False, "error": "agent name required"}))
                return 1
            _emit(resume_agent(sb, tenant, args.target), args.json)
        elif args.scope == "lead":
            if not args.target:
                print(json.dumps({"ok": False, "error": "lead_id required"}))
                return 1
            _emit(resume_lead(sb, tenant, args.target), args.json)
        return 0

    if args.cmd == "status":
        _emit(list_active_pauses(sb, tenant), args.json)
        return 0

    if args.cmd == "set-mode":
        _emit(set_operating_mode(sb, tenant, args.mode, args.actor), args.json)
        return 0

    if args.cmd == "get-mode":
        _emit(get_operating_mode(sb, tenant), args.json)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
