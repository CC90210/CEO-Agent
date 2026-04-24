---
name: Strategic Review
trigger: /strategic-review
schedule: quarterly
description: Comprehensive 90-day business review — financial performance, pipeline health, competitive position, OKR progress, and strategic recommendations
---

# Strategic Review Workflow

## When to Run
- End of each quarter (last week of March, June, September, December)
- When CC asks "how are we tracking?", "do a strategic review", or "run /strategic-review"
- Before setting next quarter's OKRs
- Before the QBR (`/qbr` workflow builds on this)

## Announce at Start
"Running strategic review — pulling live data across revenue, pipeline, competition, and OKRs."

---

## Step 1: Revenue Performance

Pull live MRR and revenue data:

```bash
python scripts/revenue_engine.py dashboard --json
python scripts/stripe_tool.py invoices --limit 20 --json
python scripts/revenue_engine.py history --months 3 --json
```

Calculate:
- MRR growth rate (MoM and QoQ)
- Gap to $5,000 target and days remaining
- Revenue vs expenses (net profit this quarter)
- Any one-time revenue vs recurring revenue split

---

## Step 2: Unit Economics

Run full financial model:

```bash
python scripts/financial_model.py unit-economics --json
python scripts/financial_model.py concentration --json
python scripts/financial_model.py runway --json
```

Flag immediately if:
- HHI > 0.75 (CRITICAL concentration)
- Runway < 6 months (burn alert)
- LTV:CAC < 3:1 (acquisition economics broken)

---

## Step 3: Pipeline Health

Pull current pipeline state:

```bash
python scripts/lead_engine.py pipeline --json
python scripts/lead_engine.py followups --json
```

Report:
- Total leads by stage (new → qualified → proposal → won/lost)
- Leads overdue for follow-up (7+ days no contact)
- Conversion rate this quarter (leads → closed won)
- Average deal size this quarter
- Pipeline value (sum of qualified + proposal stages)

---

## Step 4: Client Health

Check active client health from Supabase:

```bash
python scripts/supabase_tool.py select leads --project bravo --json
```

Filter for status = 'client'. For each:
- Days since last interaction
- Deliverable status (overdue?)
- Revenue contribution
- Flag AT-RISK if: no contact >14 days, or client = >50% of MRR with no contract

---

## Step 5: Competitive Position

Generate current competitive landscape:

```bash
python scripts/competitive_intel.py report --json
```

Identify:
- Any stale competitor profiles (not updated >30 days)
- New competitors or positioning changes to note
- Battlecard gaps (missing counter-positioning)
- Any win/loss patterns from this quarter's pipeline

---

## Step 6: OKR Progress

Read current OKRs from `memory/ACTIVE_TASKS.md`:
1. For each Key Result, assess current status vs target
2. Calculate confidence score (0-100%) for each KR
3. Identify any KRs at <40% confidence that need tactical intervention
4. Note any KRs at >90% that can be stretched

---

## Step 7: Synthesize and Present

Using `skills/strategic-planning/SKILL.md` QBR template, compile:

```
## Strategic Review — [Date]

### Headline Numbers
MRR: $X,XXX | Gap: $X,XXX | Days to target: X
Gross Margin: X% | Net/mo: $X,XXX | HHI: X.XX

### Revenue
[3-5 bullet points on revenue performance]

### Pipeline
[3-5 bullet points on pipeline health]

### Client Health
[Status per client — HEALTHY/AT-RISK/CRITICAL]

### Competitive
[Key developments this quarter]

### OKR Status
[Each objective with current score estimate]

### Top 3 Wins This Quarter
1.
2.
3.

### Top 3 Issues to Address
1.
2.
3.

### Recommended Strategic Adjustments
- Continue: [what's working]
- Stop: [what's not]
- Start: [what to add next quarter]
```

---

## Step 8: Log to Memory

```bash
# Update STATE.md with current strategic position
# Append summary to SESSION_LOG.md
```

Append to `memory/SESSION_LOG.md`:
```
### [DATE] — Strategic Review
Ran Q[X] strategic review. MRR: $X,XXX ([X]% of target). Top risk: [risk]. Top priority: [priority].
```

---

## Output
Present the full review to CC. Ask: "Want to run `/qbr` to grade OKRs and set next quarter's targets?"

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
