---
name: project-management
description: Lightweight project management for OASIS client engagements. Project definition, 5-phase structure, milestone tracking, status reporting, scope management, multi-project dashboard, and retrospective template.
tags: [skill, project-management, clients, oasis, delivery]
---

# Project Management — Lightweight Client Delivery Framework

## Overview

At CC's current stage, project management means: define clearly, track ruthlessly, communicate proactively, and never let a client be surprised by a slip. This isn't enterprise PM — it's a lean system that takes 15 min/week to maintain and eliminates the most common failure modes (scope creep, missed deadlines, unclear success criteria).

**When to load this skill:** When starting a new client engagement, when a project is going sideways, or when CC needs to present a status update.

---

## 1. Project Definition Template

Complete this before any paid engagement begins. File it in `memory/` or the client's folder.

```
PROJECT DEFINITION
──────────────────
Project name:
Client name:
Client primary contact: [Name, email, phone]
Start date:
Target end date:
Contract type: [Fixed price / Hourly cap / Retainer]
Contract value: $[total or $/month]

OBJECTIVE (1 sentence — what this project accomplishes for the client)

SUCCESS CRITERIA (measurable — what "done" looks like)
1. [Specific, measurable outcome]
2. [Specific, measurable outcome]
3. [Specific, measurable outcome]

SCOPE
In-scope:
  - [Deliverable 1]
  - [Deliverable 2]
Out-of-scope (explicitly stated to the client):
  - [Thing that sounds related but isn't included]
  - [Thing client might assume is included but isn't]

STAKEHOLDERS
Client contact: [Name, role]
Decision maker (if different): [Name, role]
Internal team: [CC + any contractors assigned]
Reviewers: [Anyone who must approve before delivery]

BUDGET
Total value: $
Estimated hours: [if hourly tracking]
Contingency buffer: 10% (default)

TOP 3 RISKS
Risk 1: [Description] — Mitigation: [How we prevent it]
Risk 2: [Description] — Mitigation: [How we prevent it]
Risk 3: [Description] — Mitigation: [How we prevent it]
```

---

## 2. Phase Structure

Every OASIS client project follows this 5-phase structure. Adapt timing to project size.

### Phase 1: Discovery and Planning
**Goal:** Confirm requirements, build the project plan, get client sign-off before building.

Tasks:
- Requirements gathering session (use discovery call template from `skills/meeting-automation/SKILL.md`)
- Document requirements with client approval
- Create project plan with milestones and timeline
- Identify dependencies and risks
- Kickoff call with client to walk through the plan

**Gate to Phase 2:** Client approves the project plan in writing.

### Phase 2: Build
**Goal:** Implement deliverables to spec, in the right order, with weekly visibility.

Tasks:
- Execute deliverables according to the plan
- Weekly status update to client (written — use status template below)
- Internal check: deliverables on track vs. behind
- Flag scope change requests immediately (do not absorb them silently)

**Gate to Phase 3:** All deliverables built and internally tested/reviewed.

### Phase 3: Client Review
**Goal:** Get structured feedback, revise, achieve sign-off.

Tasks:
- Deliver a review-ready version (staged, tested, documented)
- Client feedback session (structured — see below)
- Implement approved revisions (one revision round included by default; more are change requests)
- Final sign-off from client in writing

**Client Feedback Session Structure:**
```
"I'm going to share my screen and walk through what we built. As we go, please hold detailed feedback until the end — I want you to see the full flow first."
[Full walkthrough — do not explain what you were trying to do. Let them react to what IS there.]
"Now let's go back to anything that needs attention. I'll capture it as we go."
[Capture verbatim — their words, not your interpretation]
"Here's what I'm hearing [read back list]. Does that cover it?"
```

**Gate to Phase 4:** Client signs off on the reviewed deliverable.

### Phase 4: Launch
**Goal:** Deploy, verify in production, hand off to client.

Tasks:
- Deploy to production environment
- Verify all success criteria are met in production (not just staging)
- Client walkthrough and training (if needed)
- Handoff documentation (how to use it, who to contact, what to monitor)
- Confirm client can operate it independently

**Gate to Phase 5:** Client confirms receipt of final deliverables and training completed.

### Phase 5: Optimize
**Goal:** Measure outcomes, iterate on what's working, identify expansion opportunity.

Tasks:
- Check in at Day 7, Day 30, Day 90 after launch
- Pull relevant metrics (if tracking was set up)
- Identify what's working and what isn't
- Surface any expansion opportunity to the client (use client check-in template from `skills/meeting-automation/SKILL.md`)

