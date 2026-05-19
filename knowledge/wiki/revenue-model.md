---
tags: [knowledge, wiki, revenue, mrr, pricing, retainer, archived]
sources: [brain/STATE.md, brain/USER.md]
last_updated: 2026-05-18
status: archived
confidence: 0.92
---

> **ARCHIVED 2026-05-18 — pre-2026-05-18 snapshot.** This file documents the revenue model as it existed before the primary retainer ended on 2026-05-18. Numbers below are historical context, NOT current state. For current MRR see [[brain/STATE]] (~$371 confirmed) and the full handoff: [docs/handovers/2026-05-18-primary-retainer-revenue-shift-handoff.md](../../docs/handovers/2026-05-18-primary-retainer-revenue-shift-handoff.md). When a current-state revenue doc is written, link it here.

# Revenue Model — MRR Breakdown and Path to $5K [ARCHIVED]

> Full picture of how revenue worked **up to 2026-05-18**, the primary retainer relationship, and what was needed to hit $5K MRR before the retainer ended.
> [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/client-playbook]]

## North Star

**$5,000 USD Net MRR by May 15, 2026.**

Previous milestone: $1,000 USD Net MRR by March 31, 2026 — achieved at $2,691 USD (+169% surplus).
Current Net MRR: ~$2,982 USD/mo.
Gap to target: ~$2,018 USD/mo.
Pace required: ~1 new client per week for 6 weeks.

## Current MRR Breakdown (as of 2026-04-06)

| Revenue Stream | Amount (USD/mo) | Type | Notes |
|----------------|-----------------|------|-------|
| OASIS base retainers | $191 | Recurring | Existing small retainers (non-primary) |
| Primary retainer flat fee | $2,500 | Recurring | Community-management deliverable |
| Primary retainer rev share | $291 | Recurring (variable) | 15% of $1,940 community MRR |
| **Total Net MRR** | **$2,982** | — | — |

**Additional one-time:** $3,000 USD upfront (coaching referral — 2 companies referred via the primary client)

## The Primary Retainer

The largest current revenue stream is a community-management retainer — CC manages a
paid community on behalf of the client.

**Structure:**
- $2,500/mo flat fee — paid regardless of community size
- 15% revenue share on community MRR — scales as the community grows
- No formal contract — friend-based relationship
- Client has referred 2 coaching prospects at $10K upfront each

**Community metrics (as of 2026-04-04):**
- 158 members total
- 63% engagement rate
- 100% retention rate
- 159 signups in last 30 days
- 5.5% conversion rate

**Rev share math:** Current community MRR = ~$1,940. At 15% = $291/mo.
As community grows, rev share grows proportionally.
At $5,000 community MRR → $750/mo rev share.
At $10,000 community MRR → $1,500/mo rev share.

**Critical risk:** the primary retainer is ~93% of total MRR. If they churn, revenue drops to
$191/mo immediately. Diversification is the #1 strategic priority.

## OASIS AI Retainer Pricing

| Tier | USD/mo | Target Client | CAC | LTV (12mo) |
|------|--------|---------------|-----|------------|
| Starter | $400 | Small local service business | ~$0 (inbound) | $4,800 |
| Growth | $500 | Established local service business | ~$0 (inbound) | $6,000 |
| Custom | $1,000+ | Multi-location or complex needs | ~$0 (relationship) | $12,000+ |

**Monthly overhead:** ~$184 USD
- Claude API: $140/mo
- Supabase: $25/mo
- Hostinger (n8n VPS): $14/mo

**Gross margin:** Very high (no cost of goods, software-only delivery). At $5K MRR with $184 overhead,
net margin approaches 96%.

## Path to $5K — Gap Analysis

| Scenario | New Clients Needed | Time to Close (at 1/week) |
|----------|-------------------|--------------------------|
| All Starter ($400/mo) | ~5 clients | ~5 weeks |
| All Growth ($500/mo) | ~4 clients | ~4 weeks |
| Mix of Starter + Growth | ~4–5 clients | ~4–5 weeks |
| Rev share growth alone | Community needs ~$22K MRR | Not fast enough |

**Recommended path:** Close 4–5 OASIS retainer clients between now and May 15, 2026.
Inbound funnel (CC Funnel + content) is the primary lead source.
Cold outreach (NEPQ-style) as secondary source.

## Revenue Concentration Risk

| Risk | Mitigation |
|------|-----------|
| Primary retainer loss → -93% MRR | Close 4+ OASIS clients before May 15 |
| Community growth stalls | CC content drives new community signups |
| No-contract churn | Deliver exceptional value each month; relationship-based retention |

## Historical MRR Trajectory

| Date | Net MRR |
|------|---------|
| March 31, 2026 | $2,691 (milestone achieved) |
| April 6, 2026 | $2,982 |
| Target May 15, 2026 | $5,000 |

## Sources
- `brain/STATE.md` — current MRR, gap analysis, risk flags
- `brain/USER.md` — CC's financial reality, primary retainer context, pricing model

## Obsidian Links
- [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/client-playbook]]
- [[brain/STATE]] | [[brain/USER]] | [[brain/OKRs]]
- [[brain/RISK_REGISTER]] | `scripts/revenue_engine.py`
