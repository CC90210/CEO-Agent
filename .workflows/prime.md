---
description: Load full project context — brain, memory, capabilities, and current state
---
// turbo-all

## Steps

1. Read (silently, do NOT dump to CC) these files in parallel:
   - `brain/SOUL.md` — Identity and values
   - `brain/STATE.md` — Current operational state
   - `brain/CAPABILITIES.md` — Tool and integration registry
   - `brain/AGENTS.md` — Subagent registry and routing
   - `memory/ACTIVE_TASKS.md` — Pending work

2. Load knowledge graph context:
   - `mcp_memory_search_nodes` (query="bravo project status")

3. Check git status:
   - Run `git status --short` and `git log -3 --oneline`

4. Report to CC in this format:
   ```
   Primed. Context loaded:
   - State: [energy level] — [focus area]
   - Tasks: [count] active, [count] blocked
   - Git: [branch] — [last commit summary]
   - Memory: [entity count] entities in knowledge graph
   Ready for commands.
   ```
