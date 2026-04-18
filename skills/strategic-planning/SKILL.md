---
name: strategic-planning
description: CEO-level strategic planning framework — OKRs, annual strategy, scenario modeling, decision frameworks, QBR and weekly review templates
tags: [skill, strategy, planning, okr, ceo]
---

# Strategic Planning

## Overview

Strategy without execution is fiction. This skill turns CC's ambition into quarterly OKRs, scenario models, and weekly checkpoints that keep the $5,000 MRR north star visible every day.

**Trigger:** `/strategic-review`, "set OKRs", "quarterly planning", "run QBR", "what's the strategy"

**Related skills:** `skills/financial-modeling/SKILL.md`, `../../Marketing-Agent/skills/competitive-intelligence/SKILL.md`, `skills/ceo-briefing/SKILL.md`

---

## OKR Framework

### Rules for Setting OKRs

1. Max 3 Objectives per quarter. If you have 5, you have zero.
2. Each Objective gets 3-5 Key Results. No more.
3. Key Results are measurable — number, percentage, or date. "Improve X" is not a KR.
4. Objectives answer "what do we want to achieve?" KRs answer "how do we know we got there?"
5. 70% achievement is success. If you hit 100% every time, your targets are too easy.
6. OKRs are set at the start of the quarter and graded at the end. Don't change them mid-quarter.

### Quarterly OKR Template

```markdown
## OKRs — Q[X] [YEAR] ([Month] - [Month])

**Set:** [Date] | **Grade due:** [Last day of quarter]

---

### O1: [Objective — inspiring, qualitative, directional]

| # | Key Result | Owner | Start | Target | Current | Confidence |
|---|-----------|-------|-------|--------|---------|------------|
| KR1 | [Measurable outcome] | CC/Bravo | [baseline] | [number/date/%] | — | —% |
| KR2 | [Measurable outcome] | CC/Bravo | [baseline] | [number/date/%] | — | —% |
| KR3 | [Measurable outcome] | CC/Bravo | [baseline] | [number/date/%] | — | —% |

**Why this matters:** [1 sentence connecting to north star]

---

### O2: [Objective]

| # | Key Result | Owner | Start | Target | Current | Confidence |
|---|-----------|-------|-------|--------|---------|------------|
| KR1 | | | | | | |
| KR2 | | | | | | |
| KR3 | | | | | | |

---

### O3: [Objective]

| # | Key Result | Owner | Start | Target | Current | Confidence |
|---|-----------|-------|-------|--------|---------|------------|
| KR1 | | | | | | |
| KR2 | | | | | | |
| KR3 | | | | | | |
```

### Weekly OKR Check-In Format

Every Monday, update the Confidence column (0-100%):
- 0-30%: Off track — needs immediate intervention
- 31-60%: At risk — monitor closely, adjust tactics
- 61-80%: On track — continue current approach
- 81-100%: Ahead — maintain pace

```markdown
## OKR Check-In — Week of [Date]

| KR | Last Week's Confidence | This Week's Confidence | Delta | Blocker / Note |
|----|----------------------|----------------------|-------|----------------|
| O1-KR1 | X% | X% | +/- | |
| O1-KR2 | X% | X% | +/- | |
| O2-KR1 | X% | X% | +/- | |

**Action items this week:**
- [ ] [Action to move a lagging KR]
```

### Quarterly OKR Grading

Grade each KR on a 0.0-1.0 scale at quarter end:

| Score | Meaning |
|-------|---------|
| 0.0-0.3 | Failed — didn't make meaningful progress |
| 0.4-0.6 | Partial — progress made but fell short |
| 0.7-0.9 | Success — hit the target (this is the goal) |
| 1.0 | Exceeded — either a win or the target was too easy |

Average KR scores to get the Objective score. OKR grade = average of all Objective scores.

---

## Annual Strategic Planning

### Hierarchy

```
Vision (10-year: where are we going?)
  → Mission (why does this business exist?)
    → Annual Goals (what must be true by Dec 31?)
      → Quarterly OKRs (what do we ship in 90 days?)
        → Weekly Priorities (what moves the needle this week?)
```

### SWOT Analysis Template

