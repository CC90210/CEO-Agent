---
name: prime
description: Load full project context, run health checks, and report operational status. Use when starting a new session or when CC asks for system status.
user-invocable: true
---

# /prime — Full Context Load & Health Report

## Steps

1. Read core brain files for context:
   - `brain/SOUL.md` — Identity and values
   - `brain/STATE.md` — Current operational state
   - `brain/USER.md` — CC's profile and goals
   - `memory/ACTIVE_TASKS.md` — Current task queue

2. Run health checks:
   - Verify MCP servers are responsive (attempt one call per server)
   - Check `git status` for uncommitted changes
   - Verify `.env.agents` exists and has content
   - Check for stale memory files (SESSION_LOG.md last entry > 7 days)

3. Report to CC:
   - Current state summary (1-2 sentences)
   - Active tasks count and top priority
   - MCP health (all green / which failed)
   - Any warnings (stale memory, uncommitted changes, expired tokens)

Keep the report under 15 lines. No walls of text.

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
