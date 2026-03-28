---
name: competitive-intelligence
description: Systematic competitor tracking, battlecard generation, market monitoring, and competitive response playbook for OASIS AI, PropFlow, and Nostalgic Requests
tags: [skill, competitive-intelligence, market-research, strategy]
---

# Competitive Intelligence

## Overview

Competitors move. Pricing changes. Features launch. New players enter. Without a monitoring system, CC finds out after losing a deal. This skill builds the intel engine that keeps OASIS AI, PropFlow, and Nostalgic Requests a step ahead.

**Trigger:** `/competitive-report`, "who are our competitors", "competitive analysis", "battlecard for [company]"

**CLI tool:** `python scripts/competitive_intel.py`

**Data store:** `data/competitors.json`

---

## Competitor Tracking Framework

### Categories to Monitor

| Category | Why It Matters | How Often |
|----------|---------------|-----------|
| Pricing | Direct deal impact — prospects compare before calling | Weekly |
| Feature launches | Differentiation erosion | Monthly |
| Positioning / messaging | How they're framing the category | Monthly |
| Hiring signals | Where they're investing (headcount by dept = growth bets) | Monthly |
| Funding / acquisitions | War chest size changes the competitive dynamic | Quarterly |
| Customer reviews (G2, Capterra) | Reveals real weaknesses we can exploit | Monthly |
| Content strategy | What topics they own, where we can out-rank | Weekly |

### Competitor Profile Template

```markdown
## Competitor Profile: [Company Name]

**Last updated:** [Date]
**Monitored by:** Bravo

### Overview
- **URL:** [homepage]
- **Pricing page:** [URL]
- **Category:** [direct / indirect / aspirational]
- **Founded:** [year]
- **Funding:** [bootstrapped / raised $X]
- **Team size:** [est. headcount]

### Target Market
- **Primary buyer:** [title, industry, company size]
- **Geography:** [local / national / global]
- **Pain point they solve:** [1-2 sentences]

### Pricing
| Plan | Price | Includes |
|------|-------|---------|
| [Plan name] | $X/mo | [Key features] |
| [Plan name] | $X/mo | [Key features] |

**Pricing model:** [per seat / flat / usage-based / retainer]
**Free tier:** [yes/no — what's included]

### Core Features
- [Feature 1]
- [Feature 2]
- [Feature 3]

### Strengths
- [Specific strength with evidence]
- [Specific strength]

### Weaknesses
- [Specific gap with evidence — reviews, missing features, complaints]
- [Specific gap]

### Differentiation vs Us
| Factor | Them | Us | Winner |
|--------|------|----|--------|
| Price | | | |
| Speed to value | | | |
| Automation depth | | | |
| Local focus | | | |
| Support | | | |

### Recent Activity
- [Date]: [Product update / funding / pricing change / hire]
- [Date]: [Event]

### Review Themes (G2/Capterra)
- **Top praise:** [What customers love]
- **Top complaints:** [What customers hate — these are our openings]
```

### Battlecard Template

Battlecards are CC's pre-call cheat sheets. One page per competitor. When a prospect mentions a competitor name, pull this.

```markdown
## Battlecard: [Competitor Name] vs OASIS AI Solutions

**Last updated:** [Date]

### How They Position Themselves
[1-2 sentences — what is their core message? What do they say they are?]

### How We Position Against Them
[1-2 sentences — how do we frame ourselves when they come up in conversation?]

### Where We Win
- **[Win condition]:** [Why we beat them — specific, not generic]
- **[Win condition]:** [Evidence or proof point]
- **[Win condition]:** [Specific feature or outcome]

### Where We Lose
- **[Loss condition]:** [Be honest — where do they beat us?]
- **[Loss condition]:** [How to handle this objection]

### Handle the "Why not [Competitor]?" Objection
Prospect says: "I was also looking at [Competitor]."
CC says: "[Specific response — use NEPQ framing, not feature-dumping]"

### Proof Point
[A specific result, case study, or fact that beats them on their own turf]

### Disqualifiers (when we should lose gracefully)
- [Situation where the competitor genuinely is the better fit]
```

---

## Monitoring Cadence

### Weekly (Every Monday — 10 min)

1. Check competitor pricing pages for changes (Playwright automation)
2. Scan new blog posts / product updates on their sites
3. Check X/LinkedIn for competitor activity
4. Note any changes in `data/competitors.json`

