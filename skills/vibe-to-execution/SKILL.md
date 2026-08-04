---
name: vibe-to-execution
description: Translate an informal brain dump, voice transcript, or screenshot into a turnkey, production-grade execution blueprint — an interactive clarification pass that asks CC every high-leverage question (up to 4) before building, Opus 5 execution contract, resolved domain vocabulary, verified DB/API contracts, UI interaction design, exact CLI/tool routing, and the 7 mandatory production defenses. Use when CC describes what he wants in loose prose rather than a spec, when a request arrives as a voice note or a screenshot, or when a one-liner implies a whole system.
triggers: ["vibe to execution", "brain dump", "voice note", "turn this into a spec", "translate this into a build", "make this a system message", "write me a system prompt", "what i mean is", "here is the vibe"]
tier: strategic
mutability: EVOLVING
tags: [skill, translation, architecture, blueprint, prompt-engineering, anti-slop, opus5]
last_updated: 2026-08-03
---

# Vibe → Execution — Neural Translation Protocol (V9.1 · Interactive Clarification Loop)

> **The problem.** CC thinks out loud. A request arrives as *"the email thing should just
> handle CodeRabbit comments and fix them, closed loop, even when I'm off my computer."*
> That sentence contains a schema, a cron, an autonomy policy, three failure modes and a
> security boundary. An agent that answers the literal sentence ships a stub. An agent that
> extrapolates without discipline ships slop. This protocol is the middle: **extrapolate the
> full system, then prove every inference against the source.**

**V9.1 delta (2026-08-03):** adds **Phase 1.5 — the Interactive Clarification Loop**. V9.0 had
exactly two outcomes for a fact it could not verify: invent a default (slop) or ship it as an
open question the executor discovers *after* building the wrong thing. V9.1 adds the third and
usually correct one — **ask CC, once, before emitting the blueprint.** Every question that
passes the leverage test, capped at four, each with the default already attached, folded back
in as verified ground truth. Cost: one message. Alternative cost: a rebuild.

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

**V9.1 corollary:** a fact you cannot read from the source and cannot infer safely is not a
default — it is a **question**. Ask it (Phase 1.5) or state it as an unconfirmed assumption
(headless path). Never let it enter the blueprint disguised as a decision.

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

### 1e. Open questions — the collection point

Every gap 1a–1d could not close lands here, in one list, before anything else happens. A gap
is anything you would otherwise have to invent: an unstated business rule, a missing credential
only CC can create, an ambiguous tenant/user boundary, an undefined edge case, a literal from a
voice transcript you cannot confirm.

Write each one as: **the gap · the default you would take · what a wrong default costs.**
That third field is what Phase 1.5 sorts on — it is the difference between a question worth
CC's attention and a decision you should just make.

**This list is never empty by wishful thinking.** If 1a–1d produced no gaps, say so explicitly
and move on; a suspiciously clean list usually means a guess already slipped in as a fact.

---

## Phase 1.5 — The Interactive Clarification Loop (V9.1)

**The rule.** Before writing a single line of the blueprint, read 1e end to end and decide, per
item: *ask CC now*, or *decide it yourself and say so*. If any item is high-leverage, **stop and
ask — every qualifying gap, up to 4, in one message.** Then fold the answers in and continue. You do not ask
permission to build; you ask for the facts that decide *what* to build.

### 1.5a. The leverage test — which gaps earn a question

Ask only when a wrong default **cannot be undone with one edit**. Four classes qualify:

| Class | Ask when | Example |
|---|---|---|
| **Missing external context/credential** | Only CC can create the account, key, domain, or approval — and the design branches on which one exists | "Is there a Postmark account, or does this route through the existing Gmail SMTP?" |
| **Unstated business logic** | A number, threshold, or rule that is a *choice*, not a fact — pricing, cadence, who gets notified, what counts as done | "Does a lead go cold at 14 days or 30?" |
| **Ambiguous user/tenant boundary** | Whose data this touches, which tenant owns the row, what an anon or wrong-tenant visitor sees | "Is this per-tenant, or does CC see every tenant's rows in one view?" |
| **Undefined edge case** | The failure/duplicate/empty path changes the schema or the contract, not just a message string | "A second submission from the same email — update the existing row, or a new one?" |

