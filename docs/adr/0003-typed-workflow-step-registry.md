---
adr: 0003
title: Typed workflow step registry (V6.9.2)
status: accepted
date: 2026-05-25
deciders: [bravo, cc]
supersedes: null
superseded_by: null
tags: [docs, adr, decision]
last_updated: 2026-05-25
---

# ADR-0003 — Typed workflow step registry

## Context

The dashboard's Automations tab was a skeleton — `TenantAutomations.tsx` rendered an empty surface, every "automation" was a bespoke Python daemon in `scripts/` with hand-rolled trigger + step logic. Operators could not define their own workflows.

Pattern observed at [twentyhq/twenty](https://github.com/twentyhq/twenty) (AGPLv3 — patterns only): every workflow step is a typed handler with a common interface, dispatched at runtime by a registry table. Adding a new step type means a new file + one registry entry. Composability comes from the (trigger + ordered steps) shape, not from a DSL.

Cross-reference table in `~/.claude/plans/i-m-dropping-you-a-magical-cat.md` confirmed this is a load-bearing gap closer.

## Decision

The workflow engine in `~/APPS/oasis-command-center/lib/workflow-steps/` follows three rules:

### 1. One file per step type, default-exporting a `WorkflowStep`

```ts
// lib/workflow-steps/<type>.ts
import type { WorkflowStep } from "./types";

const handler: WorkflowStep = {
  type: "<type>",
  async execute(input: unknown, ctx: StepContext): Promise<StepResult> { ... },
};
export default handler;
```

The `type` string is the lookup key; the file name SHOULD match for grep-ability.

### 2. The registry in `run-step.ts` is explicit — no `eval` / dynamic require

```ts
const REGISTRY: Record<string, WorkflowStep> = {
  [recordCrud.type]: recordCrud,
  [aiAgent.type]: aiAgent,
  // ...
};
```

Security review can read one file to know every step type that exists. Adding a step is a two-line change (import + registry entry).

### 3. The dispatcher (`runStep`) enforces step + outbound caps BEFORE calling the handler

`step_count_remaining <= 0` → `failed: step_cap_exhausted`. The handler never sees an exhausted context. Outbound caps (`outbound_cap_remaining`) are the responsibility of send-routed steps (mail-sender, future sms-sender) — they check before fan-out and return `failed: outbound_cap_would_exceed` proactively.

### Substrate set (V6.9.2 + V6.9.3) — 6 step types

| type | purpose | depends on | current state |
|---|---|---|---|
| `record-crud` | create/update/delete `tenant_records` | service-role Supabase client | functional (V6.9.5: update uses fetch-then-merge) |
| `http-request` | outbound fetch w/ timeout | network | functional (V6.9.5: SSRF guard against private/metadata IPs) |
| `if-else` | predicate eval → `then`/`else` branch label | (pure) | functional |
| `delay` | sleep inline only (≤5s) | (pure) | gated — long delays return failed pending workflow_runner.py daemon (V6.9.2.x) |
| `mail-sender` | (will) route email through bridge `/exec-tool` → `send_gateway` | bridge daemon | **gated — refuses to fire pending bridge-exposed send_gateway tool** (V6.9.5.1 honesty fix; see note below) |
| `ai-agent` | Anthropic call w/ persona + template substitution | `ANTHROPIC_API_KEY` | functional (V6.9.5: `anthropic-version: 2023-06-01` matching repo) |

**Note on `mail-sender` chokepoint compliance (V6.9.5.1):** ADR principle is that
mail-sender MUST route through `send_gateway`. The bridge today exposes
`send_email` which calls `scripts/integrations/google_tool.py` — documented at
google_tool.py:262 as an OPERATOR CLI exception that intentionally bypasses
`send_gateway`. V6.9.2's initial implementation had a broken wire format
(would 400). V6.9.5's first hotfix made the wire format work by routing
through `send_email` — but that meant bypassing the chokepoint, violating
the principle. V6.9.5.1 reverted the step to a `failed` state with an
explicit setup pointer, awaiting a bridge-exposed `send_gateway` tool
(scripts/bravo_cli/bridge_chat_server.py needs a new tool_name registered).
This is the right tradeoff: a gated step that refuses to fire is honest;
a functional step that bypasses CASL/cooldown/daily-cap is not.

### Anti-slop guardrails

- No DSL bloat. `if-else`'s predicate language has 9 ops; anything more becomes a custom step type.
- No silent passes. Every unknown input shape returns `{ status: 'failed', error: '<reason>' }`.
- No bypass of `send_gateway`. The `mail-sender` step MUST route through the bridge's `/exec-tool` → CASL + cooldown + daily-cap chokepoint. **A step that fulfills its principle by failing-with-pointer is preferable to a step that runs by bypassing the principle.** New outbound step types follow the same rule.

## Consequences

- Adding a step type is a small isolated commit: one new file + one REGISTRY line + one ADR-0001 dep classification.
- Workflow definitions stored as JSONB in `workflows.definition` are forward-compatible with new step types; old definitions don't break when the registry grows.
- The bridge daemon (V6.9.2.x `scripts/workflow_runner.py`) is the only consumer of `runStep`; it claims pending `workflow_runs` rows via `FOR UPDATE SKIP LOCKED` and invokes the dispatcher via `POST /api/workflows/run-step`.
- Field-level permission enforcement (ADR-0004) wraps step execution at the API boundary — steps do not need to be permission-aware individually.

## Related

- Migration: `database/072_workflow_engine.sql` (workflows + workflow_runs + workflow_run_steps + status enum)
- Implementation: `~/APPS/oasis-command-center/lib/workflow-steps/`
- Tests: `~/APPS/oasis-command-center/tests/workflow-steps.test.ts`
- Plan: `~/.claude/plans/i-m-dropping-you-a-magical-cat.md`
- Source (patterns only): https://github.com/twentyhq/twenty

## Obsidian Links
- [[docs/adr/INDEX]]
- [[CONTEXT]]
