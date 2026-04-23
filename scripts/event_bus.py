"""
Bravo V6.0 — Event Bus (publisher + subscriber)

Replaces the file-based pulse JSON coordination (cfo_pulse.json,
cmo_pulse.json, ceo_pulse.json) with a Postgres-backed durable pub/sub.

WHY
----
- Three agents (Bravo, Atlas, Maven) wrote to shared JSON files. Concurrent
  writes could corrupt state (documented in brain/ORCHESTRATION.md and
  docs/V6_ARCHITECTURE.md).
- Migration 015 adds LISTEN/NOTIFY + claim_events() for concurrent-safe
  dequeue via FOR UPDATE SKIP LOCKED.
- This module is the Python-side API every agent uses to publish/consume.

DESIGN
------
- Publishers call `publish(event_type, payload, target=None, source="bravo")`.
  INSERT fires a trigger that NOTIFYs the subscriber's channel.
- Subscribers run `async for event in subscribe("bravo", handlers={...}):`
  - LISTENs on its channel + 'broadcast' for push notifications
  - Calls `claim_events()` RPC to atomically grab pending rows
  - Runs handler; acks on success, fails on exception (retries up to 3)
- Offline durability: if Supabase is unreachable, publisher falls back to
  appending to tmp/events_offline.jsonl. A separate drain job replays these.

USAGE
-----
Publisher::
    from event_bus import publish
    publish(
        event_type="lead.classified",
        payload={"lead_id": "...", "intent": "hot"},
        target="maven",
        correlation_id="abc-123",
        idempotency_key=f"lead:{lead_id}:classified",
    )

Subscriber (long-lived daemon)::
    import asyncio
    from event_bus import subscribe

    async def on_budget_gate(event):
        # ... handle ...
        return True  # ack; False triggers retry

    asyncio.run(subscribe(
        agent="bravo",
        handlers={"budget.gate": on_budget_gate},
    ))

CLI::
    python scripts/event_bus.py publish --type lead.classified --payload '{"lead_id":"..."}'
    python scripts/event_bus.py tail --agent bravo
    python scripts/event_bus.py stats
    python scripts/event_bus.py reap
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

OFFLINE_QUEUE_PATH = PROJECT_ROOT / "tmp" / "events_offline.jsonl"

# ---- Env helpers (same pattern as send_gateway.py) --------------------------

def _load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _get_supabase(env: Optional[dict[str, str]] = None):
    env = env or _load_env()
    url = env.get("BRAVO_SUPABASE_URL") or env.get("SUPABASE_URL")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("BRAVO_SUPABASE_URL/KEY missing in .env.agents")
    try:
        from supabase import create_client  # type: ignore
    except ImportError as e:
        raise RuntimeError("pip install supabase") from e
    return create_client(url, key)


# ---- Offline queue (failure-safe publish) -----------------------------------

def _append_offline(record: dict[str, Any]) -> None:
    OFFLINE_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OFFLINE_QUEUE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ---- Publisher --------------------------------------------------------------

def publish(
    event_type: str,
    payload: dict[str, Any],
    *,
    source: str = "bravo",
    target: Optional[str] = None,
    severity: str = "info",
    correlation_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    expires_in_seconds: Optional[int] = None,
    db: Any = None,
) -> dict[str, Any]:
    """
    Durable publish. Returns {"status": "published"|"duplicate"|"offline",
                              "id": <uuid>|None, "reason": str}.
    NEVER raises. On Supabase outage, writes to tmp/events_offline.jsonl.
    """
    if severity not in {"info", "warn", "error", "critical"}:
        severity = "info"

    row = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "source_agent": source,
        "publisher_agent": source,   # migration 006 compat
        "target_agent": target,
        "severity": severity,
        "payload": payload or {},
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    if expires_in_seconds:
        from datetime import timedelta
        row["expires_at"] = (datetime.now(timezone.utc)
                             + timedelta(seconds=expires_in_seconds)).isoformat()

    try:
        client = db or _get_supabase()
        res = client.table("agent_events").insert(row).execute()
        inserted_id = res.data[0]["id"] if res.data else row["id"]
        return {"status": "published", "id": inserted_id, "reason": ""}
    except Exception as exc:
        msg = str(exc)
        # Idempotency conflict is a feature, not a failure.
        if "idempotency" in msg.lower() or "duplicate" in msg.lower() or "unique" in msg.lower():
            return {"status": "duplicate", "id": None, "reason": "idempotency_key already published"}
        _append_offline(row)
        return {"status": "offline", "id": None, "reason": f"queued to offline: {msg}"}


# ---- Subscriber -------------------------------------------------------------

HandlerFn = Callable[[dict[str, Any]], Awaitable[bool]]


async def subscribe(
    agent: str,
    handlers: dict[str, HandlerFn],
    *,
    poll_interval_seconds: float = 5.0,
    batch_size: int = 10,
    visibility_seconds: int = 30,
    db: Any = None,
) -> None:
    """
    Long-running consumer loop. Claims pending events targeted at `agent`
    (or broadcast), runs the matching handler, acks/fails appropriately.

    `handlers` maps event_type → async handler. Handler returns True=ack,
    False=retry, raises=fail-with-error.

    Implementation note: we do not use Postgres native LISTEN here because
    the supabase-py client doesn't expose it. Instead we poll claim_events()
    which is O(1) via the target_pending partial index. When load grows
    past ~1000 events/day this can be swapped for asyncpg LISTEN/NOTIFY
    without changing the public contract.
    """
    client = db or _get_supabase()
    while True:
        try:
            rpc = client.rpc(
                "claim_events",
                {"p_agent": agent, "p_max": batch_size, "p_visibility_seconds": visibility_seconds},
            ).execute()
            rows = rpc.data or []
        except Exception as exc:
            print(f"[event_bus] claim_events failed: {exc}", file=sys.stderr)
            await asyncio.sleep(poll_interval_seconds)
            continue

        if not rows:
            await asyncio.sleep(poll_interval_seconds)
            continue

        for event in rows:
            handler = handlers.get(event.get("event_type", ""))
            if not handler:
                try:
                    client.rpc("ack_event", {"p_event_id": event["id"], "p_agent": agent}).execute()
                except Exception:
                    pass
                continue
            try:
                ok = await handler(event)
                if ok:
                    client.rpc("ack_event", {"p_event_id": event["id"], "p_agent": agent}).execute()
                else:
                    client.rpc("fail_event", {
                        "p_event_id": event["id"],
                        "p_agent": agent,
                        "p_error": "handler returned False",
                    }).execute()
            except Exception as exc:
                try:
                    client.rpc("fail_event", {
                        "p_event_id": event["id"],
                        "p_agent": agent,
                        "p_error": str(exc)[:500],
                    }).execute()
                except Exception:
                    pass


# ---- Maintenance helpers ----------------------------------------------------

def reap_stuck() -> int:
    """Move visibility-expired rows back to pending. Run on a 60s cron."""
    try:
        client = _get_supabase()
        res = client.rpc("reap_stuck_events", {}).execute()
        return int(res.data) if res.data is not None else 0
    except Exception as exc:
        print(f"[event_bus] reap failed: {exc}", file=sys.stderr)
        return -1


def drain_offline_queue() -> dict[str, int]:
    """Replay tmp/events_offline.jsonl into the DB. Returns stats."""
    if not OFFLINE_QUEUE_PATH.exists():
        return {"replayed": 0, "failed": 0, "remaining": 0}
    lines = OFFLINE_QUEUE_PATH.read_text(encoding="utf-8").splitlines()
    replayed = 0
    failed: list[str] = []
    client = _get_supabase()
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            client.table("agent_events").insert(row).execute()
            replayed += 1
        except Exception as exc:
            failed.append(line)
            print(f"[event_bus] drain skip: {exc}", file=sys.stderr)
    # Rewrite the file keeping only failed rows.
    OFFLINE_QUEUE_PATH.write_text("\n".join(failed) + ("\n" if failed else ""), encoding="utf-8")
    return {"replayed": replayed, "failed": len(failed), "remaining": len(failed)}


def stats() -> dict[str, Any]:
    """Quick counts by status for dashboards."""
    try:
        client = _get_supabase()
        out: dict[str, Any] = {"as_of": datetime.now(timezone.utc).isoformat()}
        for status in ("pending", "processing", "done", "failed", "dead"):
            r = (client.table("agent_events")
                 .select("id", count="exact")
                 .eq("status", status)
                 .execute())
            out[status] = r.count or 0
        # Offline queue length
        out["offline_queued"] = (
            sum(1 for _ in OFFLINE_QUEUE_PATH.open("r", encoding="utf-8"))
            if OFFLINE_QUEUE_PATH.exists() else 0
        )
        return out
    except Exception as exc:
        return {"error": str(exc)}


# ---- CLI --------------------------------------------------------------------

def _cli() -> int:
    p = argparse.ArgumentParser(description="V6.0 event bus")
    sub = p.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("publish", help="Publish an event")
    pub.add_argument("--type", required=True)
    pub.add_argument("--source", default="cli")
    pub.add_argument("--target")
    pub.add_argument("--severity", default="info")
    pub.add_argument("--payload", default="{}")
    pub.add_argument("--correlation-id")
    pub.add_argument("--idempotency-key")

    sub.add_parser("stats", help="Counts by status")
    sub.add_parser("reap", help="Move stuck 'processing' rows back to pending")
    sub.add_parser("drain", help="Replay tmp/events_offline.jsonl")

    tail = sub.add_parser("tail", help="Subscribe and print events")
    tail.add_argument("--agent", required=True)
    tail.add_argument("--types", nargs="+", default=["*"])

    args = p.parse_args()

    if args.cmd == "publish":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"invalid --payload JSON: {e}", file=sys.stderr)
            return 2
        result = publish(
            event_type=args.type,
            payload=payload,
            source=args.source,
            target=args.target,
            severity=args.severity,
            correlation_id=args.correlation_id,
            idempotency_key=args.idempotency_key,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["status"] in ("published", "duplicate") else 1

    if args.cmd == "stats":
        print(json.dumps(stats(), indent=2, default=str))
        return 0

    if args.cmd == "reap":
        n = reap_stuck()
        print(json.dumps({"reaped": n}))
        return 0 if n >= 0 else 1

    if args.cmd == "drain":
        print(json.dumps(drain_offline_queue(), indent=2))
        return 0

    if args.cmd == "tail":
        async def _handler(event):
            print(json.dumps(event, indent=2, default=str))
            return True
        wildcard = "*" in args.types
        handlers: dict[str, HandlerFn] = (
            {t: _handler for t in args.types} if not wildcard
            else {}  # empty map; we'll intercept below
        )
        if wildcard:
            async def _run():
                client = _get_supabase()
                while True:
                    try:
                        rpc = client.rpc("claim_events", {
                            "p_agent": args.agent, "p_max": 10, "p_visibility_seconds": 30,
                        }).execute()
                        for ev in (rpc.data or []):
                            print(json.dumps(ev, indent=2, default=str))
                            client.rpc("ack_event", {
                                "p_event_id": ev["id"], "p_agent": args.agent,
                            }).execute()
                        await asyncio.sleep(3)
                    except KeyboardInterrupt:
                        return
                    except Exception as e:
                        print(f"[tail] {e}", file=sys.stderr)
                        await asyncio.sleep(5)
            asyncio.run(_run())
        else:
            asyncio.run(subscribe(agent=args.agent, handlers=handlers))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(_cli())
