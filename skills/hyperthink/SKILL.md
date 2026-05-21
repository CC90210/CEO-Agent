---
name: hyperthink
description: Maximum-depth reasoning protocol. Wraps Claude Code's native ultrathink (31,999 thinking tokens) with a structured multi-hypothesis framework. Fires on architectural decisions, multi-root-cause debugging, or expensive-to-reverse choices.
triggers: [hyperthink, ultrathink, think harder, think super hard, think intensely, think really hard, architectural decision, irreversible choice]
tier: strategic
dependencies: [sequential-reasoning, systematic-debugging, codex-delegation]
canonical_source: ~/.claude/AGENT_COORDINATION.md
tags: [reasoning, protocol, top-tier]
disable_model_invocation: true
---

# HYPERTHINK — Maximum-Depth Reasoning Protocol

> When the problem is ambiguous, the stakes are high, or the decision is architectural — slow down, think harder, verify twice.

> **Canonical cross-project definition lives at** `~/.claude/AGENT_COORDINATION.md`. Do not diverge without a Proposed Change entry there.

## What Hyperthink Actually Is

Hyperthink is **not a new Anthropic feature**. It is CC's preferred name for Claude Code's highest-depth reasoning mode, combined with a structured multi-hypothesis protocol.

**Under the hood — native Claude Code trigger-word budget ladder:**

| User's phrase | Thinking tokens | Use for |
|---|---|---|
| `think` | ~4,000 | Routine debugging, simple refactors |
| `think hard` / `megathink` / `think deeply` / `think more` | ~10,000 | Architecture decisions, moderate problem-solving |
| `think harder` / `ultrathink` / `hyperthink` / `think intensely` / `think super hard` / `think really hard` / `think very hard` / `think longer` | **~31,999** | Hardest tasks: irreversible calls, 3+ plausible root causes, system invariants |

Claude Code only activates extended thinking when the magic word appears in the **user's** message. When CC says "hyperthink" explicitly, Claude Code may or may not route through ultrathink depending on token matching — so agents must **also** run this structured protocol regardless, to guarantee the depth CC expects.

## When to Hyperthink

**USE for:**
- Architectural decisions (database schema changes, framework migrations, API redesigns)
- Security audits (auth flows, input validation, RBAC, cross-tenant isolation)
- Adversarial code reviews (finding hidden bugs, race conditions, edge cases)
- Multi-agent coordination (avoiding redundant work across parallel Claude instances)
- Cross-cutting refactors (changes that touch many files)
- Debugging production incidents (where surface symptoms mislead)
- Pricing/business model decisions (where emotion clouds logic)
- Trade-off analysis (A vs B vs C with different completeness scores)

**SKIP for:**
- Simple file edits
- Well-defined CRUD operations
- Already-solved patterns from memory
- One-line fixes

## The Hyperthink Loop

### 1. REFRAME — Strip the emotion, name the real problem
What is the user actually asking? What's the unstated goal? What's the risk of getting this wrong?

### 2. MAP — Identify every moving piece
- What files are involved?
- What agents/services are affected?
- What's upstream (triggers) and downstream (consequences)?
- What's the blast radius if this goes wrong?

### 3. GENERATE — Multi-hypothesis thinking
Produce 2-3 candidate approaches. For each:
- **Completeness score** (0-10)
- **Human team estimate** (days/weeks)
- **CC+Bravo estimate** (minutes/hours)
- **Risk profile** (what breaks if this fails?)
- **Reversibility** (can we undo this?)

### 4. STRESS TEST — Find the ways this breaks
For the top candidate, ask:
- What happens if the user double-clicks?
- What happens if the network drops mid-request?
- What happens if the DB is at capacity?
- What happens with 10,000 rows? 10 million?
- What happens with malicious input?
- What happens if two agents modify the same resource simultaneously?
- What happens if a dependency is misconfigured?

### 5. COORDINATE — Check for redundancy
Before writing code:
- Is another agent already working on this?
- Is there an existing skill, pattern, or utility that covers this?
- Will my changes conflict with work in progress?
- Whose territory does this touch?

