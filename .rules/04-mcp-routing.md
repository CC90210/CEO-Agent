---
description: Route queries to the correct MCP server tool
---

# MCP Tool Routing

| CC Asks About | MCP Server | Tools |
|---|---|---|
| n8n workflows | n8n-mcp | `search_workflows`, `get_workflow_details`, `execute_workflow` |
| Social posts | Late | `posts_create`, `posts_list`, `posts_cross_post`, `accounts_list` |
| Browse URL | Playwright | `browser_navigate`, `browser_snapshot`, `browser_click` |
| Library docs | Context7 | `resolve-library-id` then `query-docs` |
| Knowledge graph | Memory | `search_nodes`, `create_entities`, `open_nodes` |
| Database/SQL | Supabase | `execute_sql`, `list_tables`, `apply_migration` |
| Payments | Stripe | Stripe MCP tools |
| Complex reasoning | Sequential Thinking | `sequentialthinking` |

**8 MCP servers** configured in `.vscode/mcp.json`. Credential-sensitive servers use `cmd /c scripts/*-wrapper.cmd` pattern. Non-credential servers use direct `npx`.

**Platform character limits** (validate BEFORE posting): X=280 | Threads=500 | IG=2200 | LinkedIn=3000 | TikTok=4000