**No gate** — Phase 5 is ongoing as long as the client relationship exists.

---

## 3. Milestone Tracking

### Milestone Definition

Each phase produces 1-3 milestones. A milestone is:
- Specific (one discrete deliverable or decision)
- Verifiable (CC and client can both see that it happened)
- Binary (either done or not done — no "80% complete" milestones)

**Milestone statuses:** NOT STARTED → IN PROGRESS → CLIENT REVIEW → COMPLETE

### Milestone Table Template

```
MILESTONES — [Project Name]
────────────────────────────────────────────────────────────────────────
Milestone                     | Target Date | Actual Date | Status          | Owner
─────────────────────────────────────────────────────────────────────────
P1: Requirements doc approved | [date]      |             | NOT STARTED     | CC
P1: Project plan signed off   | [date]      |             | NOT STARTED     | CC
P2: [Core deliverable] built  | [date]      |             | NOT STARTED     | CC
P2: [Integration] complete    | [date]      |             | NOT STARTED     | CC
P3: Client review session     | [date]      |             | NOT STARTED     | CC
P3: Revisions complete        | [date]      |             | NOT STARTED     | CC
P4: Production deployment     | [date]      |             | NOT STARTED     | CC
P4: Client handoff + training | [date]      |             | NOT STARTED     | CC
────────────────────────────────────────────────────────────────────────
```

### Milestone Dependencies

Before assigning dates, map dependencies explicitly:
- P1 milestone 2 depends on: P1 milestone 1
- P2 milestone 1 depends on: P1 milestone 2
- P2 milestone 2 depends on: [may run parallel to P2 M1]
- P3 milestone 1 depends on: all P2 milestones
- etc.

**Rule:** If a milestone slips, every downstream milestone date must be recalculated and the client must be notified within 24 hours — not at the next status update.

---

## 4. Status Reporting

### Weekly Project Status Template

Send this every Friday to the client for active engagements. Takes 10 minutes to write.

```
Subject: [Project Name] — Weekly Update [Week of DATE]

Hi [Name],

Here's a quick update on where things stand:

━━ OVERALL STATUS: [🟢 GREEN / 🟡 YELLOW / 🔴 RED] ━━

PROGRESS
[X] of [Y] milestones complete ([Z]%)
This week I completed:
• [Specific item 1]
• [Specific item 2]

NEXT WEEK
• [Planned item 1] — targeting [date]
• [Planned item 2] — targeting [date]

RISKS / BLOCKERS
[None — OR — specific issue with mitigation plan]

BUDGET
[Hours/dollars consumed]: [X] of [Y] allocated ([Z]%)
[Note if approaching cap]

Questions or feedback? Reply here or let's catch up on [day].

Conaugh McKenna
OASIS AI Solutions
```

**Status color logic:**
- GREEN: On track, no risks, all milestones on schedule
- YELLOW: 1 milestone at risk OR budget >80% consumed with >20% work remaining
- RED: Milestone missed without a recovery plan OR client satisfaction issue unresolved

**Rule:** Never let a project go from GREEN to RED in one report. YELLOW is the warning. Hiding a YELLOW until it becomes RED damages trust permanently.

### Internal Project Dashboard (Per Active Project)

Keep this current in `memory/ACTIVE_TASKS.md` or a project-specific file:

```
PROJECT: [Name]
Client: [Name] | Contract: $[value] | Phase: [1-5]
Status: [GREEN/YELLOW/RED]
Health: [Client satisfaction if known]

MILESTONES
[✅ Done] P1: Requirements approved — [date]
[🔄 In progress] P2: Core build — target [date]
[⬜ Not started] P3: Review session — target [date]

LAST CLIENT CONTACT: [date] — [1-line summary]
NEXT CLIENT CONTACT: [date] — [purpose]

OPEN ITEMS
- [Item]: [owner] — [deadline]
- [Item]: [owner] — [deadline]
```

---

## 5. Scope Management

### Change Request Template

Use this any time a client requests something that was explicitly out of scope OR significantly exceeds the original spec.

```
CHANGE REQUEST — [Project Name] — [Date]
─────────────────────────────────────────
Requested by: [Client name]
Description: [What they're asking for]

IMPACT ASSESSMENT
Additional work: [~X hours]
Additional cost: $[amount] (based on $[rate]/hr or fixed)
Timeline impact: [+X days to target completion date]
Risk to current scope: [None / Low / High — explain if High]

RECOMMENDATION
[Include this at no charge because it's minor / Quote separately / Defer to Phase 5]

REQUIRED APPROVAL
To proceed, please reply with your approval and confirmation of the additional fee.
```

