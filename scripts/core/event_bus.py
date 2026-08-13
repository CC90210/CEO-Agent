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
    python scripts/core/event_bus.py publish --type lead.classified --payload '{"lead_id":"..."}'
    python scripts/core/event_bus.py tail --agent bravo
    python scripts/core/event_bus.py stats
    python scripts/core/event_bus.py reap
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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
    # Turso-migration fallback, matching the ~40 other call sites. This module
    # was missed in that sweep because it has its OWN _load_env() and never goes
    # through lib.secret_loader (which injects the same sentinel via setdefault)
    # — so unlike its neighbours it saw a genuinely empty BRAVO_SUPABASE_URL and
    # raised. The "Event Bus Offline Drain" cron sat in ERROR as a result.
    # The sentinel is resolved by lib.turso_supabase_compat to the real bravo
    # database; TURSO_* are the credentials that actually authenticate.
    url = (env.get("BRAVO_SUPABASE_URL") or env.get("SUPABASE_URL")
           or "https://bravo.turso.compat")
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY")
           or "turso-compat-key")
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
        msg_lower = msg.lower()
        # Real idempotency conflict (unique-index hit) — feature, not failure.
        # Distinguished from PGRST204 by the presence of 'PGRST204' / 'schema cache'.
        if ("PGRST204" in msg or "schema cache" in msg_lower):
            # Migration 015's columns aren't in PostgREST's schema yet. Strip them
            # and retry with the migration-006 base shape so the publish still
            # lands. Idempotency degrades to last-writer-wins for now.
            # Strip every migration-015 addition. Base shape (migration 006)
            # is: id, event_type, publisher_agent, target_agent, severity,
            # payload, correlation_id, published_at.
            stripped = {k: v for k, v in row.items()
                        if k not in {"source_agent", "idempotency_key", "status",
                                     "expires_at", "processed_at", "processed_by",
                                     "retry_count", "last_error", "visibility_until"}}
            try:
                res = client.table("agent_events").insert(stripped).execute()
                inserted_id = res.data[0]["id"] if res.data else stripped["id"]
                return {"status": "published", "id": inserted_id,
                        "reason": "schema-cache lag; published without idempotency_key"}
            except Exception as exc2:
                _append_offline(row)
                return {"status": "offline", "id": None,
                        "reason": f"queued to offline (PGRST204 retry failed): {exc2}"}
        if ("idempotency" in msg_lower or "duplicate" in msg_lower or "unique" in msg_lower):
            return {"status": "duplicate", "id": None, "reason": "idempotency_key already published"}
        _append_offline(row)
        return {"status": "offline", "id": None, "reason": f"queued to offline: {msg}"}


# ---- Subscriber -------------------------------------------------------------

HandlerFn = Callable[[dict[str, Any]], Awaitable[bool]]


def _get_pg_dsn(env: Optional[dict[str, str]] = None) -> Optional[str]:
    """Compose a direct-Postgres DSN for LISTEN/NOTIFY.

    Supabase pgbouncer (port 6543) is transaction-pooled and does NOT
    support LISTEN — it bounces session-scoped state on every transaction.
    For LISTEN we connect to the session-pool port (5432) on the same host.

    Returns None if env vars are absent — caller falls back to polling.
    """
    env = env or _load_env()
    host = env.get("PGBOUNCER_DB_HOST") or env.get("BRAVO_PG_HOST")
    user = env.get("PGBOUNCER_DB_USER") or env.get("BRAVO_PG_USER") or "postgres"
    password = env.get("PGBOUNCER_DB_PASSWORD") or env.get("BRAVO_PG_PASSWORD")
    dbname = env.get("PGBOUNCER_DB_NAME") or env.get("BRAVO_PG_DBNAME") or "postgres"
    if not host or not password:
        return None
    # urllib-quote the password (Supabase passwords often contain @/:/etc.)
    from urllib.parse import quote
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:5432/{dbname}?sslmode=require"


async def _consume_claimed_rows(client, agent: str, rows: list, handlers: dict[str, "HandlerFn"]) -> None:
    """Shared dispatch logic — runs the handler for each claimed row, acks/fails."""
    for event in rows:
        handler = handlers.get(event.get("event_type", ""))
        if not handler:
            try:
                client.rpc("ack_event", {"p_event_id": event["id"], "p_agent": agent}).execute()
            except Exception as exc:
                print(f"[event_bus] ack_event failed for {event.get('id')} (will reprocess on timeout): {exc}", file=sys.stderr)
            continue
        try:
            ok = await handler(event)
            if ok:
                client.rpc("ack_event", {"p_event_id": event["id"], "p_agent": agent}).execute()
            else:
                client.rpc("fail_event", {
                    "p_event_id": event["id"], "p_agent": agent,
                    "p_error": "handler returned False",
                }).execute()
        except Exception as exc:
            try:
                client.rpc("fail_event", {
                    "p_event_id": event["id"], "p_agent": agent,
                    "p_error": str(exc)[:500],
                }).execute()
            except Exception as exc2:
                print(f"[event_bus] fail_event RPC failed for {event.get('id')} (will reprocess on timeout): {exc2}", file=sys.stderr)


