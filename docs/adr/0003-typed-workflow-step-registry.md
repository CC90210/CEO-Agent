---
adr: 0003
title: Typed workflow step registry (V6.9.2)
status: accepted
date: 2026-05-25
deciders: [bravo, cc]
supersedes: null
superseded_by: null
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

| type | purpose | depends on |
|---|---|---|
| `record-crud` | create/update/delete `tenant_records` | service-role Supabase client |
| `http-request` | outbound fetch w/ timeout | network |
| `if-else` | predicate eval → `then`/`else` branch label | (pure) |
| `delay` | sleep w/ inline (<5s) or deferred (>5s) mode | (pure) |
| `mail-sender` | route email through bridge `/exec-tool` → `send_gateway` | bridge daemon |
| `ai-agent` | Anthropic call w/ persona + template substitution | `ANTHROPIC_API_KEY` |

### Anti-slop guardrails

- No DSL bloat. `if-else`'s predicate language has 9 ops; anything more becomes a custom step type.
- No silent passes. Every unknown input shape returns `{ status: 'failed', error: '<reason>' }`.
- No bypass of `send_gateway`. The `mail-sender` step MUST route through the bridge's `/exec-tool` → CASL + cooldown + daily-cap chokepoint. New outbound step types follow the same rule.

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
