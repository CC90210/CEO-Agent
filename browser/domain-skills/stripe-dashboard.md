# Stripe Dashboard

## Site

- URL patterns: `https://dashboard.stripe.com/`
- Auth assumptions: CC may be logged in locally. Money movement is approval-gated.
- Agent owner: Bravo/Atlas
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect balances, customers, invoices, subscriptions, payment links, payouts, events.
- Draft-only: prepare invoice/payment-link instructions.
- Approval required: refunds, charges, cancellations, subscription changes, payment method changes, account/bank settings.

## Preferred Tools

- Use `python scripts/integrations/stripe_tool.py balance`, `customers`, `invoices`, `subscriptions`, `payment-links` first.
- Browser Harness is for dashboard verification, screenshots, and UI-only details.

## Traps

- Live/test mode toggle matters. Confirm mode before interpreting data.
- Multiple Stripe accounts may be present. Confirm account context.
- Refund and cancel flows can be one or two clicks from final action.

## Approval Gates

Approval required before refunds, charges, cancellations, subscription edits, payment-link creation if it will be sent, payout/bank changes, or user access changes.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]


## Related (graph)

- [[browser/domain-skills/README]]
- [[browser/domain-skills/browser-use-cloud]]
- [[browser/domain-skills/canva]]
- [[browser/domain-skills/client-portal-template]]