```markdown
## SWOT — [Business/Product] — [Date]

### Strengths (internal, we control)
- [Specific advantage — not generic]
- [Specific advantage]
- [Specific advantage]

### Weaknesses (internal, we can fix)
- [Specific gap — not generic]
- [Specific gap]

### Opportunities (external, we can capture)
- [Specific market opportunity with signal]
- [Specific opportunity]

### Threats (external, we must mitigate)
- [Specific risk with probability estimate]
- [Specific risk]

### Strategic Implications
**Double down on:** [Strength × Opportunity]
**Fix urgently:** [Weakness blocking an Opportunity]
**Hedge against:** [Threat we can't ignore]
```

### Porter's Five Forces Template

```markdown
## Porter's Five Forces — [Market/Product] — [Date]

| Force | Rating (1-5) | Evidence | Strategic Response |
|-------|-------------|----------|-------------------|
| Threat of New Entrants | X/5 | [Why easy/hard to enter] | |
| Bargaining Power of Buyers | X/5 | [Client switching cost] | |
| Bargaining Power of Suppliers | X/5 | [Key dependencies] | |
| Threat of Substitutes | X/5 | [Alternatives available] | |
| Competitive Rivalry | X/5 | [Number and strength of competitors] | |

**Overall attractiveness:** [Favorable / Neutral / Unattractive]
**Recommended positioning:** [Where to compete based on force analysis]
```

### Blue Ocean Strategy Canvas

```markdown
## Blue Ocean Canvas — [Product] vs [Competitors] — [Date]

Rate 1-10 on each factor for each player:

| Compete Factor | [Competitor A] | [Competitor B] | [Our Product] | Target |
|---------------|---------------|---------------|--------------|--------|
| Price | | | | |
| Speed to value | | | | |
| Ease of use | | | | |
| [Factor specific to market] | | | | |
| [Factor specific to market] | | | | |

**Eliminate:** [Factors competitors invest in that buyers don't value]
**Reduce:** [Factors well below industry standard]
**Raise:** [Factors well above industry standard]
**Create:** [Factors the industry has never offered]

**Insight:** [The uncontested market space identified]
```

---

## Scenario Planning

### Bull / Base / Bear Model

For each planning cycle, define three scenarios before committing resources.

```markdown
## Scenario Model — [Initiative/Quarter] — [Date]

### Assumptions Matrix

| Variable | Bear | Base | Bull |
|----------|------|------|------|
| New clients per month | 0 | 1-2 | 3+ |
| Average deal size | $500 | $1,000 | $1,500 |
| Churn rate | 5%/mo | 2%/mo | 0.5%/mo |
| [Key variable] | [pessimistic] | [realistic] | [optimistic] |

### Financial Impact

| Metric | Bear | Base | Bull |
|--------|------|------|------|
| MRR at end of period | | | |
| Revenue change | | | |
| Cost change | | | |
| Net outcome | | | |

### Timeline
- **Bear:** Hits by [date] if [trigger]
- **Base:** Hits by [date] if [trigger]
- **Bull:** Hits by [date] if [trigger]

### Probability (must sum to 100%)
- Bear: X% | Base: X% | Bull: X%

### Expected Value = (Bear × P) + (Base × P) + (Bull × P)
= $X

### Trigger Events
| If this happens → | Shift to scenario | Action |
|-------------------|-----------------|--------|
| [Event] | Bear | [Specific response] |
| [Event] | Bull | [Specific response] |
```

### CC-Specific Scenarios (Q2 2026)

**Scenario: Bennett churns**
- Probability: 10% (friend relationship, no contract risk is low)
- Revenue impact: -$2,791/mo (drop from $2,982 to $191)
- Timeline: MRR collapses to $191 immediately
- Action: Emergency pipeline activation — 3 cold outreach campaigns, pitch deck ready, price list updated
- Prevention: Deliver high-visibility wins monthly, lock in a longer-term arrangement by April

**Scenario: 3 new clients in Q2**
- Probability: 60% (pipeline exists, 5 warm leads)
- Revenue impact: +$1,500-$3,000/mo (3 × $500-$1,000 retainers)
- Timeline: MRR $4,500-$6,000 by May 15
- Action: Content-led inbound + 1:1 outreach, 2 calls/week minimum
- North star hit: Likely

