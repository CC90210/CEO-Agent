---
name: financial-modeling
description: Unit economics, SaaS metrics, cohort analysis, scenario modeling, cash flow forecasting, and CC-specific financial calculations for OASIS AI
tags: [skill, finance, modeling, unit-economics, saas-metrics]
triggers: ["financial modeling", "use financial modeling", "run financial modeling", "unit economics"]
---

# Financial Modeling

> **Note (2026-05-18):** Worked examples below use pre-primary retainer-end numbers ($2,500 primary retainer, $2,982 MRR, 94% concentration). They remain as **pedagogical references** — the formulas + structure still apply. For current state: brain/STATE.md (~$371 confirmed MRR, no dominant client). For the revenue shift event: [docs/handovers/2026-05-18-primary_retainer-revenue-shift-handoff.md](../../docs/handovers/2026-05-18-primary_retainer-revenue-shift-handoff.md).

## Overview

Every business decision is a financial decision with numbers attached. This skill gives CC the formulas, templates, and CLI tool to model revenue, measure unit economics, and make decisions from data rather than gut feel.

**Trigger:** `python scripts/financial_model.py`, "unit economics", "runway", "financial model", "what's our LTV"

**CLI tool:** `python scripts/financial_model.py`

**Related:** `skills/strategic-planning/SKILL.md`, `skills/ceo-briefing/SKILL.md`

---

## Unit Economics

### Core Formulas

**Customer Acquisition Cost (CAC)**
```
CAC = Total Sales & Marketing Spend (period) ÷ New Customers Acquired (period)

Example: CC spends $500 in ad spend + 10 hours × $50/hr opportunity cost = $1,000
Acquired 2 clients → CAC = $1,000 ÷ 2 = $500 per client
```

Note: For CC currently, CAC ≈ $0 cash (all organic/referral) but has real opportunity cost in time.

**Lifetime Value (LTV)**
```
LTV = ARPU × Gross Margin % × Average Customer Lifespan (months)

Where average customer lifespan = 1 ÷ Monthly Churn Rate

Example: ARPU = $1,000/mo, Gross Margin = 94%, Churn = 5%/mo
LTV = $1,000 × 0.94 × (1 ÷ 0.05) = $1,000 × 0.94 × 20 = $18,800
```

**LTV:CAC Ratio**
```
LTV:CAC = LTV ÷ CAC

Target: ≥ 3:1 (good), ≥ 5:1 (great), ≥ 10:1 (exceptional for early stage)
Below 1:1 → you're losing money on every customer

Example: LTV $18,800, CAC $500 → LTV:CAC = 37.6:1 (exceptional)
```

**Payback Period**
```
Payback Period (months) = CAC ÷ (ARPU × Gross Margin %)

Example: CAC $500, ARPU $1,000, Gross Margin 94%
Payback = $500 ÷ ($1,000 × 0.94) = $500 ÷ $940 = 0.5 months
```

**Monthly Burn Rate**
```
Burn Rate = Total Monthly Expenses - Total Monthly Revenue

Positive burn = profitable (revenue > expenses)
Negative burn = losing money each month
```

**Runway**
```
Runway (months) = Cash On Hand ÷ Monthly Net Burn

If profitable: runway is theoretically infinite — shift focus to growth metrics
```

---

## SaaS Metrics Dashboard

### Monthly Recurring Revenue (MRR) Components

```
Net MRR = New MRR + Expansion MRR - Contraction MRR - Churned MRR

New MRR:        Revenue from brand new customers this month
Expansion MRR:  Revenue increase from existing customers (upsells, add-ons)
Contraction MRR: Revenue decrease from existing customers (downgrades)
Churned MRR:    Revenue lost from customers who cancelled
```

Example (CC, March 2026):
- New MRR: $0 (no new clients)
- Expansion MRR: +$291 (primary retainer rev share grew)
- Contraction MRR: $0
- Churned MRR: $0
- Net MRR: +$291 → $2,982

**ARR (Annual Recurring Revenue)**
```
ARR = MRR × 12
Current ARR = $2,982 × 12 = $35,784
```

### Margin Metrics

```
Gross Margin % = (Revenue - Direct Costs) ÷ Revenue × 100

CC's direct costs (per client):
  - Supabase hosting: ~$8/client/mo
  - AI API costs (Claude/GPT): ~$10-30/client/mo
  - Time cost: variable

Current gross margin: ~94% (services business, near-zero COGS)
```

