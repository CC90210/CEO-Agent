---
name: meeting-automation
description: Pre-meeting briefs, meeting type templates, post-meeting capture protocol, follow-up cadence, and calendar intelligence. Turns every meeting into a documented, actionable event.
tags: [skill, meetings, automation, follow-up, calendar]
triggers: ["meeting automation", "use meeting automation", "run meeting automation", "pre-meeting briefs"]
---

# Meeting Automation — Prep, Capture, Follow-Up System

## Overview

Every meeting CC takes costs time and should produce a decision, a deal advancement, or a documented outcome. This skill automates the prep and follow-up so nothing slips and every relationship stays warm.

**When to load this skill:** Before any scheduled call, after any meeting, when setting up a meeting cadence, or when CC asks "can you prep me for this call?"

---

## 1. Pre-Meeting Brief Template

Auto-generate this before any call using available context sources (memory files, lead tracker, calendar events, email threads).

```
PRE-MEETING BRIEF
─────────────────
Meeting: [Title or description]
Date/Time: [Date] at [Time] [Timezone]
Format: [Zoom / Phone / In-person / Slack huddle]
Duration: [X minutes]

WHO
Name: [Full name]
Role: [Title + Company]
Relationship: [Prospect | Client | Partner | Referral | Other]
How we met: [Context — LinkedIn, referral from X, cold outreach, etc.]

CONTEXT
Last interaction: [Date + what was discussed]
Outstanding items: [Anything they're waiting on from CC / anything CC is waiting on from them]
Recent intel: [Any recent news about their company, industry, or personal updates]
Pipeline stage: [If prospect — Awareness / Interest / Discovery / Proposal / Negotiation / Closed]
Revenue potential: $[estimate if known]

OBJECTIVE
What CC wants from this meeting (be specific):
- [Primary: e.g., "Book the follow-up with a proposal attached"]
- [Secondary: e.g., "Qualify budget and decision timeline"]

AGENDA (suggested — adapt live)
1. [Talking point 1] — est. X min
2. [Talking point 2] — est. X min
3. [Talking point 3] — est. X min
4. Next steps + close — est. 5 min

PREP
Numbers to know: [Revenue, MRR, client count, relevant metrics to reference]
Documents to review: [Proposal draft, previous email, their website, LinkedIn]
Questions to ask: [The 2-3 most important open questions]

ALERTS
[Any risks, sensitive topics, objections likely to come up, or context CC should not bring up]
```

**Data sources to pull from (in priority order):**
1. `memory/LEAD_TRACKER.csv` — relationship stage and history
2. `memory/SESSION_LOG.md` — last time this person was mentioned
3. GWS Gmail — recent email threads with this person
4. GWS Calendar — any prior meetings in calendar history
5. Memory MCP (`search_nodes`) — any stored knowledge graph entities

---

## 2. Meeting Types and Templates

### Discovery Call (New Prospect)

**Purpose:** Qualify the lead (BANT + pain depth), not sell.

**Structure (30-45 min):**
```
1. OPEN (5 min)
   "Thanks for making time. Quick agenda: I'd like to spend most of this call learning about your situation — what's working, what's not — and then if it makes sense, we can talk about whether we're a fit. Sound good?"

2. PAIN ASSESSMENT (10-15 min)
   "Tell me a bit about how you're currently handling [the problem area]."
   "What's the biggest friction point in that process right now?"
   "What happens if that doesn't get solved? What does that cost you?"
   [Let them talk. Ask "tell me more" twice before moving on.]

3. BUDGET QUALIFICATION (5 min — handle carefully)
   "To make sure I'm thinking about the right kind of solution — do you have a rough sense of what you'd be open to investing to solve this?"
   [If resistance]: "I ask because I want to make sure what I put together is realistic for where you're at."

4. TIMELINE + DECISION (5 min)
   "If you decided to move forward, what does your timeline look like?"
   "Who else would be part of the decision?"
   "What would need to be true for you to feel confident moving forward?"

5. CLOSE (5 min)
   "Based on what you've shared, I think there's a real fit here. What I'd like to do is [send a proposal / book a follow-up with Adon / start a trial]. Does that work for you?"
```

**Capture after this call:**
- Pain in their own words (exact quotes are gold for proposal writing)
- Budget range (even a rough number)
- Timeline
- Decision maker(s)
- Next step agreed

### Client Check-In (Existing Client)

**Purpose:** Maintain relationship, surface issues early, identify expansion opportunities.

