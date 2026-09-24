---
description: "Specifies lead routing: Tier 1 (inbound nurture via email_engine.py + draft_critic), Tier 2 (customer management); cold outreach operator-initiated"
tags: [strategy, crm, outreach, leads]
last_updated: 2026-09-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# CRM Strategy: Two-Tier Architecture

To maintain system integrity and focus on high-conversion leads, we distinguish between two operational CRM states:

## 1. Outreach CRM (Tier 1) — INBOUND capture
*   **Purpose:** Capture and nurture INBOUND leads — funnel submissions, DMs, and social-content responses → nurture sequence → book a call.
*   **Target:** Leads who raised their hand: native funnel (oasisai.work/f/oasis-ai-cc/start), Instagram/LinkedIn DMs, and content-driven inquiries.
*   **Success Metric:** Booked calls and qualification rate from inbound volume.
*   **Process:** Inbound leads land here first and enter nurture sequences via [[skills/outreach-send/SKILL]] (`email_engine.py send-template`). Eligibility + cadence is managed by `scripts/outreach_eligible.py`. Auto-flagged drafts go through `scripts/draft_critic.py` before SMTP.
*   **Cold outbound (demoted — on-demand only):** Cold/scraped lists are NOT the default motion. Cold batches run only when CC explicitly directs one (operator-initiated, never cron'd — see the no-cold-outreach-cron decision). Same send rail, same critic gates.

## 2. Legit CRM (Tier 2)
*   **Purpose:** High-leverage management of actual paying customers and highly qualified opportunities.
*   **Target:** The top ~5% of leads that convert from Outreach.
*   **Success Metric:** MRR growth, retention, and referral.
*   **Process:** Once a lead demonstrates legitimate buying intent or becomes a customer, they are promoted to the Tier 2 CRM for high-touch management by the C-Suite agents — see [[brain/CEO_OPERATING_SYSTEM]] for the post-conversion playbook (client health scoring, QBRs, retention tracking).

---

**Note:** This distinction prevents our primary business management systems from being cluttered with unqualified/unresponsive data while Tier 1 absorbs the inbound top-of-funnel (plus the occasional operator-approved cold batch). Anchored to the current goal — ≥ US$6,000 revenue collected 2026-09-24 → 2026-10-24 (October sprint, set 2026-09-24; baseline = live Stripe MRR); the number is owned by Atlas (CFO-Agent). The former $10K-by-2026-09-30 target is retired.

## Related
- [[brain/STATE]] — current MRR + pipeline state
- [[brain/CAPABILITIES]] — outreach + CRM tooling registry
- [[brain/USER]] — operator profile (whose CRM this is)
- [[skills/outreach-send/SKILL]] — canonical Tier 1 send path
- [[brain/OKRs]] — Q2 2026 revenue OKRs that drive both tiers
- Content/inbound funnel that feeds Tier 1 leads → see `../CMO-Agent/brain/CONTENT_BIBLE.md` (Maven canonical)
