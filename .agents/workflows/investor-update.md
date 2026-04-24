---
name: Investor Update
trigger: /investor-update
schedule: monthly (last business day)
agent: chief-of-staff
dependencies: [stripe_tool.py, supabase_tool.py, financial-modeling]
---

# Investor Update Workflow

Generate and draft a monthly investor update email using live data from Stripe, Supabase, and the financial model.

## When to Run

- Manually via `/investor-update` command
- Scheduled: last business day of every month
- Before any investor or advisor meeting where a current update is expected

## Steps

### Step 1 — Pull Revenue Data
```bash
python scripts/stripe_tool.py subscriptions --status active --json
python scripts/stripe_tool.py invoices --limit 10 --json
```
Extract: current MRR, new MRR added this month, churned MRR, total active subscriptions.

### Step 2 — Pull Pipeline Data
```bash
python scripts/supabase_tool.py select leads --project bravo --limit 50
```
Filter for leads with status `active` or `proposal_sent`. Calculate: number of active prospects, estimated pipeline value (sum of deal values for open opportunities).

### Step 3 — Calculate Burn Rate
```bash
python scripts/stripe_tool.py invoices --limit 30 --json
```
Pull last 30 days of outgoing charges (Stripe subscriptions CC pays). Reference `brain/USER.md` for fixed monthly overhead (~$184 USD/month as of 2026-03-28).

### Step 4 — Compile Metrics Table

Build the metrics comparison table:
| Metric | This Month | Last Month | Change |
|--------|------------|------------|--------|
| MRR (USD) | [from Stripe] | [from last session log] | [calc] |
| ARR (USD) | MRR × 12 | — | [calc] |
| Active Clients | [from Supabase] | [from last log] | [diff] |
| Pipeline (USD) | [from leads query] | — | — |
| Burn Rate (USD) | [from expenses] | — | — |
| Runway | Net MRR / burn | — | — |

### Step 5 — Review Session Log for Monthly Highlights
```
Read memory/SESSION_LOG.md — last 30 days
```
Extract:
- Biggest win (most significant client, feature shipped, or milestone)
- Biggest challenge (honest — investors respect candor)
- Product updates (what shipped)
- Content and outreach activity

### Step 6 — Draft the Update

Use the monthly investor update template from `skills/investor-communications/SKILL.md`.

Fill in all sections:
1. TL;DR (3 bullets: win, metric, challenge)
2. Key Metrics (populated from Steps 1-4)
3. Product Updates (from session log)
4. Sales & Marketing (pipeline + content performance)
5. Team (any changes — usually "Solo execution" at current stage)
6. Financials (revenue, expenses, net)
7. Asks (1-2 specific asks from CC's current needs)
8. Next Month Focus (top 3 priorities from ACTIVE_TASKS.md)

### Step 7 — Present to CC for Review

Output the draft email with:
- Subject line using the format: `[Company] — [Month YYYY] Update: [headline]`
- Full email body
- List of any data points that were estimated vs. pulled from live data

Wait for CC's review and approval before sending.

### Step 8 — Log to Session Log
After CC approves and sends:
```
Append to memory/SESSION_LOG.md:
### [DATE] — Monthly Investor Update Sent
MRR: $X,XXX | Pipeline: $X,XXX | Recipients: [N advisors/investors]
```

## Output

A draft investor update email, ready for CC to review and send.
The update is also saved to `memory/SESSION_LOG.md` for historical tracking.

## Error Handling

- Stripe API fails: use last known MRR from `brain/STATE.md` and flag as estimated
- Supabase query fails: use lead count from last session log entry
- Missing data point: always flag as estimated rather than omitting — transparency builds trust

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
