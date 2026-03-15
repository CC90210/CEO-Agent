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
   - `mcp_n8n-mcp_n8n_list_workflows` (limit=1)
   - `mcp_late_posts_list` (limit=1)
   - `mcp_memory_search_nodes` (query="bravo")

4. Report to CC in this format:
   ```
   ## Status — [date]
   **North Star:** $X / $1,000 Net MRR
   **Active Tasks:** [count] — [top 3 tasks]
   **MCP Health:** [X/6 servers responding]
   **Known Issues:** [any blockers]
   ```
