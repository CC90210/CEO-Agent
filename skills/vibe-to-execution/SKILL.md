---
name: vibe-to-execution
description: Translate an informal brain dump, voice transcript, or screenshot into a turnkey, production-grade execution blueprint — Opus 5 execution contract, resolved domain vocabulary, verified DB/API contracts, UI interaction design, exact CLI/tool routing, and the 7 mandatory production defenses. Use when CC describes what he wants in loose prose rather than a spec, when a request arrives as a voice note or a screenshot, or when a one-liner implies a whole system.
triggers: ["vibe to execution", "brain dump", "voice note", "turn this into a spec", "translate this into a build", "make this a system message", "write me a system prompt", "what i mean is", "here is the vibe"]
tier: strategic
mutability: EVOLVING
tags: [skill, translation, architecture, blueprint, prompt-engineering, anti-slop, opus5]
last_updated: 2026-08-02
---

# Vibe → Execution — Neural Translation Protocol (V9.0 · Opus 5 Agentic)

> **The problem.** CC thinks out loud. A request arrives as *"the email thing should just
> handle CodeRabbit comments and fix them, closed loop, even when I'm off my computer."*
> That sentence contains a schema, a cron, an autonomy policy, three failure modes and a
> security boundary. An agent that answers the literal sentence ships a stub. An agent that
> extrapolates without discipline ships slop. This protocol is the middle: **extrapolate the
> full system, then prove every inference against the source.**

**V9.0 delta (2026-08-02):** adds the Opus 5 execution contract (Phase 0), multimodal intake
(screenshots + audio transcripts), the 7 mandatory production defenses that every emitted
system message must carry, and a fixed output skeleton so blueprints are copy-pasteable
without reformatting.

## The iron rule

**Extrapolate ambition. Never extrapolate facts.**

Widen scope to the complete working system CC obviously wants — the cron, the guard, the
alert, the test. But every concrete detail (column name, script path, env key, API signature)
comes from reading the source, never from inference. Rows 1 and 7 of the Anti-Slop Matrix are
the two halves of this rule.

---

## Phase 0 — The Opus 5 execution contract (applies to you AND to every prompt you emit)

Four protocols. They govern how the blueprint is written *and* are restated inside every
system message it produces, because the executor is usually a fresh context.

**0a. Zero-stub mandate.** Complete the feature suite end-to-end in one run. No `// TODO`, no
`pass  # implement later`, no truncated edit that "the next agent can finish", no handler that
returns a success shape it did not compute. If the work genuinely cannot finish — a credential
only CC can create, a vendor account, a human approval — finish everything that does not
depend on it and name the blocker explicitly. Partial delivery is acceptable; *silent* partial
delivery is the defect.

**0b. Scope boundary control.** Deliver what was asked, at the scope intended. Make routine
technical judgment calls independently — file layout, helper naming, which existing util to
reuse. If the request looks mistaken, state the alternative in **one sentence** and continue as
asked; CC's reaffirmation ends the debate. Do not widen into adjacent files, do not "tidy while
you're here" (Anti-Slop #5), do not narrow the ask because part of it looks hard.

**0c. Controlled subagent delegation.** Spawn subagents only for large, genuinely independent,
parallelizable tracks — a multi-file backend implementation running beside frontend work, a
codebase-wide sweep, an independent audit. **Never** spawn one for a trivial edit, for a
lookup you can do in two greps, or to re-verify your own work; self-verification is a command
you run, not an agent you hire. The one delegation that is always correct is the *independent*
audit on a big task: `python scripts/core/codex_review.py review --session "<slug>"` (Rule 8),
because its value is that it is not you.

**0d. Focused narration.** One sentence before the first tool call stating what you are about
to do. No plan recitation, no "I'll start by…" preamble per step. The final report **leads with
the outcome** — what now exists and works — then the proof beneath it. Progress chatter is
noise; the four-line report is the product.

---

## Phase 1 — Dissect the dump (no code yet)

Extract four layers. Anything you cannot fill from the transcript is an **open question**, not
a default you quietly invent.

