---
tags: [v6, event-bus, cross-agent, contract]
last_updated: 2026-05-10
freshness_threshold_days: 14
---

# EVENT BUS CONTRACT — V6 BUILD 3

> Canonical registry of cross-agent event types + the operational state of the LISTEN/NOTIFY substrate. When a producer emits an event that's not in this file, add it here before merging. When a subscriber filters on an event type, this file is the source of truth for the schema it can expect.

## Substrate

| Component | Path | Status |
|-----------|------|:------:|
| Postgres table | `public.agent_events` (Supabase project `phctllmtsogkovoilwos`) | ✅ live |
| Migration 015 | `database/015_v6_event_bus_extensions.sql` | ⚠ see prerequisite §3 below |
| Trigger | `trg_notify_agent_event` → `pg_notify(target_agent OR 'broadcast', payload)` | ⚠ active only if migration 015 applied |
| RPC: `claim_events()` | `FOR UPDATE SKIP LOCKED` atomic dequeue | ⚠ active only if migration 015 applied |
| RPC: `ack_event` / `fail_event` / `reap_stuck_events` | retry + reaper helpers | ⚠ active only if migration 015 applied |
| Publisher API | `scripts/event_bus.py::publish(event_type, payload, source, target, ...)` | ✅ shipped; PGRST204-resilient |
| Subscriber API | `scripts/event_bus.py::subscribe(agent, handlers={...})` | ✅ shipped; LISTEN-first, polling fallback |
| Offline queue | `tmp/events_offline.jsonl` (drained by `drain_offline_queue()`) | ✅ active when Supabase unreachable |

## Producer wiring (V6 BUILD 3 batch)

| Producer | Event type | Where fired | Payload shape |
|----------|------------|-------------|---------------|
| `state_manager.append_session_log` | `BRAVO_SESSION_LOG_APPENDED` | every successful insert (skipped on dedup) | `{agent, session_id, note (≤200 chars)}` |
| `pulse_publish.cmd_refresh` | `BRAVO_PULSE_REFRESHED` | after `_atomic_write` succeeds | `{updated_at, net_mrr_usd, gap_usd, v6_mode}` |
| `bridge_chat_server._v6_log_chat_interaction` | `BRAVO_CHAT_INTERACTION` | every successful POST to `/chat` or `/local-chat` | `{agent, kind ('cloud-chat'\|'local-chat'), preview (≤160 chars)}` |
| `webhook_listener` | `inbound.classified` (legacy) | inbound classification, via the existing `bus_publish` import | `{lead_id, intent, …}` |
| `send_gateway` | `BRAVO_OUTBOUND_SENT` | after a successful `send()` returns `status='sent'` (BOTH email + non-email paths; idempotency-keyed on `interaction_id`) | `{lead_id, channel, interaction_id, intent, brand}` |

**Wired 2026-05-11 (V6 Ascension Step 1):** `_emit_outbound_sent()` helper at module scope; called before each of the two `status='sent'` returns in `send()`. Best-effort + lazy import — never raises, never mutates the V5.6 chokepoint return shape. Dry-run + reserved-domain blocks short-circuit BEFORE the emit; verified via smoke (zero events on `dry_run`; 67/67 send_gateway regression tests green).

## Standard event-type registry (locked schemas)

All producers tag events with these exact `event_type` strings. Subscribers filter on them. Adding a new type? Add a row here first.

| event_type | source | target | severity | payload required keys | meaning |
|------------|--------|--------|:--------:|------------------------|---------|
| `BRAVO_SESSION_LOG_APPENDED` | bravo | (broadcast) | info | `agent`, `session_id`, `note` | a new line landed in `memory/SESSION_LOG.md` (via state DB) |
| `BRAVO_CHAT_INTERACTION` | bravo | (broadcast) | info | `agent`, `kind`, `preview` | operator typed into the dashboard chat |
| `BRAVO_PULSE_REFRESHED` | bravo | (broadcast) | info | `updated_at`, `net_mrr_usd`, `gap_usd`, `v6_mode` | `ceo_pulse.json` was rewritten — sibling agents should reload it |
| `BRAVO_OUTBOUND_SENT` (Phase 2) | bravo | (broadcast) | info | `lead_id`, `channel`, `interaction_id`, `intent` | a CASL-compliant outbound message was successfully delivered |
| `MAVEN_POST_COMPLETE` (sibling-emitted, reserved) | maven | (broadcast) | info | `platform`, `post_url`, `scheduled_at` | a social post went live |
| `ATLAS_BUDGET_LOCKED` / `ATLAS_BUDGET_RELEASED` (sibling-emitted, reserved) | atlas | (broadcast) | warn / info | `period`, `amount_cad`, `reason` | spend gate state changed |
| `AURA_PRESENCE_HOME` / `AURA_PRESENCE_AWAY` (sibling-emitted, reserved) | aura | (broadcast) | info | `since`, `prev_state` | operator presence changed |
| `HERMES_INVOICE_SHIPPED` (sibling-emitted, reserved) | hermes | (broadcast) | info | `client`, `invoice_id`, `amount_usd` | a Hermes-managed invoice cleared |

## Subscriber contract

Every subscriber gets exactly-once delivery per row PER claim attempt (rows are marked `processing` with a visibility timeout; `claim_events` uses `FOR UPDATE SKIP LOCKED` so concurrent workers of the same agent never claim the same row).