### Churn Metrics

```
Logo Churn Rate = Customers Lost ÷ Customers at Start of Period
Revenue Churn Rate = MRR Lost ÷ MRR at Start of Period

Net Revenue Retention (NRR) = (MRR Start + Expansion - Contraction - Churn) ÷ MRR Start × 100

NRR > 100% → existing customers are growing faster than they're churning (expansion revenue)
NRR = 100% → flat from existing base
NRR < 100% → churning out faster than expanding

CC's NRR (March 2026): ~110% (primary retainer rev share growing)
```

### SaaS Quick Ratio

```
Quick Ratio = (New MRR + Expansion MRR) ÷ (Contraction MRR + Churned MRR)

> 4: Healthy, efficient growth
2-4: Growing with acceptable efficiency
< 2: Growing but inefficiently (churn is eating gains)
< 1: Net negative growth

CC's current Quick Ratio: Undefined (no churn denominator = perfect retention)
```

---

## Cohort Analysis Framework

### Monthly Cohort Retention Table

Track each cohort of clients (grouped by the month they started) and see how their revenue evolves.

```markdown
## Cohort Retention — Revenue ($)

| Cohort | Month 1 | Month 2 | Month 3 | Month 6 | Month 12 |
|--------|---------|---------|---------|---------|----------|
| Jan 2026 | $X | $X (X%) | $X (X%) | $X (X%) | $X (X%) |
| Feb 2026 | $X | $X (X%) | $X (X%) | — | — |
| Mar 2026 | $X | — | — | — | — |

Percentages are vs Month 1 revenue for that cohort.
100%+ in later months = expansion. <100% = contraction or churn.
```

### Building the Table

1. Pull client start dates and monthly revenue from Supabase
2. Group by month started (= cohort)
3. For each cohort × time offset, sum total revenue
4. Divide by Month 1 revenue to get retention %

### Interpreting Cohorts

- Cohorts retaining >90% at Month 6 = sticky product
- Cohorts that grow to 110%+ = expansion revenue engine (good)
- Cohorts that drop below 60% at Month 3 = onboarding problem
- Compare cohort curves over time: is retention improving?

---

## Scenario Modeling Templates

### Revenue Projection

```markdown
## Revenue Projection — [Date to Date]

### Assumptions
| Variable | Conservative | Moderate | Aggressive |
|----------|-------------|---------|-----------|
| New clients/mo | 0 | 1 | 2 |
| Avg deal size | $500 | $1,000 | $1,500 |
| Monthly churn rate | 5% | 2% | 0.5% |
| Expansion MRR/mo | 0% | 2% | 5% |

### Projected MRR

| Month | Conservative | Moderate | Aggressive |
|-------|-------------|---------|-----------|
| Mar 2026 (actual) | $2,982 | $2,982 | $2,982 |
| Apr 2026 | $X | $X | $X |
| May 2026 | $X | $X | $X |
| Jun 2026 | $X | $X | $X |

North star: $5,000 MRR by May 15, 2026
Gap: $2,018 ÷ $1,000 avg deal = 2 new clients needed minimum
```

### Price Change Model

```
Price Elasticity ≈ % Change in Demand ÷ % Change in Price

Typical SMB SaaS elasticity: -0.3 to -1.0
(10% price increase → 3-10% customer loss)

Revenue impact = New Price × (1 - Elasticity × Price Change %) × Current Customers

Example: Raise price 20% with -0.5 elasticity
  Expected customer loss: 0.5 × 20% = 10%
  Net revenue change: 1.20 × 0.90 = 1.08 → +8% revenue
  Decision: Take it (revenue positive, better client quality)
```

### Hiring Impact Model

```
Monthly Revenue Per Employee = MRR ÷ Headcount (equivalent)
Current: $2,982 ÷ 1 (CC) = $2,982/person (excellent)

Hire break-even month = (Annual salary ÷ 12) ÷ Expected Monthly Revenue Generated

For a $2,000/mo VA:
  If VA handles 10 hrs/week × $50/hr CC opportunity cost = $2,000/mo recovered
  Break-even: $2,000 ÷ $2,000 = Month 1
  Decision: Take it. Any recovered CC time that generates $1 in sales pays for itself.
```

