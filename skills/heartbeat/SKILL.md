---
name: heartbeat
description: Proactive autonomous monitoring and session management. Runs at session start and end. Checks memory consistency, infrastructure health, pending tasks, and workspace cleanliness. Enables Bravo to act without prompting.
triggers: [heartbeat, health check, session start, monitoring, proactive, autonomous]
tier: core
dependencies: [self-healing, memory-management]
---

# Heartbeat Skill

## Overview

The heartbeat is what separates a reactive assistant from an autonomous agent. It enables Bravo to proactively check conditions, flag issues, and take action without CC having to ask.

## Session-Start Heartbeat

Execute this checklist when Bravo wakes up:

### Step 1: Identity Load (5 seconds)
```bash
# Read core identity files
read brain/SOUL.md      # Who am I?
read brain/STATE.md     # What's my current state?
read brain/USER.md      # Who is CC? (if needed for context)
```

### Step 2: Memory Check (10 seconds)
```bash
# Check for stale or inconsistent memory
read memory/ACTIVE_TASKS.md    # Any leftover in-progress tasks?
read memory/SESSION_LOG.md     # Last 3 entries for continuity
check: Any tasks older than 7 days still marked "in progress"?
check: SESSION_LOG under 200 lines?
```

### Step 3: Infrastructure Health (10 seconds)
```bash
# Verify critical systems
git status                      # Clean tree? Unexpected changes?
check: Known MCP issues from last session?
check: Any blocked items in ACTIVE_TASKS?
```

### Step 4: Workspace Scan (5 seconds)
```bash
# Look for junk files
scan: *.js, *.txt, *.log in project root
scan: debug dumps, temp files, mcp_out.json
action: Report if found (auto-clean only trivial junk)
```

### Step 5: Report
```
HEARTBEAT COMPLETE
- Memory: [OK | X stale tasks found]
- Infrastructure: [OK | issues listed]
- Pending: [X tasks in queue]
- Workspace: [CLEAN | needs attention]
Ready, CC.
```

## Session-End Self-Heal

Execute this when session is ending:

### Step 1: Task Reconciliation
- Mark completed tasks as done in ACTIVE_TASKS.md
- Flag any in-progress tasks that won't be finished
- Add new tasks discovered during session

### Step 2: Session Logging
- Append session summary to SESSION_LOG.md
- Format: Date, Agent, Summary, Tasks Completed, Tasks Blocked, Key Insights

### Step 3: Pattern Extraction
- Did we learn anything new? → PATTERNS.md
- Did we make a mistake? → MISTAKES.md
- Did we discover a new capability? → brain/GROWTH.md

### Step 4: Memory Hygiene
- Check file sizes (SESSION_LOG < 200 lines, etc.)
- Compress if needed (→ ARCHIVES/)
- Remove completed tasks older than 7 days

### Step 5: State Update
- Update brain/STATE.md with:
  - Current confidence level
  - Focus area
  - Known issues
  - System health summary

## Autonomous Task Queue

For future daemon mode (n8n → Telegram → CLI):

```yaml
heartbeat_tasks:
  - name: "Check Late MCP health"
    interval: "6h"
    condition: "Late MCP was patched (Pydantic issue)"
    action: "Test posts_list call. If fails, alert CC."

  - name: "Review ACTIVE_TASKS staleness"
    interval: "24h"
    condition: "Always"
    action: "Flag tasks older than 7 days with no update."

  - name: "Memory bloat check"
    interval: "24h"
    condition: "Always"
    action: "Check all memory file sizes. Compress if needed."

  - name: "Content calendar check"
    interval: "24h"
    condition: "Content calendar exists"
    action: "Check if today has scheduled content. Alert CC if posts are due."
```

## Integration Points

- **Brain Loop:** Heartbeat results inform Step 1 (ORIENT) and Step 3 (ASSESS)
- **Self-Healing:** Heartbeat triggers Tier 1 auto-fixes and Tier 2 diagnostics
- **Memory Management:** Heartbeat triggers bloat prevention checks
- **Growth Engine:** Heartbeat tracks session-over-session improvements

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
