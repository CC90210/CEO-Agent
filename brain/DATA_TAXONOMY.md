---
description: "Maps data through three tiers (Pantry=raw sources, Prep Table=aggregated snapshots, Plate=consumed views) to route queries and validate freshness"
title: Data Taxonomy — Pantry / Prep Table / Plate
mutability: GOVERNED
purpose: Single source of truth for what data lives where, how it's aggregated, and which consumers read which views. The audit target for the silver-platter skill.
related: brain/AGENTIC_OS_REFERENCE.md (§3 — the principle), brain/CAPABILITIES.md (tool inventory)
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
---
# Data Taxonomy

Three tiers, one rule per tier: **Pantry is raw. Prep Table is deterministic Python (no LLM). Plate is what agents consume.**

When in doubt: does it require an LLM call to produce? → not Prep Table. Is it raw API output? → Pantry. Is it the artifact an agent reads to answer CC? → Plate.

---

## Pantry — Raw Sources

External integrations and on-disk raw data. Agents should NOT read these directly during a synthesis turn — read the matching Prep Table snapshot instead.

| Domain | Source | Access | Owner |
|--------|--------|--------|-------|
| Sales / CRM | Supabase `leads`, `lead_interactions`, `revenue_events` | `scripts/integrations/supabase_tool.py`, `scripts/lead_engine.py` | Bravo |
| Revenue | Stripe (subs, charges, balance) | `scripts/integrations/stripe_tool.py`, `scripts/revenue_engine.py sync-stripe` | Bravo |
| Comms | Gmail, Google Calendar, GWS | `scripts/integrations/google_tool.py` | Bravo |
| Inbound funnel | JotForm webhooks, n8n triggers, funnel_leads table | `scripts/core/cron_engine.py` (Funnel Fast-Poll), `scripts/inbound_classifier.py` | Bravo |
| Content | Late / Zernio (cross-platform posts) | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | Maven (CMO-Agent) |
| Finance / Trading | Kraken, QuickBooks API | (Atlas-owned: `~/APPS/trading-agent/`) | Atlas |
| Ops state | `state/empire_state.db` (SQLite/WAL), `state/memory_index.db` (FTS5+LanceDB) | `scripts/state/state_manager.py`, `scripts/core/memory_retriever.py` | Bravo |
| On-disk data | `data/competitors.json`, `data/email_suppressions.csv`, `data/pulse/`, `data/content_research/` | direct file read | Bravo |
| Cross-agent inbox | `tmp/agent_inbox/inbox/`, `tmp/agent_inbox/read/` | `scripts/core/agent_inbox.py` | Bravo |
| Event bus | Postgres `agent_events` (LISTEN/NOTIFY), `tmp/events_offline.jsonl` fallback | `scripts/core/event_router.py` | Bravo |

---

## Prep Table — Deterministic Pre-Aggregations

Python-only. No LLM. Runs on a schedule (cron) and writes a JSON artifact agents can read in O(1). The whole point: agents stop burning context on retrieval.

| Snapshot | Script | Schedule | Output | Read by |
|----------|--------|----------|--------|---------|
| Daily briefing | `scripts/snapshots/briefing_snapshot.py` | `0 6 * * *` | `state/snapshots/latest_briefing.json` + dated | `skills/ceo-briefing/`, `skills/ceo-dashboard/`, `agents/chief-of-staff.md` |
| Weekly qualified leads | `scripts/snapshots/leads_snapshot.py` | `0 22 * * SAT` | `state/snapshots/latest_leads.json` + ISO-week | `agents/revenue-hunter.md`, `agents/chief-of-staff.md` |
| Daily client alerts | `scripts/snapshots/client_alerts_snapshot.py` | `0 7 * * *` | `state/snapshots/latest_client_alerts.json` + dated | `agents/chief-of-staff.md`, `skills/client-success/` |
| FTS5 + vector index | `scripts/core/memory_retriever.py update` (incremental on PostToolUse Edit/Write) | event-driven | `state/memory_index.db` + `state/memory_index.lance/` | All hooks + agents via `memory_retriever.py query` |
| Stripe → revenue_events | `scripts/revenue_engine.py sync-stripe` | `0 6 * * *` (existing) | Supabase `revenue_events` rows | `revenue_engine.py mrr`, downstream snapshots |
| Funnel lead sync | `scripts/core/cron_engine.py` action_type `funnel_sync` | `*/5 * * * *` | Supabase `leads` (welcome email backstop) | `lead_engine.py`, downstream snapshots |

**Refresh cadence rule:** Read-path checks `ts` field. If > 24h old (or > 8 days for weekly), trigger a manual rebuild or fall back to live engines.

**Naming convention:** `state/snapshots/{type}_{date_or_week}.json` + `state/snapshots/latest_{type}.json` (copy, not symlink — Windows-compatible).

---

## Plate — Agent / Operator Consumers

What CC and the agents actually read. Snapshot-first; live engines only as fallback.

| Consumer | Source it reads | Delivery channel |
|----------|-----------------|------------------|
| `/briefing` slash command | `latest_briefing.json` → `revenue_engine`, `lead_engine`, `client_health` live (fallback) | Terminal / Telegram |
| `agents/chief-of-staff.md` | `latest_briefing.json`, `latest_client_alerts.json`, `latest_leads.json` | Terminal / Telegram digests |
| `agents/revenue-hunter.md` | `latest_leads.json` | Outreach session output |
| `agents/researcher.md` | `memory_retriever.py query` over Prep Table indexes | Terminal |
| Command Center web | Supabase + state-api fastapi service (separate from snapshots) | `oasis-command-center:` Next.js |
| Telegram bridge | `latest_briefing.json` on demand via `telegram_agent.js` | Telegram chat |
| `ceo-dashboard` skill | `latest_briefing.json` → `ceo_dashboard.py` live (fallback) | Terminal / Markdown report |
| `silver-platter` skill (audit) | This file + scans `state/snapshots/`, `scripts/snapshots/`, `memory/` | HTML report at `tmp/silver-platter-*.html` |

---

## Add-a-Source Protocol

When wiring a new integration:

1. **Pantry first:** Get the raw data flowing (`scripts/*_tool.py` CLI wrapper with `--json`).
2. **Decide if it needs a Prep Table.** If agents will read it more than 2×/day, build a snapshot script under `scripts/snapshots/`. Else, agents can call the CLI directly.
3. **If Prep Table:** add a row to the table above, register in `scripts/core/cron_engine.py` SEED_JOBS, write a `scripts/snapshots/<name>_snapshot.py`. Output to `state/snapshots/latest_<name>.json`.
4. **Update consumers:** the agents/skills that read it should prefer the snapshot, fall back to live.
5. **Index it:** `silver-platter` audit picks it up automatically from this file.

---

## Anti-Patterns

- ❌ Agent calls 3+ subprocess CLIs in one turn to assemble a briefing. → Build a snapshot.
- ❌ Hand-edited `memory/LEAD_TRACKER.csv` as if it were a Prep Table. → Decide: is it Pantry (raw input) or Plate (curated view)? Pick one role; don't mix.
- ❌ Snapshot script that calls an LLM. → That's not Prep Table, that's a synthesis step belonging in a skill.
- ❌ Reading raw Supabase from an `oasis-command-center:` API route when a snapshot exists. → Switch to snapshot read; saves wall time + Vercel cold-start cost.
