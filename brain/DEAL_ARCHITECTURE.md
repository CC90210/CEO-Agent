---
name: DEAL ARCHITECTURE
description: Canonical OASIS website-first offer, compensation, and sales rules.
last_updated: 2026-08-19
freshness_threshold_days: 30
---
# DEAL ARCHITECTURE — OASIS Website Sales Engine V5

## Positioning

OASIS sells conversion-focused websites to local-service SMBs in Canada and the United States. The website is the entry offer because owners already understand it, can see the quality gap, and can connect it to calls and bookings. Focused automations are prescribed only after discovery exposes a matching operational leak. Agent harnesses and custom software are not the opening pitch.

## Packages

| Package | Setup floor | Monthly floor | Includes |
|---|---:|---:|---|
| Essential | $2,000 | $250 | Conversion website, lead form, hosting, maintenance, analytics, basic SEO |
| Growth | $3,500 | $350 | Essential, more pages, copy support, booking/review integration, one standard automation |
| Authority | $5,000+ | $500+ | Growth, advanced SEO, custom integrations, two standard automations |

Prices use the client's selling currency: CAD in Canada and USD in the United States. No automatic conversion. The default payment schedule is 50% of setup at signature, 50% before launch, with monthly service beginning at launch.

Only CC or Adon may discount, customize scope, promise a delivery date, or approve a below-floor quote. Reps qualify and book by default; a rep on the closer track (see Rep Compensation) may run the demo, proposal, and close at listed floors — discounts, scope changes, and below-floor approvals remain founder-only.

## Approved Automation Menu

1. Google review request and follow-up.
2. Website lead capture, notification, and CRM routing.
3. Gmail inbound classification and routing.
4. Missed-call and after-hours lead recovery.
5. Quote or estimate follow-up.
6. Appointment reminders and no-show recovery.
7. Dormant-lead reactivation.
8. Invoice, estimate, or document generation.
9. Local SEO content and reporting.

Custom automation is “quoted after discovery.” A rep never improvises feasibility or price.

## ICP and Qualification

Prioritize owner-operated trades, professional services, wellness/beauty, and local home services with no website, weak mobile presentation, outdated design, unclear calls to action, broken forms, poor local search visibility, or slow lead response.

A lead is qualified only when the rep confirms decision authority, a specific website/conversion problem, real timing, and willingness to invest at least $2,000.

## Roles and Attribution

- Adon/APEX owns the upstream lead-scraping fleet, `leadgen_*` territory model, and Command Center lead-sheets surface. Its promoted output is a normal `tenant_records` lead with `data.assigned_to`, `website`, `website_condition`, `audit_findings`, `icp_track`, and initial stage `researched`.
- **Interim (CC-directed, 2026-08-19): until the APEX `leadgen_*` system ships, Bravo runs the research layer via `scripts/scrape_website_sales_leads.py`** — Firecrawl discovery + contact extraction + AI website audit (`website_condition`, `audit_findings`, `pitch_angle`, `icp_track`, `automation_openings`), promoted straight into `tenant_records` on `oasis-webdev` at stage `researched` under the same contract. APEX takes over at the promotion boundary with no schema change.
- CC and Adon choose territories, approve batches, and assign the promoted leads; this sales engine does not duplicate territory storage.
- Sales reps call assigned leads, diagnose, qualify, and book a founder Google Meet.
- CC or Adon owns the audit/demo, package, automation discovery, price, proposal, and close — unless the deal's attributed rep is on the closer track and runs the close themselves; founder approval of the commission remains mandatory before payout.
- The fulfillment owner collects assets, builds, runs QA, launches, and maintains.

The rep assigned when the founder meeting is booked owns attribution. Later reassignment does not rewrite earned attribution.

## Rep Compensation

Commission applies only to collected website setup revenue. There is no recurring commission in V1. The $2,000 setup floor is unchanged.

| Path | Rate |
|---|---:|
| **Opener** — rep sources the conversation and books the founder meeting; a founder closes | **20%** |
| **Opener-closer** — the same rep also runs the demo, proposal, and close | **30%** |

The rate is flat across deal sizes (V5, 2026-08-19 — replaces the V4 tiers of 10/12.5/15%). Worked examples: a $2,000 Essential pays $400 open / $600 open-and-close; a $5,000 Authority pays $1,000 / $1,500. Commission accrues only after payment clears. It moves through accrued → approved → paid; founder approval is required before payout on every deal and is non-delegable on rep-closed deals. A refund creates an offset instead of deleting history. Each payment/deal can create one accrual only.

## Lifecycle

Researched → Assigned → Attempting Contact → Connected → Qualified → Founder Meeting Booked → Demo Completed → Proposal Sent → Won/Lost → Onboarding → In Build → Client Review → Launched.

### Role-specific pipeline contract

- `Agent` is the launch-V1 appointment-setter role. An Agent sees only leads whose `assigned_to` value is that Agent's authenticated user UUID. By default their job ends with a qualified Google Meet for CC or Adon; an Agent granted the closer track may run the close on their own attributed leads (the 30% path).
- The Agent interface has exactly five tabs: Assigned, Attempting Contact, Connected, Qualified, and Founder Meeting.
- Member, Admin, and Owner users operate the internal pipeline. Admin/Owner assign leads and control founder-close, payment, commission, and fulfilment mutations.
- Research is an internal intake queue. APEX owns scraping and enrichment; promoted records enter the `oasis-webdev` tenant with `sales_program=website_sales_v1`. This separates the fresh website campaign from historical OASIS records without deleting history.
- No Answer and Voicemail are dispositions, not stages. Both keep the lead in Attempting Contact and require a next-action timestamp.
- Connected advances only after a real conversation. Qualified requires authority, a confirmed website/conversion need, timing, and willingness to consider at least $2,000.
- Booking freezes attribution, requires one selected founder, a meeting time, and the exact promised audit/demo. From that point the founder owns scope, price, and close; delivery stages are never exposed to Agents.
- The closer track is live in V5: a proven Agent granted closer permissions runs demo → proposal → close on their own attributed leads at the 30% rate, with founder approval gating every payout. Closing authority is never implied by the base Agent role — it is granted per rep.
- On entry to Qualified, the system auto-sends the lead the founder booking link by email (gated by `OASIS_QUALIFIED_BOOKING_EMAIL_LIVE=1`, fail-closed) and notifies the founders.

All calls, notes, emails, and dispositions stay in the existing lead-interaction ledger. Outbound email always goes through `scripts/integrations/send_gateway.py`; import or assignment never triggers a live send.

## Launch KPIs

Track attempts, conversations, qualified rate, founder meetings booked/held, proposals sent, close rate, average setup value, monthly value, collected revenue, commission accrued, days to launch, and automation attach rate by rep, founder, ICP track, geography, and loss reason.
