---
name: ceo-dashboard
description: Unified KPI framework — North Star metrics, revenue dashboard, pipeline dashboard, operations dashboard, content dashboard, client health dashboard, and the weekly CEO digest template. Powers the /briefing command output format.
tags: [skill, ceo, dashboard, kpi, revenue, pipeline]
triggers: ["ceo dashboard", "use ceo dashboard", "run ceo dashboard", "unified kpi framework \u2014 north star metrics"]
---

# CEO Dashboard — Unified KPI Framework

## Overview

Five numbers every morning. One digest every week. No vanity metrics, no noise.

CC's business is $5,000 Net MRR by May 15, 2026. Every KPI in this skill is chosen because it either predicts that number or explains why it moved.

**Snapshot (preferred):** Read `state/snapshots/latest_briefing.json` first. Rebuilt daily 06:00 UTC by `scripts/snapshots/briefing_snapshot.py`. If `ts` is <24h old, every section in this skill can be answered from it without a single subprocess call.
**Live tool (fallback):** `python scripts/ceo_dashboard.py briefing` — pulls Stripe, Supabase, and memory files. Use only when snapshot is stale or errored.
**Manual fallback:** Each section below has a manual source when both above are unavailable.

---

## 1. North Star Metrics (5 Numbers, Every Morning)

These are the only 5 numbers CC needs to see before starting his day.

```
NORTH STAR SNAPSHOT — [Date]
──────────────────────────────────────────────────────
1. Net MRR:        $[X] / $5,000 target  ([X]% — [Y] days to deadline)
   [████████░░] [X]%
   Trend: [↑ +$X vs last month / → flat / ↓ -$X vs last month]

2. Pipeline Value:  $[X] total potential revenue across [N] active leads
   Trend: [↑ growing / → stable / ↓ shrinking]
   Next likely close: [Lead name] — $[value] — [estimated close date]

3. Client Health:   [X]/100 average health across [N] clients
   At risk: [N clients below 70 — names if any]

4. Cash Position:   $[bank balance] + $[receivables due <30d] - $[payables due <30d]
   Net available: $[X]
   Note: [any large upcoming expenses]

5. Content Velocity: [X] posts published this week / [Y] target
   [Platform breakdown: X:0 | IG:0 | LinkedIn:0 | TikTok:0 | Threads:0]
   Trend: [↑ above pace / → on pace / ↓ below pace]
──────────────────────────────────────────────────────
```

**Manual sources when script unavailable:**
1. MRR: `memory/ACTIVE_TASKS.md` last known MRR entry + `python scripts/stripe_tool.py subscriptions --status active --json`
2. Pipeline: `memory/LEAD_TRACKER.csv` — sum value of leads in Discovery, Proposal, Negotiation stages
3. Client health: `python scripts/client_health.py alerts` or `skills/client-success/SKILL.md`
4. Cash: Stripe balance (`python scripts/stripe_tool.py balance`) + bank (manual input)
5. Content: `python scripts/late_tool.py posts --status published` filtered to current week

---

## 2. Revenue Dashboard

### MRR Breakdown by Client

```
MRR BREAKDOWN — [Month YYYY]
───────────────────────────────────────────────────────
Client / Source          | MRR       | Type         | Since
─────────────────────────────────────────────────────────
[Client name]            | $[X]      | Retainer     | [Date]
[Client name]            | $[X]      | Rev share    | [Date]
[App name — Stripe subs] | $[X]      | Subscription | [Date]
───────────────────────────────────────────────────────
TOTAL NET MRR:           | $[X]
Target:                  | $5,000
Gap:                     | $[X] (~[N] new clients at $[avg deal size])
```

### MRR Trend (Rolling 6 Months)

```
MRR TREND
Month       | MRR     | New MRR | Churned | Net Change
────────────────────────────────────────────────────
[M-5]       | $[X]    | +$[X]   | -$[X]   | [±$X]
[M-4]       | $[X]    | +$[X]   | -$[X]   | [±$X]
[M-3]       | $[X]    | +$[X]   | -$[X]   | [±$X]
[M-2]       | $[X]    | +$[X]   | -$[X]   | [±$X]
Last month  | $[X]    | +$[X]   | -$[X]   | [±$X]
This month  | $[X]    | +$[X]   | -$[X]   | [±$X (proj)]
────────────────────────────────────────────────────
```

