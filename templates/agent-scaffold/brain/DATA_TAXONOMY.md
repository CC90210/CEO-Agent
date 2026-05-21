---
title: Data Taxonomy — {{AGENT_NAME}} — Pantry / Prep Table / Plate
mutability: GOVERNED
purpose: Single source of truth for what data lives where in {{AGENT_NAME}}'s domain. Audit target for skills/silver-platter.
canonical_spec: brain/AGENTIC_OS_REFERENCE.md (§3)
---

# {{AGENT_NAME}} Data Taxonomy

Three tiers, one rule per tier: **Pantry is raw. Prep Table is deterministic Python (no LLM). Plate is what agents consume.**

When in doubt: does it require an LLM call to produce? → not Prep Table. Is it raw API output? → Pantry. Is it the artifact an agent reads to answer the operator? → Plate.

---

## Pantry — Raw Sources

Fill in {{AGENT_NAME}}'s domain integrations. Examples below; replace with real entries as the agent is wired.

| Domain | Source | Access | Owner |
|--------|--------|--------|-------|
| (e.g.) CRM | (e.g.) Supabase `leads` | `scripts/integrations/supabase_tool.py` | {{agent_name}} |
| (e.g.) Payments | (e.g.) Stripe | `scripts/integrations/stripe_tool.py` | {{agent_name}} |
| (e.g.) Comms | (e.g.) Gmail | `scripts/integrations/google_tool.py` | {{agent_name}} |
| Domain-specific N | TBD | TBD | {{agent_name}} |

---

## Prep Table — Deterministic Pre-Aggregations (V6.7 — fill in as agent matures)

Python-only. No LLM. Runs on schedule and writes JSON for O(1) agent reads.

| Snapshot | Script | Schedule | Output | Read by |
|----------|--------|----------|--------|---------|
| (e.g.) Daily briefing | `scripts/snapshots/briefing_snapshot.py` | `0 6 * * *` | `state/snapshots/latest_briefing.json` | briefing skill |
| TBD per domain | TBD | TBD | TBD | TBD |

**Refresh cadence rule:** Read-path checks `ts` field. If > 24h old, fall back to live engines.

**Naming convention:** `state/snapshots/{type}_{date_or_week}.json` + `state/snapshots/latest_{type}.json`.

---

## Plate — Consumers

What the operator and the agent's skills actually read. Snapshot-first; live engines only as fallback.

| Consumer | Source it reads | Delivery channel |
|----------|-----------------|------------------|
| `/briefing` slash command | `latest_briefing.json` → live engines (fallback) | Terminal / Telegram |
| `silver-platter` skill audit | This file + scans `state/snapshots/`, `scripts/snapshots/` | HTML at `tmp/silver-platter-{{agent_name}}-*.html` |
| TBD per domain | TBD | TBD |

---

## Add-a-Source Protocol

When wiring a new integration:

1. **Pantry first:** wrap raw API in `scripts/<source>_tool.py` with `--json`.
2. **Decide Prep Table necessity.** If read > 2×/day, build a snapshot under `scripts/snapshots/`.
3. **If Prep Table:** add row above, register in `cron_engine.py` SEED_JOBS, write the snapshot script.
4. **Update consumers** to prefer snapshot, fall back to live.
5. **Index it:** `silver-platter` picks it up from this file.

---

## Anti-Patterns

- ❌ Agent calls 3+ subprocess CLIs in one turn to assemble a briefing. → Build a snapshot.
- ❌ Snapshot script that calls an LLM. → That's synthesis; belongs in a skill, not Prep Table.
- ❌ Reading raw database from a UI route when a snapshot exists. → Switch to snapshot read.
