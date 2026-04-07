---
tags: [template, document, client, reporting]
name: Weekly Status Report
type: document
use_case: Client-facing weekly update for active projects and retainer engagements
variables: [project_name, client_name, report_date, report_number, overall_status, progress_pct, budget_spent, budget_total]
---

# Weekly Status Report

> **When to send:** Every [agreed day] of the week during active projects. For retainer clients without an active project, use the monthly check-in template instead.
> **How to send:** Paste into an email with subject "[Project Name] — Week [N] Update" or attach as a PDF.

---

## {{project_name}} — Week {{report_number}} Status

**Client:** {{client_name}}
**Report Date:** {{report_date}}
**Overall Status:** {{overall_status}}
**Progress:** {{progress_pct}}% complete

---

### Status Key

| Status | Meaning |
|--------|---------|
| GREEN | On track — no issues affecting timeline or budget |
| YELLOW | Minor issues — timeline or budget at risk but manageable |
| RED | Significant issue — timeline or budget impact confirmed, mitigation in progress |

---

## This Week

What was completed or advanced since the last report.

- [Completed item 1 — be specific about the outcome, not just the activity]
- [Completed item 2]
- [Completed item 3]

*If nothing was completed this week, state why and what was worked on instead. Silence is not a status update.*

---

## Next Week

What will be completed or advanced before the next report.

- [Planned item 1 — with target completion date if within the week]
- [Planned item 2]
- [Planned item 3]

---

## Blockers and Risks

| Item | Type | Impact | Owner | Resolution Plan |
|------|------|--------|-------|----------------|
| [Blocker or risk] | BLOCKER / RISK | HIGH / MEDIUM / LOW | CC / Client | [What is being done] |

*If no blockers or risks: "None — clear to execute."*

---

## Decisions Needed from Client

Items that require a client decision before work can proceed or a decision deadline has been reached.

| Decision | Context | Deadline | Impact if Delayed |
|----------|---------|----------|------------------|
| [Decision needed] | [1-sentence context] | [Date] | [What gets delayed] |

*If no decisions needed: "None this week."*

---

## Budget

| | Planned | Actual | Variance |
|---|---------|--------|---------|
| **Hours this week** | [X] | [Y] | [+/- Z] |
| **Total hours to date** | [X] | [Y] | [+/- Z] |
| **Budget spent** | {{budget_spent}} | | |
| **Budget remaining** | | | |
| **Projected completion** | [Within budget / Over by X] | | |

*If this is a fixed-price project, replace the table above with: "This project is fixed-price at {{budget_total}}. Budget tracking is for internal planning only."*

---

## Upcoming Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| [Next major milestone] | [Date] | On track / At risk |
| [Following milestone] | [Date] | On track / At risk |

---

## Notes

[Any context that does not fit the above sections — client decisions made verbally, relevant external factors, changes to team availability, etc.]

*If nothing to add, remove this section.*

---

*OASIS AI Solutions — Weekly Project Update*
*Questions? Reply to this email or book time at [calendar link]*

---

## Filling Out This Template — Common Mistakes

**"This week" section errors:**
- Do not list meetings as accomplishments ("Had a call with client" is not a deliverable)
- Do not use vague verbs ("Worked on X" tells the client nothing — "Completed X" or "Advanced X to [state]" is specific)
- One sentence per bullet is enough — do not explain the work, just state the outcome

**Budget section errors:**
- Never report budget as "fine" without numbers — clients need the actual figures
- If you are over budget, surface it here before they ask — proactive disclosure builds trust, reactive disclosure damages it

**Status color errors:**
- GREEN means nothing is threatening the delivery. If there is a nagging concern, it is YELLOW.
- YELLOW does not mean failure — it means "heads up, here's what I'm watching and what I'm doing about it"
- RED means you need the client's help or they need to accept a timeline change — do not go to RED without a mitigation plan

## Obsidian Links
- [[data/templates/documents/project-brief]] | [[data/templates/emails/client-checkin]]
- [[brain/USER]] | [[memory/ACTIVE_TASKS]]
