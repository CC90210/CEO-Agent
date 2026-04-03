---
tags: [patterns, learning]
---
# LEARNED PATTERNS
> What works, what doesn't. Check this BEFORE starting a task type you've done before.
> `[VALIDATED]` = proven across 3+ sessions. `[PROBATIONARY]` = needs more evidence.

> [[brain/BRAIN_LOOP]] | [[memory/MISTAKES]] | [[memory/SOP_LIBRARY]]

## Effective Patterns

### [PROBATIONARY] 2026-04-02 — Python Daemon Change Deployment Protocol
**Observation:** Changing a Python daemon's source code requires a full restart cycle, not just a file save. Running processes keep old code in memory indefinitely.
**Pattern — The 5-Step Daemon Redeploy:**
1. EDIT: Make code changes to the .py file
2. KILL: Find and kill the running process (check by StartTime, not just CommandLine)
3. CLEAN: Delete __pycache__/*.pyc for the changed module
4. VERIFY DEAD: Confirm process is gone with `Get-Process -Id X` AND confirm log files stop updating (check timestamps 30s apart)
5. RESTART: Start new process, verify first cycle output matches expected behavior
**Critical Windows commands:**
- Find zombies: `Get-Process python | Select Id, StartTime, Path | Sort StartTime`
- Kill invisible processes: `(Get-WmiObject Win32_Process -Filter 'ProcessId=X').Terminate()`
- Verify log stopped: `stat -c '%Y' logfile; sleep 30; stat -c '%Y' logfile` (timestamps must match)
**Implication:** Every future daemon deployment (skool, scheduler, instagram, any background Python) must follow this 5-step protocol. Skipping step 4 (verify dead) caused 7 days of unwanted DMs.

### [PROBATIONARY] 2026-03-23 — Vercel Node v24 shared module crash
Importing npm packages from shared `api/_lib/*.ts` causes FUNCTION_INVOCATION_FAILED. Vercel's bundler traces all imports from shared files. Fix: inline `await import('package')` in each handler, never from shared modules.

### [PROBATIONARY] 2026-03-23 — Windows watchdog: use tasklist not os.kill
`os.kill(pid, 0)` unreliable on Windows. Use `tasklist`-based process detection. Use `CREATE_NO_WINDOW` for headless daemons. Never use `/rl highest` in Task Scheduler.

### Zernio (Late) API Posting `[VALIDATED]`
Validate char limits → rewrite per platform (X=280, Threads=500, IG=2200, LinkedIn=3000) → present to CC → post via Zernio CLI (late_tool.py) → log.

### Multi-Agent Routing `[VALIDATED]`
Simple tasks → Gemini. Multi-file architecture → Claude Code. Research → Anti-Gravity. Content → any agent.

### Query-First MCP Routing `[VALIDATED]`
User asks a question → identify topic → map to tool → call IMMEDIATELY → return real data. Never describe what you'd do — do it.

### Cross-File Sync `[VALIDATED]`
When changing ANY config/structure file, update ALL referencing files. After file delete/rename: `grep -rn "filename" --include="*.md"` → fix every hit.

### MCP Error Recovery `[VALIDATED]`
Report exact error → check if auth or schema → suggest fix → STOP. Never retry in loop. Never create bypass scripts.

### Outreach Names `[VALIDATED]`
B2B/professional → "Conaugh McKenna". DJ/entertainment → "CC". Google Meet link is NOT a booking/calendar link — never say "schedule" or "grab a time slot" with it.

### Multi-Hypothesis `[PROBATIONARY]`
Generate 2-3 approaches → rank → execute best → on failure switch to next → after 3 total attempts, STOP and report.

### Anti-Bloat `[VALIDATED]`
Update existing files, don't create new ones unless strictly required. Lean brain = faster + more accurate.

## Anti-Patterns (NEVER Do These)

- **Bypass scripts on MCP failure** — Report error, suggest fix, STOP. Don't write direct API scripts.
- **PowerShell `>` redirect** — Outputs UTF-16LE. Use `Out-File -Encoding utf8` or filesystem tools.
- **Same content across platforms** — Rewrite per platform. Same message, different delivery.
- **Guessing APIs without Context7** — Always verify current API before writing code.
- **Deleting files without scanning refs** — `grep -rn "filename"` after EVERY delete/rename.
- **Hardcoding counts in docs** — Verify actual file counts match documented counts on commit.

*Last updated: 2026-04-02*
