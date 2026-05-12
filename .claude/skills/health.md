---
name: health
description: Full system health check — MCP servers, git status, memory freshness, credential validation, workspace cleanliness. Quick diagnostic of everything.
user-invocable: true
---

# /health — System Health Check

## Checks (run all in parallel where possible)

### Infrastructure
- [ ] MCP servers responding (test one call per server)
- [ ] Git status clean (no unexpected uncommitted changes)
- [ ] `.env.agents` exists and has expected keys (by name, never print values)
- [ ] No junk files in root (PNGs, temp files, test outputs)
- [ ] `tmp/` directory exists for sandboxed operations

### Memory Health
- [ ] `brain/STATE.md` — last updated within 24 hours?
- [ ] `memory/SESSION_LOG.md` — under 200 lines? Last entry recent?
- [ ] `memory/ACTIVE_TASKS.md` — under 50 items? No stale tasks?
- [ ] `memory/MISTAKES.md` — under 30 entries? No duplicates?

### Cross-AI Sync
- [ ] CLAUDE.md root matches `.agents/rules/CLAUDE.md`
- [ ] GEMINI.md root matches `.agents/rules/gemini.md` and `.gemini/rules/GEMINI.md`
- [ ] ANTIGRAVITY.md root matches `.agents/rules/antigravity.md`

### Report Format
```
System Health: [GREEN / YELLOW / RED]
MCP: [X/8 servers OK]
Memory: [fresh / stale (N days)]
Workspace: [clean / N issues]
Sync: [aligned / N files out of sync]
```

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
