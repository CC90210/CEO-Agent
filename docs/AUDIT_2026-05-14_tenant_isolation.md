---
title: Tenant-isolation audit — Reasoning agent-decisions leak
date: 2026-05-14
author: Bravo (Claude Opus 4.7)
trigger: CC screenshot showing OASIS funnel data on /t/sun/reasoning
status: read-layer fixed (proxy); write-layer schema migration deferred
tags: [audit, tenant-isolation, data-leak, schema-debt]
---

# Tenant-isolation audit

## What CC reported

While signed in as the SunBiz tenant (`submissions@sunbizfunding.com`, agents_enabled = `[solara, helios]`), the Reasoning page rendered "Agent Decisions" rows showing OASIS Bravo's autonomous-loop history — including "Inbound lead from CC Funnel — mid-market B2B SaaS, 50-200 employees, classified for routing into outreach pipeline." That's CC's data leaking across tenant boundaries.

## Root cause

Three tables predate the multi-tenant `tenant_manifests` system and have **no `tenant_id` column** to filter by:

| Table | Keyed by | Read paths | Write paths |
|---|---|---|---|
| `agent_decisions` | `agent_name + tick_id` | `recentDecisions()` → /reasoning Agent Decisions card | `scripts/autonomous_agent.py` |
| `agent_state_snapshot` | `agent_name` | `agentStates()` → /agents, /operations Workers card | `scripts/state/state_manager.py heartbeat` |
| `agent_events` | `publisher_agent + correlation_id + idempotency_key` | `recentEvents()` → /operations + /agents Event Bus card | `scripts/state_manager.append_session_log`, `pulse_publish.cmd_refresh`, `bridge_chat_server._v6_log_chat_interaction`, `send_gateway._emit_outbound_sent`, others |

Service-role Supabase reads (which bypass RLS) returned every row regardless of caller. Every existing row was written by CC's OASIS Bravo because that's the only autonomous loop running today. When a SunBiz session hit `/reasoning`, those Bravo rows landed in the SunBiz tenant's view.

## What's now fixed at the read layer (commits `9383d7d` + `<this commit>`)

Proxy filter: scope by `agent_name` / `publisher_agent` ∈ tenant's enabled agents. SunBiz has `[solara, helios]` enabled; every existing row has `agent_name="bravo"` → SunBiz sees zero rows.

- `recentDecisions(tenantId, agentNames, limit)` — filters `agent_name IN agentNames`. Empty agents → empty result (safer than leaking).
- `agentStates(agentNames)` — filters `agent_name IN agentNames`.
- `recentEvents(limit, { agentNames, isOperator, ... })` — filters `publisher_agent IN agentNames`. Operator bypass for the activity-tape debug surface.

Callers updated:
- `app/reasoning/page.tsx` passes `tenant_id + manifestEnabledSlugs`.
- `app/agents/page.tsx` passes `manifestEnabledSlugs + isAdmin`.
- `app/operations/page.tsx` resolves manifest, passes `agentNamesForOps + isOperator`; switched from raw `agent_state_snapshot` query to the `agentStates()` helper.

## What the proxy does NOT cover

The proxy filter has one residual leak: **two tenants who both enable the same agent**. If a second SunBiz-style tenant signs up and enables `solara`, both tenants would see each other's Solara decisions. Today there's exactly one tenant per agent_name combination (CC for Bravo/Atlas/Maven/etc.; the SunBiz test account for Solara/Helios but no decisions exist for those slugs yet), so the leak is **latent, not active**. It becomes real the moment the autonomous loop writes a Solara row from the Marketing-Agent (Phase 3).

## The real fix (deferred — separate migration PR)

### 1. Schema migration

```sql
-- Migration 040 (illustrative)
ALTER TABLE agent_decisions ADD COLUMN tenant_id uuid REFERENCES tenants(id);
ALTER TABLE agent_state_snapshot ADD COLUMN tenant_id uuid REFERENCES tenants(id);
ALTER TABLE agent_events ADD COLUMN tenant_id uuid REFERENCES tenants(id);

-- Backfill existing rows with CC's OASIS tenant (only writer today)
UPDATE agent_decisions SET tenant_id = '<OASIS_TENANT_ID>' WHERE tenant_id IS NULL;
UPDATE agent_state_snapshot SET tenant_id = '<OASIS_TENANT_ID>' WHERE tenant_id IS NULL;
UPDATE agent_events SET tenant_id = '<OASIS_TENANT_ID>' WHERE tenant_id IS NULL;

ALTER TABLE agent_decisions ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE agent_state_snapshot ALTER COLUMN tenant_id SET NOT NULL;
-- agent_events stays nullable for system events with no tenant context.

CREATE INDEX ix_agent_decisions_tenant ON agent_decisions(tenant_id, created_at DESC);
CREATE INDEX ix_agent_state_tenant ON agent_state_snapshot(tenant_id, last_tick_at DESC);
CREATE INDEX ix_agent_events_tenant ON agent_events(tenant_id, published_at DESC);
```

