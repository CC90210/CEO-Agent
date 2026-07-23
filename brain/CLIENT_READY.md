---
description: "Readiness audit for client cloning; covers proof-of-self-use, revenue, deliverables, sanitization, credentials, onboarding, pricing, support, and contractual maturity"
tags: [readiness, cloning, productization, honest]
owner: CC (Conaugh McKenna)
purpose: The single honest checklist that gates whether Bravo's operating system is ready to be cloned and sold to OASIS AI agency clients.
last_updated: 2026-07-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# CLIENT_READY — Can We Ship This to a Client Yet?

> **The rule:** You cannot sell a system you have not proven on yourself. This file is the audit.
> **Owner mindset:** Read this when you want to tell yourself "it's ready." Usually it won't be. That's the point.

---

## Honest Scorecard (2026-04-11)

| Domain | Score | Evidence |
|---|---|---|
| **Proof of self-use** | **2/10** | Bravo is built. Skool daemon runs. But the content engine has never shipped a daily video. The sales-closing skill has never reviewed a real call transcript. The CRM has 4 leads total. |
| **Revenue proof** | **3/10** | $3,322 MRR exists, but $2,951 of it is the primary retainer (one friend referral, not a cold-closed retainer). System has not generated a net-new OASIS retainer independently. |
| **Deliverable clarity** | **4/10** | Skills exist. Workflows exist. But the "what does a client get on day 1" doc does not. No onboarding flow. No demo env. No client-facing dashboard. |
| **Sanitization** | **1/10** | Brain/SOUL.md is literally CC's identity. USER.md is CC's personal profile. Content-strategy.md is CC's voice. Entire system is CC-specific — cloning = 60+ files of search-and-replace. |
| **Credential scaffolding** | **3/10** | `.env.agents` exists but is single-tenant. No per-client key namespacing. No secrets rotation protocol. No tenant isolation in Supabase. |
| **Onboarding automation** | **0/10** | Does not exist. No script to spin up "a new Bravo for a new client." No template repo. No documented setup on a fresh machine. |
| **Pricing model** | **2/10** | "Some kind of retainer" is not a pricing model. No SKUs. No tiers. No delivery SLA. No what's-included vs what's-extra. |
| **Support story** | **0/10** | If a client's Bravo breaks at 2am, who fixes it? There is no answer. |
| **Legal / contract** | **0/10** | No client contract template. No DPA. No terms. No liability cap. No CASL compliance per client. |
| **Testimonial readiness** | **0/10** | Zero testimonials from having used Bravo to generate client revenue (the existing testimonial from the primary retainer is for a coaching partnership, different product). |

**Overall: 15/100.** This is not a ready-to-clone product. It is a working prototype CC uses on himself — barely.

---

## The Honest Truth

You asked for brutal. Here it is:

### 1. You cannot sell what you have not used
Bravo has 150 skills and CC uses maybe 5 of them on a regular day. The ones he doesn't touch are not "options for later" — they're decoration. A client signing up expects CC to say "this exact skill, fired in this exact situation, generated this exact result." Today, for most skills, CC can't say that.

### 2. You are building instead of shipping
The rate at which new skills, workflows, and brain files appear in this repo is faster than the rate at which revenue is generated. That is the definition of a builder's trap. More code does not equal more clients.

### 3. Four leads is not a pipeline
The current CRM state is: 1 new, 2 dead (March 19 — over 3 weeks stale), 1 won. This is not a sales pipeline. This is proof that CC stopped doing outreach weeks ago and instead built more Bravo. **No amount of AI fixes this.**

### 4. $29 is killing $29,000
Zernio free plan hit 20 posts/month on April 4. CC pays $140/mo for Claude Pro but not $29 for Zernio. The content engine cannot distribute what Zernio won't schedule. That $29 is blocking the single highest-leverage inbound funnel. It's not frugality — it's friction in the wrong place.

### 5. The primary retainer is 93% of revenue
This is catastrophic concentration risk. If the primary retainer goes cold next month, CC drops to $822 MRR — less than rent in most Canadian cities. The "4 retainers by April 30" stretch target is not ambitious, it's **survival**.

### 6. Cloning for clients is the wrong next move
CC's instinct is to productize Bravo for clients. That's the CEO brain kicking in early. But the right sequence is:
1. Use Bravo to close 4 of your own OASIS retainers (proof)
2. Deliver those retainers with Bravo running in the background (validation)
3. Extract the 10 skills/workflows that actually moved the needle (distillation)
4. **Those 10** get productized — not the full 150 (focus)
5. Sell that to clients (revenue)