**Data source:** `python scripts/revenue_engine.py history --months 6 --json`

### Revenue Composition Analysis

```
REVENUE COMPOSITION
New MRR (from new clients this month):    $[X]  ([X]%)
Expansion MRR (existing clients grew):   $[X]  ([X]%)
Churned MRR (clients lost this month):  -$[X]  ([X]%)
Net MRR change:                          $[±X]

Revenue concentration (top client %):    [X]%
[WARNING if any single client > 40% of MRR — concentration risk]
```

**Concentration risk flag:** If any single client accounts for >40% of MRR, flag it. (Historical note: primary retainer retainer was 84% concentration through 2026-05-17 — that risk materialized 2026-05-18 when the retainer ended. Current state: ~$371 confirmed MRR, no dominant client. The flag is now a guardrail against re-creating the same concentration.)

### Revenue by Brand

```
REVENUE BY BRAND
OASIS AI (retainers + consulting): $[X]/mo  ([X]%)
PropFlow (Stripe subscriptions):   $[X]/mo  ([X]%)
Nostalgic Requests (Stripe subs):  $[X]/mo  ([X]%)
Other (consulting, ad-hoc):        $[X]/mo  ([X]%)
```

**Data source:** Multi-account Stripe data via `python scripts/stripe_tool.py subscriptions --json` for each account.

---

## 3. Pipeline Dashboard

### Pipeline by Stage

```
PIPELINE SNAPSHOT — [Date]
────────────────────────────────────────────────────────────────────────
Stage          | Count | Total Value | Avg Age | Next Action Due
────────────────────────────────────────────────────────────────────────
Awareness      | [N]   | —           | —       | —
Interest       | [N]   | $[X]        | [X]d    | [soonest due]
Discovery      | [N]   | $[X]        | [X]d    | [soonest due]
Proposal Sent  | [N]   | $[X]        | [X]d    | [soonest due]
Negotiation    | [N]   | $[X]        | [X]d    | [soonest due]
────────────────────────────────────────────────────────────────────────
TOTAL PIPELINE: $[X] across [N] leads
Weighted (×50% win rate): $[X] expected
```

**Data source:** `memory/LEAD_TRACKER.csv` — filter to stages Discovery, Proposal, Negotiation.

### Pipeline Funnel Metrics

```
FUNNEL CONVERSION — Last 90 Days
Awareness → Interest:    [X]%
Interest → Discovery:    [X]%
Discovery → Proposal:    [X]%
Proposal → Closed-Won:   [X]%
────────────────────────────
Overall close rate:      [X]% (from first contact to close)
Average deal size:       $[X]/mo
Average sales cycle:     [X] days
```

### Pipeline Velocity

Formula: (Active deals × Win rate × Avg deal size) ÷ Avg cycle length (in days) = $ per day

```
Pipeline velocity: $[X]/day
Monthly projected closes: $[X]
At current velocity, MRR target reached: [Date or "N/A — need to increase pipeline"]
```

### Top Priority Leads

```
TOP 3 LEADS TO FOCUS ON
1. [Name / Company] — $[value]/mo — Stage: [X] — Last contact: [date] — Next action: [action by date]
2. [Name / Company] — $[value]/mo — Stage: [X] — Last contact: [date] — Next action: [action by date]
3. [Name / Company] — $[value]/mo — Stage: [X] — Last contact: [date] — Next action: [action by date]
```

---

## 4. Operations Dashboard

### Active Projects

```
ACTIVE PROJECTS — [Date]
──────────────────────────────────────────────────────────────────────────────
Project            | Client   | Phase | Status | % Done | Next Milestone        | Due
──────────────────────────────────────────────────────────────────────────────
[Project name]     | [Client] | P2    | 🟢     | 40%    | Build complete        | [date]
[Project name]     | [Client] | P3    | 🟡     | 75%    | Client review         | [date]
──────────────────────────────────────────────────────────────────────────────
```

