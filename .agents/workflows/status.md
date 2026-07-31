---
description: Check project status — revenue, tasks, MCP health, and system state
---
// turbo-all

# Status Command

## What This Command Does
Quick snapshot of project state — revenue progress, active tasks, MCP health, and blockers.

## When to Use
Use `/status` for a fast overview without loading full context.

## How It Works / Steps

1. Read `brain/STATE.md` for current operational state (do NOT output raw contents — summarize).

2. Read `memory/ACTIVE_TASKS.md` for pending work.

3. Quick MCP health check — call one tool from each active server:
   - `mcp__n8n-mcp__search_workflows` (limit=1)
   - `mcp__late__posts_list` (limit=1)
   - `mcp__memory__search_nodes` (query="bravo")

4. Report to CC in this format:
   ```
   ## Status — [date]
   **North Star ($10K MRR by 2026-09-30):** Atlas-owned — status reports ops only
   **Active Tasks:** [count] — [top 3 tasks]
   **MCP Health:** [X/13 servers responding]
   **Known Issues:** [any blockers]
   ```

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
