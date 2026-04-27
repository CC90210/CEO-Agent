---
name: n8n-mcp-integration
description: Utilize the n8n-mcp community package (REST API) to list, search, execute, and manage n8n workflows.
triggers: [n8n MCP, n8n API, workflow list, workflow execute, n8n REST]
tier: specialized
dependencies: [mcp-operations]
---

# Instructions

You have access to an `n8n-mcp` server integrated via the community `n8n-mcp` npm package using n8n's REST API. This gives full access to ALL workflows (not just MCP-trigger workflows).

## MCP Connection

- **MCP Server Name:** `n8n-mcp`
- **Package:** `n8n-mcp` (npm, community)
- **Transport:** stdio (via `cmd /c "set N8N_API_URL=...&& set N8N_API_KEY=...&& npx -y n8n-mcp"`)
- **Instance URL:** `https://n8n.srv993801.hstgr.cloud`
- **Auth:** REST API key (JWT with `public-api` audience) set via `N8N_API_KEY` env var
- **Credential source:** `.env.agents` → `N8N_API_KEY`

## Available MCP Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `search_workflows` | List/search all workflows | "List my workflows", "Find workflow X", "Show active workflows" |
| `get_workflow_details` | Get full workflow config (nodes, triggers, connections) | Before executing, for debugging, for understanding a workflow |
| `execute_workflow` | Run a workflow by ID | "Run the email automation", "Execute workflow X" |

## Tool Usage Patterns

### List All Workflows
```
search_workflows(limit=200)
```

### Search by Name
```
search_workflows(query="email")
```

### Execute a Workflow
Always call `get_workflow_details` first to understand input schema:
```
get_workflow_details(workflowId="1cGIN32alM8sf8OV")
# Then:
execute_workflow(workflowId="1cGIN32alM8sf8OV", inputs={...})
```

## Active Workflows (as of 2026-03-02)

| ID | Name | Status |
|----|------|--------|
| 1cGIN32alM8sf8OV | OASIS Email Automation | Active |
| 4t5VjmsByTfRCeu0 | OasisAI Website bot | Active |
| BzWIRlWeQEvPTnrq0KWo_ | Bravo | Active |
| GfTyojYcq9hnJUHm | Oasis Content Agent LinkedIn | Active |
| NdiNBgHOPOxSP4Y2LeJqf | PropFlow Automations | Active |
| P5sRAFEeO4fQxYll | Invoice Automation | Active |
| YfozmGzasm2CUJgD | Shopify Automation | Active |
| ZxjYvh351CXcSbel | Oasis Content Agent X | Active |
| c5QBEQTNpbNU6UmB | Personal Booking Agent | Active |
| iRkiltEX9JMsg2BQ | Oasis Voice Agent | Active |
| wfAZrrZ6j744QPcr-dGXk | GrapeVine Cottage Automations | Active |

**Total: 44 workflows (11 active, 33 inactive)**

## Operating Principles

1. **Read before executing**: Always call `get_workflow_details` before `execute_workflow`.
2. **Error handling**: Every workflow should have error handling nodes. Check before building new ones.
3. **Webhook triggers**: Use webhook triggers for integrations.
4. **Document changes**: Log workflow modifications in `memory/SESSION_LOG.md`.
5. **Never hallucinate**: Don't guess node names or structures — read the actual workflow first.

## Fallback: Direct REST API

If the MCP server lacks a capability, use curl with the API key:
```bash
curl -H "X-N8N-API-KEY: $N8N_API_KEY" "https://n8n.srv993801.hstgr.cloud/api/v1/workflows"
```

Key REST endpoints:
- `GET /api/v1/workflows` — List all workflows
- `GET /api/v1/workflows/{id}` — Get workflow details
- `POST /api/v1/workflows/{id}/activate` — Activate a workflow
- `POST /api/v1/workflows/{id}/deactivate` — Deactivate a workflow
- `GET /api/v1/executions` — List recent executions

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
