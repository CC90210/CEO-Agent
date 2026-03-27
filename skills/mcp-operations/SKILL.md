---
name: mcp-operations
description: Tool routing guide — CLI-first for credential services, MCP for stateless tools. Single source of truth for all agents.
triggers: [tool routing, Late, n8n, Supabase, Stripe, MCP, tool failure]
tier: core
dependencies: []
---

# Tool Operations Guide (CLI-First Architecture)

> **For:** All agents (Claude Code, Gemini CLI, Anti-Gravity, Telegram bridge)
> **Rule:** When a user query matches a tool, USE IT. Never describe what you would do — do it.
> **Architecture (2026-03-22):** Stateless MCPs work reliably. Credential-dependent MCPs break. Use CLI tools for anything requiring API keys.

## Quick Routing Table

### Working MCP Servers (stateless — use directly)

| User Intent | MCP Server | Tool | Example |
|---|---|---|---|
| Browse web / take screenshot | **Playwright** | `browser_navigate`, `browser_snapshot` | "Go to this URL" |
| Look up library docs | **Context7** | `resolve-library-id`, `query-docs` | "How does Next.js routing work?" |
| Search/store knowledge | **Memory** | `search_nodes`, `create_entities` | "What do you know about X?" |
| Complex reasoning | **Sequential Thinking** | `sequentialthinking` | Multi-step analysis |

### CLI Tools (credential-dependent — more reliable than MCPs)

| User Intent | CLI Tool | Command | Example |
|---|---|---|---|
| n8n workflows | `python scripts/n8n_tool.py` | `list`, `get <id>`, `execute <id>`, `activate/deactivate <id>` | "List my workflows" |
| Social media posts | `python scripts/late_tool.py` | `accounts`, `posts`, `create --text "..." --account <id>`, `cross-post` | "Post this to X" |
| Database queries | `python scripts/supabase_tool.py` | `select <table>`, `insert`, `update`, `delete`, `sql "..."` | "Show my tables" |
| Payments / billing | `python scripts/stripe_tool.py` | `balance`, `customers`, `invoices`, `products`, `subscriptions` | "Check my Stripe balance" |
| Email / Calendar | `gws` CLI | `gws gmail users messages list`, `gws calendar events list` (REST-style syntax, use --params for filters) | "Check my email" |
| Website-to-CLI | OpenCLI | `opencli explore <url>`, `opencli <platform> <cmd>` | "What's trending?" |

**Why CLI-first:** MCP servers requiring credentials (Supabase, n8n, Stripe, Late) consistently fail due to env var passing issues on Windows, token expiry, and package auth changes. CLI tools read `.env.agents` directly — they never break.

---

## MCP Server Details

### Playwright (Browser Automation)
**Package:** `@playwright/mcp@latest` (headless)
**Status:** WORKING

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Go to URL |
| `browser_snapshot` | Accessibility tree (use for interactions) |
| `browser_take_screenshot` | Visual capture (use for evidence) |
| `browser_click` | Click element by ref |
| `browser_type` | Type into field |
| `browser_evaluate` | Run JavaScript |
| `browser_fill_form` | Fill multiple fields |

**Pattern:** Always `browser_snapshot` before interacting. Re-snapshot after navigation/DOM changes.

### Context7 (Library Docs)
**Package:** `@upstash/context7-mcp@latest`
**Status:** WORKING

| Tool | Purpose |
|------|---------|
| `resolve-library-id` | Find library ID (MUST call first) |
| `query-docs` | Get docs/code examples |

**Pattern:** Always resolve library ID before querying. Max 3 calls per question.

### Memory (Knowledge Graph)
**Package:** `@modelcontextprotocol/server-memory`
**Status:** WORKING

| Tool | Purpose |
|------|---------|
| `search_nodes` | Search entities |
| `create_entities` | Add entities |
| `create_relations` | Link entities |
| `add_observations` | Add facts |
| `open_nodes` | Get specific entities |

### Sequential Thinking
**Package:** `@modelcontextprotocol/server-sequential-thinking`
**Status:** WORKING

| Tool | Purpose |
|------|---------|
| `sequentialthinking` | Structured step-by-step reasoning |

---

## CLI Tool Details