async def _subscribe_via_listen(
    agent: str,
    handlers: dict[str, "HandlerFn"],
    *,
    batch_size: int,
    visibility_seconds: int,
    client,
    dsn: str,
) -> None:
    """LISTEN/NOTIFY consumer. Wakes on pg_notify; otherwise idle.

    Race-free: every wake-up calls `claim_events()` which uses
    `FOR UPDATE SKIP LOCKED`, so multiple subscribers on the same agent
    name never claim the same row. The trigger emits per-INSERT, so a
    single notification is enough to drain the queue.
    """
    import psycopg2  # type: ignore
    import psycopg2.extensions  # type: ignore

    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    # Channel names from migration 015's trigger: target_agent OR 'broadcast'
    cur.execute(f"LISTEN {psycopg2.extensions.AsIs(agent)}; LISTEN broadcast;")

    loop = asyncio.get_running_loop()
    notify_event = asyncio.Event()
    loop.add_reader(conn.fileno(), notify_event.set)

    try:
        # Drain anything already pending at startup BEFORE blocking on notify.
        rpc = client.rpc("claim_events",
                         {"p_agent": agent, "p_max": batch_size,
                          "p_visibility_seconds": visibility_seconds}).execute()
        if rpc.data:
            await _consume_claimed_rows(client, agent, rpc.data, handlers)

        while True:
            await notify_event.wait()
            notify_event.clear()
            conn.poll()
            # Drop the queued notifies (we don't need their payloads — claim_events
            # is the source of truth for what to dequeue).
            del conn.notifies[:]
            try:
                rpc = client.rpc("claim_events",
                                 {"p_agent": agent, "p_max": batch_size,
                                  "p_visibility_seconds": visibility_seconds}).execute()
                rows = rpc.data or []
            except Exception as exc:
                print(f"[event_bus] claim_events failed during LISTEN: {exc}", file=sys.stderr)
                continue
            if rows:
                await _consume_claimed_rows(client, agent, rows, handlers)
    finally:
        try:
            loop.remove_reader(conn.fileno())
        except Exception:
            pass
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


async def _subscribe_via_polling(
    agent: str,
    handlers: dict[str, "HandlerFn"],
    *,
    poll_interval_seconds: float,
    batch_size: int,
    visibility_seconds: int,
    client,
) -> None:
    """Original polling consumer. Used as fallback when the LISTEN connection
    isn't available (no PGBOUNCER_DB_PASSWORD in env, no psycopg2, etc.)."""
    while True:
        try:
            rpc = client.rpc(
                "claim_events",
                {"p_agent": agent, "p_max": batch_size, "p_visibility_seconds": visibility_seconds},
            ).execute()
            rows = rpc.data or []
        except Exception as exc:
            print(f"[event_bus] claim_events failed (poll): {exc}", file=sys.stderr)
            await asyncio.sleep(poll_interval_seconds)
            continue
        if not rows:
            await asyncio.sleep(poll_interval_seconds)
            continue
        await _consume_claimed_rows(client, agent, rows, handlers)


async def subscribe(
    agent: str,
    handlers: dict[str, HandlerFn],
    *,
    poll_interval_seconds: float = 5.0,
    batch_size: int = 10,
    visibility_seconds: int = 30,
    db: Any = None,
    force_polling: bool = False,
) -> None:
    """
    Long-running consumer loop. Claims pending events targeted at `agent`
    (or broadcast), runs the matching handler, acks/fails appropriately.

    `handlers` maps event_type → async handler. Handler returns True=ack,
    False=retry, raises=fail-with-error.

    V6 BUILD 3 — primary path is raw psycopg2 LISTEN/NOTIFY (low-latency,
    no WebSocket, no Supabase Realtime quotas). Race-free because
    `claim_events()` uses `FOR UPDATE SKIP LOCKED` regardless of which
    transport delivers the wake-up.

    Fallback: if `PGBOUNCER_DB_PASSWORD` isn't in env, or psycopg2 isn't
    importable, or the LISTEN connection fails to open, the function
    silently degrades to the original 5-second polling loop.
    """
    client = db or _get_supabase()
    if not force_polling:
        dsn = _get_pg_dsn()
        if dsn:
            try:
                await _subscribe_via_listen(
                    agent, handlers,
                    batch_size=batch_size,
                    visibility_seconds=visibility_seconds,
                    client=client,
                    dsn=dsn,
                )
                return  # only reached if listen path exits cleanly
            except (ImportError, Exception) as exc:
                # ImportError → psycopg2 missing; Exception → connect/LISTEN failed.
                # Fall through to polling. Production logs the downgrade once.
                print(f"[event_bus] LISTEN unavailable, falling back to polling: {exc}",
                      file=sys.stderr)
    await _subscribe_via_polling(
        agent, handlers,
        poll_interval_seconds=poll_interval_seconds,
        batch_size=batch_size,
        visibility_seconds=visibility_seconds,
        client=client,
    )


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
        # Compact, NOT indent=2: the scheduler records the last stdout line as
        # last_result, so an indented block made the cron report a bare "}" —
        # the same trap Daily MRR Auto-Sync hit on 2026-06-06. One line parses
        # identically for any json.loads consumer and reads as a real result.
        # (`reap` above already prints compact, which is why it never had this.)
        print(json.dumps(drain_offline_queue()))
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
