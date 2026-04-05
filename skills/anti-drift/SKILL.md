---
name: anti-drift
description: >
  Prevents agent divergence from task intent through checkpoint validation, scope monitoring,
  and alignment gates. Detects scope creep, time overruns, and error cascades, then forces
  re-alignment before work continues. Use when: multi-agent tasks, complex implementations,
  long-running sessions. Skip when: trivial single-step tasks, pure research.
tags: [orchestration, quality, agents]
---

# Anti-Drift — Agent Alignment & Divergence Prevention

> **Purpose:** Agents solving complex tasks will drift from the original intent. This skill
> detects drift early and forces re-alignment before wasted work compounds.

## Why This Matters

Without anti-drift:
- Agent starts fixing a bug, ends up refactoring 12 files nobody asked for
- Multi-agent task has each agent making conflicting assumptions
- 30-minute task balloons to 2 hours because scope expanded silently
- Agent retries the same failing approach 5 times instead of escalating

With anti-drift:
- Checkpoint every N steps forces "am I still on track?"
- Scope monitor flags when files touched exceed the plan
- Error cascade detector stops thrashing after 2 consecutive failures
- Time overrun detector flags when work exceeds 2x the estimate

## The Three Drift Detectors

### 1. Scope Creep Detector

**Trigger:** Agent touches files not in the original plan or routing decision.

**How it works:**
1. At task start, the routing decision lists expected files/directories
2. After each edit, compare touched files against the plan
3. If files touched exceed plan by >3 files → **SCOPE CREEP ALERT**

**Response to scope creep:**
```
DRIFT DETECTED: Scope Creep
  Planned files: [list from routing decision]
  Actual files touched: [current list]
  Excess: [N files outside plan]

  OPTIONS:
  A) Revert to plan — undo out-of-scope changes
  B) Expand plan — update routing decision to include new files (requires justification)
  C) Escalate to CC — ask if scope expansion is warranted
```

**Config:** `.agents/config.toml` [anti_drift.signals] scope_creep_threshold = 3

### 2. Error Cascade Detector

**Trigger:** 2+ consecutive errors/failures in the same task.

**How it works:**
1. Track each execution step's success/failure
2. If 2 consecutive steps fail → **ERROR CASCADE ALERT**
3. This prevents the "keep trying the same thing" anti-pattern

**Response to error cascade:**
```
DRIFT DETECTED: Error Cascade
  Failed step 1: [description + error]
  Failed step 2: [description + error]

  MANDATORY ACTIONS:
  1. STOP executing. Do not attempt fix #3.
  2. Switch to alternative approach (BRAIN_LOOP Step 4 alternatives)
  3. If no alternatives exist, generate them NOW
  4. If 3 total approaches have failed → ESCALATE TO CC
```

**Config:** `.agents/config.toml` [anti_drift.signals] error_cascade_limit = 2

### 3. Time Overrun Detector

**Trigger:** Task is taking >2x the estimated time.

**How it works:**
1. At routing, estimate task duration based on complexity tier:
   - TRIVIAL: 2 min | SIMPLE: 10 min | MODERATE: 30 min | COMPLEX: 60 min | ARCHITECTURAL: 120 min
2. Track elapsed time from task start
3. If elapsed > 2x estimate → **TIME OVERRUN ALERT**

**Response to time overrun:**
```
DRIFT DETECTED: Time Overrun
  Estimated: [X minutes]
  Elapsed: [Y minutes] ([Z]x overrun)
  Current step: [what's happening now]

  CHECKPOINT:
  1. Is the original approach still viable?
  2. Should we simplify scope?
  3. Is there a blocking issue that needs CC's input?
  4. Should we commit partial progress and reassess?
```

**Config:** `.agents/config.toml` [anti_drift.signals] time_overrun_factor = 2.0

## Checkpoint Protocol

**Every N task steps** (default: 5, configurable in config.toml), the executing agent must pause and answer:

```
CHECKPOINT [step N]:
  Original intent: [1-sentence task summary]
  Current state: [what's been done so far]
  Remaining: [what's left to do]
  On track: [YES / DRIFTING — explain]
  Files touched: [count] / [planned count]
  Errors encountered: [count]
```

If "DRIFTING" → apply the relevant drift detector response above.

## Validation Gates

Gates are hard stops between phases. Work cannot proceed until the gate passes.

### Pre-Execute Gate
Before any code is written:
- [ ] Plan exists and is approved (COMPLEX+ tasks)
- [ ] Files to be modified are identified
- [ ] Agent permissions are sufficient (check config.toml [permissions])
- [ ] No conflicting work in progress (check ACTIVE_TASKS.md)

### Post-Execute Gate
After implementation, before commit:
- [ ] All planned changes are complete
- [ ] No unplanned files were modified (scope check)
- [ ] Build passes (`npm run build` or equivalent)
- [ ] No hardcoded secrets introduced
- [ ] Changes match the original intent

### Pre-Commit Gate
Before any git commit:
- [ ] Code review passed (MODERATE+ tasks)
- [ ] Commit message follows conventional format
- [ ] No .env files staged
- [ ] SESSION_LOG.md updated with what was done

### Post-Deploy Gate
After pushing to remote / Vercel deploy:
- [ ] Production URL loads correctly
- [ ] No console errors on affected pages
- [ ] Webhook handlers respond correctly (if applicable)
- [ ] Mobile responsiveness verified (if UI changed)

## Multi-Agent Coordination Rules

When multiple agents work on the same task (COMPLEX+):

1. **One coordinator** — The architect agent owns the overall plan
2. **Isolated scopes** — Each agent works on assigned files only
3. **Sequential handoffs** — Agent B waits for Agent A to finish before starting dependent work
4. **Shared memory** — All agents read/write to the same ACTIVE_TASKS.md
5. **Conflict detection** — If two agents modify the same file, flag immediately
6. **Max concurrent agents:** 4 (configurable in config.toml [anti_drift.max_concurrent_agents])

## Integration Points

- **BRAIN_LOOP Step 6 (EXECUTE):** Checkpoint protocol runs during execution
- **BRAIN_LOOP Step 10 (HEAL):** Drift metrics logged to MISTAKES.md if drift occurred
- **Task Routing Skill:** Routing decision provides the baseline for scope monitoring
- **Config:** All thresholds and limits in `.agents/config.toml` [anti_drift]

## Obsidian Links
- [[brain/BRAIN_LOOP]] | [[brain/AGENTS]] | [[skills/task-routing/SKILL]] | [[brain/CAPABILITIES]]
- [[memory/MISTAKES]] | [[memory/PATTERNS]]
