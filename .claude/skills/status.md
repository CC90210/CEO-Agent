---
name: status
description: Quick status report — what's active, what's blocked, what shipped recently. Reads from memory files, never answers from LLM memory alone.
user-invocable: true
---

# /status — Quick Status Report

## Steps

1. **ALWAYS read these files first** (another AI may have done work):
   - `memory/SESSION_LOG.md` — recent activity across all agents
   - `memory/ACTIVE_TASKS.md` — current task queue
   - `brain/STATE.md` — operational state

2. Report:
   - **Last session:** When, which agent, what was done (1-2 sentences)
   - **Active tasks:** List in-progress and blocked items
   - **Recently completed:** Last 3-5 completed items
   - **North star progress:** Current MRR vs $10K target

3. Keep to under 10 lines. No walls of text.

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
