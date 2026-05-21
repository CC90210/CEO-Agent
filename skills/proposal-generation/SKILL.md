---
name: proposal-generation
description: Generate proposals, SOWs, and NDAs for OASIS AI Solutions. Covers discovery proposals, retainer proposals, and project-based SOWs with Good/Better/Best pricing tiers. Uses proposal_generator.py.
tags: [skill, proposal-generation, sales, client]
triggers: ["proposal generation", "use proposal generation", "run proposal generation", "generate proposals"]
---

# Proposal Generation — OASIS AI Solutions

## Overview

Every proposal is a sales document, not a document dump. The goal is to make the client feel understood, make the solution feel inevitable, and make saying yes the obvious next step.

**Primary tool:** `python scripts/proposal_generator.py`
**Output directory:** `proposals/` (date-stamped markdown files)
**Follow-up cadence:** Logged in Supabase against the lead record

---

## Proposal Types

| Type | When to Use | Typical Length |
|------|------------|---------------|
| **Discovery** | First paid engagement with an unknown client | 1–2 pages |
| **Retainer** | Ongoing monthly automation work | 3–5 pages |
| **Project** | One-time deliverable with a defined end | 3–5 pages |
| **SOW** | Detailed scope appendix attached to any proposal | 1–3 pages |

---

## Proposal Structure

Every proposal follows this section order. Do not reorder. Do not skip sections.

### 1. Executive Summary

Write this in the client's language, describing their problem. Not our solution — their problem.

Template:
> "[Client Name] is a [type of business] that [core function]. Right now, [specific bottleneck] is costing the team [time/money/opportunity]. The biggest drag is [root cause]. This proposal outlines how OASIS AI will [one-sentence solution] so [client] can [business outcome]."

Rules:
- No more than 3 sentences
- Use words the client used in your discovery call
- Do not mention AI unless the client already used that word

### 2. Proposed Solution

Describe what we will build or automate. Concrete and specific — no generic "AI transformation" language.

Template:
> "We will build [specific system] that [does X], connected to [tool they already use] to [outcome]. This replaces the manual process of [what they currently do by hand]. The result: [measurable impact]."

Include a 3-bullet "What You Get" summary for scannability.

### 3. Scope of Work

List every deliverable with an acceptance criterion. No open-ended deliverables.

Template:
```
| Deliverable | Description | Acceptance Criterion | Timeline |
|-------------|-------------|---------------------|----------|
| [Name] | [What it is] | [How we both know it's done] | Week X |
```

Rules:
- Each deliverable has exactly one acceptance criterion
- If you cannot define the acceptance criterion, the deliverable is not scoped — do not include it
- Include "Not included in this scope" section to prevent scope creep disputes

### 4. Timeline

Break the work into phases. Every phase has a start date, end date, and milestone.

Template:
```
Phase 1: Discovery & Setup (Week 1–2)
  - Access to client accounts and systems
  - Milestone: All integrations confirmed and credentials received

Phase 2: Build (Week 3–5)
  - Core automation built and tested in staging
  - Milestone: Client reviews and approves in staging environment

Phase 3: Launch & Handoff (Week 6)
  - Live deployment and go-live support
  - Milestone: Client confirms system is operating correctly
```

For retainers: replace phases with a "First 30 Days" plan + ongoing rhythm.

### 5. Investment

Always present three tiers. Never present one price — it gives the client a yes/no choice instead of a tier choice.

#### Retainer Pricing Tiers

| Tier | Monthly Investment | What's Included |
|------|-------------------|-----------------|
| **Starter** | $500–$1,500/mo | 1–2 automations, async support, monthly report |
| **Growth** | $1,500–$3,000/mo | 3–5 automations, bi-weekly calls, priority support, full reporting |
| **Scale** | $3,000–$5,000/mo | Unlimited automations, weekly calls, dedicated Slack, custom dashboards |

#### Project Pricing Tiers

