---
tags: [mistakes, prevention]
---
# MISTAKES LOG
> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[memory/SELF_REFLECTIONS]]

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
