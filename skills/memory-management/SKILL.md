---
name: memory-management
description: MemoryBox system for preventing bloat, scoring confidence, compressing archives, and maintaining memory hygiene. Ensures cross-session intelligence without context window overflow.
---

# Memory Management (MemoryBox)

## Overview

Memory is Bravo's most critical asset. Without active management, memory files grow until they bloat the context window, cause hallucinations, or crash sessions. MemoryBox prevents this.

## Five-Gate Knowledge Filter

Every memory write must pass through all five gates before being stored. Run these in order. Stop at the first gate that fails.

**Gate 1: VALUE** — Does this information change how the agent acts? If not, discard.
**Gate 2: ALIGNMENT** — Does this fit an existing memory category? If not, is it worth creating one?
**Gate 3: REDUNDANCY** — Does a memory already capture this? If yes, update existing instead of creating new.
**Gate 4: FRESHNESS** — Is this time-sensitive? If yes, set a decay trigger. If timeless, mark as stable.
**Gate 5: PLACEMENT** — Which tier does this belong in? (Tier 1-5). Place it correctly.

The most common outcome of running the Five Gates is: **DO NOTHING.**
Most observations are not worth persisting. Only write when the information will change future behavior.

---

## Memory Architecture

### Tier 1: Brain (Always Loaded)
**Files:** `brain/SOUL.md`, `brain/USER.md`, `brain/STATE.md`
**Budget:** <500 lines combined
**Rule:** Loaded at every session start. Must be concise.

### Tier 2: Active Memory (Loaded on Demand)
**Files:** `memory/ACTIVE_TASKS.md`, `memory/LONG_TERM.md`, `memory/SOP_LIBRARY.md`
**Budget:** <300 lines each
**Rule:** Read during Brain Loop Step 2 (RECALL). Only when relevant.

### Tier 3: Reference Memory (Loaded When Needed)
**Files:** `memory/PATTERNS.md`, `memory/MISTAKES.md`, `memory/DECISIONS.md`
**Budget:** <200 lines each
**Rule:** Read when debugging, planning, or reviewing. Not every session.

### Tier 4: Log Memory (Write-Mostly)
**Files:** `memory/SESSION_LOG.md`, `memory/SELF_REFLECTIONS.md`, `memory/daily/*.md`
**Budget:** Unlimited (compressed regularly)
**Rule:** Written to frequently, read rarely. Compressed when bloated.

### Tier 5: Archive (Cold Storage)
**Files:** `memory/ARCHIVES/*.md`
**Budget:** Unlimited
**Rule:** Historical data. Only accessed for monthly audits or deep investigations.

## Confidence Scoring

Every memory entry gets a confidence score:

| Score | Meaning | Action |
|-------|---------|--------|
| 0.95-1.0 | Verified fact | Persist in LONG_TERM.md |
| 0.8-0.94 | High confidence | Persist, verify quarterly |
| 0.5-0.79 | Medium confidence | Keep in active memory, verify monthly |
| 0.2-0.49 | Low confidence | Flag for verification, don't rely on |
| 0.0-0.19 | Speculation | Don't store. Use only in session context. |

### Confidence Decay
- Facts not re-verified in 30 days: confidence -= 0.1
- Facts not re-verified in 90 days: confidence -= 0.3
- Facts contradicted by evidence: immediately review
- Facts confirmed by evidence: confidence += 0.05 (cap at 1.0)

## Bloat Prevention Rules

### SESSION_LOG.md
- **Threshold:** 200 lines
- **Action:** Compress entries older than 14 days → `memory/ARCHIVES/sessions-YYYY-MM.md`
- **Keep:** Last 10 session entries in active file

### ACTIVE_TASKS.md
- **Threshold:** 50 items
- **Action:** Completed tasks older than 7 days → remove from file
- **Keep:** All in-progress, blocked, and recent completed items

### MISTAKES.md
- **Threshold:** 30 entries
- **Action:** Deduplicate. Merge similar mistakes. Archive resolved ones.
- **Keep:** Active prevention strategies only

### PATTERNS.md
- **Threshold:** 30 entries
- **Action:** Promote high-confidence patterns to SOPs. Archive low-use patterns.
- **Keep:** Active patterns with recent usage

### daily/ logs
- **Threshold:** 30 days of logs
- **Action:** Compress months older than current → `memory/ARCHIVES/daily-YYYY-MM.md`
- **Keep:** Last 30 days

## Memory Sync Protocol (File ↔ Supabase)

When Supabase is available:

### Session Start
1. Read local memory files
2. Query Supabase for any updates from other agent interfaces
3. Merge: Supabase wins on newer timestamps
4. Update local files with merged data

### Session End
1. Write session data to local files
2. Sync to Supabase `memories`, `session_logs`, `daily_logs` tables
3. Confirm sync success

### Conflict Resolution
- Newer timestamp wins
- Higher confidence score wins (for memory facts)
- If truly ambiguous: flag for CC's review

## Memory Hygiene Checklist (Monthly)

```
[ ] SESSION_LOG.md under 200 lines
[ ] ACTIVE_TASKS.md under 50 items
[ ] MISTAKES.md under 30 entries (no duplicates)
[ ] PATTERNS.md under 30 entries (no duplicates)
[ ] LONG_TERM.md — all facts still valid? Confidence scores current?
[ ] SOP_LIBRARY.md — all SOPs still relevant? Success rates accurate?
[ ] daily/ — older than 30 days archived?
[ ] brain/ files — under 500 lines combined?
[ ] No orphaned references (links to deleted files)?
[ ] Supabase sync current (if available)?
```