**Structure (30 min — monthly or as needed):**
```
1. OPEN (3 min)
   Genuine personal check-in. Ask about something not work-related.

2. PROGRESS UPDATE (10 min)
   "Here's what we've shipped in the last [period]: [specific items]"
   "Here's what's coming next: [next deliverables + timeline]"

3. SATISFACTION CHECK (7 min)
   "On a scale of 1-10, how happy are you with what we're delivering?"
   "What would make it a 10?" (ask even if they say 10 — reveals expansion signals)
   "Is there anything that's been bothering you that you haven't mentioned yet?"

4. UPSELL EXPLORATION (5 min — only if satisfaction ≥ 7)
   "We've been thinking about [adjacent service/expansion]. Is that a problem space you're dealing with?"
   [Don't pitch. Ask. Let them tell you if they want it.]

5. CLOSE (5 min)
   Confirm next deliverable + deadline.
   Schedule next check-in.
```

**Capture after this call:**
- Satisfaction score (log trend over time)
- Issues raised (add to active tasks immediately)
- Upsell signals (log to lead tracker)

### Strategy Session (Decision Meeting)

**Purpose:** Review data, align priorities, make a concrete decision.

**Structure (60 min):**
```
1. REVIEW METRICS (15 min)
   Share prepared dashboard or relevant numbers.
   "Before we dive in, here's where things stand: [numbers]"

2. DISCUSS PRIORITIES (20 min)
   "Given those numbers, here are the top 3 things I think we should address:
   1. [Priority 1 + evidence]
   2. [Priority 2 + evidence]
   3. [Priority 3 + evidence]
   What's your read on that order?"

3. MAKE DECISIONS (20 min)
   For each priority, reach a clear decision:
   - What are we doing?
   - Who owns it?
   - What does success look like?
   - By when?

4. CLOSE (5 min)
   Read back the decisions and action items out loud.
   "Just to confirm — [Decision 1], [Decision 2], [Action item 1 — Owner, deadline]. Does that match your notes?"
```

**Capture after this call:**
- Each decision (what was decided, who owns it, deadline)
- All action items
- Next strategy session date

### Partnership Discussion

**Purpose:** Explore mutual interest, define roles and terms, establish working relationship.

**Structure (45-60 min):**
```
1. ALIGN ON SHARED INTEREST (10 min)
   "What made you want to explore this? What does success look like for you?"
   [Listen fully before sharing your vision.]

2. DEFINE ROLES (15 min)
   "Here's how I see this working: [CC's vision for the partnership]"
   "What's your take? Where do you see yourself contributing most?"
   "What do you want to NOT be responsible for?"

3. ESTABLISH TERMS (15 min)
   Revenue split: [discuss range, not fixed number in first meeting]
   IP ownership: [what each party owns]
   Decision authority: [who decides what]
   Exit terms: [how do we unwind if it doesn't work?]

4. NEXT STEPS (10 min)
   "Let's agree on what 'done' looks like for the first 30 days of this."
   Set a follow-up date to review a written term sheet.
```

**Capture after this call:**
- Mutual interests confirmed
- Role boundaries discussed (even if informal)
- Revenue model discussed
- Next step: written agreement

### Team Standup (When Team Exists)

**Purpose:** Unblock, align, coordinate. Not a status report.

**Structure (15 min max — no exceptions):**
```
Round-robin, each person answers 3 questions:
1. What did you ship yesterday?
2. What are you working on today?
3. What's blocking you or needs a decision?

After round-robin:
  CC handles blockers immediately (≤2 min each) or schedules a follow-up call.
  Standup does NOT become the follow-up call.
```

---

## 3. Post-Meeting Protocol

Run this within 2 hours of every meeting.

### Step 1: Capture Decisions

```
DECISIONS — [Meeting name] — [Date]
────────────────────────────────────
Decision 1: [What was decided]
  Made by: [Who]
  Deadline: [If applicable]

Decision 2: [What was decided]
  Made by: [Who]
  Deadline: [If applicable]
```

### Step 2: Capture Action Items

```
ACTION ITEMS — [Meeting name] — [Date]
───────────────────────────────────────
Task: [Specific action]
Owner: [Name]
Deadline: [Date]
Status: [ ] Not started

Task: [Specific action]
Owner: [Name]
Deadline: [Date]
Status: [ ] Not started
```

Add CC's action items to `memory/ACTIVE_TASKS.md` immediately.

### Step 3: Draft Follow-Up Email

Use this structure — write it within 2 hours while the context is fresh:

