---
name: retro
description: Weekly retrospective analysis. Use when CC says "/retro", "weekly retro", "how did we do this week", or "what shipped this week". Analyzes all agent activity, rates 4 operational dimensions, and generates specific improvement actions.
triggers: [retro, retrospective, weekly retro, what shipped, how did we do]
tier: specialized
dependencies: [memory-management]
disable_model_invocation: true
---

# Retro — Weekly Retrospective Engine

## Overview

Every week, look at what all three agents (Claude Code, Gemini CLI, Anti-Gravity) actually shipped, broke, learned, and repeated. Generate a structured report with honest scores and concrete actions — not feel-good summaries.

**Core principle:** Patterns that go unnoticed become permanent. A weekly retro is the minimum cadence to catch drift before it compounds.

**Announce at start:** "Running weekly retrospective. Analyzing the past 7 days across all agents."

---

## Phase 1: Data Collection

Run all collection steps before analyzing anything.

### 1a. Git Activity (All App Repos)

For each repo in @brain/APP_REGISTRY.md that exists locally:

```bash
# Business-Empire-Agent (agent intelligence)
cd /c/Users/User/Business-Empire-Agent
git log --oneline --since="7 days ago" --all

# TIKTIK
cd /c/Users/User/APPS/tiktik
git log --oneline --since="7 days ago" --all 2>/dev/null || echo "No commits"

# PropFlow
cd /c/Users/User/realestate-App
git log --oneline --since="7 days ago" --all 2>/dev/null || echo "No commits"

# OASIS AI Platform
cd /c/Users/User/APPS/oasis-ai-platform
git log --oneline --since="7 days ago" --all 2>/dev/null || echo "No commits"

# Grape Vine Cottage
cd /c/Users/User/APPS/Grape-Vine-Cottage
git log --oneline --since="7 days ago" --all 2>/dev/null || echo "No commits"

# Mindset Companion
cd "/c/Users/User/APPS/MINDSET COMPANION APP/cc-mindset"
git log --oneline --since="7 days ago" --all 2>/dev/null || echo "No commits"

# On The Hill
cd /c/Users/User/APPS/ON-THE-HILL-WEBSITE
git log --oneline --since="7 days ago" --all 2>/dev/null || echo "No commits"
```

Count: total commits, number of repos touched, number of distinct days with commits.

### 1b. Files Changed (Business-Empire-Agent)

```bash
cd /c/Users/User/Business-Empire-Agent
git log --oneline --since="7 days ago" --name-only | grep -v "^$" | grep -v "^[a-f0-9]" | sort -u
```

Categorize changed files:
- `brain/` → agent intelligence updates
- `memory/` → memory system activity
- `skills/` → new or updated skills
- `scripts/` → tooling changes
- Any app path → code shipped

### 1c. Memory Files

```bash
cd /c/Users/User/Business-Empire-Agent
```

Read all four:
- `memory/SESSION_LOG.md` — what all agents did this week
- `memory/MISTAKES.md` — errors logged this week (look for new entries by date)
- `memory/SELF_REFLECTIONS.md` — failures and lessons
- `memory/ACTIVE_TASKS.md` — task completion rate (how many were marked done vs. added)

---

## Phase 2: Metric Calculation

From the collected data, calculate these exact numbers:

| Metric | How to Calculate |
|--------|----------------|
| **Commits** | Total git commits across all repos in the 7-day window |
| **Files changed** | Unique files touched across all repos |
| **Features shipped** | Commits with `feat:` prefix OR session log entries tagged as new features |
| **Bugs fixed** | Commits with `fix:` prefix OR session log entries tagged as bug fixes |
| **Skills added/updated** | New or modified files in `skills/*/SKILL.md` |
| **Mistakes logged** | New entries in `memory/MISTAKES.md` with dates in the window |
| **Repeated mistakes** | Mistakes in MISTAKES.md that share a root cause with a prior entry |
| **Task completion rate** | Tasks marked `[DONE]` ÷ (tasks marked `[DONE]` + tasks still `[IN PROGRESS]` or `[BLOCKED]`) |

---

## Phase 3: Scoring (0-10 Scale)