### 1a. Core intent, multimodal intake & domain vocabulary
- Restate the request in one sentence a non-technical founder would confirm.
- **Voice transcripts are lossy.** Numbers, names, domains and env keys survive dictation
  badly ("dot work" / "dot org", "OASIS" / "Oasis AI"). Echo every literal back for
  confirmation rather than committing it to a config file.
- **Screenshots are evidence, read them directly.** `Read` renders images natively — read the
  image before describing it. A screenshot of an error is the stack trace; a screenshot of a
  UI is the spec, including its spacing and type scale. Never paraphrase a screenshot you have
  not opened.
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

## Phase 2 — The 7 mandatory production defenses

These are the defects that reach production from vibe-coded work. **Every** system message this
skill emits carries this block verbatim, scoped to the task at hand — a defense that does not
apply is marked `N/A — <reason>`, never deleted. Silence reads as "handled".

| # | Defense | The enforcement, in this repo |
|---|---|---|
| 1 | **Probe credentials first** | `python scripts/capability_probe.py check <service>` (or `list`) before claiming any gap. AVAILABLE = authorized, run the tool. Never attempt to read `.env*` — `secret_guard` blocks it and logs the attempt to `state/secret_guard.log`. "I don't have access" is true only after the probe exits non-zero and you quote that output. |
| 2 | **No UI-only security** | Authorization is re-checked server-side on **every** endpoint — session/JWT verified in the route handler, RLS enabled *and* forced on the table. A hidden button is not a blocked route; a client-side redirect is not a gate. See EXECUTION_RULES § 13 (public routes need two layers) and § 14 (boundaries are server-side). |
| 3 | **Tenant data isolation** | Every multi-tenant query carries an explicit `tenant_id` / `user_id` filter, and every insert stamps the same value (§ 17 — write what you filter). Prove it by querying as anon **and** as an authed user of the wrong tenant. `apply_migration.py --allow-rls` is required when a migration touches RLS and it means "I ran both queries". |
| 4 | **Closed-loop error tracking** | No bare `except: pass`, no broad catch that returns a success shape. Log the full traceback and publish an `agent_events` row — `event_type`, `publisher_agent`, `severity` (`warn`/`error` surfaces in dashboards), `payload`, `correlation_id`, `published_at`. Incident: `notify.py` swallowed a TLS failure and the inbox sweep died 31 times over 25 hours with zero alerts. |
| 5 | **Verified restore point before schema change** | The gate is runnable, so run it: `python scripts/db_snapshot.py create --name pre-<migration>` then `python scripts/db_snapshot.py verify --max-age-hours 1` — exit 0 means a checksummed, complete, fresh baseline exists (schema + exact row counts, optional `--rows` export). Then `apply_migration.py <file> --dry-run` and `--status`. Destructive verbs are hard-blocked by `BLOCKED_PATTERNS`, and that guard is explicitly **not a substitute for a backup**. `db_snapshot` is a *logical* baseline — it proves what existed and detects what changed; byte-level point-in-time restore is Supabase PITR in the dashboard. For a genuinely destructive change, confirm the PITR window covers the snapshot timestamp. `verify` non-zero → you do not have a restore point; escalate to CC rather than applying. |
| 6 | **Server-side payment math** | Every amount is computed server-side from the DB or a Stripe price object — never from a client-supplied number. Webhook handlers verify the Stripe signature *before* trusting the body, and dedup on `event.id` scoped by tenant. CLI: `python scripts/integrations/stripe_tool.py`. Money paths are also a Rule 9 irreversible line: operator confirmation, always. |
| 7 | **Zero unrequested visual rewrites** | Touch only the components the request names. Before shipping a UI change, capture the core pages (`python scripts/browser/browse_and_capture.py`) and compare against the previous state or CC's reference image side by side. Shipping a redesign nobody asked for is Anti-Slop #4 and #5 at once. |

**Relationship to the Anti-Slop Matrix.** The matrix in the entry points (EXECUTION_RULES § 19)
governs how *you* work; this table governs what the *system you build* must guarantee. Both
apply. Rows 1, 4 and 7 overlap deliberately — those three are where the fleet actually bleeds.

