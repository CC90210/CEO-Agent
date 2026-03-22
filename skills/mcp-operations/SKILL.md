---
name: mcp-operations
description: Comprehensive MCP operations guide — routing, tool usage, troubleshooting. Single source of truth for all agents.
triggers: [MCP, tool routing, Late, n8n, Supabase MCP, tool failure, MCP config]
tier: core
dependencies: []
---

# MCP Operations Guide

> **For:** All agents (Claude Code, Gemini CLI, Anti-Gravity, Telegram bridge)
> **Rule:** When a user query matches an MCP tool, CALL THE TOOL FIRST. Never describe what you would do — do it.

## Quick Routing Table

| User Intent | MCP Server / Tool | Tool | Example |
|---|---|---|---|
| List/search/run n8n workflows | **n8n-mcp** | `search_workflows`, `execute_workflow` | "List my workflows" |
| Post/schedule social media | **Late** | `posts_create`, `posts_cross_post` | "Post this to X" |
| Query database / run SQL | **Supabase** | `execute_sql`, `list_tables` | "Show my tables" |
| Browse web / take screenshot | **Playwright** | `browser_navigate`, `browser_snapshot` | "Go to this URL" |
| Read from websites / trending / search platforms | **OpenCLI** | `opencli <platform> <cmd> --json` | "What's trending on Twitter?" |
| Discover website APIs | **OpenCLI** | `opencli explore <url>` | "Find APIs on this site" |
| Look up library docs | **Context7** | `resolve-library-id`, `query-docs` | "How does Next.js routing work?" |
| Search/store knowledge | **Memory** | `search_nodes`, `create_entities` | "What do you know about X?" |
| Complex reasoning | **Sequential Thinking** | `sequentialthinking` | Multi-step analysis |
| Payment/subscription info | **Stripe** | (see Stripe tools) | "Show my Stripe balance" |

---

## Server Details

### n8n-mcp (Workflow Automation)

**Package:** `n8n-mcp` (community npm — uses REST API)
**Config:** `cmd /c "set N8N_API_URL=https://n8n.srv993801.hstgr.cloud&& set N8N_API_KEY=<key>&& npx -y n8n-mcp"`
**Instance:** https://n8n.srv993801.hstgr.cloud (Hostinger VPS)
**Inventory:** 44 workflows, 11 active

| Tool | Purpose | Key Params |
|------|---------|------------|
| `search_workflows` | List/search workflows | `query` (optional), `limit` (max 200) |
| `get_workflow_details` | Full workflow config | `workflowId` (required) |
| `execute_workflow` | Run a workflow | `workflowId`, `inputs` (chat/form/webhook) |

**Pattern:** Always call `get_workflow_details` before `execute_workflow` to understand input schema.
**Fallback:** `curl -H "X-N8N-API-KEY: $N8N_API_KEY" https://n8n.srv993801.hstgr.cloud/api/v1/workflows`

---

### Late (Social Media)

**Package:** `late-sdk[mcp]` (via uvx)
**Config:** `bash -c "LATE_API_KEY=... uvx --from 'late-sdk[mcp]' late-mcp"` — inline env var with bash wrapper
**IMPORTANT:** The `env` block in MCP configs does NOT work on Windows for injecting env vars. Use `bash -c` with inline env vars instead. Applied to all 3 config files (2026-03-03).

| Tool | Purpose |
|------|---------|
| `posts_create` | Create/schedule a post |
| `posts_cross_post` | Same content → multiple platforms |
| `posts_list` | List posts (filter by status) |
| `posts_update` | Edit draft/scheduled post |
| `posts_delete` | Delete non-published post |
| `accounts_list` | List connected accounts |
| `profiles_list` | List profiles |
| `media_generate_upload_link` | Get upload URL for images/video |
| `media_check_upload_status` | Check upload completion |

**Platform Limits:** X=280 | Threads=500 | IG=2200 | LinkedIn=3000 | TikTok=4000
**Pattern:** Always validate character count per platform BEFORE posting. Use `posts_cross_post` for multi-platform.

---

### Supabase (Database)

**Package:** `@supabase/mcp-server-supabase@latest`
**Config:** `npx -y @supabase/mcp-server-supabase@latest --access-token <token>`
**Token:** Management API token (sbp_*), 30-day expiry

| Tool | Purpose |
|------|---------|
| `execute_sql` | Run raw SQL (SELECT, INSERT, UPDATE) |
| `list_tables` | List tables in schema(s) |
| `apply_migration` | DDL operations (CREATE TABLE, ALTER, etc.) |
| `list_projects` | List all projects |
| `get_project` | Project details |
| `list_migrations` | Migration history |
| `get_logs` | Service logs (last 24h) |
| `get_advisors` | Security/performance advisories |
| `generate_typescript_types` | TypeScript type generation |