Selling a 150-skill system that only 5 skills are proven for = selling vaporware with extra steps.

### 7. The infrastructure is not the bottleneck
CC has asked 4 times in this conversation for "optimization" and "perfection." The shed is not the problem. The shed is 95/100. CC's execution on the shed is 30/100. **Optimizing the shed from 95 to 99 does nothing for revenue.** Execution from 30 to 70 does everything.

---

## What "Ready to Clone" Actually Looks Like

All of these must be true. None of them are today:

- [ ] CC has closed ≥3 OASIS retainers that were not friend referrals
- [ ] Each of those retainers has been delivered for ≥30 days using Bravo
- [ ] The top 10 skills/workflows that generated measurable client value are documented
- [ ] A "seed repo" exists: `~/APPS/bravo-client-template` with all CC-specific content ripped out
- [ ] `sanitize-for-client.sh` exists and rewrites SOUL.md, USER.md, APP_REGISTRY.md, content-strategy.md with generic placeholders
- [ ] `onboard-client.sh` exists: takes `<client_name>`, `<email>`, `<stack>` → produces a working clone in <5 min
- [ ] `.env.agents.template` exists with every required key documented (not the values)
- [ ] A per-tenant Supabase project pattern is documented (so client A's data never touches client B's)
- [ ] A client-facing dashboard exists showing what Bravo is doing and what it has produced
- [ ] A 1-page client SLA defines uptime, support response, escalation path
- [ ] A contract template exists (scope, payment terms, kill clause, liability cap, IP ownership)
- [ ] A CASL compliance checklist per client is templated
- [ ] At least 1 video testimonial from a self-delivered retainer (showing Bravo live, generating the work)
- [ ] A pricing page exists: $X/mo gets you [this exact list], $Y/mo adds [this]
- [ ] A fallback plan for the "2am Bravo breaks" scenario

**14 checkboxes. 0 checked.**

---

## The Minimum Viable Path (30 Days)

If CC wants to be client-ready, here is the shortest honest path:

### Week 1 (Apr 12-18) — Pipeline Revival (Not More Building)
- **Monday:** Pay for Zernio ($29/mo). Not optional.
- **Monday:** Import the 47 stale leads into CRM. `python scripts/lead_engine.py bulk-import`
- **Monday:** Send 20 cold emails via `outreach_engine.py`. Today.
- **Tuesday-Friday:** 20 cold emails/day. Every day. No excuses.
- **Tuesday-Friday:** Ship 1 video/day through content_pipeline.py. Raw phone video → full pipeline → posted. Even if it's ugly the first time.
- **Friday:** Run `/close-review` on any discovery calls that happened.
- **Sunday retro:** How many replies? How many calls booked? Did we hit 20 leads/day?

**Target:** 100 cold touches, 5 discovery calls, 1 retainer signed.

### Week 2 (Apr 19-25) — First Real Close
- Keep the volume: 20 cold/day, 1 video/day
- Every call → `/close-review` → log pattern
- Target: 5 more discovery calls, 1-2 retainers signed

### Week 3 (Apr 26-May 2) — Deliver While Selling
- Onboard signed clients (use Bravo live — take screenshots, record video)
- Keep sending: don't drop outreach when delivery starts
- Target: 3 retainers signed total, 1 delivered for ≥1 week

### Week 4 (May 3-9) — Extract the 10
- Identify which skills/workflows actually moved the needle for the clients
- Kill the ones that didn't (or de-prioritize in Bravo routing)
- Start the sanitization work ONLY on proven skills
- Target: 4 retainers signed total, 2 delivering, $5K+ MRR

### Day 30 (May 11) — Honest Audit
Re-run the scorecard above. Most boxes should still be unchecked. **That's fine.** The only boxes that must be checked before cloning begins are "3+ retainers closed non-referral" and "10 proven skills identified."

If those two are not true on day 30, cloning does not start. Period.

---

## What This Document Does NOT Do

- It does not tell CC to slow down on capability-building forever
- It does not say the shed is bad
- It does not say CC can't sell AI services

What it says is: **use the shed first, prove which 10 tools matter, then sell those.**

---

## Review Cadence

Update this file:
- Every Monday at sprint review
- After every closed retainer
- After every lost deal
- Before any "let's productize Bravo" conversation

If it's been >14 days without a score change, that's a flag — the week was spent on the wrong things.

## Obsidian Links
- [[brain/USER]]
- [[brain/SOUL]]
- [[brain/CEO_OPERATING_SYSTEM]]
- [[brain/RISK_REGISTER]]
- [[memory/ACTIVE_TASKS]]
- [[skills/sales-closing/SKILL]]
