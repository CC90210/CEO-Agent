---
name: task-routing
description: >
  Complexity-based intelligent task routing to specialized agents. Analyzes incoming tasks
  for file count, domain signals, estimated steps, and risk level, then auto-assigns to
  the optimal agent or agent team. Use when: any non-trivial task arrives, multi-file changes,
  unclear which agent should handle work. Skip when: trivial single-file edits, CC explicitly
  names the agent to use.
tags: [orchestration, routing, agents]
triggers: ["task routing", "use task routing", "run task routing"]
---

# Task Routing — Complexity-Based Agent Assignment

> **Purpose:** Automatically route tasks to the right agent(s) based on complexity analysis.
> No more manual "which agent handles this?" decisions — the router decides.

## When to Trigger

- Any task touching 3+ files
- Tasks with unclear ownership (could be coder OR architect OR debugger)
- Multi-step features requiring coordination
- CC says "do X" without specifying an agent
- Cross-module refactoring
- Any COMPLEX or ARCHITECTURAL task

## When to Skip

- CC explicitly says "use the debugger" or names an agent
- Trivial tasks (typo fix, single-line change)
- Pure research/lookup queries
- Simple status checks

## The Routing Algorithm

### Step 1: Complexity Classification

Analyze the task and classify it:

| Complexity | File Count | Steps | Example |
|-----------|-----------|-------|---------|
| **TRIVIAL** | 1 file | 1-2 | Fix a typo, update a constant |
| **SIMPLE** | 1-2 files | 3-5 | Add a function, fix a bug |
| **MODERATE** | 3-5 files | 5-15 | New feature, refactor a module |
| **COMPLEX** | 6-15 files | 15-30 | Multi-module feature, new integration |
| **ARCHITECTURAL** | 15+ files | 30+ | System redesign, new service, schema migration |

**Classification signals:**
- Count files mentioned or implied in the request
- Count distinct modules/directories affected
- Identify cross-cutting concerns (auth, DB, API, UI)
- Check if tests need to be written or updated
- Check if documentation changes are needed

### Step 2: Domain Detection

Scan the task for domain keywords to identify the primary domain:

| Domain Signal | Keywords | Primary Agent |
|--------------|----------|---------------|
| **Security** | auth, RLS, encryption, XSS, injection, credentials | reviewer |
| **Database** | schema, migration, table, query, Supabase, RPC | architect |
| **Content** | post, copy, caption, pillar, brand voice | content-creator |
| **Outreach** | email, lead, follow-up, client, proposal | chief-of-staff |
| **Revenue** | pricing, Stripe, invoice, subscription, MRR | revenue-hunter |
| **Workflow** | n8n, automation, trigger, webhook | workflow-builder |
| **Video** | FFmpeg, Remotion, caption, render, audio | video-editor |
| **Research** | investigate, compare, analyze market, documentation | researcher |
| **Debugging** | bug, error, broken, fix, crash, stack trace | debugger |
| **Documentation** | docs, README, update memory, changelog | documenter |
| **Git** | commit, branch, PR, merge, rebase | git-ops |
| **Social** | post, schedule, Zernio, Late, cross-post, publish | social-publisher |
| **Skool** | lesson, course, classroom, community | writer (+ skool-automation skill) |
| **Exploration** | find, where is, search, locate, navigate | explorer |

### Step 3: Agent Assignment

Based on complexity + domain, assign agents:

**TRIVIAL → Inline (no delegation)**
Handle directly. No agent spawn needed.

**SIMPLE → Single Agent**
Assign the domain-matched agent. Default: `writer`.

**MODERATE → Agent + Review Gate**
1. Assign primary agent (domain-matched)
2. After completion, route through `reviewer` for quality gate
3. Config reference: `.agents/config.toml` [routing.agents] moderate

**COMPLEX → Full Team**
1. `architect` designs the approach (Step 4 of BRAIN_LOOP)
2. `writer` implements (may be multiple writers for parallel work)
3. `reviewer` validates
4. `debugger` on standby for failures
5. Requires plan approval from CC before execution
6. Config reference: `.agents/config.toml` [routing.agents] complex

**ARCHITECTURAL → Full Team + CC Approval**
1. `architect` produces full design document
2. CC approves design before any code is written
3. `writer` implements in phases with checkpoint gates
4. `reviewer` reviews each phase
5. `debugger` + `documenter` for cleanup
6. Config reference: `.agents/config.toml` [routing.agents] architectural

### Step 4: Output the Routing Decision

After classification, output this to the session:

```
ROUTING DECISION:
  Task: [1-sentence summary]
  Complexity: [TRIVIAL | SIMPLE | MODERATE | COMPLEX | ARCHITECTURAL]
  Domain: [primary domain]
  Agent(s): [assigned agent list]
  Files (est): [N files across M directories]
  Plan required: [yes/no]
  CC approval needed: [yes/no]
```

Then proceed with execution via the assigned agent(s).

## Domain Override Rules

These override the standard complexity routing:

1. **Any task touching `.env.agents`** → STOP. Credentials are manual-only.
2. **Any task touching Stripe webhook handlers** → Always include `reviewer`
3. **Any task touching Supabase RLS policies** → Always include `architect` + `reviewer`
4. **Any task creating new API routes** → Always include `reviewer` for auth checks
5. **Any task touching brain/ files** → Check mutability level (SOUL.md is IMMUTABLE)

## Integration with BRAIN_LOOP

This skill plugs into **Step 3: ASSESS** and **Step 4: PLAN** of the Brain Loop:

- Step 3 (ASSESS): Run complexity classification + domain detection
- Step 4 (PLAN): Use routing decision to determine which agents to spawn
- The routing config in `.agents/config.toml` is the single source of truth for thresholds and agent assignments

## Anti-Drift Integration

When routing to multiple agents (COMPLEX+):
- Each agent checks in at the checkpoint interval defined in `.agents/config.toml` [anti_drift]
- If an agent touches files outside its assigned scope, the drift detector flags it
- See `skills/anti-drift/SKILL.md` for the full protocol

## Obsidian Links
- [[brain/AGENTS]] | [[brain/BRAIN_LOOP]] | [[brain/CAPABILITIES]]
- [[skills/anti-drift/SKILL.md]] | [[skills/agent-permissions/SKILL.md]]
