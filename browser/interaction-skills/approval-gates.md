---
tags: [browser, automation]
last_updated: 2026-05-21
---

# Approval Gates

Use this before any browser action that can affect a real account.

## Stop And Ask

Ask CC before clicking actions that send, publish, delete, charge, refund, deploy, invite, approve, disable, cancel, archive, submit, merge, or update production settings.

## Approval Prompt Shape

Use plain English:

```text
CC, I can see the final confirmation button for <action>. This will <impact>. Do you want me to click it?
```

Do not bundle multiple risky approvals into one ask.

## Logged Alternatives

Prefer existing tools that log business activity:

- `scripts/integrations/send_gateway.py` for outbound messages.
- `scripts/integrations/stripe_tool.py` for Stripe inspection and safe operations.
- `scripts/integrations/supabase_tool.py` for database reads.
- `scripts/integrations/n8n_tool.py` for workflow inspection.
- `scripts/integrations/google_tool.py` for Google Workspace.

Browser clicks should not bypass Bravo's logs.

## Related
- [[browser/README]]
- [[browser/interaction-skills/INDEX]]
- [[skills/browser-automation/SKILL]]


## Related (graph)

- [[browser/interaction-skills/INDEX]]
- [[browser/interaction-skills/connection]]
- [[browser/interaction-skills/domain-skill-lifecycle]]
- [[browser/interaction-skills/evidence]]
