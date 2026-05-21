---
name: n8n-patterns
description: Design-pattern reference for n8n workflows — error handling, idempotency, retry shape, common pipeline templates. Pairs with n8n-mcp-integration (which handles HOW to build via SDK). This skill answers WHAT shape a workflow should take.
triggers: [n8n pattern, workflow design, webhook intake, AI pipeline, error handling pattern, retry pattern, idempotency, scheduled monitoring]
tier: standard
dependencies: [n8n-mcp-integration]
---

# N8N Workflow Engineering — Design Patterns

> **For HOW to build:** see `skills/n8n-mcp-integration` — code-first SDK flow (`get_sdk_reference` → `search_nodes` → `get_node_types` → `validate_workflow` → `create_workflow_from_code`). This skill is the design-pattern companion: error shapes, retry templates, idempotency, common pipelines.

## Workflow Design Principles

1. **Error-first design.** Every workflow starts with an Error Trigger node connected to a notification (Slack/Email/SMS).
2. **Idempotent operations.** Every workflow should be safe to re-run without duplicate effects.
3. **Clear naming.** Nodes are named by function: "Fetch Lead from ClearBit" not "HTTP Request 3".
4. **Sticky notes.** Every workflow has a Start sticky explaining purpose, trigger, and expected behavior.
5. **Credential isolation.** Use n8n's credential store. Never hardcode keys in nodes.

## Core Patterns

### Pattern: Webhook Intake Pipeline
```
Webhook → Validate Input → Process/Transform → Store (Supabase) → Respond 200
                                                    ↓
                                              Notify (Slack/Email)
```
Use for: Form submissions, API integrations, external triggers.

### Pattern: AI Processing Pipeline  
```
Trigger → Fetch Context → Build Prompt → LLM Call (with retry) → Parse Response → Store/Send
                                              ↓ (on failure)
                                        Fallback Response
```
Use for: Chatbots, content generation, classification, extraction.

### Pattern: Lead Enrichment Pipeline
```
New Lead Trigger → Validate Email → ClearBit/Apollo Lookup → AI Score Lead → Update CRM → Notify Sales
                                          ↓ (not found)
                                    Manual Review Queue
```
Use for: Lead qualification, CRM enrichment, sales automation.

### Pattern: Scheduled Monitoring
```
Cron (every X minutes) → Fetch Current State → Compare to Expected → Branch: OK/Alert → Notify if Alert
```
Use for: Uptime monitoring, stock alerts, competitor tracking, SLA monitoring.

### Pattern: Multi-Channel Support Bot
```
Webhook (from any channel) → Identify Channel → RAG Lookup → AI Generate Response → Route to Channel API → Log Interaction
                                                                                            ↓
                                                                                    Update Analytics
```
Use for: Customer support across web chat, SMS, email, WhatsApp.

## Node Configuration Standards

### HTTP Request Nodes
- Always set timeout (30s default)
- Enable "Continue on Fail" where appropriate
- Add retry logic: 3 attempts, 1000ms backoff
- Set proper Content-Type headers

### AI/LLM Nodes
- Use the AI Agent node for complex tasks
- Include system prompt in every call
- Set temperature based on use case (0.1 for factual, 0.7 for creative)
- Always parse and validate LLM output before using downstream
- Include fallback for malformed responses

### Database Nodes (Supabase)
- Use parameterized queries (never string concatenation)
- Handle "no rows returned" gracefully
- Include created_at/updated_at timestamps on all inserts
- Use upsert when appropriate to prevent duplicates

### Error Handling
- Every workflow has an Error Trigger → Notification path
- Critical workflows send to both Slack and Email
- Include the workflow name, node that failed, and error message in notifications
- Log errors to a Supabase `error_log` table for trending

## Workflow Code Structure (SDK, not JSON)

**Don't hand-roll JSON.** The n8n-mcp SDK exposes a TypeScript-style code builder. Get the current syntax from:

```
get_sdk_reference()
get_sdk_reference(sections=["guidelines", "design"])
```

Always pull exact parameter shapes from `get_node_types(nodeIds=[...])` before writing code — node parameter shapes change between n8n versions, and guessing is the #1 cause of invalid workflows. Validate with `validate_workflow(code=...)` until clean, then deploy with `create_workflow_from_code(code=..., description=...)`.

If you find yourself building JSON by hand, stop and re-read [[skills/n8n-mcp-integration]].

## Testing Checklist
- [ ] `validate_workflow` returns clean (no errors, no warnings you can't justify)
- [ ] Trigger fires correctly (use `prepare_test_pin_data` for pinned-input dry runs)
- [ ] Each node processes expected data format
- [ ] Error paths trigger on actual errors (force a failure, verify notification fires)
- [ ] Retry logic works (test with temporary failure)
- [ ] Output matches expected format
- [ ] No hardcoded credentials — every secret references an n8n credential name
- [ ] Monitoring/alerting is in place
- [ ] Workflow has a Start sticky note: purpose, trigger, owner

## Obsidian Links
- [[skills/n8n-mcp-integration]] | [[brain/CAPABILITIES]] | [[skills/INDEX.md]] | [[brain/DASHBOARD]]