Everything else you decide yourself and record in the blueprint. Deciding is the default; asking
is the exception you earn.

### 1.5b. The ban list — never spend a question on these

- **Anything a `grep`, `Read`, or `mcp__supabase__list_tables` answers.** Asking CC for a column
  name is Anti-Slop #7 with a politeness wrapper. Read the source.
- **Anything `CONTEXT.md` defines.** The glossary is the answer; re-deriving a canonical term is
  a documented failure mode.
- **Anything `capability_probe.py check <service>` answers.** "Do we have Stripe access?" is a
  command, not a question (Anti-Slop #1).
- **Permission to proceed.** "Shall I start?", "does this plan look good?", "should I use
  TypeScript?" — Fix-First mode killed those. Routine technical judgment is yours (Phase 0b).
- **Cosmetic preference you should own.** Helper naming, file layout, which existing util to
  reuse. If CC would answer "you pick", you should have picked.

### 1.5c. Question form — each one answerable in a word

Numbered, ≤2 lines each, **with the default already attached** so a one-word reply unblocks the
whole build. CC should be able to answer `1b, 2 default, 3 yes` and be done.

```
Two things I can't read from the repo, then I build:

1. Cold-lead cutoff — 14 days or 30?  [default: 14, matches the existing drip gap]
2. This dashboard view — CC-only across all tenants, or scoped per tenant like /leads?
   [default: per-tenant, consistent with every other view]
```

**Budget — deterministic, not a range.** Ask **every** gap that passes 1.5a, capped at 4, in one
round. Zero qualifying gaps → ask nothing and emit. One → ask one; never pad to a minimum with
a question the ban list forbids. More than four → ask the four highest-cost and carry the rest
as stated defaults in § 4. **One round is the rule.** A second round is allowed only when an
answer opens a genuinely new fork (a "no, use Postmark" that introduces a credential you must
now probe). After the second round you stop asking: everything still open becomes a stated
assumption or a named blocker, and the blueprint ships.

**Harness form.** Ask in chat by default — the numbered block above, inline in the translation
output. When the runtime provides a native question control (Claude Code's `AskUserQuestion`)
**and** CC is at the keyboard, use it instead: same budget, recommended option first,
labelled `(Recommended)`. Never open a modal in a headless run.

### 1.5d. Headless and non-interactive runs — never wait, never half-mutate

**How you know which mode you are in.** Interactive is the default — if an operator turn is in
this conversation, CC can answer. Treat the run as unattended only on positive evidence: a cron
or scheduler invoked you, you were dispatched as a subagent, or the harness passed a headless
flag. When genuinely unsure, ask; a needless question costs one message, a wrong assumption
costs a rebuild.

When no operator can answer, **the loop does not wait — and it does not start what it cannot
finish.** It:

1. Takes the stated default for every item;
2. Marks each one in the blueprint as `[ASSUMED: <default> — unconfirmed]`, never as a decision;
3. Copies all of them into § 4 OPEN QUESTIONS verbatim;
4. **Orders the work so every step that depends on an assumption sits behind the reversible
   ones.** Do all the reversible work; then, at the first **irreversible** step resting on an
   `[ASSUMED]` value — money, a send, a migration, a production push — **stop and exit,
   reporting it as a named blocker with the assumption that needs confirming.** You do not sit
   waiting on an answer that cannot arrive, and you do not mutate halfway and then hang.

"Never block" means never *wait*; it does not mean proceed regardless. The failure this rule
prevents is a cron that half-migrated on a guess. A deadlocked cron is a worse failure than a
labelled assumption; an *unlabelled* assumption is worse than both; and a cron that spent real
money on a default nobody confirmed is worse than all three.

### 1.5e. Folding the answer back in — and the one thing CC's answer is not

CC's reply is ground truth for **decisions**. Tag it `[VERIFIED: CC Clarification]` and give it
the same standing as a command's output: it goes into CONTRACTS and into the BUILD phases
directly, and it is restated in the emitted blueprint so the executor never re-asks a question
CC already answered.

**But CC's reply is not evidence about repo state.** "The status column is already there" is a
belief, not a `grep`. Verify system facts against the source and tag those
`[VERIFIED: <the command you ran>]`, exactly as before — Rule 10 and Anti-Slop #7 do not get an
exemption because the claim came from CC. When the live check contradicts CC's recollection,
say so in one sentence and use the live result.

Then **re-run only the parts of Phase 1 the answer changed** — a new tenant boundary may add a
table to 1b; a new vendor may add a probe to 1d — and proceed to Phase 2.

### 1.5f. Durable answers get written down

If CC's answer establishes a rule that will outlive this task — a pricing rule, a naming
convention, a cadence, a "we always do X" — write one dated line to `memory/PATTERNS.md`
(or `memory/DECISIONS.md` when it reads as a decision rather than a pattern), per Rule 9. A
one-off answer stays in the blueprint only. **The iron law applies: CC never answers the same
question twice.**

---

## Phase 2 — The 7 mandatory production defenses

These are the defects that reach production from vibe-coded work. **Every** system message this
skill emits carries this block verbatim, scoped to the task at hand — a defense that does not
apply is marked `N/A — <reason>`, never deleted. Silence reads as "handled".

| # | Defense | The enforcement, in this repo |
|---|---|---|
| 1 | **Probe credentials first** | `python scripts/capability_probe.py check <service>` (or `list`) before claiming any gap. AVAILABLE = authorized, run the tool. Never attempt to read `.env*` — `secret_guard` blocks it and logs the attempt to `state/secret_guard.log`. "I don't have access" is true only after the probe exits non-zero and you quote that output. |
| 2 | **No UI-only security** | Authorization is re-checked server-side on **every** endpoint — session/JWT verified in the route handler. On paths that query as the **user** (anon/authed key), RLS must be enabled *and* forced on the table. On paths that query as the **service role**, RLS is bypassed by design and is *not* your gate — see Defense 3, which is the boundary there. A hidden button is not a blocked route; a client-side redirect is not a gate. See EXECUTION_RULES § 13 (public routes need two layers) and § 14 (boundaries are server-side). |
| 3 | **Tenant data isolation** | Every multi-tenant query carries an explicit `tenant_id` / `user_id` filter, and every insert stamps the same value (§ 17 — write what you filter). **On a service-role path this filter IS the entire isolation boundary** — RLS will not save you, so the tenant must be resolved server-side from the session or bridge token and never read from the request body. A `.from(...)` with no adjacent `.eq('tenant_id', …)` on such a path is a cross-tenant leak, not a style issue. Prove it by querying as anon **and** as an authed user of the wrong tenant. `apply_migration.py --allow-rls` is required when a migration touches RLS and it means "I ran both queries". |
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

**Every answer from Phase 1.5 is already in here.** The executor is a fresh context; it never
saw the conversation where CC answered. So each clarified fact appears *inside the phase that
depends on it*, tagged `[VERIFIED: CC Clarification]` — in § 1 when it changes the objective or
the vocabulary, in § 2's CONTRACT line when it fixes a value, a threshold, or a boundary. A
clarification that lives only in § 4 has been thrown away. Conversely, § 4 carries what CC did
*not* resolve: unasked low-leverage items with the default you took, and — on a headless run —
every `[ASSUMED: … — unconfirmed]` item verbatim.

````markdown
# SYSTEM PROMPT: [DESCRIPTIVE TASK TITLE]

**MODE: FIX-FIRST EXECUTION MODE (NO PLANNING, NO PROPOSALS, EXECUTE IMMEDIATELY)**

---

## 1. OBJECTIVE & EXECUTIVE SUMMARY
[2–3 sentences. The outcome, not the activity. Name the repo and branch, and the
canonical vocabulary this task uses (from CONTEXT.md). Any Phase 1.5 answer that
changed the objective itself belongs here, tagged [VERIFIED: CC Clarification].]

---

## 2. DETAILED EXECUTION PHASES
[Numbered, ordered, actionable. Every phase names the exact file it touches. Each
phase carries, inline:
  - CONTRACT   — the table/column, API signature, env key, or CC-clarified business
                 rule it depends on, plus its provenance: the command that VERIFIED
                 it, or [VERIFIED: CC Clarification]. Never an assumption.
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
[Anything a default would have silently decided and Phase 1.5 did not put to CC —
each with the default taken. On a headless run, every [ASSUMED: … — unconfirmed]
item appears here verbatim. Items CC already answered do NOT belong here; they are
resolved facts in §§ 1–2. Empty is a valid answer; omitting the section is not.]
````

**Quality bar:** if a step says "update the schema", it is not finished — name the table and
the column. If a step says "verify it works", it is not finished — name the command and the
string its output must contain. If § 4 repeats something CC answered in Phase 1.5, the loop
leaked — move it into the phase that consumes it.

**Alternate rendering (7 headings).** The operator-facing copy of this protocol ships in the
Command Center — `~/APPS/oasis-command-center/content/playbooks/11-vibe-translator.md`, live at
`/playbook/11-vibe-translator` — and renders the same contract as seven flat headings:
OBJECTIVE · CONTEXT · CONTRACTS · BUILD · GUARDRAILS · VERIFICATION · OPEN QUESTIONS. That is
the shape the **Prompt translator** entry in the Prompts Library
(`~/APPS/oasis-command-center/lib/prompts-library.ts`, id `vibe-to-execution-translator`) emits,
because its output gets pasted straight into a fresh chat. Identical content, identical 7
defenses; the lossless mapping table lives in that playbook.

**Keep all three in lockstep** — this skill, the Command Center playbook, and the Prompts Library
entry. The 4-section skeleton above stays canonical *in this repo*, matching
[[prompts/_TEMPLATE_SYSTEM_PROMPT]]; the 7-heading form is canonical on the dashboard. A version
bump here that stops at this file leaves the prompt CC actually copies two versions behind —
which is exactly what happened between V8.0 and V9.1.

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

Phase 1.5 scales with the protocol, not independently of it: a task too small for this skill is
too small for a clarifying question. Asking is a tool for load-bearing forks, and it stops
being cheap the moment it becomes a habit — an agent that asks about everything has just moved
its own work onto CC's desk, which is the exact inversion of the North Star.

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

**Phase 1.5 on the same dump.** 1e produced six gaps. Four were decided in place — cron cadence
(`*/15`, matches the existing sweep), branch naming, log location, the dry-run default. Two
passed the leverage test, because both change the *contract* and neither is recoverable in one
edit:

```
Two things before I build this:

1. Autonomy ceiling — should the loop push fixes to the PR branch on its own, or open
   them as suggestions for you to accept?  [default: push to the PR branch, never main]
2. When a fix touches a migration or a credential, escalate to you — Telegram, or just
   leave it in the queue for the morning?  [default: Telegram, matches the outage path]
```

CC answered `1 default, 2 telegram`. Both went straight into the blueprint —
`review_fix` pushes to the PR branch `[VERIFIED: CC Clarification]`, and `DANGER_PATHS` hits
notify via the operator channel `[VERIFIED: CC Clarification]` — so § 4 OPEN QUESTIONS came out
empty rather than handing the executor a fork it had no authority to resolve. The alternative
was a closed loop that either did nothing without approval or force-pushed to `main`.

## Related

[[brain/EXECUTION_RULES]] (§ 18 the loop, § 19 the Anti-Slop Matrix, § 20 the Opus 5 contract) ·
[[CONTEXT]] · [[brain/AGENT_ROUTER]] · [[skills/writing-plans/SKILL]] ·
[[skills/sop-breakdown/SKILL]] · [[skills/self-evolution/SKILL]] ·
[[skills/codex-delegation/SKILL]]
