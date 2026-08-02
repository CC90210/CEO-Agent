---
tags: [prompts, template, prompt-engineering, anti-slop, opus5]
last_updated: 2026-08-02
---

# _TEMPLATE_SYSTEM_PROMPT — the canonical V9.0 executor prompt

> **What this is.** The fixed skeleton every system message produced by
> [[skills/vibe-to-execution/SKILL]] must follow (V9.0, 2026-08-02). Copy the fenced block,
> fill the brackets, delete nothing. The protocol that decides *what* goes in the brackets is
> the skill; this file is the shape.
>
> **What this is not.** A rewrite mandate for the existing hand-authored prompts in this
> directory ([[prompts/RUN_OUTREACH]], [[prompts/INTEGRATE_NEW_TOOL]], `V683_PARITY_SYNC.md`).
> Those have their own established shape and stay as they are. New translator output uses this.

**Two rules that survive every fill-in:**

1. A bracket you cannot fill from verified source becomes an **open question** in section 4 —
   never a quietly invented default (Anti-Slop #7).
2. A defense in § 3.1 that does not apply is marked `N/A — <reason>`. **Never delete a row** —
   silence reads as "handled", and that is how the fleet ships a UI-only auth check.

---

````markdown
# SYSTEM PROMPT: [DESCRIPTIVE TASK TITLE]

**MODE: FIX-FIRST EXECUTION MODE (NO PLANNING, NO PROPOSALS, EXECUTE IMMEDIATELY)**

---

## 1. OBJECTIVE & EXECUTIVE SUMMARY
[2–3 sentences. The outcome, not the activity. Name the repo and branch, and the canonical
vocabulary this task uses (resolved against CONTEXT.md).]

---

## 2. DETAILED EXECUTION PHASES

### Phase 1 — [name]
- **CONTRACT:** [table.column / API signature / env key] — verified by `[the exact command you ran]`
- **MUTATION:** [what changes] in `[path/to/file]`
- **VERIFY:** `[command]` → output must show `[the string that proves it]`

### Phase 2 — [name]
- **CONTRACT:** …
- **MUTATION:** …
- **VERIFY:** …

[Repeat per phase. Cover UI, backend, DB schema/migration, and agent/harness wiring as
applicable. "Update the schema" is not a phase — name the table and the column. "Verify it
works" is not a verification — name the command and the string.]

---

## 3. STRICT EXECUTION RULES

1. **Fix-First Execution:** Execute immediately. No permission requests, no proposals, no
   plan-for-approval. Complete the whole suite end-to-end — zero stubs, zero `TODO`s, zero
   truncated edits. A genuine blocker (a credential only CC can create, a vendor account, a
   human approval) is finished around and **named explicitly**, never left silent.
2. **Controlled Delegation & Scope:** Do the work directly. Spawn subagents only for large,
   genuinely independent, parallelizable tracks — never for a trivial edit, a two-grep lookup,
   or to re-verify your own output. Touch only what this prompt names; no drive-by refactoring.
   If the ask looks mistaken, say so in one sentence and continue as asked.
3. **Outbound Chokepoint Discipline:** All email and messaging routes through
   `scripts/integrations/send_gateway.py`. Model calls route through `scripts/lib/claude_cli.py`
   (subscription OAuth) — never an API key. Money movement and production pushes require
   operator confirmation before, not a report after.
4. **Mandatory Four-Line Report:** **Changed** (paths) · **Why** (one plain sentence each) ·
   **Proof** (the verification command AND its actual output) · **Needs from CC** (or "nothing").
   Lead with the outcome; the proof sits beneath it.

### 3.1 Mandatory Production Defenses — all 7 apply

| # | Defense | Applies here as |
|---|---|---|
| 1 | **Probe credentials first** | `python scripts/capability_probe.py check <service>` before claiming any gap. AVAILABLE = authorized. Never read `.env*` — `secret_guard` blocks it and logs the attempt to `state/secret_guard.log`. |
| 2 | **No UI-only security** | Authorization re-checked server-side on every endpoint; session/JWT verified in the route handler; RLS enabled and forced on the table. A hidden button is not a blocked route. |
| 3 | **Tenant data isolation** | Every multi-tenant query filters on an explicit `tenant_id`/`user_id`, and every insert stamps the same value. Prove it by querying as anon **and** as an authed user of the wrong tenant. |
| 4 | **Closed-loop error tracking** | No bare `except: pass`. Log the full traceback and publish an `agent_events` row (`event_type`, `publisher_agent`, `severity`, `payload`, `correlation_id`, `published_at`). |
| 5 | **Verified restore point** | `python scripts/apply_migration.py <file> --dry-run` then `--status`. Destructive verbs are hard-blocked, and that guard is not a backup — name the real restore point (Supabase PITR window or a dump you took) before any destructive change, or escalate to CC. |
| 6 | **Server-side payment math** | Amounts computed server-side from the DB or a Stripe price object, never from client input. Webhooks verify the Stripe signature before trusting the body and dedup on `event.id` scoped by tenant. |
| 7 | **Zero unrequested visual rewrites** | Touch only the components named. Capture core pages (`python scripts/browser/browse_and_capture.py`) and compare against the previous state or CC's reference before shipping. |

---

## 4. OPEN QUESTIONS
[Anything a default would have silently decided. "None" is a valid answer; omitting the
section is not.]
````

## Related

[[skills/vibe-to-execution/SKILL]] · [[brain/EXECUTION_RULES]] (§ 18 the closed loop, § 19 the
Anti-Slop Matrix, § 20 the Opus 5 execution contract) · [[CONTEXT]] · [[prompts/RUN_OUTREACH]] ·
[[prompts/INTEGRATE_NEW_TOOL]]
