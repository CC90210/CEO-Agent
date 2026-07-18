---
description: "Session-start heartbeat system: checklist of proactive checks (memory, infrastructure, Supabase sync, pending tasks) that run before engaging with CC's requests"
tags: [heartbeat, monitoring]
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# HEARTBEAT — Proactive Autonomous Operations (V5.5 Enhanced)

> Unlike a cron job that fires blindly, the heartbeat exercises judgment.
> It checks conditions and only acts when action is warranted.
> **V5.5 Enhancements:** OpenClaw-inspired merge window (prevents duplicate actions), Supabase state sync, interaction protocol compliance check, duplicate suppression.

## Trigger

The heartbeat runs at **session start** (IDE-based agent, not daemon). When Bravo wakes up, it runs through this checklist before engaging with CC's request.

### Merge Window (OpenClaw Pattern)
If multiple triggers fire simultaneously (e.g., session start + pending task alert), merge them into a single heartbeat run. Prevents duplicate actions and wasted context.

## Session-Start Heartbeat Checks

### 1. Memory Consistency (Priority: HIGH)
```
CHECK: Are memory files internally consistent?
- Read ACTIVE_TASKS.md — any tasks marked "in progress" from a previous session?
- Read SESSION_LOG.md (last 3 entries) — any incomplete work?
- Read MISTAKES.md — any recent mistakes that apply to today's work?
- Read PATTERNS.md — any new [VALIDATED] patterns to internalize?
- Check for [PROBATIONARY] items that have passed 3 sessions → promote to [VALIDATED]
- Check for [UNDER_REVIEW] items → flag for CC attention
ACTION: Flag stale tasks. Carry forward or close them. Promote validated items.
```

### 2. Infrastructure Health (Priority: HIGH)
```
CHECK: Are critical systems operational?
- git status — clean working tree? Uncommitted changes?
- MCP servers — any known issues from last session?
- .env.agents — referenced but never read values
ACTION: Report any issues before starting work.
```

### 3. Supabase State Sync (Priority: HIGH)
```
CHECK: Is the database in sync with files?
- Query agent_state table → compare with brain/STATE.md
- If diverged, files win — update DB
- Query last session's agent_traces for context on previous actions
- Check for any pending self_modification_log entries
ACTION: Sync state. Report any divergence found.
```

### 4. Pending Tasks (Priority: MEDIUM)
```
CHECK: Are there scheduled tasks in memory/ACTIVE_TASKS.md?
- Overdue items (marked with dates)
- Blocked items (waiting on dependencies)
- Priority items flagged by CC
ACTION: Present status to CC. Suggest next action.
```

### 5. Self-Healing Scan (Priority: MEDIUM)
```
CHECK: Is the workspace healthy?
- Junk files in project root? (*.js, *.txt, *.log, debug dumps)
- Memory bloat? (SESSION_LOG > 200 lines? ACTIVE_TASKS > 50 items?)
- Stale context? (CONTEXT files older than 30 days without update?)
- Confidence decay? (LONG_TERM.md facts not verified in 30+ days?)
ACTION: Auto-clean junk. Suggest compression for bloated files. Flag stale facts.
```

### 6. Growth & Evolution Check (Priority: MEDIUM)
```
CHECK: Has Bravo learned anything new recently?
- New patterns discovered in last 3 sessions?
- New skills used for the first time?
- Recurring problems that could become SOPs? (3+ similar task completions → auto-suggest SOP)
- Any [PROBATIONARY] SOPs ready for promotion? (3+ successful executions)
- Activation scores: any memories/skills decaying below threshold?
ACTION: Log insights to brain/GROWTH.md. Promote validated items. Archive low-activation items.
```

## Session-End Heartbeat (Self-Heal + Sync Protocol)

Execute the full session-end protocol from `brain/INTERACTION_PROTOCOL.md` Section 8:

1. **Context Diagnostics** — Prune temp files, compress logs
2. **API Hardening** — Did anything fail? Log to MISTAKES.md + Supabase
3. **Code Verification** — Any uncommitted changes? Remind CC.
4. **Pattern Distillation** — Extract new patterns/mistakes from this session
5. **Reflexion Check** — Any failed tasks this session? Generate structured reflections.
6. **Memory Sync** — Update ACTIVE_TASKS, SESSION_LOG
7. **State Update** — Update brain/STATE.md with current operational state
8. **Supabase Sync** — Update agent_state, insert session_logs, flush agent_traces, insert new memories/growth
9. **Git Commit** — Stage brain/ + memory/ changes → commit with `bravo: sync — session YYYY-MM-DD`
10. **Confirmation** — State to CC: "Memory synced. [X] files updated, [Y] traces logged, [Z] new learnings captured."

## Heartbeat Response Format

When reporting heartbeat results to CC:
```
HEARTBEAT COMPLETE (V5.5)
- Memory: [OK/ISSUES FOUND] ([X] probationary items, [Y] pending validation)
- Infrastructure: [OK/ISSUES FOUND]
- Supabase Sync: [IN SYNC/DIVERGED — files win]
- Pending Tasks: [X items] ([Y] blocked)
- Workspace: [CLEAN/NEEDS ATTENTION]
- Growth: [X new insights] ([Y] items promoted to VALIDATED)
Ready for orders, CC.
```

## Duplicate Suppression (OpenClaw Pattern)

If the same heartbeat issue was reported in the last session and no action was taken:
- Don't repeat the same alert verbatim
- Instead: "Previously flagged: [issue]. Still unresolved. Priority: [level]."
- This prevents alert fatigue while keeping issues visible.

## Future: Daemon Mode

When n8n webhook triggers are configured, heartbeat can run on a schedule:
- n8n cron trigger → Telegram bot → Claude Code CLI → heartbeat check
- This enables 24/7 autonomous monitoring without CC opening the IDE
- See: telegram_agent.js for the existing Telegram → CLI bridge
- Daemon heartbeat uses the same checks but with reduced verbosity (only report issues, not OKs)

## Obsidian Links
- [[brain/STATE]] | [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]]


## Related (graph)

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
- [[brain/AGENT_ORCHESTRATION]]