### Deliverable Health

```
DELIVERABLES HEALTH
On track:  [N] deliverables — due this week, all on schedule
At risk:   [N] deliverables — risk: [brief reason]
Delayed:   [N] deliverables — impact: [client name, resolution plan]
```

### Tool Costs vs Budget

```
TOOL COSTS — [Month]
────────────────────────────────────────────────
Tool              | Cost     | Budget   | Status
────────────────────────────────────────────────
Claude API        | $140/mo  | $150/mo  | ✅
Supabase          | $25/mo   | $30/mo   | ✅
Hostinger VPS     | $14/mo   | $15/mo   | ✅
[Other tools]     | $[X]/mo  | $[Y]/mo  | [✅/⚠️]
────────────────────────────────────────────────
TOTAL OVERHEAD:   | $[X]/mo  | $[Y]/mo  |
────────────────────────────────────────────────
```

**Rule:** Keep total overhead below 10% of MRR. At $5,000 MRR target, overhead cap is $500/mo.

---

## 5. Content Dashboard

### Weekly Content Volume

```
CONTENT VOLUME — [Week of DATE]
────────────────────────────────────────────────
Platform   | Posts | Target | Status | Top Post
────────────────────────────────────────────────
X          | [N]   | [Y]    | ✅/⚠️  | [brief desc — X engagements]
Instagram  | [N]   | [Y]    | ✅/⚠️  | [brief desc]
LinkedIn   | [N]   | [Y]    | ✅/⚠️  | [brief desc]
TikTok     | [N]   | [Y]    | ✅/⚠️  | [brief desc]
Threads    | [N]   | [Y]    | ✅/⚠️  | [brief desc]
────────────────────────────────────────────────
TOTAL:     | [N]   | [Y]    |
```

**Data source:** `python scripts/late_tool.py posts --status published` — filter to current week by date.

### Engagement Metrics (Last 7 Days)

```
ENGAGEMENT SUMMARY
Total posts published: [N]
Total likes:      [N]
Total comments:   [N]
Total shares:     [N]
Total DMs:        [N]
────────────────────
Avg engagement rate: [X]% (likes+comments+shares ÷ followers)
```

### Content-to-Lead Attribution

```
INBOUND LEADS THIS WEEK
Total inbound: [N]
Source breakdown:
  From specific posts: [N] — [which post(s)]
  From bio/profile: [N]
  From DMs: [N]
  Unknown source: [N]
```

Track this manually: when a new lead comes in, ask "How did you find me?" and log it.

### Audience Growth

```
AUDIENCE GROWTH — Month over Month
Platform   | Last Month | This Month | Change
───────────────────────────────────────────
X          | [N]        | [N]        | [±N] ([±X]%)
Instagram  | [N]        | [N]        | [±N]
LinkedIn   | [N]        | [N]        | [±N]
TikTok     | [N]        | [N]        | [±N]
───────────────────────────────────────────
```

---

## 6. Health Dashboard

### Client Health Scores

```
CLIENT HEALTH — [Date]
────────────────────────────────────────────────────────────────────────
Client      | Health Score | Risk Tier    | Last Check-in | Alert
────────────────────────────────────────────────────────────────────────
[Name]      | [85/100]     | 🟢 Healthy   | [date]        | None
[Name]      | [68/100]     | 🟡 Watch     | [date]        | [brief reason]
[Name]      | [45/100]     | 🔴 At Risk   | [date]        | [action needed]
────────────────────────────────────────────────────────────────────────
```

**Risk tiers:**
- 🟢 Healthy: 75-100 — stable, no action needed
- 🟡 Watch: 55-74 — proactive check-in this week
- 🔴 At Risk: 0-54 — immediate intervention required

**Data source:** `python scripts/client_health.py report --json` (see `skills/client-success/SKILL.md`)

### Agent System Health

