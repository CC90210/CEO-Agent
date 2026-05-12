---
name: Meeting Prep
trigger: /meeting-prep
description: Generate pre-meeting briefs for upcoming calls, capture post-meeting decisions and action items, and draft follow-up emails.
---

# Meeting Preparation Workflow

## When to Use
When CC says "prep me for [meeting/name]", "what do I need to know before my call with [name]", or `/meeting-prep`. Also triggered automatically before the start of any day with external meetings.

## Step 1: Identify Upcoming Meetings

Pull CC's calendar for the next 24 hours:

```bash
gws calendar events list --params '{"calendarId":"primary","singleEvents":true,"orderBy":"startTime","maxResults":10,"timeMin":"[NOW_ISO8601]","timeMax":"[24H_FROM_NOW_ISO8601]"}'
```

Filter for events with external attendees (not just CC). Skip internal reminders.

If `/meeting-prep [name]` was called with a specific name, skip the calendar scan and target that person directly.

## Step 2: Gather Context for Each Meeting

For each identified meeting, collect context from available sources:

**Source 1: Lead Tracker** — `memory/LEAD_TRACKER.csv`
Search for the attendee's name or company. Pull: stage, last contact date, deal value, last notes.

**Source 2: Session Log** — `memory/SESSION_LOG.md`
Search for the person's name. Pull the last 3 mentions with dates.

**Source 3: Knowledge Graph** — Memory MCP
```
search_nodes: "[person name]" or "[company name]"
```
Pull any stored entities, observations, or relationships.

**Source 4: Recent Email Threads** — GWS Gmail
```bash
gws gmail users messages list --params '{"userId":"me","q":"from:[email] OR to:[email]","maxResults":5}'
```
Read subject lines and latest message in each thread.

**Source 5: Active Tasks** — `memory/ACTIVE_TASKS.md`
Search for any open items tagged with this person or company.

## Step 3: Generate Pre-Meeting Briefs

For each meeting, generate a brief using the template from `skills/meeting-automation/SKILL.md`:

```
PRE-MEETING BRIEF — [Date] at [Time]
─────────────────────────────────────

WHO
Name: [Full name]
Role: [Title] at [Company]
Relationship: [Prospect | Client | Partner | Referral | Other]
How we met: [Context]

CONTEXT
Last interaction: [Date and what was discussed — or "No prior contact found"]
Outstanding items: [What's waiting on CC / what CC is waiting on from them]
Recent intel: [Anything relevant found in email or memory]
Pipeline stage: [If applicable] — $[deal value]

OBJECTIVE
[What CC should aim to accomplish in this meeting — based on the relationship stage]

AGENDA (suggested)
1. [Most important talking point]
2. [Second talking point]
3. [Third talking point]
4. Next steps + close (5 min)

PREP
Numbers to know: [Current MRR, relevant metrics, their metrics if known]
Questions to ask: [2-3 most important open questions]

ALERTS
[Any risks, sensitive topics, or context flags — or "None identified"]
```

If no context is found for a person, flag it: "No prior history found for [Name]. This appears to be a first contact."

## Step 4: Present Briefs to CC

If there are multiple meetings, present all briefs in a single digest:

```
MEETING BRIEFS — [Date]
═══════════════════════════════════════════

[X meetings today]

━━━ [Time] — [Name / Company] ━━━━━━━━━━━━
[Brief 1]

━━━ [Time] — [Name / Company] ━━━━━━━━━━━━
[Brief 2]

═══════════════════════════════════════════
```

If there's only one meeting, present it directly without the wrapper.

## Step 5: Post-Meeting Capture (On-Demand)

After a meeting, if CC says "capture that meeting" or "follow up on my call with [name]":

### 5a: Capture Decisions and Actions

Ask CC (or if sufficient context exists, generate from CC's description):

```
MEETING CAPTURE — [Meeting name] — [Date]
──────────────────────────────────────────

DECISIONS MADE
1. [What was decided] — Owner: [Name] — By: [Date]
2. [What was decided] — Owner: [Name] — By: [Date]

ACTION ITEMS
[ ] [Task] — Owner: CC — Due: [Date]
[ ] [Task] — Owner: [Other person] — Due: [Date]

NEXT TOUCHPOINT
[Scheduled date/time or "Needs scheduling"]

LEAD UPDATE
[If prospect: update stage to [X]]
[If client: satisfaction signal was [positive/neutral/negative]]
```

Add CC's action items to `memory/ACTIVE_TASKS.md` immediately.

### 5b: Draft Follow-Up Email

Generate within 2 hours of the meeting:

```
Subject: [Meeting topic] — Next steps

Hi [Name],

[Opening that references something specific from the conversation — not generic.]

[DECISIONS section if decisions were made]:
We aligned on:
• [Decision 1]
• [Decision 2]

[ACTION ITEMS section]:
Next steps:
• [CC's action] — [deadline]
• [Their action] — [deadline]

[NEXT MEETING if scheduled]:
Our next conversation is on [date] at [time]. I'll send a calendar invite.

[One-sentence close — warm but not over-the-top.]

Best,
Conaugh McKenna
OASIS AI Solutions
```

Present the draft to CC for review before sending. Do not auto-send.

### 5c: Update Lead Tracker

Update `memory/LEAD_TRACKER.csv` with:
```
[Date] | [Name] | [Meeting type] | [Key outcome — 1 sentence] | [Next action] | [Next action date]
```

If pipeline stage changed (e.g., from Discovery to Proposal), update the stage column.

### 5d: Log to Session Log

```
### [DATE] — Meeting: [Name] / [Company]
**Type:** [Discovery / Check-in / Strategy / Partnership]
**Outcome:** [1-sentence — what happened, what's the state of the relationship now]
**Action:** [CC's next action + deadline if applicable]
```

## Step 6: Follow-Up Cadence Reminders

Set reminders based on the meeting type (see `skills/meeting-automation/SKILL.md` Follow-Up Cadence):

- Discovery call → Remind CC in 3 days if no follow-up sent
- Client check-in → Remind CC in 7 days for next check-in
- Proposal sent → Remind CC in 3 days if no response
- Partner meeting → Remind CC in 48 hours to send term sheet draft

Add these to `memory/ACTIVE_TASKS.md` with due dates.

## Completion

Tell CC: "Briefs ready for [N] meeting(s) today. [Highlight any alert-level context — at-risk client, large deal meeting, first contact with high-value prospect]."

After post-meeting capture: "Meeting captured. [N] action items added to ACTIVE_TASKS. Follow-up email drafted — review before sending."

## Skill Reference
See `skills/meeting-automation/SKILL.md` for:
- Full pre-meeting brief template
- Meeting type templates (discovery, check-in, strategy, partnership)
- Post-meeting protocol
- Follow-up cadence rules

## Obsidian Links
- [[skills/meeting-automation/SKILL]] | [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]]
- [[skills/client-success/SKILL]] | [[brain/STATE]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