### 6. DECIDE — Pick one, commit, document why
- State the recommendation in one sentence
- Note what was rejected and why
- Flag any assumptions that could invalidate the choice
- Identify the rollback path if it fails

### 7. EXECUTE — With guard rails
- Run the build/tests after every significant change
- Commit incrementally, not in monster PRs
- Update memory if the pattern is novel or validated
- Report back with what was done, what was skipped, and what's left

## Multi-Agent Coordination Protocol

When multiple Claude agents run in parallel on the same user's projects:

### Territory Rules
1. **Each agent owns specific apps.** Before touching any app, verify it's in your scope.
2. **Shared infrastructure is off-limits.** Business-Empire-Agent root files (CLAUDE.md, brain/, memory/) are read-only across agents unless you own that session's scope.
3. **When in doubt, ask first.** A 30-second clarification beats a 30-minute revert.

### Redundancy Prevention
Before starting a multi-step task:
- Ask the user: "What are the other agents working on?"
- Grep for recent commits in shared directories to detect active work
- If two agents build the same feature in different apps, that's fine
- If two agents modify the same file, that's a conflict — stop and coordinate

### Handoff Discipline
If work needs to cross agent boundaries:
- Document the handoff point clearly
- Leave a breadcrumb in memory/SESSION_LOG.md
- Tag the target agent/session in the note

## Output Format (required when hyperthink fires)

Start the response with `HYPERTHINK ENGAGED` and include the phases inline:

```
HYPERTHINK ENGAGED
════════════════════
PHASE 1 — REFRAME
Goal: [one sentence]
Constraints: [bullets]
Assumptions (challenge-worthy): [bullets]
Reversibility: [HIGH / MEDIUM / LOW]

PHASE 2 — MAP
Files: [...]   Agents: [...]   Blast radius: [...]

PHASE 3 — GENERATE (force 3 distinct approaches — not variations)
A) [name]: [2 sentences]  Risk: [biggest]  Completeness: [x/10]
B) [name]: [2 sentences]  Risk: [biggest]  Completeness: [x/10]
C) [name]: [2 sentences]  Risk: [biggest]  Completeness: [x/10]

PHASE 4 — STRESS TEST (top candidate only)
- Double-click / retry:
- Network failure mid-op:
- Scale (10k, 10M rows):
- Malicious input:
- Concurrent modification:

PHASE 5 — COORDINATE
Another agent working this? [check ~/.claude/AGENT_COORDINATION.md]
Existing skill / util covers it? [link or "no"]

PHASE 6 — DECIDE
Winner: [A/B/C]    Reasoning: [one sentence]
Killers (abort conditions): [list]
Rollback path: [one sentence]

PHASE 7 — EXECUTE
[do the work; on failure, append a Reflexion line and either adjust or fall back to Plan B]
════════════════════
```

## Anti-Patterns (What NOT to Do)

- **Firing hyperthink on trivial tasks** — it's expensive and dilutes signal. Match depth to task.
- **Speed over correctness** — if the user says "hyperthink", slow down, don't rush
- **Assuming without verifying** — run the build, check the file, query the DB
- **Generating 3 variations of the same idea in Phase 3** — that's anchored, not diverged. Force real alternatives.
- **Picking the winner before Phase 4** — self-justification scoring is worthless
- **Preaching** — if the user already knows a fact, don't repeat it back
- **Silent failures** — if something didn't work, say so explicitly
- **Scope creep** — fix what was asked, note what's related, don't drive-by refactor
- **Building before asking** — for ambiguous requests, ask 1-3 tight questions first
- **Forgetting Reflexion on failure** — the lesson is lost if not logged to `memory/SELF_REFLECTIONS.md`

## Integration with Other Skills

- **Pairs with** `systematic-debugging` for root-cause analysis
- **Pairs with** `codex-delegation` for backend-heavy tasks
- **Pairs with** `agent-teams` for parallel execution
- **Triggers** `sparc-methodology` for architectural builds
- **Triggers** `anti-drift` check before executing multi-step plans

## Obsidian Links
- [[skills/systematic-debugging/SKILL.md]]
- [[skills/codex-delegation/SKILL.md]]
- [[skills/agent-teams/SKILL.md]]
- [[brain/BRAIN_LOOP]]
