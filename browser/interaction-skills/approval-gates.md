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

- `scripts/send_gateway.py` for outbound messages.
- `scripts/stripe_tool.py` for Stripe inspection and safe operations.
- `scripts/supabase_tool.py` for database reads.
- `scripts/n8n_tool.py` for workflow inspection.
- `scripts/google_tool.py` for Google Workspace.

Browser clicks should not bypass Bravo's logs.