Score each dimension honestly. 7 is the minimum acceptable. Below 7 triggers mandatory improvement actions.

### Dimension 1: Shipping Velocity (0-10)

Measures: Are we actually deploying working code, or spinning in planning/debugging loops?

| Score | What it Looks Like |
|-------|--------------------|
| 9-10 | 5+ commits to app repos, 2+ features shipped, no weeks without a deploy |
| 7-8 | 2-4 app commits, at least 1 shipped feature |
| 5-6 | Commits only to agent intelligence (brain/, memory/), no app code |
| 3-4 | 1 commit total, mostly planning and conversations |
| 0-2 | No commits. Session existed but nothing shipped. |

**Penalty:** Subtract 2 if any feature was "shipped" but broke in production.

### Dimension 2: Code Quality (0-10)

Measures: Are we shipping clean code or accumulating debt?

| Score | What it Looks Like |
|-------|--------------------|
| 9-10 | Build passed before every merge, code review ran, zero CRITICAL/HIGH issues |
| 7-8 | Build passed, minor issues noted and addressed |
| 5-6 | Build passed but code review skipped, or MEDIUM issues left unresolved |
| 3-4 | TypeScript errors suppressed with `any` or `// @ts-ignore`, or hardcoded values |
| 0-2 | CRITICAL security issue shipped (secret exposed, RLS disabled, auth bypassed) |

**Evidence to check:** Look at commit messages for "fix build", "ts error", "hotfix" patterns — these indicate quality problems that slipped through.

### Dimension 3: Memory Health (0-10)

Measures: Is the agent intelligence staying current and useful across AI switches?

| Score | What it Looks Like |
|-------|--------------------|
| 9-10 | STATE.md, ACTIVE_TASKS.md, SESSION_LOG.md all updated same day as work |
| 7-8 | Memory updated within 24 hours of work |
| 5-6 | Memory updated but incomplete (missing key decisions or outcomes) |
| 3-4 | Memory 2-3 days stale, context would be lost on agent switch |
| 0-2 | Memory not updated at all — other agents would start blind |

**Check:** Does STATE.md reflect what actually happened this week? Does SESSION_LOG.md have entries for each active day?

### Dimension 4: Agent Coordination (0-10)

Measures: Are all three agents (Claude, Gemini, Anti-Gravity) working from the same ground truth?

| Score | What it Looks Like |
|-------|--------------------|
| 9-10 | No agent did duplicate work, no contradictory outputs, memory sync ran after each session |
| 7-8 | Minor overlap but caught quickly, STATE.md stayed current |
| 5-6 | One instance of duplicate work or conflicting agent outputs |
| 3-4 | Multiple conflicting memory states, work done in one agent lost to another |
| 0-2 | Total desync — agents contradicting each other or repeating work blind |

---

## Phase 4: Improvement Actions

**For every dimension scored below 7, generate 2 specific, actionable improvements.**

Format:
```
[DIMENSION] scored [X/10] — Root cause: [1 sentence]
Action 1: [Specific, doable this week — not vague]
Action 2: [Specific, doable this week]
```

### Improvement Bank (Reference)

**Shipping Velocity below 7:**
- Schedule a specific "ship window" — 2-hour block dedicated only to deploying code, not planning
- Identify the single task that has been in ACTIVE_TASKS.md the longest; ship it or kill it this week
- Check if any task is blocked on CC input — surface it explicitly so it doesn't sit

**Code Quality below 7:**
- Add `npm run build` as the first command in every session before touching code
- Run the code-review skill before every PR, not after
- Review MISTAKES.md for the most recent entry — make sure it has a prevention strategy

**Memory Health below 7:**
- Set a rule: no session ends without updating STATE.md and SESSION_LOG.md first
- Review ACTIVE_TASKS.md — remove any task completed 7+ days ago, it's cluttering context
- If STATE.md is stale, update it right now before writing the retro report

**Agent Coordination below 7:**
- Add a "sync checkpoint" entry to SESSION_LOG.md at the start of each session summarizing what the previous agent left off
- Verify that ACTIVE_TASKS.md task IDs are used consistently across all agent entries
- Run a STATE.md audit — does it reflect what CC told any agent in the past week?

---

## Phase 5: Trend Analysis

