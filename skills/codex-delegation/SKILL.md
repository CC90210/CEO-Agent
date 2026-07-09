---
name: codex-delegation
description: Intelligent routing between Bravo and Codex — decides when to delegate tasks to Codex vs handle internally
tags: [skill]
triggers: ["codex delegation", "use codex delegation", "run codex delegation"]
tier: core
---

# Codex Delegation — Intelligent Dual-AI Routing

> **Purpose:** Bravo and Codex are complementary AI engines. This skill determines WHEN and HOW
> to delegate work to Codex for maximum leverage — two AIs working in parallel, each on their strengths.

## The Dual-AI Architecture

```
CC → Bravo (Claude Opus 4.6)           CC → Codex (GPT-5.4)
├── Architecture & planning             ├── Backend implementation
├── Frontend & UI                       ├── Deep debugging
├── Creative & brand voice              ├── Adversarial code review
├── Business ops & strategy             ├── Parallel task execution
├── Orchestration & memory              ├── Root-cause analysis
└── Client communications               └── Write-capable rescue tasks
```

## Delegation Decision Matrix

### Auto-Delegate to Codex (No CC approval needed)

| Task Type | Codex Command | Why Codex |
|-----------|---------------|-----------|
| Pre-ship code review | `/codex:review --background` | Second pair of AI eyes catches Bravo's blind spots |
| Architecture challenge | `/codex:adversarial-review` | Questions assumptions Bravo might accept |
| Backend bug with stack trace | `/codex:rescue investigate [bug]` | Codex excels at systematic root-cause |
| Heavy backend implementation | `/codex:rescue --background [task]` | Runs parallel while Bravo does other work |
| Test suite debugging | `/codex:rescue fix the failing tests` | Codex is strong at test diagnosis |

### Keep in Bravo (Never delegate)

| Task Type | Why Bravo |
|-----------|-----------|
| Frontend/UI components | Bravo has better design sense and CC's brand voice |
| Content creation (posts, copy) | Bravo owns CC's authentic voice |
| Business strategy & client comms | Bravo has full business context |
| Memory/state/orchestration | Bravo's infrastructure — Codex has no access |
| Social media automation | Bravo has the MCP and CLI integrations |
| Cross-file sync (brain/, memory/) | Bravo's domain knowledge required |
| Simple fixes (< 3 files) | Delegation overhead > task effort |

### Ask CC (Judgment call)

| Task Type | Why Ask |
|-----------|---------|
| Full feature implementation | Split work or assign to one AI? |
| Refactoring > 10 files | Coordination risk between two AIs |
| Security-sensitive changes | Need explicit human review |

## Parallel Execution Patterns

### Pattern 1: Review While Building
```
Bravo: Implements feature in frontend
Codex: /codex:review --background (reviews existing changes)
Result: By the time Bravo ships, Codex review is ready
```

### Pattern 2: Dual Investigation
```
Bravo: Debugs frontend rendering issue
Codex: /codex:rescue --background investigate the API timeout
Result: Two bugs investigated simultaneously
```

### Pattern 3: Implement + Adversarial Check
```
Bravo: Writes the implementation
Codex: /codex:adversarial-review --background challenge the caching design
Result: Design validated before ship
```

### Pattern 4: Bravo Orchestrates, Codex Implements
```
Bravo: Creates SPARC spec + architecture (Phases 1-3)
Codex: /codex:rescue implement the backend per the spec in .agents/plans/
Bravo: Reviews Codex output, handles frontend + docs
Result: Full-stack feature with parallel execution
```

### Pattern 5: End-of-Task Self-Review (MANDATORY for big tasks — added 2026-05-23)
```
Bravo: Finishes the work, runs final smoke checks
Bravo: Writes its own honest self-review (against Stop-hook prompts)
Bravo: node ~/.claude/codex-plugin/scripts/codex-companion.mjs review --wait
Bravo: Presents BOTH reviews verbatim — Bravo's first, then a
       "### Codex independent audit" section with Codex's report
Result: CC sees the work AND a second-opinion audit before declaring done
```