```
SYSTEM HEALTH — [Date]
MCP Servers: [Playwright ✅ | Context7 ✅ | Memory ✅ | Sequential ✅]
Memory health: SESSION_LOG.md [X lines — 🟢/🟡] | ACTIVE_TASKS.md [N tasks — 🟢/🟡]
Last sync: brain/STATE.md updated [date]
Last git commit: [hash] — [date]
n8n workflows: [N active of Y total]
```

### Infrastructure Costs Trend

```
INFRA COST TREND — Last 3 Months
[M-2]: $[X]
[M-1]: $[X]
Current: $[X]
Trend: [↑ rising / → stable / ↓ falling]
% of MRR: [X]%
```

---

## 7. Weekly CEO Digest Template

This is the output format for `/briefing`. One page, maximum signal.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CEO DIGEST — [Date, Day of Week]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXECUTIVE SUMMARY
[2-3 sentences. One sentence on where MRR stands vs. target.
One sentence on the highest-leverage thing happening right now.
One sentence on the biggest risk or open item needing attention today.]

NORTH STAR
  Net MRR:        $[X] / $5,000  ([X]%) — [X] days remaining ↑↓→
  Pipeline:        $[X] potential ([N] warm leads) ↑↓→
  Client Health:   [X]/100 avg ([N] at risk) ↑↓→
  Cash Position:   $[X] net available ↑↓→
  Content:         [N] posts / [target] target ([N] behind/ahead) ↑↓→

TOP 3 WINS THIS WEEK
  1. [Specific win — numbers where possible]
  2. [Specific win]
  3. [Specific win]

TOP 3 PRIORITIES NEXT WEEK
  1. [Specific priority — why it matters for MRR]
  2. [Specific priority]
  3. [Specific priority]

ALERTS (address today)
  [🔴 Client at risk: Name — reason — suggested action]
  [🔴 Missed deadline: Project — milestone — recovery plan]
  [🔴 System issue: What — impact — fix]
  [None if all clear]

TODAY'S #1 PRIORITY
→ [One specific action that moves the needle most right now]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Rules for the digest:**
- Executive summary is 3 sentences max. If it's longer, cut it.
- Top 3 wins must be specific. "Had good calls" is not a win. "Booked discovery call with [Name] — $1,500/mo potential" is.
- Alerts section only has real alerts. Empty is fine — don't invent items.
- Today's #1 priority is one action. Not three. One.

---

## Dashboard Cadence

| Dashboard | Frequency | Trigger | Tool |
|-----------|-----------|---------|------|
| North Star briefing | Daily (morning) | `/briefing` or session start | `ceo_dashboard.py briefing` |
| Full revenue dashboard | Weekly (Monday) | `/briefing` on Mondays | `ceo_dashboard.py revenue` |
| Pipeline dashboard | Weekly | Every Monday | `ceo_dashboard.py pipeline` |
| Full dashboard | Monthly | 1st of month | `ceo_dashboard.py full` |
| Content dashboard | Weekly | Friday review | Manual from Zernio (fmr. Late) posts |
| Client health | Weekly | After Monday briefing | `client_health.py report` |

---

## Integration Points

- **Live data** → `python scripts/ceo_dashboard.py briefing`
- **Revenue** → `python scripts/revenue_engine.py mrr --json`
- **Stripe** → `python scripts/stripe_tool.py subscriptions --status active --json`
- **Pipeline** → `memory/LEAD_TRACKER.csv`
- **Client health** → `python scripts/client_health.py report --json`
- **Content** → `python scripts/late_tool.py posts --status published`
- **Atlas CFO snapshot** → `C:\Users\User\APPS\trading-agent\brain\STATE.md` (read-only)

## Obsidian Links
- [[brain/STATE]] | [[brain/USER]] | [[memory/ACTIVE_TASKS]] | [[brain/CAPABILITIES]]
- [[skills/client-success/SKILL]] | [[skills/ceo-briefing/SKILL]]
- `/ceo-briefing` | `scripts/ceo_dashboard.py`
