---
name: vibe-to-execution
description: Translate an informal brain dump or voice transcript into a turnkey, production-grade execution blueprint — resolved domain vocabulary, DB/API contracts, UI interaction design, and the exact CLI/tool routing. Use when CC describes what he wants in loose prose rather than a spec, when a request arrives as a voice note, or when a one-liner implies a whole system.
triggers: ["vibe to execution", "brain dump", "voice note", "turn this into a spec", "translate this into a build", "make this a system message", "what i mean is", "here is the vibe"]
tier: strategic
mutability: EVOLVING
tags: [skill, translation, architecture, blueprint, prompt-engineering, anti-slop]
last_updated: 2026-07-29
---

# Vibe → Execution — Neural Translation Protocol (V8.0)

> **The problem.** CC thinks out loud. A request arrives as *"the email thing should just
> handle CodeRabbit comments and fix them, closed loop, even when I'm off my computer."*
> That sentence contains a schema, a cron, an autonomy policy, three failure modes and a
> security boundary. An agent that answers the literal sentence ships a stub. An agent that
> extrapolates without discipline ships slop. This protocol is the middle: **extrapolate the
> full system, then prove every inference against the source.**

## The iron rule

**Extrapolate ambition. Never extrapolate facts.**

Widen scope to the complete working system CC obviously wants — the cron, the guard, the
alert, the test. But every concrete detail (column name, script path, env key, API signature)
comes from reading the source, never from inference. Rows 1 and 7 of the Anti-Slop Matrix are
the two halves of this rule.

---

## Phase 1 — Dissect the dump (no code yet)

Extract four layers. Anything you cannot fill from the transcript is an **open question**, not
a default you quietly invent.

### 1a. Core intent & domain vocabulary
- Restate the request in one sentence a non-technical founder would confirm.
- Canonicalize every domain term against `CONTEXT.md` — Pulse, OASIS Outbound, Interaction,
  tenant, drip sequence, Inbound CRM. **Never re-derive a term the glossary defines.**
- Separate the **stated** ask from the **implied** system. "Handle CodeRabbit comments" implies
  harvest + triage + fix + verify + report + schedule. Name the implied parts explicitly so CC
  can veto rather than discover them later.

### 1b. Backend & data contracts
- Tables touched: exact names and columns, read via `Read`/`grep` or
  `mcp__supabase__list_tables`. **A guessed column is Anti-Slop #7.**
- Migration needed? → `database/NNN_*.sql`, applied with `scripts/apply_migration.py`.
- RLS: does this path cross a tenant boundary? Reads scoped **and** writes stamped (Rule 17).
- Background work: cron row in `cron_engine.py SEED_JOBS`, or a PM2 daemon, or neither.
- Idempotency: what is the dedup key, and where is it persisted? (`lib/json_ledger.py`.)

### 1c. Frontend & interaction design
- Component hierarchy and where state lives (server component / client / URL).
- The empty, loading, and error states — **all three**, or it is not shipped.
- Visual tokens: real palette and type scale. If the answer is "gradient hero + 3 icon cards",
  that is Anti-Slop #4; start again.
- Which repo? Dashboard work is `~/APPS/oasis-command-center`, never this one (RULE 7).

### 1d. Agent harness & tool routing
- Resolve the owner: `python scripts/capability_query.py resolve "<intent>"`.
- Probe every service the plan touches: `python scripts/capability_probe.py check <service>`.
  AVAILABLE means authorized — Anti-Slop #1.
- Name the exact scripts (`scripts/integrations/*_tool.py`), MCP tools, and subagents.
- Model calls go through `scripts/lib/claude_cli.py` (subscription OAuth). Never an API key.
- Outbound sends go through `scripts/integrations/send_gateway.py`. No exceptions.

---

## Phase 2 — Emit the blueprint

Produce a **copy-pasteable system message** for a high-capability executor (Bravo, Claude Code,
Codex). Structure:

```
OBJECTIVE      one sentence, the outcome — not the activity
CONTEXT        repo + branch, canonical vocabulary, what already exists (with file:line)
CONTRACTS      schema / API / env keys — each one VERIFIED, with the command that verified it
BUILD          ordered mutations, each with the file it touches
GUARDRAILS     what must never happen (money, credentials, main, force-push, prod)
VERIFICATION   the exact command per step, and what its output must show
OPEN QUESTIONS anything a default would have silently decided
```

**Quality bar:** the executor must be able to work from the blueprint alone, without
re-deriving anything and without a single guess. If a step says "update the schema", it is not
finished — name the table and the column.

## Phase 3 — Execute the 8-step closed loop

Hand off to `brain/EXECUTION_RULES.md` § 18. The blueprint is step 3 of that loop, not a
replacement for it. Steps 5 (DB gate) and 7 (CI + machine review) are the ones agents skip;
if they do not apply, say so out loud — silence reads as done.

---

## Calibration — when NOT to use this

A brain dump is not every message. Per the Triage block in the entry points:

- "wsp" / "thanks" / an emoji → answer in one line. No skill, no tool call.
- A quick factual question → answer it.
- A single-file fix → just fix it. This protocol's overhead exceeds the task.

Use it when the request is **loose prose implying a system**, when a one-liner hides a schema,
or when CC explicitly asks for a spec or a system message.

## Worked example

> **CC:** *"the email thing should just handle CodeRabbit comments and fix them, closed loop,
> even when I'm off my computer"*

| Layer | Extrapolated | Verified against |
|---|---|---|
| Intent | Automated review findings become pushed fixes without CC present | — |
| Vocabulary | "the email thing" = the inbound sweep, `email_engine.cmd_check_inbox` | `CONTEXT.md`, `brain/EMAIL_PIPELINE.md` |
| Data | No new table. Seen-set + queue as JSON ledgers | `lib/json_ledger.py` |
| Source of truth | Email is a NOTIFICATION; live `gh` GraphQL is truth (`isResolved`/`isOutdated` exist only there) | GitHub API docs |
| Harness | `review_harvest` → `review_fix` → `review_loop`, cron `*/15` with `timeout: 1500` | `cron_engine.py SEED_JOBS` |
| Guardrails | Never merge, never `main`, never force-push; escalate migrations/credentials/CI/money | `review_fix.DANGER_PATHS` |
| Verification | `--dry-run` first, then one low-severity live run, inspect the pushed diff | — |

The implied-but-unstated parts — the cron cadence, the danger-path escalation, the test
baseline before editing — are exactly what "turnkey" meant. Surfacing them **before** building
is the whole job.

## Related

[[brain/EXECUTION_RULES]] (§ 18 the loop, § 19 the Anti-Slop Matrix) · [[CONTEXT]] ·
[[brain/AGENT_ROUTER]] · [[skills/writing-plans/SKILL]] · [[skills/sop-breakdown/SKILL]] ·
[[skills/self-evolution/SKILL]]