### Client Concentration Risk — Herfindahl Index

```
Herfindahl-Hirschman Index (HHI) = Sum of (each client's revenue share)²

HHI = 1.0    → 100% concentrated (one client = all revenue) — CRITICAL
HHI 0.5-1.0  → Highly concentrated — dangerous
HHI 0.2-0.5  → Moderately concentrated — manageable
HHI < 0.2    → Diversified — healthy

CC current (March 2026):
  Primary retainer: $2,791 / $2,982 = 93.6%
  Base (other): $191 / $2,982 = 6.4%
  HHI = (0.936)² + (0.064)² = 0.876 + 0.004 = 0.880

Interpretation: CRITICAL concentration risk.
One bad call with the primary retainer = 94% revenue collapse.
Target by Q3 2026: HHI < 0.5 (add 3+ clients with no single client >40%)
```

---

## Cash Flow Forecasting

### 90-Day Rolling Cash Flow Projection

```markdown
## Cash Flow Forecast — [Start Date] to [End Date]

### Revenue (Inflows)
| Source | Monthly | Notes |
|--------|---------|-------|
| Primary retainer | $2,500 | Flat, invoiced 1st of month |
| Primary retainer rev share | ~$291 | 15% × ~$1,940 community MRR |
| Base retainers | $191 | Other clients |
| One-time projects | $0 | Add when confirmed |
| **Total Inflows** | **~$2,982** | |

### Expenses (Outflows)
| Item | Monthly | Notes |
|------|---------|-------|
| Claude Pro | $140 | Critical infrastructure |
| Supabase | $25 | Database |
| Hostinger VPS | $14 | n8n automation server |
| Domain/misc | $5 | Estimated |
| **Total Outflows** | **~$184** | |

### Net Cash Position
| Month | Net Monthly | Running Cash |
|-------|------------|-------------|
| Month 1 | $2,798 | [Balance + $2,798] |
| Month 2 | $2,798 | [+ $2,798] |
| Month 3 | $2,798 | [+ $2,798] |
```

### Revenue Recognition Rules

**Retainers:** Recognized monthly when work is delivered (accrual). Do not count as revenue until the month it covers.

**Project work:** Recognized on completion of agreed milestones. If multi-month, recognize proportionally.

**RevShare (primary retainer):** Recognized monthly based on actual community MRR reported. Volatile — model conservatively.

### Emergency Fund Sizing

```
3-month emergency fund = 3 × Monthly Expenses = 3 × $184 = $552 (trivial for CC)

Better emergency metric: primary-retainer churn buffer
If primary-retainer churns tomorrow, how many months until we need to cut costs?
Cash reserve ÷ Monthly expenses after primary-retainer churn = $X ÷ $184 = X months

Build pipeline NOW such that HHI < 0.5 before needing the emergency fund.
```

---

## CC-Specific Financial Snapshot

Current state as of Q1 2026. Update after each `/briefing` run.

```markdown
## CC Financial Snapshot — March 2026

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| MRR | $2,982 | $5,000 | 59.6% |
| ARR | $35,784 | $60,000 | 59.6% |
| Gross Margin | ~94% | >85% | OK |
| Monthly Overhead | $184 | <$500 | OK |
| Net Profit/mo | ~$2,798 | >$4,500 | Tracking |
| CAC (cash) | ~$0 | <$300 | Exceptional |
| LTV (est.) | $18,000+ | >$10,000 | OK |
| LTV:CAC | 36:1+ | >3:1 | Exceptional |
| HHI (concentration) | 0.88 | <0.5 | CRITICAL |
| Runway | Indefinite | >12 mo | OK |
| MRR gap to target | $2,018 | $0 | 48 days |
| Clients needed | ~2 × $1,000 | 0 | In pipeline |
```

### Key Financial Risks

1. **Client concentration** (HHI 0.88): the primary retainer is 94% of revenue. No contract. Mitigate by closing 2-3 new clients this quarter.
2. **No diversification**: All OASIS, no PropFlow or Nostalgic revenue yet. Mitigate with PropFlow MVP launch.
3. **RevShare volatility**: the primary retainer's 15% rev share fluctuates with community size. Don't plan expansion from this source.

### Financial Priorities (Q2 2026)