```python
import asyncio
from event_bus import subscribe

async def on_pulse(event):
    # event = {"id": uuid, "event_type": "BRAVO_PULSE_REFRESHED", "payload": {...}, ...}
    print(f"pulse refreshed: {event['payload']['net_mrr_usd']}")
    return True   # ack; False = retry; raise = fail-with-error

asyncio.run(subscribe(
    agent="atlas",
    handlers={
        "BRAVO_PULSE_REFRESHED": on_pulse,
        "BRAVO_OUTBOUND_SENT":   on_outbound,
    },
))
```

Handler returns: `True` → `ack_event`; `False` → `fail_event` (re-queues); raises → `fail_event` with the exception message recorded. After 3 retries (default), the row moves to `dead` status and requires operator intervention via `reap_stuck()`.

## Prerequisites (current operational state, 2026-05-10 late-night update)

### ✅ Prerequisite 2 — RESOLVED: Migration 015 applied

Initial BUILD 3 ship discovered migration 015 was NEVER applied to the live DB (Postgres `42703 column does not exist`, not just a PostgREST cache miss). The `claim_events`, `ack_event`, `fail_event`, `reap_stuck_events` RPCs and the `notify_agent_event` trigger were all missing.

**Applied 2026-05-10 ~21:30 UTC** via `python scripts/apply_migration.py tmp/015_event_bus_no_backfill.sql` — a backfill-stripped variant of migration 015 (the backfill UPDATE was deliberately removed so apply_migration's "no broad UPDATE" guardrail accepts it; backfill is operationally optional since `source_agent` defaults to `'unknown'`).

End-to-end smoke verified: publish writes with migration-015 columns; claim_events dequeues correctly (pending → processing via FOR UPDATE SKIP LOCKED); ack_event returns True; idempotency_key unique index enforces dedup (second publish with same key returns `duplicate`).

**The PGRST204 fallback path in `publish()` is now DEFENSIVE DEAD CODE** — it still exists as a safety net in case the schema is ever reverted or a future migration breaks the cache. The expected execution path no longer touches it.

**Tiny optional cleanup:** if you want the 8 pre-existing dev rows backfilled, run via Supabase Dashboard SQL editor:
```sql
UPDATE agent_events
SET    source_agent = publisher_agent
WHERE  source_agent = 'unknown' AND publisher_agent IS NOT NULL;
```

### ⏳ Prerequisite 1 — pending: `PGBOUNCER_DB_PASSWORD` in agent env file

The LISTEN connection bypasses pgbouncer (transaction pooling drops session state) and connects directly to `db.<ref>.supabase.co:5432`. Requires the Supabase project's Postgres password.

**Current state (2026-05-10):** `PGBOUNCER_DB_HOST` is set; `PGBOUNCER_DB_PASSWORD` is NOT. `subscribe()` silently degrades to 5-second polling — which **fully works now** that claim_events RPC exists; just higher latency than LISTEN.

**To enable LISTEN's sub-100ms wake-up:** add `PGBOUNCER_DB_PASSWORD=<password>` to the agent env file. The password is the "Database password" shown in Supabase Settings → Database → Connection string (the part after `postgres:` and before `@`). After the next `subscribe()` invocation, the LISTEN path activates automatically — no code change.

## Reliability properties

- **Idempotent emit:** when migration 015's unique index on `idempotency_key` is live, passing the same key twice is a silent no-op. Producers SHOULD include `idempotency_key=f"<source>:<id>:<event_type>"` for any event that has a natural unique key. While the schema-cache fallback is active, idempotency degrades to last-writer-wins.
- **Concurrent-safe consume:** `claim_events()` uses `FOR UPDATE SKIP LOCKED`. Two workers of the same agent never claim the same row.
- **Retry budget:** 3 attempts before `dead`. `fail_event()` records the exception in `last_error`. `reap_stuck_events()` cron job moves visibility-timeout rows back to `pending`.
- **Offline durability:** when Supabase is unreachable, `publish()` appends to `tmp/events_offline.jsonl`. The replay job `drain_offline_queue()` re-publishes when connectivity returns.
- **Wake-up latency:** with the LISTEN path active, sub-100ms from `publish` to handler. With polling fallback, 0-5000ms (5-second poll cadence — tunable via `poll_interval_seconds`).

## Operations

```bash
# Publish from CLI
python scripts/event_bus.py publish --type BRAVO_TEST --payload '{"hello":"world"}'

# Tail recent events (for debugging)
python scripts/event_bus.py tail --agent bravo

# Stats: counts per status, per agent
python scripts/event_bus.py stats

# Manually re-queue visibility-timeout rows (cron job runs this every 60s)
python scripts/event_bus.py reap

# Replay offline queue after Supabase outage
python scripts/event_bus.py drain
```

## Relationship to other V6 systems

- **State DB (`state/empire_state.db`)** — local-only; the event bus is its cross-agent broadcast layer. State DB writes (`append_session_log`, `heartbeat`) auto-emit corresponding events.
- **Pulse files (`data/pulse/ceo_pulse.json`)** — still the per-agent snapshot. The bus broadcasts CHANGES to the snapshot; the file remains the canonical "current state" reference.
- **Agent inbox (`scripts/agent_inbox.py`)** — durable point-to-point messages with response expectations. Bus is fire-and-forget broadcast/multicast. Use inbox when you NEED a reply; use bus when you just want subscribers to know.

## Obsidian
- [[brain/CAPABILITIES]] · [[brain/AGENTS]] · [[brain/CROSS_AGENT_AWARENESS]] · [[ARCHITECTURE]]