Look back at the last 3-4 retro reports (if they exist in SESSION_LOG.md or memory/).

Track:
- Is shipping velocity trending up, flat, or down over 4 weeks?
- Are the same mistakes appearing in MISTAKES.md across multiple weeks?
- Which dimension has the lowest score pattern?

**Repeating mistake rule:** If the same mistake category appears in MISTAKES.md in 2 or more weeks, it is a systemic pattern — not a one-off. Escalate: create an SOP or add an auto-check to prevent it.

---

## Phase 6: Memory Update

After generating the report:

**Append to `memory/PATTERNS.md`** any new pattern discovered (tag `[PROBATIONARY]`):
```
[PROBATIONARY] [DATE] — [Pattern name]
Observation: [What was seen in the retro data]
Implication: [What this means for how we work]
```

**Append to `memory/MISTAKES.md`** any recurring mistake identified:
```
### [DATE] — [Mistake name]
What happened: [Brief description from retro data]
Root cause: [Why it happened]
Prevention: [Specific check or rule to prevent recurrence]
Recurrence: [If this is a repeat, note the original date]
```

**Update `memory/SESSION_LOG.md`**:
```
### [DATE] — Weekly Retro
Scores: Velocity [X]/10 | Quality [X]/10 | Memory [X]/10 | Coordination [X]/10
Commits this week: [N] across [N] repos
Actions: [N] improvement actions generated
```

---

## Report Output Format

```
## Weekly Retro — [Week of YYYY-MM-DD]

### By the Numbers
- Commits: [N] across [N] repos
- Files changed: [N]
- Features shipped: [N]
- Bugs fixed: [N]
- Mistakes logged: [N] ([N] repeats)
- Task completion rate: [X]%

### Scores
| Dimension | Score | Trend |
|-----------|-------|-------|
| Shipping Velocity | [X]/10 | [↑ / → / ↓] |
| Code Quality | [X]/10 | [↑ / → / ↓] |
| Memory Health | [X]/10 | [↑ / → / ↓] |
| Agent Coordination | [X]/10 | [↑ / → / ↓] |
| **Overall** | **[avg]/10** | |

### What Shipped
- [App]: [brief description of feature/fix]
- ...

### What Went Wrong
- [Issue] — [Root cause in one sentence]
- ...

### Improvement Actions
[Only for dimensions < 7]
- [DIMENSION] [X/10]: [Action 1]
- [DIMENSION] [X/10]: [Action 2]

### Patterns Spotted
- [Any trend worth noting — positive or negative]

### Next Week Focus
[1-3 sentences: what should the week accomplish to move the needle on MRR and quality]
```

---

## Insights-to-Rules Pipeline

After the retrospective analysis, run the insights extraction loop:

### Step 1: Pattern Extraction
For each repeated behavior (positive or negative) found in the retro:
- If a positive pattern appeared 3+ times → candidate for CLAUDE.md rule
- If a negative pattern appeared 2+ times → candidate for CLAUDE.md rule or hook

### Step 2: Rule Drafting
For each candidate, draft a concrete rule:
- State the behavior to enforce or prevent
- Include the "why" (what went wrong without this rule)
- Keep to 1-2 sentences max

### Step 3: Hook Consideration
For critical rules (security, destructive operations):
- Can this be enforced via a Claude Code hook instead of an instruction?
- "An instruction can be forgotten. A hook fires every single time."
- If yes, draft the hook config for `.claude/settings.local.json`

### Step 4: Integration
- Append new rules to CLAUDE.md (in the appropriate section)
- Sync to GEMINI.md and ANTIGRAVITY.md
- If hook created, add to settings
- Log the insight and resulting rule in memory/PATTERNS.md

### The Weekly /insights Loop
Run `/retro` weekly. The insights pipeline runs automatically as part of it.
Over time, the system's CLAUDE.md becomes a living document that grows
smarter from every session — not through bloat, but through distilled rules
that prevent repeated mistakes and encode proven patterns.

---

## Scheduling Note

Run `/retro` every Sunday or Monday morning before starting the week's first task. A retro that runs mid-week is better than no retro, but the Sunday/Monday rhythm creates the clearest before/after boundary.

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