### Monthly (First Monday of month — 30 min)

1. Pull G2/Capterra/Trustpilot new reviews for top 3 competitors
2. Check LinkedIn job postings (signals growth areas)
3. Review any feature launches or product announcements
4. Update battlecards if positioning has shifted
5. Generate monthly competitive summary: `python scripts/competitive_intel.py report`

### Quarterly (QBR week)

1. Full competitive landscape review — any new entrants?
2. Market sizing update (is the pie growing?)
3. Win/loss analysis: did we beat or lose to specific competitors?
4. Positioning review: is our differentiation still sharp?
5. Feed findings into quarterly SWOT

---

## Data Collection Methods

### Playwright Automation (Pricing Scrapes)

```python
# Pattern for monitoring competitor pricing pages
browser_navigate url="https://competitor.com/pricing"
browser_snapshot  # Get page structure
browser_evaluate function="() => document.querySelector('.pricing-card').innerText"
```

Schedule via cron or n8n workflow. Alert when page content hash changes.

### OpenCLI Discovery

```bash
opencli explore https://competitor.com  # Discover all public pages and API endpoints
```

Useful for finding:
- Hidden pricing tiers
- Feature documentation
- API limitations

### Job Posting Signals

LinkedIn searches to run monthly:

```
site:linkedin.com/jobs "[Company Name]" "sales"     → hiring sales = scaling
site:linkedin.com/jobs "[Company Name]" "engineer"  → hiring engineers = building
site:linkedin.com/jobs "[Company Name]" "support"   → hiring support = user growth
```

Interpret signals:
- Heavy sales hiring → aggressive growth mode → pricing pressure coming
- Heavy engineering hiring → major feature launch in 6-12 months
- Support hiring → user base growing OR product has issues

### Review Site Monitoring

Platforms to check monthly:
- **G2:** `g2.com/products/[product-slug]/reviews`
- **Capterra:** `capterra.com/p/[product]/reviews`
- **Trustpilot:** `trustpilot.com/review/[domain]`

What to extract:
- 1-star and 5-star reviews (extremes reveal true character)
- Recurring complaint themes → our selling angles
- Feature requests → roadmap intelligence

---

## Analysis Frameworks

### Feature Comparison Matrix

```markdown
## Feature Matrix — [Our Product] vs Competitors — [Date]

| Feature | [Us] | [Comp A] | [Comp B] | [Comp C] |
|---------|------|---------|---------|---------|
| [Feature] | ✅ | ✅ | ❌ | ✅ |
| [Feature] | ✅ | ❌ | ✅ | ❌ |
| [Feature] | ✅ | ❌ | ❌ | ❌ |
| [Feature] | ❌ | ✅ | ✅ | ✅ |

**Our unique features** (checkmarks only in our column): [list]
**Their unique features** (gaps for us to close or dismiss): [list]
**Table stakes** (everyone has it — don't lead with this): [list]
```

### Pricing Positioning Map

Plot competitors on a 2×2:

```
High Price
     |
[B]  |  [Premium]
     |
     +-------------- High Value
     |
[Cheap] | [C]
     |
Low Price
```

Where does OASIS AI sit? Where should we sit? This informs pricing strategy.

### Win/Loss Analysis

Track every competitive sales outcome:

```markdown
## Win/Loss Log

| Date | Prospect | Competitor | Outcome | Reason | Learning |
|------|---------|-----------|---------|--------|---------|
| [Date] | [Name] | [Comp] | Won/Lost | [1 sentence] | [1 sentence] |
```

Calculate quarterly:
- Win rate vs [Competitor A]: X%
- Win rate vs [Competitor B]: X%
- Most common loss reason: [theme]
- Most common win reason: [theme]

### Differentiation Gap Analysis

Every quarter, score your differentiation (1=parity, 5=clear leader):

```markdown
## Differentiation Gaps — [Date]

| Axis | Our Score | Best Competitor Score | Gap | Priority |
|------|----------|----------------------|-----|---------|
| AI automation depth | X/5 | X/5 | +X/-X | High/Med/Low |
| Local market knowledge | X/5 | X/5 | +X/-X | |
| Onboarding speed | X/5 | X/5 | +X/-X | |
| Price | X/5 | X/5 | +X/-X | |
| Support responsiveness | X/5 | X/5 | +X/-X | |

**Defensive priorities** (where we're losing ground): [list]
**Attack priorities** (where we can widen the gap): [list]
```

