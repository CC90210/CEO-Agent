---
description: Search, inspect, and manage n8n workflows via MCP
---
// turbo-all

## Steps

1. Search for workflows:
   - `mcp_n8n-mcp_search_workflows` with optional `query` filter and `limit=200`

2. If CC asks about a specific workflow:
   - `mcp_n8n-mcp_get_workflow_details` with the workflow ID

3. If CC wants to run a workflow:
   - `mcp_n8n-mcp_execute_workflow` with workflow ID and any required inputs
   - Check the workflow description first for input schema

4. Report results to CC. If the n8n server returns 0 workflows but should have 44+:
   - Report: "n8n-mcp returned 0 workflows. The n8n instance at https://n8n.srv993801.hstgr.cloud may need restarting, or the API key may need regenerating."
   - Do NOT attempt workarounds.
