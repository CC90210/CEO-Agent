---
name: n8n-patterns
description: Use this skill whenever the user wants to build an N8N workflow, mentions n8n, automation, webhook intake, AI processing pipelines, or anything related to n8n node configurations. Essential for any n8n automation.
triggers: [n8n, workflow, automation, trigger, node, webhook, n8n build]
tier: standard
dependencies: []
---

# N8N Workflow Engineering — Skill Reference

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

## Workflow JSON Structure Reference
```json
{
  "name": "Workflow Name",
  "nodes": [
    {
      "parameters": {},
      "id": "unique-uuid",
      "name": "Descriptive Node Name",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [250, 300]
    }
  ],
  "connections": {
    "Node Name": {
      "main": `{"node": "Next Node", "type": "main", "index": 0}`
    }
  },
  "settings": {
    "executionOrder": "v1"
  }
}
```

## Testing Checklist
- [ ] Trigger fires correctly
- [ ] Each node processes expected data format
- [ ] Error paths trigger on actual errors
- [ ] Retry logic works (test with temporary failure)
- [ ] Output matches expected format
- [ ] No hardcoded credentials
- [ ] Monitoring/alerting is in place
- [ ] Workflow is documented with sticky notes

## Obsidian Links
- [[brain/CAPABILITIES]] | [[skills/INDEX]] | [[brain/DASHBOARD]]
