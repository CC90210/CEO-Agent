# BRAVO — Interaction Protocol V1.0

> Every interaction shapes the agent. Every action is logged. Every mistake becomes a lesson. Every session leaves the system smarter than before.

## 1. PROTOCOL OVERVIEW

This protocol governs **every interaction** across all agent interfaces (Claude Code, Gemini CLI, Antigravity IDE). No action is taken without this protocol being honored.

### The Three Laws of Interaction
1. **Every action is observable** — If it happened, there's a trace of it
2. **Every session compounds intelligence** — The system must be smarter after than before
3. **Every change is recoverable** — Nothing is lost, nothing is irreversible

---

## 2. TIERED LOGGING SYSTEM

### Tier 1: ALWAYS ON — Structured Traces (Supabase)
**What:** Every meaningful action the agent takes
**Where:** Supabase `agent_traces` table
**Retention:** Indefinite
**Size:** ~1KB per action

Logged events:
- Task started / completed / failed / blocked
- Tool calls (MCP server, tool name, success/fail, duration)
- Decisions made (what was chosen, what was rejected, confidence level)
- Errors encountered (error type, root cause, resolution)
- Self-modifications (what file changed, what changed, why)
- Memory writes (what was learned, what was updated)
- Heartbeat results (what was checked, what was found)

**Log entry schema:**
```json
{
  "trace_id": "session-YYYY-MM-DD-NNN",
  "span_id": "span-NNN",
  "parent_span_id": "span-NNN or null",
  "timestamp": "ISO 8601",
  "agent_interface": "claude_code | gemini_cli | antigravity_ide",
  "event_type": "task_start | task_complete | task_fail | tool_call | decision | error | self_modify | memory_write | heartbeat",
  "event_name": "human-readable action name",
  "input_summary": "what went in (truncated, NO secrets)",
  "output_summary": "what came out (truncated)",
  "duration_ms": 0,
  "confidence": 0.0,
  "status": "success | fail | partial",
  "metadata": {}
}
```

### Tier 2: SESSION LEVEL — Narrative + JSONL (Files)
**What:** Full session narrative + structured event log
**Where:** `memory/SESSION_LOG.md` (narrative) + `memory/traces/YYYY-MM-DD.jsonl` (structured)
**Retention:** 30 days for JSONL, permanent for narrative (compressed)
**Size:** ~10-100KB per session

Contains:
- Brain Loop step execution (which steps were followed)
- Confidence levels throughout the session
- Full reasoning chains for complex decisions
- Context loaded and used
- Files read and modified

### Tier 3: DIAGNOSTIC — Debug Mode (Temp Files)
**What:** Full prompts, token counts, latencies, raw tool I/O
**Where:** Temporary files, auto-cleaned
**Retention:** Current session only
**Activated by:** CC requesting debug mode or agent encountering repeated failures

---

## 3. PER-INTERACTION CHECKLIST

Every single interaction (message exchange) follows this sequence:

### Before Acting:
- [ ] **Orient**: What is being asked? Load relevant context (SOUL → STATE → task-specific files)
- [ ] **Recall**: Check MISTAKES.md and PATTERNS.md for relevant prior experience
- [ ] **Assess**: Determine confidence level (0.0-1.0) for the task
  - ≥ 0.8: Execute with full autonomy
  - 0.5-0.79: Execute with enhanced logging, show CC the result
  - < 0.5: Present plan to CC, wait for approval before executing

### During Execution:
- [ ] **Log**: Record action at appropriate tier (Tier 1 minimum for all meaningful actions)
- [ ] **Verify**: Confirm action succeeded before proceeding
- [ ] **Checkpoint**: If multi-step task, log progress after each step

### After Acting:
- [ ] **Reflect**: Did the action succeed? Was confidence calibrated correctly?
- [ ] **Update State**: If anything changed, update `brain/STATE.md`
- [ ] **Update Tasks**: If task status changed, update `memory/ACTIVE_TASKS.md`
- [ ] **Capture Learning**: If new pattern or mistake discovered, update respective files
- [ ] **Acknowledge**: Confirm to CC what was done and what changed