1. Reduce HHI to <0.6 by adding 2 new clients at $500+ MRR
2. Hit $5,000 MRR by May 15 (48 days from March 28)
3. Begin PropFlow revenue modeling once MVP ships
4. Re-evaluate pricing quarterly (current floor: $500/mo, ceiling: $1,500/mo)

---

## CLI Reference

```bash
# Calculate all unit economics from current data
python scripts/financial_model.py unit-economics

# 12-month revenue forecast
python scripts/financial_model.py forecast --months 12

# Bull/base/bear scenario model
python scripts/financial_model.py scenario --type base

# Client concentration risk (HHI)
python scripts/financial_model.py concentration

# Cash runway calculation
python scripts/financial_model.py runway

# JSON output for agent consumption
python scripts/financial_model.py unit-economics --json
```

---

---

## Unit Economics Calculator — Step-by-Step

Use this when evaluating a pricing change, new client acquisition strategy, or hiring decision. Run with actual numbers, not estimates.

### Step 1 — Calculate CAC

```
CAC = (Monthly cash spend on sales/marketing) + (CC hours on sales × $50/hr opportunity cost)
      ÷ New clients acquired that month

Example (April 2026):
  Cash spend: $0 (organic only)
  CC hours on sales: 8 hrs × $50 = $400
  New clients: 1
  CAC = $400 ÷ 1 = $400
```

If CAC is $0 cash (referral/organic), still track opportunity cost. Invisible costs are real costs.

### Step 2 — Calculate LTV

```
LTV = Monthly MRR per client × Gross Margin % × Avg Lifespan (months)

Avg Lifespan = 1 ÷ Monthly Churn Rate

Example:
  ARPU: $1,000/mo
  Gross Margin: 94%
  Churn rate: 4%/mo → Avg lifespan: 25 months
  LTV = $1,000 × 0.94 × 25 = $23,500
```

### Step 3 — Calculate LTV:CAC Ratio

```
LTV:CAC = LTV ÷ CAC

Benchmarks:
  < 1:1  → You lose money on every client. Stop and fix.
  1–3:1  → Barely viable. Improve margin or reduce CAC.
  3–5:1  → Healthy. Standard for services.
  5–10:1 → Great. Keep scaling.
  > 10:1 → Exceptional. Increase sales spend aggressively.

Example: $23,500 ÷ $400 = 58.75:1 (exceptional — organic acquisition + high margin)
```

### Step 4 — Calculate Payback Period

```
Payback Period (months) = CAC ÷ (Monthly ARPU × Gross Margin %)

Example: $400 ÷ ($1,000 × 0.94) = $400 ÷ $940 = 0.4 months (~12 days)
```

Target: < 6 months for services. < 12 months for SaaS with high churn risk.

### Step 5 — Break-Even Analysis Per Client

At what point does a client become profitable, net of all costs?

```
Monthly net from client = ARPU - Direct costs (hosting + API + time)
Cumulative net = Monthly net × Months active

Break-even month = CAC ÷ Monthly net

Example:
  ARPU: $1,000
  Direct costs: $60 (Supabase $8 + API $30 + 1hr CC time $22)
  Monthly net: $940
  CAC: $400
  Break-even: $400 ÷ $940 = 0.4 months → profitable by end of month 1
```

Add this to every new client onboarding record in Supabase.

---

## Scenario Modeling — Bull / Base / Bear

Use for any significant decision: pricing change, new hire, product launch, marketing spend.

### Input Assumptions Matrix

```markdown
## Scenario: [Decision Name] — [Date]

| Variable | Bear | Base | Bull |
|---------|------|------|------|
| New clients/month | 0 | 1 | 2–3 |
| Avg deal size | $500 | $1,000 | $1,500 |
| Monthly churn rate | 5% | 2% | 0.5% |
| Expansion MRR/month | 0% | 2% | 5% |
| CAC (time cost) | $600 | $400 | $200 |

Assign probabilities (must sum to 100%):
  Bear: X% | Base: X% | Bull: X%
```

### Output: Expected MRR Trajectory

```
Month 1: Bear $X | Base $X | Bull $X
Month 3: Bear $X | Base $X | Bull $X  
Month 6: Bear $X | Base $X | Bull $X

Expected Value (weighted avg) = (Bear × P) + (Base × P) + (Bull × P)

Trigger to shift scenarios:
  → Bear: [specific event, e.g., "primary-retainer churns or 0 new clients in April"]
  → Bull: [specific event, e.g., "2 new clients close in April"]
```

