---
tags: [mistakes, prevention]
---
# MISTAKES LOG
> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[memory/SELF_REFLECTIONS]]

### Capability Regression from Optimization (2026-04-06)
**Systemic failure:** After CLAUDE.md compression (386→119 lines), QUICK_REFERENCE.md only documented 11 of 47 CLI tools. Agent tried to use `claude.ai Gmail` MCP instead of `google_tool.py` CLI. Root causes: (1) GWS missing from CLI routing list, (2) QUICK_REFERENCE.md was 75% incomplete, (3) ANTIGRAVITY.md still referenced dead MCPs, (4) no regression prevention protocol existed. **Prevention:** Created `brain/ORCHESTRATION.md` — governance doc with regression prevention protocol, tool hierarchy, and stress test checklist. QUICK_REFERENCE.md rebuilt with all 47 tools organized by intent. Rule 2 in CLAUDE.md rewritten to say "NEVER ask CC to authenticate anything". All 3 entry points synchronized. **The iron law: optimizing documentation must NEVER reduce routing accuracy.**

### Day-of-Week Hallucination (2026-04-04)
Said "Friday" repeatedly when it was Saturday. Never assume or state the day of the week. The system provides the date (2026-04-04) but NOT the day name. If needed, compute it: `date +%A` or `python -c "from datetime import date; print(date.today().strftime('%A'))"`. Never guess temporal information.

### Zombie Python Daemon (2026-04-02)
Editing .py does NOT affect running process. Must kill+restart. Find zombies: `Get-Process python | Select Id,StartTime | Sort StartTime`. Kill: `(Get-WmiObject Win32_Process -Filter 'ProcessId=X').Terminate()`. Verify log timestamps stop updating.

### Vercel Shared Module Crash (2026-03-23)
Shared `api/_lib/*.ts` causes FUNCTION_INVOCATION_FAILED. Fix: inline `await import()` per handler. Diagnostic: create two minimal test endpoints first.

### Windows Watchdog Zombies (2026-03-23)
`os.kill(pid, 0)` unreliable on Windows. Use `tasklist`. Never use `/rl highest` in Task Scheduler. Use `CREATE_NO_WINDOW` for headless daemons.

### subprocess cp1252 UnicodeDecodeError (2026-03-19)
`text=True` defaults to cp1252 on Windows. Always add `encoding="utf-8"`.

### Stale Cross-References (2026-03-03)
After ANY file delete/rename: `grep -rn "filename" --include="*.md"` across full project.

### Platform-Specific (archived)
- Twitter: validate char limits BEFORE posting (X=280, Threads=500, IG=2200, LinkedIn=3000)
- `__future__` import must be first line. PowerShell: use `Out-File -Encoding utf8`
- Idempotency: scripts with external side effects MUST check sent flag before execution

*Last updated: 2026-04-03*