### n8n (Workflow Automation)
**Script:** `python scripts/n8n_tool.py`
**Instance:** https://n8n.srv993801.hstgr.cloud (Hostinger VPS)
**Inventory:** 47 workflows, 10 active
**Credentials:** `N8N_API_URL` + `N8N_API_KEY` from `.env.agents`

| Command | Purpose |
|---------|---------|
| `list [--active] [--limit N]` | List workflows |
| `get <id>` | Full workflow details |
| `execute <id> [--data '{}']` | Run a workflow |
| `activate <id>` / `deactivate <id>` | Toggle workflow |
| `executions [--workflow-id <id>]` | View execution history |
| `export <id>` / `import <file>` | Backup/restore |

All commands support `--json` flag for agent consumption.

### Late (Social Media)
**Script:** `python scripts/late_tool.py`
**Credentials:** `LATE_API_KEY` from `.env.agents`
**Connected:** 8 accounts (Facebook, Google Business, Instagram, LinkedIn, Threads, TikTok, Twitter, YouTube)

| Command | Purpose |
|---------|---------|
| `accounts` | List connected accounts |
| `profiles` | List profiles |
| `posts [--status draft\|scheduled\|published\|failed]` | List posts |
| `create --text "..." --account <id> [--schedule ISO8601]` | Create post |
| `cross-post --text "..." --profile <id>` | Multi-platform post |
| `delete <post_id>` | Delete post |
| `publish <post_id>` | Publish now |
| `failed` / `retry <id>` / `retry-all` | Failed post management |

**Platform Limits:** X=280 | Threads=500 | IG=2200 | LinkedIn=3000 | TikTok=4000
Always validate character count BEFORE posting.

### Supabase (Database)
**Script:** `python scripts/supabase_tool.py`
**Credentials:** `SUPABASE_ACCESS_TOKEN`, project-specific URLs + keys from `.env.agents`

| Command | Purpose |
|---------|---------|
| `select <table> [--project bravo] [--limit 10]` | Query rows |
| `insert <table> --data '{}'` | Insert row |
| `update <table> --match '{}' --data '{}'` | Update rows |
| `delete <table> --match '{}'` | Delete rows |
| `sql "SELECT ..."` | Raw SQL |
| `tables` | List tables |

**Projects:** bravo (`phctllmtsogkovoilwos`), nostalgic-requests (`jqybbrtzpvmefgzzdagz`), oasis-ai-platform (`sajanpiqysuwviucycjh`)

### Stripe (Payments)
**Script:** `python scripts/stripe_tool.py`
**Credentials:** Stripe API key from `.env.agents`
**Note:** Stripe MCP (v0.3.1) switched to OAuth proxy mode — permanently broken. CLI tool is the only option.

| Command | Purpose |
|---------|---------|
| `balance` | Current balance |
| `customers [--limit N]` | List customers |
| `invoices [--limit N]` | List invoices |
| `products` | List products |
| `subscriptions [--status active]` | List subscriptions |

All commands support `--json` flag.

---

## Config Locations

| File | Used By | Servers |
|------|---------|---------|
| `.claude/mcp.json` | Claude Code CLI | 4 stateless MCPs |
| `.vscode/mcp.json` | Anti-Gravity IDE | 4 stateless MCPs |
| `~/.gemini/settings.json` | Gemini CLI | 4 stateless MCPs |
| `.env.agents` | CLI tools | All credentials |

All 3 MCP configs are identical (4 servers: Playwright, Context7, Memory, Sequential Thinking).
Credential-dependent services use CLI tools that read `.env.agents` directly.

## ANTI-PATTERNS (NEVER DO THESE)

1. **Never try broken MCPs.** Supabase, n8n, Stripe, and Late MCPs are removed. Use CLI tools.
2. **Never generate audit reports.** CC asks "how many workflows?" → answer is "47". One sentence.
3. **Never dump brain/state files as output.** Boot sequence is internal context.
4. **Never curl when a CLI tool exists.** CLI tools handle auth, error handling, and JSON output.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| CLI tool "not found" | Wrong Python path | Use `python scripts/<tool>.py` from project root |
| "API key not found" | Missing from .env.agents | Add the key to `.env.agents` |
| Supabase "Unauthorized" | Token expired (30-day) | Regenerate at supabase.com, update `.env.agents` |
| Playwright "browser in use" | Already open | Not an error — reuse existing session |
| MCP server hangs | Server crash on init | Restart terminal |
