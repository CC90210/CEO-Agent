---
name: n8n-mcp-integration
description: Build, validate, and deploy n8n workflows through the n8n-mcp server using the TypeScript-SDK code-first flow. Replaces hand-rolled JSON. Use whenever an automation, workflow, webhook intake, scheduled job, or integration pipeline needs to ship.
triggers: [n8n, n8n MCP, build workflow, automation, webhook intake, scheduled job, n8n SDK, create_workflow_from_code, validate_workflow]
tier: standard
dependencies: [n8n-patterns]
disable-model-invocation: false
---

# n8n MCP — Code-First SDK Flow (V6.7)

> The n8n-mcp server (community package, REST-API-backed) exposes a TypeScript-style SDK. You write workflow code, the MCP validates it, then `create_workflow_from_code` ships it directly to the n8n instance. No more hand-rolling JSON, no more guessing parameter names, no more drift between docs and runtime.

## When to use this skill vs `scripts/integrations/n8n_tool.py`

| Task | Tool |
|------|------|
| **Build / update a workflow** | This skill (n8n-mcp SDK flow) |
| **List, search, inspect existing workflows** | This skill (`search_workflows`, `get_workflow_details`) |
| **Execute a workflow with inputs** | This skill (`execute_workflow`) |
| **Quick CLI-only ops in a script (cron, agent_inbox, etc.)** | `scripts/integrations/n8n_tool.py` |
| **Bulk listing or JSON dump for piping** | `scripts/integrations/n8n_tool.py` (returns `--json`) |

**Default: build and modify through MCP. Read and execute through either.** CLI exists as the always-works fallback per CLAUDE.md Rule 2.

## Connection

- **MCP Server Name:** `n8n-mcp`
- **Package:** `n8n-mcp` (community npm)
- **Instance URL:** `https://n8n.srv993801.hstgr.cloud`
- **Auth:** REST API key set via `N8N_API_KEY` (sourced from `.env.agents`)
- **Backed by:** n8n REST API — covers ALL workflows, not just MCP-trigger ones

## Templates First (always check before building)

The community package ships with ~2,350 community templates indexed for search. **Before building from scratch**, run:

```
search_templates(query="<intent>")     # e.g. "lead enrichment", "stripe webhook"
get_template(templateId="<id>")        # full template definition
```

If a template covers ~70%+ of the brief, fork it via `create_workflow_from_code` (after pulling it through the SDK) and modify. The template gives you a known-valid starting point — fewer validation cycles, fewer hallucinated parameters. Reach for this BEFORE the build flow below.

## The SDK Flow (canonical, in order)

When no template fits, this is the only blessed path. **Skipping a step produces invalid workflows.**

```
1. get_sdk_reference        → Learn current SDK syntax + design rules
2. search_nodes             → Find the right nodes (Gmail, Schedule Trigger, etc.)
3. (optional) get_suggested_nodes → Curated picks for technique categories
4. get_node_types           → Get EXACT TypeScript parameter definitions for each node
5. write workflow code      → Use SDK patterns + exact param names from step 4
6. validate_workflow        → Iterate until valid (loop, don't ship invalid)
7. create_workflow_from_code → Deploy with a 1-2 sentence description
   OR update_workflow       → Modify existing workflow by ID
```

### Step 1 — Read the SDK reference (always first)

```
get_sdk_reference()
# Or with sections:
get_sdk_reference(sections=["guidelines", "design"])
```

This returns the current SDK conventions. **n8n updates this — don't cache it in your head.**

### Step 2 — Discover nodes by intent

```
search_nodes(queries=["gmail send", "schedule trigger", "supabase insert"])
search_nodes(queries=["set", "if", "merge", "code"])  # utility nodes
```

Note the **discriminators** (resource / operation / mode) returned in results — you need these for step 4.

### Step 3 — Get exact parameter definitions

**Mandatory.** Guessing parameter names creates invalid workflows.

```
get_node_types(nodeIds=["n8n-nodes-base.gmail", "n8n-nodes-base.scheduleTrigger", ...])
```

Pass EVERY node ID you plan to use, including discriminators from search results.

### Step 4 — Write the workflow code

Use the patterns from `get_sdk_reference` (step 1) and the exact parameter shapes from `get_node_types` (step 3). Cover the design guidelines section — it documents idempotency, error handling, and connection rules.

### Step 5 — Validate, loop until clean

```
validate_workflow(code=<your code>)
```

Returns errors with line/parameter-level detail. **Fix → re-validate → repeat.** Do not call `create_workflow_from_code` with anything other than a clean validation result.

### Step 6 — Deploy

```
create_workflow_from_code(
  code=<validated code>,
  description="<1-2 sentences — what does this workflow do, what triggers it>"
)
```

For updates:
```
update_workflow(workflowId="<id>", code=<validated code>)
```

To pause:
```
unpublish_workflow(workflowId="<id>")
```

To remove:
```
archive_workflow(workflowId="<id>")
```

## Read & Execute Operations (no SDK needed)

These don't require the build flow — call them directly:

| Tool | Use |
|------|-----|
| `search_workflows(query, limit=200)` | List or search workflows |
| `get_workflow_details(workflowId)` | Full config: nodes, triggers, connections |
| `execute_workflow(workflowId, inputs)` | Run a workflow with input payload |
| `get_execution(executionId)` | Inspect a past run |
| `prepare_test_pin_data(workflowId)` | Generate pinned test data for a node |
| `test_workflow(code)` | Dry-run validated code without persisting |
| `search_templates(query)` | Search ~2,350 community templates by intent |
| `get_template(templateId)` | Pull a full template — fork it instead of building blank |
| `validate_node(...)` | Validate a single node config in isolation (faster than full validate) |

## Active Workflows (refresh via `search_workflows` — this list ages fast)

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

## Operating Principles

1. **Read before executing.** `get_workflow_details` before `execute_workflow`.
2. **Validate before deploying.** Never call `create_workflow_from_code` on un-validated code.
3. **One workflow per concern.** Don't bundle unrelated logic — orchestration belongs in a parent workflow.
4. **Sticky note on start.** Purpose, trigger, expected behavior, owner.
5. **Error handling is non-negotiable.** Every workflow has an Error Trigger path. See `n8n-patterns` for the exact shape.
6. **Idempotency on writes.** Check event/record IDs before inserts. Webhook retries are a fact of life.
7. **Credentials by name, never by value.** Reference n8n credential names; never paste keys.
8. **Document on deploy.** Append to `APPS_CONTEXT/OASIS_WORKFLOWS.md`. Log a 1-line note in `memory/SESSION_LOG.md`.

## Failure Recovery

| Failure | Action |
|---------|--------|
| `validate_workflow` rejects code 3+ times | Re-read `get_sdk_reference`. The SDK shape probably changed. |
| `get_node_types` returns nothing for a node | Re-run `search_nodes` with broader query — node ID was wrong. |
| MCP server unreachable | Fall back to `scripts/integrations/n8n_tool.py` for read/exec. Building blocked until MCP returns. |
| `create_workflow_from_code` succeeds but workflow won't activate | Open in n8n UI, check trigger node config. Often a missing credential binding. |

## What this replaces

- ❌ Hand-rolling JSON in `workflows/<name>.json` and importing through the UI (drift-prone, breaks on n8n version changes)
- ❌ Guessing node parameter names from memory (the #1 cause of invalid workflows)
- ❌ The "build JSON blob, push to git, hope" flow

The SDK flow is the n8n team's official answer to those failure modes. Use it.

## Obsidian Links
- [[skills/n8n-patterns]] | [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
- [[agents/workflow-builder]] | [[memory/SESSION_LOG]]
