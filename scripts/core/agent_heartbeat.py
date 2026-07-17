#!/usr/bin/env python3
"""agent_heartbeat.py — write a heartbeat to agent_state_snapshot.

The Command Center's Agents page detects "live within 15 minutes" by reading
this table. Each agent (Bravo, Atlas, Maven, Hermes, Codex, Aura) needs to
ping it whenever the agent runs so the operator knows everyone is alive.

Library use:
    from agent_heartbeat import heartbeat
    heartbeat("bravo", working_memory={"task": "ship V5"})

CLI use:
    python scripts/core/agent_heartbeat.py --agent bravo
    python scripts/core/agent_heartbeat.py --agent maven --tick 42 --json

Best-effort: never raises on Supabase errors. Logs + continues.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# V6.8.3: migrated from python-dotenv to lib.secret_loader.
# scripts/core/<file>.py → parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_REPO / 'scripts'))
from lib.secret_loader import load_env as _load_env  # noqa: E402

_env = _load_env()
import os as _os
for _k, _v in _env.items():
    _os.environ.setdefault(_k, str(_v))

VALID_AGENTS = {"bravo", "atlas", "maven", "hermes", "codex", "aura", "lex", "sunbiz", "suga_sean"}


def _configure_ca_bundle() -> None:
    """Use the OS trust store or certifi when Python has no default CA file."""
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE"):
        return
    try:
        import truststore  # type: ignore
    except ImportError:
        pass
    else:
        truststore.inject_into_ssl()
        return
    try:
        import certifi  # type: ignore
    except ImportError:
        return
    ca_path = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)


def _client():
    _configure_ca_bundle()
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        print("[heartbeat] supabase-py not installed", file=sys.stderr)
        return None
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("[heartbeat] BRAVO_SUPABASE env vars missing", file=sys.stderr)
        return None
    return create_client(url, key)


def heartbeat(
    agent_name: str,
    *,
    tick_id: str | None = None,
    working_memory: dict | None = None,
    pending_actions: list | None = None,
    health: str = "healthy",
) -> bool:
    """Upsert a heartbeat for `agent_name`. Returns True on success.

    - Auto-generates a tick_id if none provided
    - Auto-increments tick_count if the agent's row already exists
    - Best-effort: returns False (never raises) on any failure
    """
    name = agent_name.lower().strip()
    if name not in VALID_AGENTS:
        print(f"[heartbeat] unknown agent: {name}", file=sys.stderr)
        return False

    db = _client()
    if not db:
        return False

    try:
        existing = (
            db.table("agent_state_snapshot")
            .select("tick_count")
            .eq("agent_name", name)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        prev_count = (rows[0] if rows else {}).get("tick_count") or 0
    except Exception:
        prev_count = 0

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "agent_name": name,
        "tick_count": prev_count + 1,
        "last_tick_at": now,
        "last_tick_id": tick_id or uuid.uuid4().hex[:12],
        "working_memory": working_memory or {},
        "pending_actions": pending_actions or [],
        "health_status": health,
        "updated_at": now,
    }
    try:
        db.table("agent_state_snapshot").upsert(payload, on_conflict="agent_name").execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[heartbeat] {name} ping warning: {e}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Ping agent_state_snapshot")
    p.add_argument("--agent", required=True, choices=sorted(VALID_AGENTS))
    p.add_argument("--tick", default=None, help="custom tick_id (defaults to a random hex)")
    p.add_argument("--health", default="healthy", choices=["healthy", "degraded", "down"])
    p.add_argument("--memory", default=None, help="JSON string for working_memory")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    memory = None
    if args.memory:
        try:
            memory = json.loads(args.memory)
        except Exception:
            print("[heartbeat] --memory is not valid JSON", file=sys.stderr)
            return 1

    ok = heartbeat(args.agent, tick_id=args.tick, working_memory=memory, health=args.health)
    if args.json:
        print(json.dumps({"ok": ok, "agent": args.agent}))
    else:
        print(f"heartbeat {args.agent}: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