```
Subject: [Meeting topic] — Next steps

Hi [Name],

Thanks for the time today. Wanted to capture what we agreed on while it's fresh:

[If decisions were made]:
What we decided:
• [Decision 1]
• [Decision 2]

[If action items were set]:
Next steps:
• [CC's action] — [deadline]
• [Their action] — [deadline]

[If follow-up is scheduled]:
Our next conversation is on [date] at [time].

[Optional: 1-sentence value statement to reinforce the relationship]

Best,
Conaugh McKenna
OASIS AI Solutions
```

### Step 4: Update CRM / Lead Tracker

Add an interaction note to `memory/LEAD_TRACKER.csv`:
```
[Date] | [Name] | [Meeting type] | [Key outcome] | [Next action] | [Next action date]
```

Update the lead's stage if it changed (e.g., Discovery → Proposal).

### Step 5: Schedule Next Touchpoint

Never leave a meeting without a confirmed next contact point:
- If prospect: next step is in the calendar before the call ends
- If client: next check-in scheduled
- If partner: follow-up with draft terms in 48 hours

### Step 6: Log to Memory

Append a one-liner to `memory/SESSION_LOG.md`:
```
### [DATE] — Meeting: [Name/Company]
**Type:** [Discovery / Check-in / Strategy / etc.]
**Outcome:** [1 sentence — what happened and what's next]
**Action:** [CC's next action + deadline]
```

---

## 4. Follow-Up Cadence

### After Discovery Call

| Day | Action |
|-----|--------|
| Same day (within 2 hrs) | Send summary email with next steps confirmed |
| Day 2 | Send proposal or follow-up document if promised |
| Day 5 | If no response: check-in — "Wanted to make sure the proposal landed" |
| Day 10 | If still no response: value-add touchpoint (relevant article, case study, or short insight) |
| Day 21 | Final nudge if still no response: "Checking in one last time — still happy to help if the timing's right." |

### After Client Check-In

| Day | Action |
|-----|--------|
| Same day (within 24 hrs) | Action items email with deadlines |
| Day 7 | Progress check on any items that have deadlines this week |
| Month 1 | Next monthly check-in |

### After Strategy Session

| Day | Action |
|-----|--------|
| Within 24 hrs | Send meeting recap with all decisions and action items |
| Within 48 hrs | Updated plan document with any revised priorities |
| Day 7 | Check in on action item progress |

### No-Response Escalation

```
Day 3 with no response:
  Subject: Quick follow-up — [topic]
  "Hi [Name], just wanted to make sure my last message didn't get buried. [One-line recap]. Happy to jump on a quick call if easier."

Day 7 with no response:
  Subject: Something that might be useful for you
  [Share a specific article, insight, or case study relevant to their problem — NOT a pitch]
  "Thought of you when I read this. No action needed — just sharing."

Day 14 with no response:
  Move to cold nurture. Reduce frequency to monthly. Don't pressure.
```

---

## 5. Calendar Intelligence

### Daily Meeting Scan

Before CC's first meeting each day, run this:
1. Check GWS calendar for all events in the next 24 hours
2. For each meeting with an external person: generate a Pre-Meeting Brief
3. For each meeting with an existing client: pull client health score from `skills/client-success/SKILL.md`
4. Present briefs to CC in a single digest

**Trigger:** `/meeting-prep` or "prep me for today's calls"

### Meeting Load Review (Weekly)

Every Monday or Friday, check:
- How many hours is CC spending in meetings this week?
- Is the ratio of meetings to deep work >40%? If yes, flag for optimization.
- Are any meetings recurring that should be async instead?
- Are there any meetings with no brief generated yet?

**Target:** CC's calendar should have no more than 3-4 external calls per week at current stage. Time in meetings beyond that is time NOT spent on content, sales, or building.

### Post-Block Prompt

After each meeting block, surface this prompt to CC:
```
Meeting with [Name] just ended. Want to capture decisions and action items now? (takes 3 min)
```

This is the highest-value habit to build — capture while context is hot.

---

## Integration Points

- **Pre-meeting prep** → trigger workflow `.agents/workflows/meeting-prep.md`
- **Action items** → add to `memory/ACTIVE_TASKS.md`
- **Lead stage updates** → update `memory/LEAD_TRACKER.csv`
- **Session log** → append to `memory/SESSION_LOG.md`
- **Client health** → cross-reference `skills/client-success/SKILL.md`
- **Calendar access** → `gws calendar events list --params '{"calendarId":"primary","singleEvents":true,"orderBy":"startTime","timeMin":"[now]","timeMax":"[+24h]"}'`

## Obsidian Links
- [[brain/USER]] | [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[brain/CAPABILITIES]]
- [[skills/client-success/SKILL]] | [[skills/ceo-dashboard/SKILL]]
- `/meeting-prep`
