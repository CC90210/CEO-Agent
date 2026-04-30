---
tags: [sales, deals, partners, canonical]
---

# DEAL ARCHITECTURE — OASIS AI (V1.0, 2026-04-30)

> CC's restructured deal framework. Replaces old "implementation + retainer" hard-pitch flow with a value-quantified, free-trial-anchored model that makes saying yes a no-brainer. Strategic partners get equity-grade rev share; casual referrers get clean commissions.

## Why this exists

The old model — flat implementation fee + monthly retainer pitched cold — wasn't converting. The friction was real: prospects had to pay before they saw proof. Every objection collapsed into "I need to think about it" because we were asking them to take the risk.

**Bravo's read:** the value of what we sell is genuinely massive (1 process automated saves a service business 5-15 hours/week, $50K-300K of custom software value at exit). The math works. The ASK was the problem, not the offer. So we flip it: we take the risk, they see the result, then they pay. And we recruit a network around it instead of selling deal-by-deal in isolation.

## The Three Client Offers

### Offer 1 — One-Off Automation (most common)

| Stage | What happens | Duration | Cost to client |
|-------|--------------|----------|----------------|
| Discovery | 15-min call, identify ONE high-pain process | Free | $0 |
| Pilot Build | We build the automation, hand it over | 5-10 days | $0 |
| Free Trial | Client runs it in production | 14 days | $0 |
| Quantification | We measure: hours saved, errors prevented, revenue captured. Joint review call. | Day 14 | $0 |
| Conversion | Client pays implementation + locks in maintenance retainer | — | **$1,500 implementation + $400-800/mo retainer** |

**Why 14 days, not 30:** for clear single-process automations (lead routing, follow-up sequences, review responses, scheduling), value shows up within a week. 14 days is enough for proof, not so long that the client forgets why they signed up.

**Conversion clause (in scope doc):** "If the automation does not save you at least [N] hours/week or [$M]/month in measurable value, you owe nothing. Otherwise the implementation fee + retainer activates on day 15."

**Walk-away math:** if 1 in 4 pilots converts, our effective build cost is 4× — still profitable on the lifetime retainer. If 2 in 4 convert, we're printing.

### Offer 2 — Custom Software Build (Gritly-style, what landed Jonathan)

| Stage | What happens | Duration | Cost to client |
|-------|--------------|----------|----------------|
| Strategy Session | Map their use cases, scope the build | Free | $0 |
| Scope + Quote | Fixed-price quote, no retainer until live | 1 week | $0 |
| Build | We build, they have weekly demos | 4-12 weeks | **50% deposit on signed scope** |
| Launch | Software goes live | — | **50% balance + maintenance retainer activates** |
| Ongoing | Support, evolution, asset stays theirs | Ongoing | **$300-1,500/mo maintenance** |

**Why this works:** the client OWNS the software. It's an asset on their balance sheet that increases business sale value at exit (Jonathan's hook — 15-year exit value angle).

### Offer 3 — C-Suite AI Consulting (associate-grade access)

| Stage | What happens | Duration | Cost to client |
|-------|--------------|----------|----------------|
| Pitch Call | Define the strategic problem | 30 min | Free |
| Strategy Sprint | 1 deliverable: roadmap, audit, or system design | 7 days | **One-off $1,500-3,000** |
| Retainer | Async access + monthly Google Meets | Monthly | **$450-1,500/mo** |

**Why this works for Alejandro-tier prospects:** they're already paying for advisory somewhere. We position as the AI-native fractional CTO/strategist. Lower volume, higher margin, builds the brand.

## Partner Tiers (the recruitment layer)

Goal: don't sell deal-by-deal forever. Build a network that brings deals to us. Partners are graded by what they bring to the table.

### Tier 1 — Strategic Partners (50% rev share)
**Who qualifies:**
- Brings 3+ qualified introductions per quarter
- Has direct decision-maker relationships in our target verticals (HVAC, real estate, dental, professional services)
- Co-sells (joins discovery calls, vouches for us, closes deals with us)
- Has their own brand authority (consultants, business coaches, agencies with adjacent services)

**The deal:**
- 50% of net revenue (implementation + retainer) on every deal they originate, for the lifetime of the client
- Paid monthly via Stripe split (or invoice if simpler)
- Co-branded option: their logo on the work they sourced
- 90-day exclusivity in their vertical (we don't sign their direct competitor on their list)

**Why this generosity makes sense:** if a partner reliably sources 4 clients/year averaging $600/mo retainer + $1,500 implementation, that's $34K/year of revenue we wouldn't have. Half of that ($17K) is still pure upside, and it scales without our cold outreach burning hours. The math compares to a salaried sales hire: $17K paid only when revenue lands beats $60K salary with no guarantee.

### Tier 2 — Network Referrers (5-15% commission)
**Who qualifies:**
- Casually plugged into a target vertical (one-off "you should talk to Conaugh" intros)
- No co-selling, just warm intro
- Friends-of-friends, satisfied clients, social network

**The deal:**
- 10% of first-year retainer revenue, OR
- 5% of implementation + 10% of first 6 months retainer (smoother for the partner if they want a quicker payout), OR
- Flat $200 finder's fee at deal close (for one-off referrers who don't want ongoing tracking)

**Pick the structure that the referrer prefers** — whatever closes the loop.

### Tier 3 — Affiliate (5% flat, future, not active yet)
For when we have content traffic / a course product. Not the play right now.

## Partner Recruitment Pitch (script-grade)

> "I'm building a partner network around OASIS — basically, anyone who's already trusted in [their vertical] and wants a no-friction way to bring AI into their book of business. I don't sell into your clients without you. You stay the relationship owner. We just plug in the AI piece, you get half of every deal we close together. If that's interesting, I'll send you the one-pager. If it's not, no harm — just figured you'd be the right call to make."

## What This Replaces

- ❌ Cold pitch with implementation + retainer up front (high friction, low conversion)
- ❌ Hourly consulting (capped income, no asset value)
- ❌ One-shot project work without retainer (no recurring revenue)

## Tracking + Hygiene

| Item | Where it lives | Owner |
|------|---------------|-------|
| Partner agreements | `contracts/partners/[name]_v1.pdf` | CC + lawyer (light) |
| Pilot conversion stats | `data/pilot_outcomes.json` | Bravo |
| Partner-sourced deals | `lead_interactions.metadata.partner_id` | Bravo (CRM) |
| Commission ledger | Stripe Connect or monthly invoice | CC |

## Risks to watch

1. **Pilot defaults** — client sees value but plays "didn't notice the difference" to dodge payment. Mitigation: written, signed scope doc with measurable conversion criteria. Every pilot has a SLA.
2. **Partner cannibalization** — strategic partner takes our process, hires their own dev, cuts us out. Mitigation: 50% is generous enough that DIY economics don't beat it for the first 18 months.
3. **Free trial drift** — clients extending the trial indefinitely. Mitigation: hard 14-day calendar, system access revokes day 15 unless paid.

## Status

**Active as of 2026-04-30.** First test deals: any cold call closing this week uses Offer 1. Jonathan Hutton (Basque Landscaping) closes under Offer 2. Alejandro deal already in flight as Offer 3.

## Obsidian Links
- [[brain/CLIENT_READY]] | [[skills/sales-closing/SKILL]] | [[skills/proposal-generation/SKILL]]
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]]