---

## Competitive Response Playbook

### Competitor Launches New Feature

1. Evaluate: Does this erode a key differentiator?
   - Yes, meaningful differentiator → prioritize response. Add to roadmap within 90 days.
   - No, table stakes → note it, don't panic.
2. Check customer reviews: Are existing users excited or indifferent?
3. Update battlecard if it changes the competitive conversation.
4. Content opportunity: Write a comparison post or explainer before they build authority on the topic.

### Competitor Drops Price

1. Immediate check: Who is this targeting? Our segment or a different one?
2. Analyze: Is this a race to the bottom (panic) or strategic expansion (different ICP)?
3. Do NOT immediately match. Hold for 2 weeks and measure if deals are actually affected.
4. If 2+ deals cite competitor pricing as the loss reason → convene pricing review.
5. Response options ranked by preference:
   - **Differentiate** (best): Double down on value we deliver that they don't. Reframe price.
   - **Bundle** (good): Add value to our offering rather than cutting price.
   - **Segment** (ok): Match price for a new entry-tier, protect premium pricing above it.
   - **Match** (last resort): Only if losing significant volume to this competitor specifically.

### Competitor Raises Funding

1. Note the amount and stage (Seed vs Series A/B changes the threat level).
2. Ask: What will they build/buy with this? (Job postings in 30 days will answer this.)
3. Assess timeline: They'll be distracted with hiring and reporting for 3-6 months — move fast now.
4. Accelerate any roadmap items that compete directly with their likely investment areas.

### Competitor Shuts Down

1. Identify their customers immediately (social media, Capterra reviews, their community).
2. Reach out within 48 hours — these are warm leads with an urgent pain.
3. Offer a migration incentive (first month free, data import help).
4. Create a comparison landing page: "[Competitor] Alternative" for SEO capture.

---

## OASIS AI Competitor Categories

### Category 1: AI Automation Agencies (Direct)

Local and regional agencies offering similar done-for-you AI/automation services.

**Competitive reality:** Most charge more (agency rates $150-$300/hr) but deliver less (no proprietary tech). Win angle: systematic delivery at lower cost via owned tooling (Bravo itself).

**Watch list:** Any agency within Ontario targeting HVAC, Wellness, Real Estate. Google "AI automation agency [city]" monthly.

### Category 2: No-Code Automation Platforms (Indirect)

Make.com, Zapier, n8n Cloud — the DIY alternative to hiring CC.

**Competitive reality:** These are tools, not services. Prospects using these are actually good leads — they want automation but are struggling to maintain it themselves.

**Win angle:** "You're spending 5 hours/week on Zapier. We'll own that, plus build what you can't."

**Pricing context:** Make Business plan = $59/mo. We charge $500-$1,500/mo. Position as "they give you the ingredients, we cook the meal."

### Category 3: Vertical SaaS for HVAC/Service (Indirect)

ServiceTitan, Jobber, Housecall Pro — built specifically for trades businesses.

**Competitive reality:** These are software products, not AI automation. They handle scheduling and invoicing but not custom AI workflows. Often CC's integrations enhance these tools rather than competing.

**Win angle:** "You already have [Jobber]. We make it 10x more productive with AI on top."

### Category 4: General AI Assistant Products

Lindy, Sintra, Relevance AI — AI agent platforms marketed to SMBs.

**Competitive reality:** These are horizontal — no vertical depth, no human expertise layer. Small businesses often feel abandoned after purchasing.

**Win angle:** "These platforms are DIY. We're done-for-you with human accountability."

---

## CLI Reference

```bash
# Add a competitor
python scripts/competitive_intel.py add "Lindy AI" --url "https://lindy.ai" --category "indirect"

# View all competitors
python scripts/competitive_intel.py list

# Generate full competitive report
python scripts/competitive_intel.py report

# Generate battlecard
python scripts/competitive_intel.py battlecard "Make.com"

# Update competitor data
python scripts/competitive_intel.py update "Lindy AI" --notes "Raised Series A"

# JSON output for agent consumption
python scripts/competitive_intel.py report --json
```

---

## Obsidian Links
- [[brain/STATE]] | [[skills/strategic-planning/SKILL]] | [[skills/financial-modeling/SKILL]]
- [[skills/market-research/SKILL]] | [[memory/ACTIVE_TASKS]] | [[brain/CAPABILITIES]]