**Projects:**
- Bravo: `phctllmtsogkovoilwos` (agent intelligence)
- nostalgic-requests: `jqybbrtzpvmefgzzdagz`
- oasis-ai-platform: `sajanpiqysuwviucycjh`

**Pattern:** Use `apply_migration` for DDL, `execute_sql` for DML. Always check `get_advisors(type="security")` after schema changes.

---

### Playwright (Browser)

**Package:** `@playwright/mcp@latest`
**Config:** `cmd /c "npx -y @playwright/mcp@latest --headless"`

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Go to URL |
| `browser_snapshot` | Accessibility snapshot (better than screenshot) |
| `browser_take_screenshot` | Visual screenshot |
| `browser_click` | Click element |
| `browser_type` | Type text |
| `browser_evaluate` | Run JavaScript |
| `browser_fill_form` | Fill multiple fields |

**Pattern:** Use `browser_snapshot` for reading page content, `browser_take_screenshot` for visual verification. Use for ALL web research — no Chrome extension available.

---

### Context7 (Library Docs)

**Package:** `@upstash/context7-mcp@latest`

| Tool | Purpose |
|------|---------|
| `resolve-library-id` | Find library ID (MUST call first) |
| `query-docs` | Get docs/code examples |

**Pattern:** Always resolve library ID before querying docs. Max 3 calls per question.

---

### Memory (Knowledge Graph)

**Package:** `@modelcontextprotocol/server-memory`

| Tool | Purpose |
|------|---------|
| `search_nodes` | Search entities by name/type/content |
| `create_entities` | Add new entities |
| `create_relations` | Link entities |
| `add_observations` | Add facts to entities |
| `open_nodes` | Get specific entities by name |

**Pattern:** Persistent across sessions. Use for cross-session context.

---

### Sequential Thinking

**Package:** `@modelcontextprotocol/server-sequential-thinking`

| Tool | Purpose |
|------|---------|
| `sequentialthinking` | Structured step-by-step reasoning |

**Pattern:** Use for MODERATE+ complexity tasks. Supports branching, revision, and hypothesis verification.

---

### Stripe (Payments)

**Package:** `@stripe/mcp@latest`
**Config:** `npx -y @stripe/mcp@latest --api-key=rk_live_*`
**Auth:** Restricted API key (rk_live_*). NEVER use secret key (sk_live_*) — causes 401.

---

## Config Locations (MUST Stay In Sync)

| File | Used By | Key Format |
|------|---------|------------|
| `.claude/mcp.json` | Claude Code CLI | `mcpServers` |
| `.vscode/mcp.json` | Anti-Gravity IDE | `servers` |
| `~/.gemini/settings.json` | Gemini CLI | `mcpServers` |
| `.env.agents` | Credentials only | `KEY=value` |

**SECURITY (2026-03-11): ALL 3 configs now use `cmd /c scripts/*-wrapper.cmd` for credential-sensitive servers (Supabase, n8n, Stripe, Late). ZERO hardcoded credentials in any config file. Credentials live ONLY in `.env.agents` (gitignored).**

**Wrapper pattern:** `cmd /c scripts/<server>-mcp-wrapper.cmd` — reads keys from `.env.agents` at runtime, sets env vars, then launches the MCP server. 4 wrappers: `supabase-mcp-wrapper.cmd`, `n8n-mcp-wrapper.cmd`, `stripe-mcp-wrapper.cmd`, `late-mcp-wrapper.cmd`. Non-credential servers (Playwright, Context7, Memory, Sequential Thinking) use direct `npx` — no wrapper needed.

## ANTI-PATTERNS (NEVER DO THESE)

1. **Never use curl/shell when an MCP tool exists.** If `search_workflows` is available, call it. Don't curl the API.
2. **Never generate audit reports.** CC asks "how many workflows?" → answer is "44". Not a 500-word verification report.
3. **Never create workaround scripts.** If MCP fails, report the error and stop. Don't write bypass code.
4. **Never dump brain/state files as output.** Boot sequence is internal context, not user-facing output.
5. **Never tell CC to restart unless they asked about infrastructure.** If tools work, answer the question.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "LATE_API_KEY required" | Env var not passing | Check `.env.agents` has `LATE_API_KEY=...`, restart terminal |
| "Unauthorized" (Supabase) | Token expired | Regenerate at supabase.com, update `SUPABASE_ACCESS_TOKEN` in `.env.agents` |
| n8n returns 0 workflows | Using native endpoint | Switch to community `n8n-mcp` package (already done) |
| MCP server hangs | Server crash during init | Fix the failing server, restart terminal |
| "Not Acceptable" (n8n) | Missing Accept headers | Use community package (handled automatically) |
| Tool returns error | Various | Report error in 1 sentence. Do NOT fall back to curl. |