### Decision Rule

- If Bear EV still covers fixed costs → proceed with the decision
- If Bear EV creates cash flow risk → add a risk mitigation step first
- If Base EV hits north star within target timeline → this is the right bet

---

## Cash Flow Runway Projection

### 90-Day Forward Projection Template

Update this monthly. It is the single most important number for a solo operator.

```markdown
## Cash Flow Projection — [Start Date]

### Revenue Inflows (Conservative)

| Source | Month 1 | Month 2 | Month 3 | Notes |
|--------|---------|---------|---------|-------|
| Primary retainer | $2,500 | $2,500 | $2,500 | Flat |
| Primary retainer rev share | $451 | $480 | $510 | Growing 6.5%/mo |
| Other retainers | $191 | $191 | $191 | Stable |
| New clients | $0 | $500 | $1,000 | 1 new/mo Base |
| **Total inflows** | **$3,142** | **$3,671** | **$4,201** | |

### Expenses (Outflows)

| Item | Monthly | Quarter Total |
|------|---------|--------------|
| Claude Pro | $140 | $420 |
| Supabase | $25 | $75 |
| Hostinger VPS | $14 | $42 |
| Misc domains/tools | $5 | $15 |
| **Total outflows** | **$184** | **$552** |

### Net Position

| Month | Net | Running Total |
|-------|-----|--------------|
| Month 1 | $2,958 | $X (starting balance + $2,958) |
| Month 2 | $3,487 | $X + $3,487 |
| Month 3 | $4,017 | $X + $4,017 |

### Runway if primary-retainer churns tomorrow
  Monthly expenses without primary retainer: $184
  Monthly revenue without primary retainer: ~$191 (other retainers)
  Net monthly: +$7 (barely cash-flow positive — no buffer)
  Runway: Indefinite on expenses, but zero growth buffer
  → This is why HHI reduction is the #1 financial priority
```

### Runway Calculation

```
Standard runway: Cash on hand ÷ Monthly burn rate
Survival runway (if major client churns): Cash on hand ÷ (Monthly expenses - retained revenue)

Target: Survival runway ≥ 6 months at all times
```

---

## Revenue Diversification Metrics

### Herfindahl-Hirschman Index (HHI) — Client Concentration Risk

Already in this skill above. Target thresholds for action:

| HHI | Status | Action |
|-----|--------|--------|
| > 0.7 | Critical | Close 2+ new clients before any other priority |
| 0.5–0.7 | High risk | Add 1 new client per month until below 0.5 |
| 0.25–0.5 | Moderate | Monitor. Keep pipeline active. |
| < 0.25 | Healthy | Shift focus from diversification to expansion |

### Revenue Stream Diversification Score

Track percentage of MRR from each category:

```
| Stream | MRR | % of Total | Target % |
|--------|-----|-----------|----------|
| OASIS retainers | $X | X% | <60% |
| OASIS rev share | $X | X% | <15% |
| PropFlow SaaS | $X | X% | >20% by Q3 |
| Nostalgic Requests | $X | X% | >10% by Q4 |
| One-time projects | $X | X% | <10% (not recurring) |
```

Alert rule: If any single stream exceeds 70% of total MRR, HHI is critical regardless of client count.

### MRR Quality Score

Not all MRR is equal. Score the MRR portfolio:

```
Quality Score = (Contracted MRR × 1.0) + (Handshake MRR × 0.7) + (Rev Share MRR × 0.5)
                ÷ Total MRR

> 0.85 → High quality (mostly contracted)
0.65–0.85 → Medium quality (mix of contracted and informal)
< 0.65 → Low quality (mostly informal — high churn risk)

CC current: ~0.64 (primary-retainer informal + rev share dominant)
Target: 0.75+ by adding formal contracts to existing clients
```

---

## Obsidian Links
- [[brain/STATE]] | [[brain/USER]] | [[skills/strategic-planning/SKILL]]
- [[skills/ceo-briefing/SKILL]] | [[../../CMO-Agent/skills/competitive-intelligence/SKILL]]
- [[skills/client-success/SKILL]] | [[memory/ACTIVE_TASKS]] | [[brain/CAPABILITIES]]