**Scenario: PropFlow launches to first 10 paying users**
- Probability: 40% (Adon's network, product partially built)
- Revenue impact: +$500-$1,000/mo (10 × $49-$99)
- Timeline: June 2026 if dev resumes now
- Action: Prioritize PropFlow MVP scope — landing page, auth, core CRM loop
- Dependency: Adon engagement

---

## Decision Framework

### Investment Decisions — Expected Value

```
EV = (Probability of Success × Upside) - (Probability of Failure × Downside)

If EV > 0 and you can afford the downside → take the bet
If EV > 0 but downside is catastrophic → hedge or reduce position
If EV < 0 → don't do it, regardless of how exciting it feels
```

Example: Hiring a VA at $800/mo
- P(success): 70% → generates $2,000/mo in recovered revenue
- P(failure): 30% → costs $800 and 2 weeks of onboarding
- EV = (0.7 × $2,000) - (0.3 × $800) = $1,400 - $240 = +$1,160/mo
- Decision: Take it. Payback: $800 ÷ $1,160 = 0.7 months.

### Strategic Pivots — Reversibility × Impact Matrix

```
HIGH IMPACT + REVERSIBLE  → Do it fast, iterate
HIGH IMPACT + IRREVERSIBLE → Decide slowly, execute decisively
LOW IMPACT + REVERSIBLE   → Delegate or automate
LOW IMPACT + IRREVERSIBLE → Avoid or delay
```

Irreversible decisions: dropping a product line, ending a client relationship, committing to a co-founder, signing a long lease.

### Hiring Decisions — ROI Timeline

```
Time to payback = Hiring cost ÷ Monthly value generated

Monthly value generated = (Tasks offloaded × CC's hourly rate) + (Revenue generated)

Acceptable payback threshold: ≤3 months for contractors, ≤6 months for full-time
```

### One-Way vs Two-Way Door (Bezos Framework)

- **Two-way door:** Reversible, low-cost to undo → decide fast with available info (Type 2)
- **One-way door:** Hard to reverse, high stakes → slow down, get more data (Type 1)

Most decisions are two-way doors. Treat them as such. Only slow down for genuine one-way doors.

---

## Quarterly Business Review (QBR) Template

```markdown
## QBR — Q[X] [YEAR] — [Date]

### 1. Financial Review
| Metric | Q[X-1] | Q[X] Actual | Q[X] Target | Delta |
|--------|--------|------------|------------|-------|
| MRR (end of quarter) | | | | |
| Total revenue | | | | |
| Total expenses | | | | |
| Gross margin % | | | | |
| Net profit | | | | |

**Key financial insight:** [1 sentence]

---

### 2. Pipeline Review
| Stage | Start of Q | End of Q | Change |
|-------|-----------|---------|--------|
| Leads (new) | | | |
| Qualified | | | |
| Proposals sent | | | |
| Closed won | | | |
| Closed lost | | | |

**Conversion rate:** [Leads → Won] = X%
**Average deal size:** $X
**Average sales cycle:** X days

---

### 3. Client Health Summary
| Client | MRR | Health | Deliverables | Risk |
|--------|-----|--------|-------------|------|
| [Name] | $X | HEALTHY/AT-RISK | [Status] | [None/Risk] |

**Net Revenue Retention this quarter:** X%

---

### 4. OKR Grades
| Objective | KR Scores | Objective Grade | Notes |
|-----------|----------|----------------|-------|
| O1: [Name] | X.X / X.X / X.X | X.X/1.0 | |
| O2: [Name] | X.X / X.X / X.X | X.X/1.0 | |
| O3: [Name] | X.X / X.X / X.X | X.X/1.0 | |

**Overall OKR score:** X.X/1.0

---

### 5. Competitive Positioning
- [Key competitive development this quarter]
- [Any positioning shifts needed]
- [Win/loss insights]

---

### 6. Top 3 Wins
1. [Specific win with impact]
2. [Specific win with impact]
3. [Specific win with impact]

### 7. Top 3 Misses
1. [What didn't happen and why]
2. [What didn't happen and why]
3. [What didn't happen and why]

---

### 8. Next Quarter OKR Draft
[Use OKR template above — based on learnings from this quarter]

---

### 9. Key Risks for Next Quarter
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk] | X% | [High/Med/Low] | [Action] |

---

### 10. Strategic Adjustments
- **Continue:** [What's working]
- **Stop:** [What's not working]
- **Start:** [What to add next quarter]
```

---

## Weekly CEO Review Template

Run every Monday morning. Target: 15 minutes.

```markdown
## Weekly CEO Review — Week of [Date]

### Revenue This Week
- MRR: $X,XXX (vs $X,XXX last week)
- Cash collected this week: $X
- Outstanding invoices: $X

### Pipeline Movements
- New leads this week: X
- Leads moved to qualified: X
- Proposals sent: X
- Deals closed: X ($X ARR)
- Deals lost: X (reason: [])

### Top 3 Priorities This Week
1. [Priority — specific deliverable — deadline]
2. [Priority — specific deliverable — deadline]
3. [Priority — specific deliverable — deadline]

### Blocked Items
- [What is stuck and what unblocks it]

### Last Week's Priorities — Did We Hit Them?
1. [Priority] — [YES/NO/PARTIAL]
2. [Priority] — [YES/NO/PARTIAL]
3. [Priority] — [YES/NO/PARTIAL]

### Next Week's Focus
[1 sentence on the single most important thing to accomplish]
```

---

## Integration

- **Data sources:** `python scripts/revenue_engine.py` for financial data, `python scripts/lead_engine.py pipeline` for pipeline
- **Competitive data:** `python scripts/competitive_intel.py report`
- **Financial modeling:** `python scripts/financial_model.py unit-economics`
- **Store OKRs:** `memory/ACTIVE_TASKS.md` for current quarter tracking, `brain/STATE.md` for north star progress
- **QBR cadence:** Last week of each quarter — run `/qbr` workflow

---

## OKR Scoring Methodology

Score each Key Result on a 0.0–1.0 scale at quarter end. Use this rubric consistently — do not adjust scores retrospectively based on what happened.

### Score Rubric

| Score | Color | Meaning | What to Do |
|-------|-------|---------|-----------|
| 0.0–0.3 | Red | Did not make meaningful progress | Root cause analysis required. Was the KR realistic? Was effort applied? |
| 0.4–0.6 | Yellow | Made progress but fell short of target | Partial credit. Carry forward or revise for next quarter. |
| 0.7–0.9 | Green | Hit the target — this is the goal zone | Validate and build on the success. |
| 1.0 | Blue | Exceeded target | Validate the win. Also ask: was the target too easy? |

**70% is the success threshold.** An average score of 0.7 across all KRs = a successful quarter. If you score 1.0 on everything, your targets were not ambitious enough.

### Calculating Objective Score

```
Objective Score = Average of all KR scores for that Objective

OKR Grade = Average of all Objective scores

Example:
  O1: KR scores = 0.8, 0.6, 0.9 → Objective score = 0.77 (Green)
  O2: KR scores = 0.4, 0.5, 0.3 → Objective score = 0.40 (Yellow)
  O3: KR scores = 1.0, 0.9, 0.8 → Objective score = 0.90 (Green)

  OKR Grade = (0.77 + 0.40 + 0.90) ÷ 3 = 0.69 (Yellow — just below target)
```

### Score Review Questions

After grading, answer these before setting next quarter's OKRs:

- Which KRs scored Red? Was it execution failure or unrealistic target?
- Which KRs scored 1.0? Should we set a harder target or declare victory and move on?
- Did any Objective become irrelevant mid-quarter? (If yes: add "OKR relevance review" to mid-quarter check-in process)

---

## Quarterly Planning Cadence

A structured 90-day cycle. Every quarter has the same shape.

### Week 1 (Planning Week)

Run during the first 5 days of the quarter.

- [ ] Complete QBR for the previous quarter (use QBR template above)
- [ ] Grade all OKRs from last quarter (use scoring rubric above)
- [ ] Identify the top 3 learnings from last quarter
- [ ] Draft next quarter's 3 Objectives — validate each: does it move the north star?
- [ ] Set 3–5 KRs per Objective — verify each is measurable and time-bound
- [ ] Assign resource allocation (see framework below)
- [ ] Publish OKRs to `brain/OKRs.md`

### Weeks 2–11 (Execution)

Every Monday:
- 15-minute OKR check-in (use weekly format above)
- Update Confidence column
- If any KR drops below 30% confidence — flag in `memory/ACTIVE_TASKS.md` and act this week

Every 30 days:
- Mid-quarter review: are the OKRs still the right ones?
- If a KR is clearly unreachable (< 20% confidence by week 6) → do not change the score target. Log what happened and redirect effort to reachable KRs.

### Week 12 (Close Week)

Final 5 days of the quarter:
- [ ] Final OKR scoring — freeze all scores
- [ ] Capture top 3 wins and top 3 misses
- [ ] Update `brain/STATE.md` with new MRR and north star progress
- [ ] Competitive positioning review — did anything change?
- [ ] Prep for Week 1 of next quarter

---

## Resource Allocation Framework

Before each quarter starts, define the time, money, and attention budgets. These are constraints — not wishes.

### Time Budget (CC's 168 hours/week)

Estimate based on current commitments:

```
| Block | Hours/Week | Non-Negotiable? |
|-------|-----------|----------------|
| Sleep (7hrs/night) | 49 | Yes |
| Nicky's Donuts (weekend job) | ~12 | Yes |
| Gym | ~5 | Yes — health is infrastructure |
| Client delivery work | ~15 | Yes — revenue at risk if missed |
| Sales (discovery calls, outreach) | ~8 | Yes — north star depends on this |
| Content creation | ~6 | Yes — #1 inbound source |
| Building / Bravo work | ~10 | Yes |
| Admin, comms, misc | ~5 | Yes |
| **Available for new commitments** | **~58** | Context-dependent |
```

Rule: Any new initiative must justify its time cost against the available budget. If it doesn't fit, something else comes out — not sleep.

### Money Budget (Monthly)

```
Fixed costs: $184/month
Variable capacity: remaining from MRR — set a monthly cap for new tool spend

Cap: No new tools > $50/month without a written ROI case (saves X hrs or generates $Y)
```

### Attention Budget

Max 3 active priorities at a time. Everything else is backlog.

```
Active priorities this quarter:
1. [Priority — the one that hits the north star fastest]
2. [Priority — the one that protects existing revenue]
3. [Priority — the one that builds future leverage]

Backlog (not this quarter):
- [Everything else — logged in memory/ACTIVE_TASKS.md as backlog]
```

---

## Strategic Pivot Criteria

When to double down vs when to pivot. Use this framework for major directional decisions.

### The Pivot Decision Matrix

Before considering a pivot, answer these 4 questions:

1. **Have we actually tested it?** If the strategy has not been executed for at least 90 days with full effort, it is not a pivot situation — it is an execution problem.

2. **Is the feedback signal clear?** Anecdote is not signal. Data is signal. What do the numbers say specifically?

3. **Is this a strategy failure or a tactics failure?** Strategy = what we're building and who it's for. Tactics = how we're reaching them. Changing tactics is not a pivot.

4. **What is the opportunity cost of not pivoting vs pivoting?**
   - Cost of staying: [X months of sub-target performance]
   - Cost of pivoting: [Sunk costs + transition time + new learning curve]

### Double Down When

- Early signs of product-market fit (NPS > 40, retention > 90%, referrals happening organically)
- Performance is below target but improving quarter-over-quarter
- The core thesis is still intact and the market is validated
- Root cause of underperformance is identifiable and fixable

### Pivot When

- Multiple quarters of flat or declining performance despite tactic changes
- A fundamentally better opportunity has emerged in the same market
- Core assumptions have been disproven by data (not feelings)
- The unit economics are structurally broken (LTV:CAC < 1)

### Pivot Types (in order of disruption)

1. **Zoom in** — narrow focus to one customer segment or use case (least disruptive)
2. **Zoom out** — broaden from feature to platform (adds scope, not direction change)
3. **Customer pivot** — same product, different buyer (medium disruption)
4. **Value capture pivot** — same product, different business model (medium-high disruption)
5. **Platform pivot** — the product becomes the enabler for something else (high disruption)
6. **Full pivot** — new direction (maximum disruption — rare and expensive)

---

## Obsidian Links
- [[brain/STATE]] | [[brain/USER]] | [[memory/ACTIVE_TASKS]] | [[brain/CAPABILITIES]]
- [[skills/financial-modeling/SKILL]] | [[../../Marketing-Agent/skills/competitive-intelligence/SKILL]] | [[skills/ceo-briefing/SKILL]]