---

## Phase 3 — Emit the blueprint (fixed skeleton, copy-pasteable)

Output a system message a fresh high-capability executor (Bravo, Claude Code, Codex) can work
from **alone**, without re-deriving anything and without a single guess. Use this exact
skeleton — no preamble above it, no commentary below it:

````markdown
# SYSTEM PROMPT: [DESCRIPTIVE TASK TITLE]

**MODE: FIX-FIRST EXECUTION MODE (NO PLANNING, NO PROPOSALS, EXECUTE IMMEDIATELY)**

---

## 1. OBJECTIVE & EXECUTIVE SUMMARY
[2–3 sentences. The outcome, not the activity. Name the repo and branch, and the
canonical vocabulary this task uses (from CONTEXT.md).]

---

## 2. DETAILED EXECUTION PHASES
[Numbered, ordered, actionable. Every phase names the exact file it touches. Each
phase carries, inline:
  - CONTRACT   — the table/column, API signature, or env key it depends on, plus the
                 command that VERIFIED it exists (not an assumption)
  - MUTATION   — what changes, in which file
  - VERIFY     — the exact command to run, and what its output must show to pass
Phases cover UI, backend, DB schema/migration, and agent/harness wiring as applicable.]

---

## 3. STRICT EXECUTION RULES
1. **Fix-First Execution:** Execute immediately. No permission requests, no proposals,
   no plan-for-approval. Complete the whole suite end-to-end — zero stubs, zero TODOs,
   zero truncated edits. A genuine blocker is named explicitly, never left silent.
2. **Controlled Delegation & Scope:** Do the work directly. Spawn subagents only for
   large, independent, parallelizable tracks — never for trivial edits or to re-verify
   your own output. Touch only what the task names.
3. **Outbound Chokepoint Discipline:** All email and messaging routes through
   `scripts/integrations/send_gateway.py`. Model calls go through
   `scripts/lib/claude_cli.py` — never an API key. Money and production pushes require
   operator confirmation.
4. **Mandatory Four-Line Report:** Changed (paths) · Why (one plain sentence each) ·
   Proof (the verification command AND its actual output) · Needs from CC (or "nothing").

### 3.1 Mandatory Production Defenses — all 7 apply
[Paste the Phase 2 table, scoped to this task. Any defense that does not apply is
marked `N/A — <reason>`. Never delete a row.]

---

## 4. OPEN QUESTIONS
[Anything a default would have silently decided. Empty is a valid answer; omitting the
section is not.]
````

**Quality bar:** if a step says "update the schema", it is not finished — name the table and
the column. If a step says "verify it works", it is not finished — name the command and the
string its output must contain.

## Phase 4 — Execute the 8-step closed loop

Hand off to `brain/EXECUTION_RULES.md` § 18. The blueprint is step 3 of that loop, not a
replacement for it. Steps 5 (DB gate) and 7 (CI + machine review) are the ones agents skip;
if they do not apply, say so out loud — silence reads as done. On a big task (≥3 commits, ≥5
files, or any user-facing change) step 7 also requires the independent Codex audit, presented
verbatim alongside your own self-review (Rule 8).

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
| Defenses | #4 every failed fix publishes an `agent_events` row; #5 N/A (no schema change); #6 N/A (no money path) | Phase 2 table |
| Verification | `--dry-run` first, then one low-severity live run, inspect the pushed diff | — |

The implied-but-unstated parts — the cron cadence, the danger-path escalation, the test
baseline before editing — are exactly what "turnkey" meant. Surfacing them **before** building
is the whole job.

## Related

[[brain/EXECUTION_RULES]] (§ 18 the loop, § 19 the Anti-Slop Matrix, § 20 the Opus 5 contract) ·
[[CONTEXT]] · [[brain/AGENT_ROUTER]] · [[skills/writing-plans/SKILL]] ·
[[skills/sop-breakdown/SKILL]] · [[skills/self-evolution/SKILL]] ·
[[skills/codex-delegation/SKILL]]