| Tier | Investment | Scope |
|------|-----------|-------|
| **Essential** | $2,000–$4,000 | Core deliverables only, 1 revision round |
| **Complete** | $4,000–$8,000 | Full scope, 2 revision rounds, 30-day support |
| **Premium** | $8,000–$15,000 | Full scope, unlimited revisions, 90-day support, training session |

#### Discovery Engagement

Flat fee: $500–$1,500 depending on complexity.
Deliverable: Written automation audit + recommended roadmap.
Applies toward first retainer or project if client proceeds within 30 days.

#### Payment Schedule (Standard)

- Retainer: First month upfront, then monthly on the 1st
- Project under $5K: 50% upfront, 50% on final delivery
- Project $5K+: 33% upfront, 33% at midpoint milestone, 33% on delivery

### 6. Terms

Include these clauses in plain English. Do not use legal jargon.

```
Payment: [per schedule above]

Revisions: [X] rounds included. Additional rounds billed at $150/hr.

Intellectual Property: All custom code and systems built for [client] become their property upon final payment. Bravo retains the right to use anonymized results for case studies unless client requests otherwise.

Confidentiality: Both parties agree to keep all shared business information confidential. A mutual NDA is available on request.

Termination: Either party may terminate with 30 days' written notice. Client is responsible for fees through the final 30 days.

Response Time: We commit to responding to all client messages within 1 business day.
```

### 7. About OASIS AI

One paragraph maximum. No bullet lists. Human and confident — not corporate.

> "OASIS AI Solutions helps small and mid-sized businesses automate the work that's eating their time and capping their growth. Founded by Conaugh McKenna, we've built automation systems for [industries], consistently cutting manual work by [X%] and [outcome]. We work with a select number of clients at a time to ensure every engagement gets full attention."

Add one relevant result specific to the client's industry if available.

### 8. Next Steps

Clear call to action with a deadline to create urgency without pressure.

Template:
> "To move forward, reply to this email with your preferred tier, and I'll send the contract and first invoice within 24 hours. If you have questions, book a 20-minute call here: [link].
>
> This proposal is valid for 14 days from [date sent]."

---

## SOW Template

A Statement of Work is attached when scope complexity requires more granularity than the main proposal.

```markdown
# Statement of Work
**Project:** [Name]
**Client:** [Company]
**Prepared by:** Conaugh McKenna, OASIS AI Solutions
**Date:** [Date]
**SOW Version:** 1.0

## Project Overview
[2–3 sentences on what's being built and why]

## Deliverables

### Deliverable 1: [Name]
- **Description:** [What it is]
- **Acceptance Criteria:** [Exact conditions for sign-off]
- **Dependencies:** [What we need from the client to deliver this]
- **Timeline:** [Target date]

[Repeat for each deliverable]

## Change Order Process
Any work outside this SOW requires a written change order before it begins.
Change orders are billed at $150/hr or negotiated as a fixed add-on.
Neither party is obligated to execute a change order.

## Assumptions
This SOW assumes:
- Client provides credentials and access within 3 business days of contract signing
- Client is available for a 30-minute feedback call within 48 hours of any deliverable submission
- [Any other key assumptions]

## Out of Scope
The following are explicitly excluded:
- [Item 1]
- [Item 2]
```

---

## NDA Template Structure

Only required when sharing proprietary systems or internal business data.

Clauses to include:
1. Definition of Confidential Information (what qualifies)
2. Obligations of both parties (what each must do to protect it)
3. Exclusions (what is not confidential: public info, independently developed)
4. Term (duration of the agreement — standard: 2 years)
5. Return or destruction of materials on request
6. Governing law (Ontario, Canada for OASIS AI engagements)

Use `scripts/contract_generator/generator.py` — it already includes NDA generation.

---

## Follow-Up Cadence After Proposal Sent

Log the proposal send date in Supabase. Trigger follow-ups on this schedule:

| Day | Action | Channel | Message Tone |
|-----|--------|---------|-------------|
| Day 1 | Confirm receipt | Text/Slack | "Just sent — let me know if anything needs clarifying" |
| Day 3 | Value reminder | Email | Share a relevant result or case study — not "following up" |
| Day 7 | Direct ask | Call | "Had a chance to review? Happy to answer questions live." |
| Day 14 | Final touch | Email | "Proposal expires [date]. Happy to extend if you need more time." |

If no response after Day 14: move lead status to `proposal-expired` in Supabase. Set a 30-day reminder for a cold re-engage.

---

## Win/Loss Analysis Framework

After every proposal outcome (won or lost), log to Supabase `proposals` table:

```
Fields to log:
- client_name
- proposal_type (discovery / retainer / project)
- tier_presented (starter / growth / scale)
- tier_selected (if won)
- decision_date
- outcome (won / lost / no_decision)
- loss_reason (price / timing / competitor / no_fit / budget / other)
- win_reason (trust / price / speed / referral / content / other)
- mrr_added (if won)
- deal_value (if project)
- notes
```

**Monthly Win/Loss Review:**
- Win rate by proposal type
- Win rate by tier
- Most common loss reasons (top 3)
- Average days from proposal send to decision
- Action: If win rate drops below 30% for any proposal type, review positioning and pricing

---

## Proposal Checklist

Before sending any proposal, verify:

```
[ ] Executive summary uses client's exact words from discovery call
[ ] Solution section names specific tools/systems (not generic "automation")
[ ] Every deliverable has a defined acceptance criterion
[ ] Three pricing tiers are presented (not one)
[ ] Payment schedule is explicit
[ ] Proposal expiration date is included
[ ] "About OASIS AI" is one paragraph or less
[ ] Next steps have a single, clear CTA
[ ] File saved to proposals/ with date-stamped filename
[ ] Supabase lead record updated with proposal_sent date and tier
```

---

## Integration Points

- **Contract Generator:** `scripts/contract_generator/generator.py` handles NDA + invoice after proposal is accepted
- **Lead Engine:** `python scripts/lead_engine.py update <id> --status proposal` when proposal is sent
- **Client Health:** After client signs, `lead_engine.py update <id> --status client` triggers onboarding
- **CEO Briefing:** Active proposals surface in Section 2 (Pipeline Health) of the daily briefing

---

## Value-First Proposal Structure

The default structure leads with ROI, not features. Prospects buy outcomes — not deliverables.

**Wrong order (features-first):**
Executive Summary → What We'll Build → Scope → Timeline → Price

**Right order (value-first):**
The Problem → The Outcome → Proof It Works → How We Do It → Investment → Next Steps

Rewrite each section with this lens:

### Reframe: Executive Summary → "The Cost of Today"

Lead with a specific dollar or hour figure representing what the current situation is costing them. Use their numbers from discovery.

> "Right now, [Client Name]'s team spends approximately [X hours/week] on [manual task]. At [their hourly value or opportunity cost], that's [$X] per month in time cost — before accounting for the [leads missed / delays / errors] that come with doing this manually."

Then one sentence on the outcome: "This proposal shows how to close that gap in 30 days."

### Reframe: Proposed Solution → "What Changes"

Frame the deliverables as before-and-after states. Not "we will build an automation" — "today you spend 3 hours on X; after this, it takes 0."

```
Today: [Current state — specific, uses their words]
After: [Future state — specific, measurable, theirs to own]
```

---

## Pricing Psychology

### Anchor High

Always present the highest tier first in the investment section. The first number sets the reference point. Everything after it feels like a relief, not a cost.

Order: Scale ($3,000–$5,000) → Growth ($1,500–$3,000) → Starter ($500–$1,500)

Describe Scale fully and specifically before mentioning the others. Most clients will land on Growth — but anchoring to Scale makes Growth feel reasonable.

### Show Savings (Not Just Price)