**Why MANDATORY:** Self-reviews by the agent that did the work are biased. Bravo will undersell mistakes and oversell completeness without realising it. Codex has no stake in Bravo's work and reads the diff cold — that independence is exactly what catches the gaps Bravo glossed over.

**When this fires:**
- ≥3 commits in the session
- ≥5 files touched
- Any user-facing change (frontend, prompts, dashboard UI, applied migration, production push, deployed to Vercel)
- Any time the Stop hook surfaces a self-review prompt and the task feels substantial

**Use `adversarial-review` instead of `review`** when the work involves architectural decisions, security-sensitive changes, or a design pattern Bravo hasn't seen before. Sober walkthrough vs. challenge-the-assumptions are different deliverables.

**Don't paraphrase.** Present Codex output verbatim under its own header. If Codex disagrees with something Bravo dismissed in its own review, surface the disagreement explicitly so CC can adjudicate.

**Optional enforcement:** `node ~/.claude/codex-plugin/scripts/codex-companion.mjs setup --enable-review-gate` makes the Stop hook block until Codex has reviewed. Per-workspace config — each rig enables it locally; the doc pattern (this section) is what survives `git pull`.

## Integration with Task Routing

When the task routing skill (`skills/task-routing/SKILL.md`) classifies a task:

| Complexity | Codex Role |
|-----------|------------|
| TRIVIAL | None — Bravo handles inline |
| SIMPLE | None — single agent sufficient |
| MODERATE | Optional: `/codex:review` after Bravo implements |
| COMPLEX | Recommended: Codex handles backend, Bravo handles frontend/orchestration |
| ARCHITECTURAL | Required: `/codex:adversarial-review` on the architecture before implementation |

## Integration with Ship Pipeline

Add to `skills/ship/SKILL.md` Phase 4 (Code Review):

After Bravo's code review, optionally run:
```
/codex:adversarial-review --background --base main
```

This gives a dual-AI review before shipping — Bravo catches implementation issues, Codex challenges design decisions.

## Pre-Flight Check (MANDATORY before any delegation — added 2026-04-25)

Run this in <2s before spawning a codex-agent. If it fails, STOP — upgrade the CLI first or execute inline. Do NOT burn 5 minutes per agent in a retry loop the way the 2026-04-25 Atlas + Maven session did.

```bash
codex --version 2>&1 | head -1
# Expected: a version string. If "command not found" → install: npm i -g @openai/codex@latest
# If version reported < the one on https://www.npmjs.com/package/@openai/codex → upgrade.
```

Symptoms of a stale CLI (all observed 2026-04-25 with @openai/codex@0.118.0):
- Every model alias (gpt-5.5, gpt-5.4-codex, gpt-5.4-codex-mini, gpt-5-codex, gpt-5, spark, gpt-5.3-codex-spark) rejected by the gateway.
- Codex companion drops into "rescue phase" repeatedly with no progress.
- Total runtime climbs past 3 minutes with no file writes — that's the canary.

Recovery: `npm i -g @openai/codex@latest && node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" status`. If still failing after upgrade, Bravo handles the task inline. Never retry the same prompt 3 times against the same broken CLI — see MISTAKES.md "Codex CLI Stale".

## Commands Quick Reference

```bash
# Standard review (second opinion)
/codex:review --background

# Challenge the design
/codex:adversarial-review --background challenge the auth design

# Delegate a task
/codex:rescue --background investigate why the API returns 500

# Quick fix with a specific model (override the gpt-5.5 default)
/codex:rescue --model gpt-5.4-mini fix the TypeScript error in api/route.ts

# Check progress
/codex:status

# Get results
/codex:result

# Cancel
/codex:cancel
```

## Context Injection — Giving Codex Codebase Intelligence

Codex runs in the same repo directory but doesn't have Bravo's brain files. When delegating tasks,
**inject relevant context into the task prompt** so Codex makes informed decisions.

### Context Injection Protocol

