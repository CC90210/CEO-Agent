---
tags: [template, document, project, client]
name: Project Brief
type: document
use_case: Kicking off a new client project — aligns scope, timeline, and expectations before work begins
variables: [project_name, client_name, client_company, start_date, end_date, objective, budget, stakeholder_list]
last_updated: 2026-04-27
---

# Project Brief: {{project_name}}

> **Usage note:** Complete this document before any work begins. Share with the client for review and written confirmation. A verbal agreement is not a project brief. If they cannot confirm scope in writing, do not start.

---

## Project Overview

| Field | Value |
|-------|-------|
| **Project Name** | {{project_name}} |
| **Client** | {{client_name}}, {{client_company}} |
| **Project Lead** | Conaugh McKenna, OASIS AI Solutions |
| **Start Date** | {{start_date}} |
| **Target Completion** | {{end_date}} |
| **Status** | Planning |
| **Budget** | {{budget}} |

---

## Objective

{{objective}}

[One to three sentences. State the business problem this project solves and the measurable outcome when it is done. Example: "Automate the lead intake and initial follow-up process for [client]'s sales team, reducing manual data entry by 80% and ensuring every lead receives a response within 5 minutes of form submission."]

---

## Success Criteria

These are the specific, measurable conditions that define "done." If the project ends and these are not met, the project is not complete.

1. [Criterion — e.g., "Lead response automation live and handling 100% of new submissions without manual intervention"]
2. [Criterion — e.g., "Average response time from form submission to first outreach is under 5 minutes"]
3. [Criterion — e.g., "Client team trained and able to manage the system without Bravo support"]

---

## Scope

### In Scope

Everything on this list is included in the agreed budget and timeline.

- [Deliverable 1 — specific and unambiguous]
- [Deliverable 2]
- [Deliverable 3]
- Up to [X] revision rounds per deliverable
- [X] weeks of post-launch support for bugs introduced by our implementation

### Out of Scope

Explicitly stating what is not included prevents scope creep and protects the budget. If a client requests anything on this list, it becomes a change order.

- [Excluded item 1 — e.g., "Design of new marketing materials"]
- [Excluded item 2 — e.g., "Integration with systems not listed in the In Scope section"]
- [Excluded item 3 — e.g., "Ongoing content creation or copywriting"]
- Bugs or issues in third-party platforms not introduced by this project
- Work outside the agreed completion date without a new SOW

---

## Deliverables and Timeline

| Phase | Deliverable | Owner | Target Date | Notes |
|-------|-----------|-------|-------------|-------|
| 1. Discovery | Requirements confirmed + access granted | Client + CC | {{start_date}} + 3 days | |
| 2. Architecture | Technical approach doc | CC | Week 1 | |
| 3. Build | [Core deliverable 1] | CC | Week 2-3 | |
| 3. Build | [Core deliverable 2] | CC | Week 3-4 | |
| 4. Review | Client walkthrough + feedback round | Client + CC | Week 4 | Max 2 revision cycles |
| 5. Launch | Production deployment | CC | {{end_date}} | |
| 6. Handoff | Documentation + training | CC | {{end_date}} + 2 days | |

---

## Stakeholders

| Name | Organization | Role | Responsibility |
|------|-------------|------|---------------|
| Conaugh McKenna | OASIS AI Solutions | Project Lead | Architecture, build, QA, delivery |
| {{client_name}} | {{client_company}} | Client Sponsor | Requirements sign-off, feedback, final approval |
| [Additional stakeholder] | {{client_company}} | [Role] | [Responsibility] |

**Primary point of contact on client side:** {{client_name}} — [email] — [preferred communication channel]

---

## Dependencies and Assumptions

This project will proceed on time only if the following are true. If any dependency is not met by the stated date, the timeline adjusts accordingly.

### Dependencies (Client Provides)

| Item | Needed By | Format |
|------|-----------|--------|
| Access to [platform/system] | {{start_date}} + 1 day | Admin credentials or API key |
| [Content or data asset] | Week 1 | [Format] |
| Feedback on Phase [X] deliverable | Within 3 business days of delivery | Written (email or document) |

### Assumptions

- All access and credentials will be provided on schedule
- Client feedback will be delivered within 3 business days of each review
- The client has authority to approve the final deliverables without additional sign-off chains
- The existing [platform/infrastructure] is functional and stable

---

## Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| Access to required systems delayed | HIGH — blocks Phase 2+ | MEDIUM | Request access before contract signing |
| Scope expansion requests mid-project | MEDIUM — budget and timeline impact | HIGH | All additions go through change order process |
| Third-party API changes or outages | MEDIUM — delays integration phase | LOW | Build with error handling and fallback states |
| Client feedback delayed beyond 3 days | MEDIUM — timeline slip | MEDIUM | Establish review deadline in project kick-off call |

---

## Communication Protocol

- **Weekly status updates:** Every [day] by [time] via email — see the status report template
- **Questions or blockers:** Email {{client_name}} with 24-hour expected response time. For urgent issues, [phone/Slack]
- **Scope change requests:** Submit via email. CC will respond within 1 business day with impact assessment and change order if applicable
- **Project review meetings:** At the end of Phase 3 (review round) and on launch day

---

## Change Order Process

Any request that is outside the In Scope section above will be handled as a change order:

1. Client submits request via email
2. CC assesses impact: time, cost, and effect on existing timeline
3. CC responds within 1 business day with a change order document
4. Client approves or declines in writing
5. Work begins only after written approval

Change orders are billed at the standard retainer rate of [$X/hour] or as a fixed addition to the project total.

---

## Payment Schedule

| Milestone | Amount | Due Date |
|-----------|--------|----------|
| Project kickoff (deposit) | [50% of total] | {{start_date}} |
| Phase 3 delivery | [25% of total] | [Mid-project date] |
| Final delivery and handoff | [25% of total] | {{end_date}} |

All payments via Stripe. Invoice will be sent 3 days before each milestone date.

---

## Signatures

By proceeding with this project, both parties agree to the scope, timeline, and terms outlined in this document.

**OASIS AI Solutions**
Conaugh McKenna
Date: ___________

**{{client_company}}**
{{client_name}}
Date: ___________

---

*Generated by OASIS AI Solutions. Project Management System — Bravo V5.5*

## Obsidian Links
- [[data/templates/documents/status-report]] | [[data/templates/emails/client-checkin]]
- [[brain/USER]] | [[memory/ACTIVE_TASKS]]
