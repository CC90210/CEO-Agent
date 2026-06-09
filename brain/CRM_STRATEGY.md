---
tags: [strategy, crm, outreach, leads]
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# CRM Strategy: Two-Tier Architecture

To maintain system integrity and focus on high-conversion leads, we distinguish between two operational CRM states:

## 1. Outreach CRM (Tier 1)
*   **Purpose:** Cold outreach, lead discovery, and "testing the waters."
*   **Target:** Mass-scraped or web-searched leads with minimal initial context.
*   **Success Metric:** Response rate and qualification.
*   **Process:** Leads are added here first to "play ball." We use automated outreach sequences via [[skills/outreach-send/SKILL]] (`email_engine.py send-template`) to gauge interest. Eligibility + cadence is managed by `scripts/outreach_eligible.py`. Auto-flagged drafts go through `scripts/draft_critic.py` before SMTP.

## 2. Legit CRM (Tier 2)
*   **Purpose:** High-leverage management of actual paying customers and highly qualified opportunities.
*   **Target:** The top ~5% of leads that convert from Outreach.
*   **Success Metric:** MRR growth, retention, and referral.
*   **Process:** Once a lead demonstrates legitimate buying intent or becomes a customer, they are promoted to the Tier 2 CRM for high-touch management by the C-Suite agents — see [[brain/CEO_OPERATING_SYSTEM]] for the post-conversion playbook (client health scoring, QBRs, retention tracking).

---

**Note:** This distinction prevents our primary business management systems from being cluttered with cold/unresponsive data while allowing for high-volume top-of-funnel activity. Anchored to the [[brain/STATE]] of $5,000 USD Net MRR by June 18, 2026 (extended 2026-05-18 from May 30).

## Related
- [[brain/STATE]] — current MRR + pipeline state
- [[brain/CAPABILITIES]] — outreach + CRM tooling registry
- [[brain/USER]] — operator profile (whose CRM this is)
- [[skills/outreach-send/SKILL]] — canonical Tier 1 send path
- [[brain/OKRs]] — Q2 2026 revenue OKRs that drive both tiers
- Content/inbound funnel that feeds Tier 1 leads → see `../CMO-Agent/brain/CONTENT_BIBLE.md` (Maven canonical)