**Rule:** Never absorb a scope change silently. Even if CC decides to include it for free, document it as a decision — it prevents "well you already did X for free, so Y should be free too."

### Scope Creep Detection

Scope creep is active when any of the following are true:
- Tasks in the project exceed the original plan by >20%
- Client requests have required more than one "favor" absorption
- Hours consumed are >80% with >30% of work remaining
- Build keeps expanding because requirements keep changing

**Scope creep response:**
1. Flag it to the client proactively: "I want to be transparent — we've added [X, Y, Z] since the original scope."
2. Offer a choice: trim to original scope OR approve a change order
3. Document the conversation

### Out-of-Scope Request Handling

Script:
```
"That's a great idea — it's outside the current scope, but I can absolutely put together a quick proposal for what that would look like. The current engagement is focused on [original scope]. Would you like me to quote the additional work separately?"
```

Never say "no" to a client request. Redirect to a paid scope.

---

## 6. Multi-Project Dashboard

For weeks when CC is running >1 active project simultaneously.

```
MULTI-PROJECT DASHBOARD — [Date]
──────────────────────────────────────────────────────────────────────────────
Project        | Client   | Phase | Status | % Done | Budget Used | Next Milestone
───────────────────────────────────────────────────────────────────────────────
[Project 1]    | [Client] | P2    | 🟢     | 40%    | 35%         | Build complete — [date]
[Project 2]    | [Client] | P3    | 🟡     | 75%    | 80%         | Client review — [date]
[Project 3]    | [Client] | P1    | 🟢     | 10%    | 5%          | Requirements approved — [date]
───────────────────────────────────────────────────────────────────────────────
```

### Resource Allocation View

```
RESOURCE ALLOCATION — [Week of DATE]
──────────────────────────────────────
Name       | Project 1 | Project 2 | Project 3 | Total Hrs | Utilization
CC         | 8 hrs     | 5 hrs     | 3 hrs     | 16 hrs    | 80%
[Contractor]| 10 hrs    | 0         | 0         | 10 hrs    | 100% ← flag
──────────────────────────────────────
```

**Flags:** Any person at >90% utilization for the week is a constraint. Resolve before assigning more work.

---

## 7. Project Retrospective Template

Run this within 1 week of Phase 4 (launch) completing.

```
PROJECT RETROSPECTIVE — [Project Name] — [Date]
────────────────────────────────────────────────
Client:
Duration: [Start date] → [End date] ([X weeks])
Final cost to client: $
Hours invested: [actual vs. estimated]
Profitability: $[revenue] - $[hours × CC effective rate] = $[profit] ([margin]%)

WHAT WENT WELL (be specific)
-
-

WHAT COULD IMPROVE (be specific and honest)
-
-

WHAT WE'LL DO DIFFERENTLY NEXT TIME
-
-

CLIENT SATISFACTION
Score: [1-10 — ask the client directly]
Testimonial received: Y / N
Referral asked for: Y / N
Referral received: Y / N

EXPANSION POTENTIAL
[Describe any Phase 5 opportunity identified]

LOG TO MEMORY
[ ] Add project to LONG_TERM.md client history
[ ] Any scope creep or estimate errors → MISTAKES.md
[ ] Any process improvements → PATTERNS.md
[ ] Log final project summary to SESSION_LOG.md
```

---

## Integration Points

- **New project start** → create project definition, add milestones to `memory/ACTIVE_TASKS.md`
- **Weekly status** → update milestone table + send status email
- **Scope changes** → document in project file, log decision to `memory/DECISIONS.md`
- **Retro findings** → log to `memory/MISTAKES.md` and `memory/PATTERNS.md`
- **Client satisfaction** → feed into `skills/client-success/SKILL.md` health score
- **Budget tracking** → reference `scripts/stripe_tool.py invoices` for revenue side

## Obsidian Links
- [[brain/USER]] | [[memory/ACTIVE_TASKS]] | [[memory/DECISIONS]] | [[brain/CAPABILITIES]]
- [[skills/client-success/SKILL]] | [[skills/meeting-automation/SKILL]]
- [[skills/ceo-dashboard/SKILL]] | [[memory/MISTAKES]]