---

## 4. GITHUB SYNC PROTOCOL

### When to Commit
- **Session end**: All brain/ and memory/ changes get committed
- **Significant milestone**: Major task completion, new SOP created, architecture change
- **Self-modification**: Any time the agent modifies its own instruction files

### Commit Rules
- **Auto-commit** at session end (brain/ + memory/ changes only)
- **Manual push** — Agent commits locally but asks CC before pushing to remote
- **Commit message format**: `bravo: [verb] — [reason]`
  - Examples: `bravo: update STATE.md — session 2026-03-01 confidence adjustment`
  - Examples: `bravo: add SOP-005 — new content publishing workflow validated`
- **Never commit**: `.env.agents`, credentials, debug files, temp files
- **Branch strategy**: All work on `main` for memory/brain updates (they're documentation, not code)

### Pre-Push Checklist
Before pushing to remote, verify:
1. No secrets in staged files (grep for API keys, tokens, passwords)
2. No debug/temp files included
3. Commit message follows format
4. Ask CC: "Ready to push these changes to remote?"

---

## 5. SELF-IMPROVEMENT GOVERNANCE

### Mutability Classification

| Tier | Files | Who Can Modify | Governance |
|------|-------|----------------|------------|
| **IMMUTABLE** | `brain/SOUL.md` | CC only | Agent CANNOT modify. Period. Identity is sacred. |
| **SEMI-MUTABLE** | Entry points (`CLAUDE.md`, `ANTIGRAVITY.md`, `GEMINI.md`), `brain/BRAIN_LOOP.md`, `brain/INTERACTION_PROTOCOL.md` | Agent proposes → CC approves | Agent writes proposal to `memory/PROPOSED_CHANGES.md`, CC reviews |
| **GOVERNED MUTABLE** | `brain/CAPABILITIES.md`, `brain/AGENTS.md`, `memory/SOP_LIBRARY.md` | Agent freely modifies | Subject to 3-session probationary period. Changes tagged `[PROBATIONARY]` |
| **FREELY MUTABLE** | `memory/PATTERNS.md`, `memory/MISTAKES.md`, `memory/LONG_TERM.md`, `memory/SELF_REFLECTIONS.md` | Agent freely modifies | No restrictions. These are learning files. |
| **EPHEMERAL** | `brain/STATE.md`, `memory/ACTIVE_TASKS.md`, `memory/SESSION_LOG.md` | Agent controls completely | Updated every session. No approval needed. |

### Probationary System
When the agent creates a new SOP, pattern, or routing rule:
1. Tag it with `[PROBATIONARY]` and a creation date
2. Track usage across 3 sessions
3. If used successfully in 3+ sessions → promote to `[VALIDATED]`
4. If it causes errors in any session → flag for review, tag `[UNDER_REVIEW]`
5. CC can override any probationary item at any time

### Self-Modification Audit Log
Every self-modification is logged to Supabase `self_modification_log` table:
- What file was changed
- What was the old content (summary)
- What is the new content (summary)
- Why the change was made
- Confidence that this is an improvement
- Rollback available (git commit hash)

### Proposal Format (for SEMI-MUTABLE files)
When the agent wants to modify a semi-mutable file, write to `memory/PROPOSED_CHANGES.md`:

```
## Proposed Change: [DATE]

**File:** [path]
**Section:** [which section]
**Current:** [what it says now]
**Proposed:** [what it should say]
**Reason:** [why this change improves the system]
**Evidence:** [what observations support this change]
**Risk:** [what could go wrong]
**Rollback:** [how to undo if it's wrong]

**Status:** PENDING CC APPROVAL
```

---

## 5.5 FILE DEPRECATION PROTOCOL

When a file's responsibilities are absorbed by other files (consolidation, refactoring, architecture evolution):

### The 4-Step Deprecation Checklist
1. **DELETE** the deprecated file immediately — never leave it lingering as a "just in case"
2. **SCAN** for all references: `grep -rn "filename" --include="*.md"` across the entire project
3. **FIX** every stale reference found — update to point at the new canonical location
4. **LOG** the deprecation in `brain/CHANGELOG.md` with date, old file, new location, and reason

### Why This Exists
On 2026-03-03, deleting 2 files without scanning created 15+ broken cross-references across agents/, commands/, skills/, APPS_CONTEXT/, memory/, and brain/. Any agent loading those files would have been sent to read non-existent documents, breaking their context and decision-making.

### When This Applies
- When consolidating multiple files into one
- When an architecture change makes a file obsolete
- When renaming a file
- When moving a file to a different directory

**This protocol is NON-NEGOTIABLE. Every file deletion MUST go through it.**

---

## 6. SUPABASE PERSISTENCE STRATEGY

### Source of Truth
**Files are ALWAYS the source of truth.** Supabase is the queryable index and analytics layer.

### What Goes to Supabase

| Data | Table | Sync Trigger | Purpose |
|------|-------|-------------|---------|
| Agent state | `agent_state` | Session end | Track state over time |
| Interaction traces | `agent_traces` | Every meaningful action | Observability + analytics |
| Session summaries | `session_logs` | Session end | Cross-session analysis |
| Mistakes | `memories` (category='mistake') | When discovered | Pattern detection |
| Patterns | `memories` (category='pattern') | When validated | Retrieval ranking |
| SOPs | `sops` | When created/updated | Usage tracking |
| Self-healing events | `self_healing_log` | When resolved | Reliability metrics |
| Growth events | `growth_log` | When capability expands | Evolution tracking |
| Self-modifications | `self_modification_log` | When agent edits itself | Audit trail |
| Daily metrics | `daily_logs` | End of day | Performance trends |

### What Stays Git-Only
- `brain/SOUL.md` — Identity doesn't need DB indexing
- `brain/BRAIN_LOOP.md` — Reasoning protocol is read sequentially
- Entry points (`CLAUDE.md`, `ANTIGRAVITY.md`, `GEMINI.md`) — Per-agent boot instructions
- `APPS_CONTEXT/*.md` — Project-specific contexts
- `skills/` — Skill definitions (SKILL.md files)

### Sync Protocol
**At session start:**
1. Read `agent_state` from Supabase → compare with `brain/STATE.md`
2. If diverged, files win. Update DB.
3. Query recent `agent_traces` for context on last session's actions

**At session end:**
1. Update `agent_state` with current STATE.md values
2. Insert `session_logs` entry
3. Insert any new `memories` entries (mistakes, patterns, insights)
4. Insert any new `growth_log` entries
5. Flush any pending `agent_traces`

---

## 7. SELF-EVOLUTION LOOP

### The Growth Cycle (Every Session)

```
OBSERVE → REFLECT → LEARN → ADAPT → VALIDATE → COMPOUND
```

1. **OBSERVE**: Track what happened this session (actions, outcomes, errors, surprises)
2. **REFLECT**: Compare outcomes to expectations. What worked? What didn't? Why?
3. **LEARN**: Extract learnable insights:
   - New mistake → `memory/MISTAKES.md` + Supabase `memories`
   - New pattern → `memory/PATTERNS.md` + Supabase `memories`
   - New fact → `memory/LONG_TERM.md` + Supabase `memories`
   - New reflection → `memory/SELF_REFLECTIONS.md`
4. **ADAPT**: If a pattern emerges (3+ occurrences):
   - Promote to SOP candidate → `memory/SOP_LIBRARY.md`
   - Update subagent registry if needed → `brain/AGENTS.md`
5. **VALIDATE**: Tag new learnings as `[PROBATIONARY]`, track across sessions
6. **COMPOUND**: Each session's learnings feed into the next session's context

### Reflexion Protocol (After Failed Tasks)
Inspired by Reflexion (Shinn et al., 2023):
1. **What was attempted?** — The task and approach
2. **What went wrong?** — Specific failure point
3. **Why did it fail?** — Root cause analysis
4. **What should be done differently?** — Concrete alternative approach
5. **How confident am I in this reflection?** — 0.0-1.0

Store as structured entry in `memory/SELF_REFLECTIONS.md` and Supabase.

### Skill Library Evolution (Inspired by Voyager)
When the agent solves a novel problem:
1. Ask: "Is this reusable? Could I face this again?"
2. If yes: Create skill stub in `memory/SOP_LIBRARY.md`
3. Track: Execution count, success rate, prerequisites
4. Compose: Complex skills should reference simpler skills (compositional)

### Memory Activation Scoring
Not all memories are equal. Rank by:
- **Recency**: When was this last accessed? (decay: `max(0, 1 - age_days / 30) * 0.3`)
- **Frequency**: How often is this accessed? (weight: `0.4`)
- **Confidence**: How certain are we this is correct? (weight: `0.3`)
- **Activation score** = (recency * 0.3) + (frequency * 0.4) + (confidence * 0.3)

High-activation memories get priority in context loading. Low-activation memories get flagged for decay or archival.

---

## 8. SESSION END PROTOCOL (MANDATORY)

Before any session ends, this MUST happen:

### Step 1: State Sync
- Update `brain/STATE.md` with current confidence, focus, known issues

### Step 2: Task Sync
- Update `memory/ACTIVE_TASKS.md` — move completed items, add new ones

### Step 3: Session Log
- Append to `memory/SESSION_LOG.md` — 3-5 line summary (Date, Goal, Done, Issues, Next)

### Step 4: Learning Capture
- If new patterns/mistakes discovered → update respective files
- If new reflection generated → append to SELF_REFLECTIONS.md

### Step 5: Supabase Sync
- Update agent_state table
- Insert session_logs entry
- Insert any new memories/growth entries
- Flush pending traces

### Step 6: Git Commit
- Stage brain/ and memory/ changes
- Commit with format: `bravo: sync — session YYYY-MM-DD summary`
- Ask CC if ready to push

### Step 7: Integrity Verification
Before committing, verify system integrity:
- **Referential integrity**: If any files were deleted/renamed, grep for stale references
- **Count accuracy**: If agents/skills/workflows changed, verify CAPABILITIES.md counts match reality
- **Config sync**: If MCP configs changed, verify .vscode/mcp.json and .gemini/settings.json match

### Step 8: Confirmation
- State to CC: **"Memory synced. [X] files updated, [Y] traces logged, [Z] new learnings captured. Integrity: verified."**

---

## 9. SECURITY CONSTRAINTS

### What NEVER Gets Logged
- API keys, tokens, passwords, secrets
- Full request/response bodies containing user data
- Supabase connection strings
- `.env.agents` contents
- Personal financial details (amounts OK, account numbers NEVER)

### What Gets Sanitized Before Logging
- Tool call parameters containing URLs (log domain only)
- Database query results (log row counts, not row contents)
- File contents (log file name and line count, not full content)

### Credential Handling
- All credentials read from `.env.agents` at runtime
- Never stored in memory files, Supabase, or git
- If a credential appears in a log, immediately flag and redact

---

## 10. COMPLIANCE VERIFICATION

### How to Know This Protocol Is Working
The agent should be able to answer these questions at any time:

1. **What did I do in my last session?** → Query `session_logs` or read `SESSION_LOG.md`
2. **What mistakes have I made?** → Query `memories` where category='mistake'
3. **What patterns have I learned?** → Query `memories` where category='pattern'
4. **What is my current state?** → Read `brain/STATE.md` or query `agent_state`
5. **How has my capability grown?** → Query `growth_log` over time
6. **What SOPs have I created?** → Query `sops` table or read `SOP_LIBRARY.md`
7. **What self-modifications have I made?** → Query `self_modification_log`

If any of these questions can't be answered, the protocol has a gap that needs fixing.
