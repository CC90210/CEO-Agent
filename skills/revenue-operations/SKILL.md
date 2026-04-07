---
name: revenue-operations
description: Track MRR, log revenue events, run forecasts, and monitor progress toward the $5,000 USD Net MRR goal using revenue_engine.py. Combines Stripe subscription data with manual entries in Supabase.
triggers: [revenue, MRR, forecast, Stripe, income, goal, monthly, clients, financial]
tier: standard
dependencies: []
---

# Revenue Operations — MRR Tracking and Forecasting

## Overview

`revenue_engine.py` is the single source of truth for CC's business revenue. It syncs Stripe subscription data and accepts manual entries for retainers, one-off projects, and consulting. Every dollar in and out runs through this system. The north star is $5,000 USD Net MRR by May 15, 2026.

---

## Tool Routing

All operations go through `python scripts/revenue_engine.py`. Append `--json` to any command for machine-readable output.

| Operation | Command |
|-----------|---------|
| Current MRR snapshot | `revenue_engine.py mrr` |
| Full dashboard | `revenue_engine.py dashboard` |
| Sync from Stripe | `revenue_engine.py sync-stripe` |
| Log a manual payment | `revenue_engine.py log-revenue --type payment --amount 500 --source manual --client "primary retainer" --notes "March retainer"` |
| Log month summary | `revenue_engine.py log-month --month 2026-03 --mrr 2691 --new-clients 0 --churned 0 --pipeline 5000 --leads 50` |
| View history | `revenue_engine.py history --months 6` |
| 90-day forecast | `revenue_engine.py forecast` |
| Active clients list | `revenue_engine.py clients` |
| Goal progress | `revenue_engine.py goal` |

---

## MRR Calculation Methodology

MRR = sum of all active monthly recurring revenue, normalized to monthly.

- **Stripe subscriptions:** Pulled automatically via `sync-stripe`. Interval-normalized (annual plans divided by 12).
- **Manual retainers:** Logged via `log-revenue --type retainer`. Example: primary retainer Community Manager at $2,500/mo.
- **One-off projects:** Logged via `log-revenue --type payment`. These count toward gross revenue but not MRR.
- **Net MRR:** Gross MRR minus churn. Churn is logged when a client is marked inactive.

Current state (March 2026): ~$2,691 USD Net MRR. Gap to goal: ~$2,309. That is 5-6 new clients at an average retainer of $400-500/mo, or 1-2 higher-ticket clients.

---

## Goal Tracking

```
python scripts/revenue_engine.py goal
```

This outputs: current MRR, gap to $5,000 USD, months remaining to May 15, 2026, and the required monthly growth rate to hit the goal.

Run `goal` at the start of every week. If the required growth rate is above 15%, the pipeline work is behind — escalate lead outreach immediately.

---

## Monthly Reporting Cadence

Run this sequence on the 1st of each month:

1. `revenue_engine.py sync-stripe` — pull latest Stripe data
2. `revenue_engine.py mrr` — confirm the number
3. `revenue_engine.py log-month --month YYYY-MM --mrr <number> --new-clients N --churned N --pipeline <pipeline_value> --leads N` — lock in the month
4. `revenue_engine.py history --months 3` — review the trend
5. `revenue_engine.py forecast` — update the 90-day projection
6. Log the summary in `memory/SESSION_LOG.md`

---

## Stripe Sync Schedule

`sync-stripe` pulls `charge.succeeded`, `invoice.paid`, and subscription create/delete events. Run it:

- **Daily during active sales periods** (any time a new client might have signed up)
- **Immediately after closing a new client** — confirm the Stripe subscription is live before logging manually
- **First of each month** as part of the monthly reporting cadence

Stripe credentials required in `.env.agents`: `STRIPE_SECRET_KEY`. The engine uses the restricted key pattern — never the full secret key unless absolutely required.

---

## Revenue Event Types

Use the correct type when logging manual entries. Types flow into the dashboard categorization.

| Type | When to Use |
|------|-------------|
| `retainer` | Fixed monthly amount from an ongoing client |
| `payment` | One-off project payment or invoice |
| `consulting` | Hourly or session-based consulting revenue |
| `referral` | Revenue from a referred client or affiliate |
| `refund` | Negative entry for a returned payment |

---

## Integration Points

- **Stripe** — primary source for SaaS and subscription revenue via `sync-stripe`
- **lead_engine.py** — when a lead hits `won`, immediately log the revenue: `revenue_engine.py log-revenue`
- **supabase_tool.py** — raw access to `revenue_events` and `monthly_snapshots` tables in the bravo project for custom reporting
- **SESSION_LOG.md** — monthly MRR snapshots belong in session log for cross-AI visibility

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
