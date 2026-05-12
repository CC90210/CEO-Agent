---
name: Competitive Report
trigger: /competitive-report
schedule: monthly (first Monday of month)
description: Monthly competitive landscape scan — pricing changes, new features, review themes, battlecard updates
---

# Competitive Intelligence Report Workflow

## When to Run
- First Monday of every month
- Before any pricing strategy discussion
- After losing a deal to a specific competitor
- When CC asks "what are competitors doing?" or runs `/competitive-report`

## Announce at Start
"Running monthly competitive intelligence report — checking pricing, features, reviews, and positioning for tracked competitors."

---

## Step 1: Load Competitor List

```bash
python scripts/competitive_intel.py list --json
```

If no competitors are tracked, prompt CC:
"No competitors tracked yet. Add your first: `python scripts/competitive_intel.py add \"Company Name\" --url \"https://...\" --category direct`"

---

## Step 2: Pricing Page Check (Top 3 Competitors)

For each direct competitor, use Playwright to check their pricing page:

```
browser_navigate url="[competitor pricing_url]"
browser_snapshot
browser_evaluate function="() => document.body.innerText"
```

Compare against last recorded pricing in `data/competitors.json`. Note any:
- Price increases or decreases
- New plan tiers
- Changed feature limits
- Free tier changes

Update competitor record if changed:
```bash
python scripts/competitive_intel.py update "CompetitorName" --pricing '{"starter": "$X/mo"}' --notes "Price changed from $Y to $X on [date]"
```

---

## Step 3: Content and Product Scan

For each tracked competitor, check for new content/product activity:

Use Playwright to check:
- Their blog (`/blog` or `/resources`)
- Their changelog (`/changelog` or `/updates`)
- LinkedIn company page (last 30 days of posts)
- Their X/Twitter profile (last 30 days)

Note any:
- New feature announcements
- Product launches
- Marketing campaign pivots
- Leadership/hiring announcements

```bash
python scripts/competitive_intel.py update "CompetitorName" --notes "[finding]"
```

---

## Step 4: Job Posting Signals

Search LinkedIn for recent job postings from each direct competitor:

Signals to interpret:
- Sales roles → aggressive growth mode
- Engineering roles → building new features
- Customer success roles → user base growing or struggling
- Marketing roles → repositioning or new ICP

Note significant hiring signals:
```bash
python scripts/competitive_intel.py update "CompetitorName" --notes "[Date] Hiring 3 sales reps — growth mode signal"
```

---

## Step 5: Review Site Check

For each competitor with G2/Capterra presence, check for new reviews:

Platforms:
- G2: `g2.com/products/[slug]/reviews` — sort by "Most Recent"
- Capterra: `capterra.com/p/[product]/reviews`

Extract from 1-star reviews (weaknesses to exploit) and 5-star reviews (what customers love about them).

Update praise/complaints themes:
```bash
python scripts/competitive_intel.py update "CompetitorName" --praise "Fast onboarding, good integrations" --complaints "Poor customer support, limited customization"
```

---

## Step 6: Generate Full Report

```bash
python scripts/competitive_intel.py report
```

Review for:
- Stale profiles (Bravo will flag these automatically)
- Missing battlecards (any competitor without `our_counter_positioning` set)
- Win/loss analysis (pull from lead_engine this month)

---

## Step 7: Update Battlecards

For any competitor where positioning has shifted:

```bash
python scripts/competitive_intel.py battlecard "CompetitorName"
```

Update counter-positioning if their message has changed:
```bash
python scripts/competitive_intel.py update "CompetitorName" --counter-positioning "Updated response..."
```

---

## Step 8: Win/Loss This Month

```bash
python scripts/lead_engine.py list --status lost --json
```

For any lost deals, note which competitor won and why. Update the relevant battlecard's `loss_conditions`.

---

## Step 9: Log and Report

Log to the V6.0 state DB (auto-mirrors to `memory/SESSION_LOG.md`):
```bash
python scripts/state_manager.py log --agent bravo \
  --note "Monthly Competitive Report — reviewed [N] competitors, changes: [list], battlecards: [Y/N], key finding: [1 sentence]"
```

Present summary to CC:
```
## Competitive Report — [Month YEAR]

**Tracked:** [N] competitors

### Key Changes This Month
- [Competitor]: [What changed]
- [Competitor]: [What changed]

### Battlecards Updated
- [Competitor]: [What changed in positioning]

### Immediate Actions
- [Any urgent response needed]

### No Action Needed
- [Competitors with no meaningful changes]
```

---

## Rules
- Do NOT update a battlecard's `win_conditions` or `loss_conditions` without confirming with CC — these affect live sales conversations.
- Do NOT add a competitor as a "new entrant" without checking it's actually targeting OASIS AI's ICP.
- Pricing changes should always be logged with a date note, not just overwritten.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
