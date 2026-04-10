---
name: background-workers
description: >
  Formalized background worker system for automated audit, memory management, state sync,
  and optimization tasks. Workers run on intervals during active sessions to maintain
  system health without manual intervention. Use when: configuring workers, debugging
  worker failures, adding new automated tasks. Skip when: workers are running correctly.
tags: [automation, workers, system-health]
---

# Background Workers — Automated System Maintenance

> **Purpose:** Manual maintenance doesn't scale. Background workers handle audit, memory
> compression, state sync, and optimization automatically during active sessions.

## Worker Registry

Four workers, each with a defined priority and interval:

### 1. Audit Worker (CRITICAL — every 5 min)

**Purpose:** Continuous security and compliance monitoring.

**Tasks:**
| Task | What It Does | On Failure |
|------|-------------|------------|
| Secret scan | Grep staged files for API keys, tokens, passwords | BLOCK commit, alert CC |
| Credential file check | Verify .env.agents not in git staging | Unstage immediately |
| Hook audit review | Check tmp/hook_audit.log for anomalies | Flag suspicious entries |
| Permission verify | Confirm no agent exceeded its claims | Log violation to MISTAKES.md |

**Implementation:**
```bash
# Secret scan (runs on staged files)
git diff --cached --name-only | xargs grep -l -E "(sk_live_|Bearer |api_key|password\s*=)" 2>/dev/null

# Credential file check
git diff --cached --name-only | grep -E "\.env" && echo "BLOCKED: .env file staged"

# Hook audit log size check
wc -l tmp/hook_audit.log 2>/dev/null | awk '{if ($1 > 1000) print "WARN: audit log bloated"}'
```

**Config:** `.agents/config.toml` [workers.audit]

### 2. Memory Worker (HIGH — every 30 min)

**Purpose:** Prevent memory bloat and maintain freshness.

**Tasks:**
| Task | What It Does | Threshold | Action |
|------|-------------|-----------|--------|
| SESSION_LOG.md size | Count lines | >200 lines | Compress entries >14 days → ARCHIVES/ |
| ACTIVE_TASKS.md count | Count items | >50 items | Remove completed tasks >7 days old |
| brain/ combined size | Count total lines | >500 lines | Flag for manual review |
| Confidence decay | Check fact freshness | >30 days unverified | Reduce confidence by 0.1 |
| Duplicate scan | Check for repeated entries | Any duplicates | Merge and deduplicate |

**Compression protocol:**
1. Read SESSION_LOG.md
2. Identify entries older than 14 days
3. Move them to `memory/ARCHIVES/sessions-YYYY-MM.md`
4. Keep the 10 most recent entries in the active file
5. Update any cross-references

**Config:** `.agents/config.toml` [workers.memory]

### 3. Sync Worker (HIGH — every 10 min)

**Purpose:** Keep all AI interfaces working from the same ground truth.

**Tasks:**
| Task | What It Does | On Failure |
|------|-------------|------------|
| STATE.md update | Refresh operational state from current session | Reconstruct from ACTIVE_TASKS.md |
| Supabase flush | Push pending traces to agent_traces table | Queue for next cycle |
| ACTIVE_TASKS.md verify | Ensure task statuses reflect actual progress | Flag stale tasks |
| Cross-agent check | Verify no conflicting state from other agents | Merge (newer wins) |

**Sync protocol:**
1. Read current brain/STATE.md
2. Compare against actual session activity
3. Update any stale fields
4. If Supabase available: flush pending agent_traces
5. Verify ACTIVE_TASKS.md hasn't drifted from actual progress

**Config:** `.agents/config.toml` [workers.sync]

### 4. Optimize Worker (LOW — every 60 min)

**Purpose:** Long-term system health and efficiency.

**Tasks:**
| Task | What It Does | On Finding |
|------|-------------|------------|
| Unused skill detection | Check skill_activation table for dormant skills | Report (don't delete) |
| Duplicate memory entries | Scan LONG_TERM.md + PATTERNS.md for duplicates | Merge automatically |
| Referential integrity | Grep for broken ``wiki-links`` in markdown | Fix broken links |
| Pattern promotion | Check [PROBATIONARY] patterns with 3+ uses | Promote to [VALIDATED] |
| SOP success rates | Review SOP execution counts and failure rates | Flag SOPs with <70% success |

**Config:** `.agents/config.toml` [workers.optimize]

## Worker Execution Model

Workers are NOT separate processes — they are logical checkpoints that run during active sessions:

1. **Session start:** All workers run their checks once (initial health scan)
2. **During session:** Workers are triggered at their configured intervals
3. **Session end:** All workers run final checks (cleanup pass)
4. **Between sessions:** No workers run (system is idle)

**Priority determines execution order when multiple workers trigger simultaneously:**
- CRITICAL (audit) → runs first, always
- HIGH (memory, sync) → runs second
- LOW (optimize) → runs last, skipped if session is ending

## Adding New Workers

To add a new background worker:

1. Define it in `.agents/config.toml` under `[workers.new_name]`:
```toml
[workers.new_name]
enabled = true
priority = "high"     # critical | high | low
interval_seconds = 600
tasks = [
    "description of task 1",
    "description of task 2"
]
```

2. Add the implementation details to this skill file
3. Update brain/CAPABILITIES.md with the new worker count

## Worker Health Monitoring

Track worker execution in the session:

```
WORKER STATUS:
  Audit: Last run [time] — [PASS | WARN: details]
  Memory: Last run [time] — [PASS | COMPRESSED: N entries]
  Sync: Last run [time] — [PASS | SYNCED: N traces]
  Optimize: Last run [time] — [PASS | FOUND: N issues]
```

If any worker consistently fails, log to MISTAKES.md and investigate root cause.

## Integration Points

- **Self-healing skill:** Workers ARE the automated arm of self-healing
- **Memory management skill:** Memory worker implements the bloat prevention rules
- **Hooks automation:** Post-task hooks trigger worker-like checks per-operation
- **Brain Loop Step 10 (HEAL):** The HEAL step runs a subset of worker checks

## Obsidian Links
- [[skills/self-healing/SKILL]] | [[skills/memory-management/SKILL]]
- [[skills/hooks-automation/SKILL]] | [[brain/BRAIN_LOOP]]
- [[brain/CAPABILITIES]] | [[brain/STATE]]
