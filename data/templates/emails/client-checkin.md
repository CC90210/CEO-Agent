---
tags: [template, email, client, retention]
name: Monthly Client Check-In
type: email
use_case: Proactive monthly touchpoint with active retainer clients
variables: [client_name, client_company, wins_this_month, metrics_summary, next_month_focus, open_questions, meeting_link]
---

# Monthly Client Check-In Email

## Purpose

Retention is easier than acquisition. A monthly check-in keeps CC visible, demonstrates ongoing value, and catches dissatisfaction before it becomes churn. This email should take 10 minutes to fill out and arrive before the client has a chance to wonder what you have been doing.

**When to send:** Between the 25th and last day of each month, before the client's invoice drops. The sequence is: update email → invoice → renewal.

---

## Email Template

**Subject:** {{client_company}} — Monthly Update + What's Next

Hi {{client_name}},

Monthly check-in. Here's where things stand:

---

**This Month's Wins**

{{wins_this_month}}

[Format as a tight bullet list. Be specific. "Launched X" is weaker than "Launched X, which reduced Y by Z%." If you do not have metrics yet, use completion milestones.]

---

**Key Metrics**

{{metrics_summary}}

[Include the 2-3 numbers that matter most to this client. Revenue impact, time saved, leads generated, tasks automated — depends on the engagement. If tracking is not yet set up, note it as an action item.]

---

**Focus for Next Month**

{{next_month_focus}}

[List 2-3 concrete priorities. This is also a commitment — what you are saying you will deliver. If priorities shifted, explain why briefly.]

---

**Open Questions / Decisions Needed**

{{open_questions}}

[If there are none, write "None — we are clear to execute." Never leave this blank or the client will wonder if there are hidden blockers.]

---

That's the summary. How are things feeling on your end? Anything you want to adjust, prioritize differently, or add to the roadmap?

If you would like to review this on a quick call, here is my calendar: {{meeting_link}}

Best,
Conaugh

---

## Filling Out the Template

### wins_this_month — Format

Write wins as outcomes, not outputs:

| Weak (Output) | Strong (Outcome) |
|---------------|-----------------|
| "Built automation for lead capture" | "Lead response time dropped from 48h to under 2 minutes" |
| "Set up email sequence" | "Sequence is live — 3 replies from first 20 sends" |
| "Updated CRM" | "CRM now auto-populates from form submissions, saving ~3h/week" |

If a deliverable is not live yet: "Completed [X] — launching [date]."

### metrics_summary — What to Include

Use the metrics agreed upon during onboarding. If not agreed, default to:
- Tasks automated (count)
- Time saved (hours/week estimate)
- Revenue impacted (if trackable)
- System uptime or reliability (if relevant)

### next_month_focus — How Specific to Be

Name the actual deliverables, not categories. "Continue automation work" is not a focus. "Build intake form → CRM integration + automated follow-up sequence for new leads" is a focus.

---

## Cadence Variants

### Quick Pulse (Mid-Month)

For clients who want more frequent contact or where something significant happened:

**Subject:** Quick mid-month pulse — {{client_company}}

Hi {{client_name}},

Quick mid-month note:

- [Update on the main active project]
- [Any blocker or decision needed from them]
- [ETA for next milestone]

Nothing urgent — just keeping you in the loop.

Best,
Conaugh

---

### QBR Prompt (Quarterly)

For long-running retainer clients (3+ months):

**Subject:** Q[N] Review — {{client_company}} + what's next

Hi {{client_name}},

We are coming up on [X] months together. I want to do a proper quarterly review to make sure we are still working on the right things and that you are getting full value from the retainer.

I will put together a short summary doc covering what we have built, what it is doing for you, and what I think the next 90 days should look like.

Can we find 30 minutes this week or next? {{meeting_link}}

Best,
Conaugh

---

## Obsidian Links
- [[data/templates/emails/invoice-reminder]] | [[data/templates/documents/status-report]]
- [[brain/USER]] | [[memory/ACTIVE_TASKS]]