For each tier, show what the client gets back — not just what they pay.

| Tier | Monthly Investment | Est. Hours Saved | Est. Revenue Impact | Payback Period |
|------|-------------------|-----------------|--------------------|----|
| Scale | $3,500/mo | 40 hrs/mo | $8,000+ | <1 month |
| Growth | $2,000/mo | 22 hrs/mo | $4,500+ | <1 month |
| Starter | $750/mo | 8 hrs/mo | $1,800+ | <1 month |

Note: Use conservative estimates. Being right is better than being impressive and wrong.

### The Middle Tier Anchor (Goldilocks)

Highlight the Growth tier as the recommended option. Bold it. Add one sentence: "Most clients in your situation start here — it covers the core outcomes without overbuilding before you've seen the results."

This is not manipulation — it's guidance. Most clients are lost without a recommendation.

### Payment Gate Strategy

For projects, tie payment gates to milestones that are visible and controllable:

```
Gate 1 (33% upfront): Kickoff — access granted, onboarding complete
Gate 2 (33% at midpoint): [Specific deliverable] approved by client
Gate 3 (33% at completion): Go-live confirmed, client signs off

Rule: Never require final payment before client has seen it work.
This reduces payment disputes by ~80% and builds trust in the relationship.
```

---

## Social Proof Integration

Every proposal should include at least one proof element. Match proof to the client's industry or pain point.

### Proof Hierarchy (strongest to weakest)

1. **Specific metrics from a named client** — "We built a lead capture system for a Collingwood HVAC company that increased qualified leads by 34% in 60 days."
2. **Specific metrics from an anonymous client** — "For a local wellness clinic, we automated appointment follow-ups and reduced no-shows from 22% to 8%."
3. **Outcome statement without metrics** — "We've helped service businesses like yours eliminate the manual bottlenecks that slow down growth."
4. **Testimonial quote** — Use verbatim, with name and company if permission granted.

### Where to Place Proof in the Proposal

- After the Executive Summary: one proof element that matches their problem
- In the "About OASIS AI" section: one industry-relevant result
- In the Timeline section (optional): "Similar builds for [industry] clients took X weeks and produced Y result"

### Case Study Template (for Appendix)

```markdown
## Case Study: [Client Industry] — [Outcome]

**The situation:** [2 sentences on what they were dealing with]
**What we built:** [1 sentence — specific system, not generic "automation"]
**The result:** [Specific metric — hours, dollars, percentage, time]
**Timeline:** [How long from start to live result]
**Quote:** "[Client quote if available]"
```

---

## Mutual Action Plan

Include a "What Happens Next" section at the end of every proposal. This is not the Next Steps CTA — it's a joint accountability map.

```markdown
## Mutual Action Plan — [Client Name] & OASIS AI

**To move forward, here's what each of us does:**

| Action | Owner | By When |
|--------|-------|---------|
| Review proposal and select tier | [Client Name] | [Date — 5 business days] |
| Sign contract + pay first invoice | [Client Name] | [Date — 2 days after selection] |
| Provide system access and credentials | [Client Name] | Day 1 of engagement |
| Send contract + payment link within 24 hours of your selection | Conaugh McKenna | Immediate |
| Kickoff call scheduled + agenda sent | OASIS AI | Within 48 hours of payment |
| First deliverable delivered for review | OASIS AI | Week 2 |
```

Why this works: It makes the client's commitment visible and time-bound. It also signals that OASIS AI is organized and moves fast — which is its own form of social proof.

---

## Obsidian Links
- [[../../CMO-Agent/skills/lead-management/SKILL]] | [[skills/client-success/SKILL.md]] | [[brain/CAPABILITIES]]
- [[skills/revenue-operations/SKILL.md]] | [[skills/ceo-briefing/SKILL.md]]
- [[skills/sales-methodology/SKILL.md]] | [[memory/SESSION_LOG]] | [[brain/USER]]
