# Browser Safety Rules

Browser automation touches real logged-in accounts. Treat every click like it can affect production.

## Safe Without Additional Approval

- Read-only inspection of dashboards.
- Screenshots for evidence, if they do not expose secrets or private client data.
- Navigating to public docs, public GitHub pages, public marketing sites, and public product pages.
- Drafting text into a local file.
- Inspecting DOM, network requests, page metadata, and public API responses.

## Requires Explicit CC Approval

- Sending email, DMs, posts, comments, proposals, invoices, contracts, or calendar invites.
- Publishing, scheduling, or deleting content.
- Changing ad budgets, audiences, campaigns, billing, domains, DNS, users, permissions, webhooks, workflows, database schema, or production settings.
- Moving money, issuing refunds, upgrading paid plans, creating subscriptions, changing payment methods, or filing taxes.
- Bulk importing, exporting, deleting, suppressing, archiving, or modifying production business data.
- Clicking buttons with labels like send, publish, delete, remove, refund, charge, upgrade, deploy, merge, invite, disable, cancel, archive, submit, approve, or confirm.

## Preferred Tool Order

Use the safest structured interface first:

1. Existing Bravo CLI/API tools.
2. Official app APIs.
3. Browser Harness read-only inspection.
4. Browser Harness write actions only after approval.

## Domain-Skill Hygiene

Never save:

- passwords
- cookies
- session tokens
- API keys
- private customer data
- raw pixel coordinates
- screenshots with sensitive visible data
- step-by-step diary narration

Do save:

- URL patterns
- robust selectors
- wait conditions
- layout traps
- framework quirks
- approval-gated actions
- safe evidence conventions