### 2. RLS policies

Mirror what `tenant_records`, `leads`, `lead_interactions` already do:

```sql
ALTER TABLE agent_decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_decisions_tenant ON agent_decisions
  USING (tenant_id = current_tenant_id());

ALTER TABLE agent_state_snapshot ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_state_tenant ON agent_state_snapshot
  USING (tenant_id = current_tenant_id());

ALTER TABLE agent_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_events_tenant ON agent_events
  USING (tenant_id IS NULL OR tenant_id = current_tenant_id());
```

### 3. Writer updates (Python)

Every writer needs to set `tenant_id` on every insert. Today these run as CC's Bravo against OASIS — they all need to read `EMPIRE_TENANT_ID` from `.env.agents` or be invoked with explicit tenant context:

| File | Writes to | Status |
|---|---|---|
| `scripts/autonomous_agent.py` | `agent_decisions` | needs tenant_id on every insert |
| `scripts/state/state_manager.py heartbeat` | `agent_state_snapshot` | needs tenant_id |
| `scripts/state/state_manager.py append_session_log` | `agent_events` | needs tenant_id |
| `scripts/pulse_publish.py cmd_refresh` | `agent_events` | needs tenant_id |
| `bravo_cli/bridge_chat_server.py _v6_log_chat_interaction` | `agent_events` | needs tenant_id |
| `scripts/integrations/send_gateway.py _emit_outbound_sent` | `agent_events` | needs tenant_id |
| `app/api/chat/route.ts (logAction)` | `agent_events` | TS path; already has `tenantId` in scope, just needs to pass it |

### 4. Reader simplification

After migration + backfill + writer updates:
- `recentDecisions` switches to `.eq("tenant_id", tenantId)` as primary filter.
- `agentStates` same.
- `recentEvents` same (with `OR tenant_id IS NULL` for system events).
- Keep `agentNames` as secondary filter ("decisions from agents I currently have enabled" — different concern from "decisions I'm allowed to see").

## Audit of every other `lib/queries.ts` function

Confirmed scoped (no further action):

- `getActiveProfile`, `getTenant`, `getTodayPlan`, `getPlanTemplates`, `getLeadById`, `todayCounts`, `pipelineBreakdown`
- `recentInbound`, `recentOutbound`, `recentLeads`, `recentActions`, `channelUtilization`
- `integrationsHealth`, `topClientConcentration`, `outreachReplyRate`, `activePipeline`, `topOpenLead`
- `mrrSnapshot`, `mrrHistory` (session-scoped via `getActiveProfile`)
- `aiServicesWithKey`
- `getRenewalsSummary`, `getRenewalsRows`, `getSmsHistory`, `getApplicationsCount`, `getLeadsForTenant`

Schema-debt (now read-layer-proxied):

- `recentDecisions` ⚠
- `agentStates` ⚠
- `recentEvents` ⚠

## Verification

- A SunBiz session loads `/reasoning` → Agent Decisions card empty ("No decisions yet").
- CC's OASIS session loads `/reasoning` → sees Bravo decisions as before.
- A SunBiz session loads `/operations` → Activity tape empty (no Solara events exist yet) or shows only Solara events once Phase 3's autonomous loop fires.
- CC's OASIS session loads `/operations` → sees the full event tape (operator bypass).

## What CC asked for vs. what I delivered

**CC's ask:** "do a deep diagnostic and audit and make sure there is no data spillover or leakage for anyone."

**Delivered (this audit):**
1. Identified the three tenant-id-less tables and every reader/writer touching them.
2. Closed the visible leak at the read layer via proxy filter.
3. Documented the full migration plan including the writer updates that need to land in lockstep.

**Not delivered:**
1. The actual schema migration. That's a separate PR — adding the column is one line; backfilling correctly + updating all writers + adding RLS is the rest, and any writer that misses the update breaks `INSERT` once the column is `NOT NULL`. It needs its own session with explicit testing of every writer.

— Bravo, 2026-05-14
