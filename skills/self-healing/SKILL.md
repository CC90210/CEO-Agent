---
name: self-healing
description: Multi-dimensional autonomous recovery and health maintenance. Triggers on errors, session boundaries, and infrastructure issues. Covers memory healing, context healing, skill healing, infrastructure healing, and relationship healing.
triggers: [heal, broken config, drift, inconsistent, stale, self-heal, recovery]
tier: core
dependencies: [memory-management]
---

# Self-Healing System

## Overview

Bravo's self-healing operates across 5 dimensions and 4 severity tiers. Unlike basic error recovery, this system proactively detects, diagnoses, and repairs issues before they cascade.

## 5 Dimensions of Self-Healing

### 1. Memory Self-Healing
**Detects:** Contradictions between memory files, stale facts, memory bloat, orphaned references
**Heals:**
- Scan for contradictions between LONG_TERM.md and recent session data
- Decay confidence scores on unverified facts (>30 days: -0.1, >90 days: -0.3)
- Compress SESSION_LOG.md when >200 lines → archive to memory/ARCHIVES/
- Remove duplicate entries across memory files
- Flag facts that conflict with observed behavior

**Trigger:** Session start (heartbeat), session end, after memory writes

### 2. Context Self-Healing
**Detects:** Stale APPS_CONTEXT files, outdated business data, wrong references
**Heals:**
- Flag APPS_CONTEXT files not updated in 30+ days
- Cross-reference USER.md with recent CC statements for drift
- Ensure brain/STATE.md reflects actual system state
- Remove references to deprecated tools/services

**Trigger:** Monthly audit, after CC corrects agent behavior

### 3. Skill Self-Healing
**Detects:** Skills with declining success rates, skills that error frequently, unused skills
**Heals:**
- Track skill usage via Supabase `skills_registry` table
- Flag skills with <70% success rate for review
- Suggest skill improvements based on failure patterns
- Identify skill gaps (tasks that fail because no skill exists)

**Trigger:** After skill execution failures, monthly audit

### 4. Infrastructure Self-Healing
**Detects:** MCP server failures, API auth issues, broken dependencies, config drift
**Heals:**
- Test MCP connectivity at session start
- Validate .env.agents has required keys (by name, never value)
- Check git status for unexpected state
- Verify workspace has no junk files
- Flag package.json dependency issues

**Trigger:** Session start (heartbeat), after MCP failures

### 5. Relationship Self-Healing
**Detects:** Communication style drift, CC frustration signals, declining task satisfaction
**Heals:**
- If CC redirects or expresses frustration → log to SELF_REFLECTIONS.md
- Recalibrate communication style based on feedback
- Track CC's most common requests → suggest proactive improvements
- Adjust verbosity/detail level based on CC's responses

**Trigger:** After CC provides negative feedback or redirects

## 4-Tier Severity Model

### Tier 1: Auto-Fix (Instant)
**Scope:** Trivial issues that can be fixed without CC's input
- Clean junk files from workspace
- Compress bloated memory files
- Update stale timestamps
- Fix formatting issues in memory files

### Tier 2: Diagnose & Suggest (1-3 minutes)
**Scope:** Issues that need CC's awareness but have clear fixes
- MCP authentication failures → suggest .env.agents check
- Character limit violations → rewrite content
- Git conflicts → suggest resolution strategy
- Stale tasks → suggest close or carry forward

### Tier 3: Deep Investigation (5-15 minutes)
**Scope:** Complex issues requiring systematic debugging
- Recurring MCP failures → trace root cause through logs
- Memory contradictions → cross-reference sources
- Skill degradation → analyze failure patterns
- Performance issues → profile and benchmark

### Tier 4: Escalate to CC (Immediately)
**Scope:** Issues that require human decision
- Destructive operations needed (data deletion, credential rotation)
- Ambiguous business decisions (which client to prioritize)
- Security concerns (exposed credentials, unauthorized access)
- Unresolvable technical issues after 3 attempts

## Self-Healing Checklist

Run this at session end (complements /self-heal command):

```
[ ] Memory consistency check (no contradictions)
[ ] Junk file scan (workspace clean)
[ ] Git status (no unexpected uncommitted changes)
[ ] MCP health (note any failures this session)
[ ] Task status (ACTIVE_TASKS.md current)
[ ] Session logged (SESSION_LOG.md updated)
[ ] Patterns extracted (new patterns/mistakes logged)
[ ] State updated (brain/STATE.md reflects reality)
[ ] Confidence scores decayed (any facts need refresh?)
[ ] Growth logged (any new capabilities this session?)
```

## Logging

All self-healing events are logged to:
- `memory/MISTAKES.md` (if a mistake was found and fixed)
- `memory/SELF_REFLECTIONS.md` (if a lesson was learned)
- Supabase `self_healing_log` table (when available)
- `brain/STATE.md` (operational state updated)