When building a Codex task prompt, prepend relevant context:

```
<context>
Project: [app name from APP_REGISTRY.md]
Stack: [from APP_REGISTRY.md — e.g., "Next.js 14, TypeScript, Supabase, Stripe"]
Key files: [list the 3-5 most relevant files for this task]
Constraints: [any architectural rules — e.g., "uses App Router, RLS enabled, Stripe webhooks verified"]
Related work: [if Bravo already started something, describe what's done]
</context>

<task>
[The actual task description]
</task>
```

### What to Inject by Task Type

| Task Type | Context to Include |
|-----------|-------------------|
| Backend bug fix | Error message, stack trace, relevant file paths, DB schema if applicable |
| API implementation | Existing route patterns, auth middleware, Supabase table schema |
| Code review | Branch diff summary, what the feature does, any known risks |
| Test debugging | Test framework (vitest/jest), failing test output, related source files |
| Refactoring | Current architecture, files involved, what "done" looks like |

### Example: Delegating a Backend Task

```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/.claude/codex-plugin"
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task --write \
  "Context: Next.js 14 App Router, Supabase with RLS, Stripe webhooks.
   The webhook handler at app/api/webhooks/stripe/route.ts is not idempotent —
   it processes the same event_id twice when Stripe retries.
   Fix: Add event_id deduplication using the payments table.
   The Supabase client is initialized in lib/supabase/server.ts.
   Constraint: Do not disable RLS. Use the service role key server-side only."
```

## Failure Recovery — When Codex Fails

Codex tasks can fail for several reasons. Bravo must handle each gracefully:

### Failure Types and Recovery

| Failure | Signal | Recovery |
|---------|--------|----------|
| **Codex CLI not found** | `setup --json` returns `codex.available: false` | Run `npm install -g @openai/codex` |
| **Auth expired** | `setup --json` returns `auth.loggedIn: false` | Tell CC to run `codex login` in terminal |
| **Task timeout** | No result after 15 minutes | Check `/codex:status`, cancel if stuck, retry with simpler scope |
| **Bad output** | Codex returns malformed or empty result | Don't retry blindly — Bravo takes over the task |
| **Codex made wrong changes** | Review shows incorrect implementation | Bravo reverts and handles the task directly |
| **Broker crash** | Session runtime errors | Restart session (SessionEnd + SessionStart hooks will clean up) |

### The 3-Strike Rule

1. **First failure:** Retry with more specific context (inject file contents, narrow scope)
2. **Second failure:** Switch to a different Codex model (`--model gpt-5.4` one tier down from the gpt-5.5 default, or `--model gpt-5.4-mini` for faster)
3. **Third failure:** Bravo takes over. Log to `memory/MISTAKES.md` with what Codex struggled with.

**Never retry the same prompt 3 times.** Each retry must change something: more context, narrower scope, different model, or Bravo takes over.

### Pre-Flight Check

Before any Codex delegation, verify readiness:
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/.claude/codex-plugin"
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" setup --json 2>/dev/null | head -1
```
If `ready: false` — don't delegate. Handle the task directly and note the issue.

## Anti-Patterns (Never Do These)

1. **Don't delegate AND do the same work.** If Codex is investigating a bug, Bravo works on something else.
2. **Don't delegate memory/state tasks.** Codex has no access to brain/, memory/, or Supabase.
3. **Don't delegate content creation.** Codex doesn't have CC's brand voice context.
4. **Don't run Codex on trivial tasks.** The startup overhead makes it slower than Bravo for small fixes.
5. **Don't ignore Codex results.** Always present Codex output verbatim to CC.
6. **Don't send vague prompts to Codex.** Always inject codebase context — file paths, stack, constraints.
7. **Don't retry the same failing prompt.** Change scope, model, or context on each retry.

## Obsidian Links
- [[agents/codex-agent]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]]
- [[skills/task-routing/SKILL.md]] | [[skills/ship/SKILL.md]] | [[skills/code-review/SKILL.md]]
