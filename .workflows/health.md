---
description: Full system health diagnostic — test all MCP servers, check configs, verify file integrity
---
// turbo-all

# Health Command

## What This Command Does
Tests every MCP server, verifies config file integrity, checks brain files for staleness, and auto-fixes broken configs.

## When to Use
Use `/health` at session start, after IDE restarts, or when something feels broken.

## How It Works / Steps

1. **Test every ACTIVE MCP server** by calling one tool each:
   - n8n-mcp: `mcp_n8n-mcp_n8n_list_workflows` (limit=1)
   - Late: `mcp_late_accounts_list`
   - Playwright: `mcp_playwright_browser_snapshot` (if page open, otherwise skip)
   - Context7: `mcp_context7_resolve-library-id` (libraryName="react", query="test")
   - Memory: `mcp_memory_search_nodes` (query="bravo")
   - Sequential Thinking: `mcp_sequential-thinking_sequentialthinking` (simple thought)

2. **Check config sync** — verify these files exist and have matching server configs:
   - `.vscode/mcp.json` (Antigravity IDE)
   - `.gemini/settings.json` (Gemini CLI)

3. **Check brain files** — verify these exist and aren't stale (>7 days since last update):
   - `brain/STATE.md`
   - `brain/SOUL.md`
   - `brain/CAPABILITIES.md`
   - `brain/AGENTS.md`
   - `memory/ACTIVE_TASKS.md`

4. **Report results** in a table:
   ```
   | Server | Status | Response |
   |--------|--------|----------|
   | n8n    | ✅/❌  | [detail] |
   | Late   | ✅/❌  | [detail] |
   | ...    | ...    | ...      |
   ```

5. If any server is broken, **fix it** (update the config file directly). Do NOT just report it.
