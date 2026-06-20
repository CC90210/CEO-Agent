---
name: CEO Briefing
trigger: /briefing
schedule: daily (morning)
description: Morning CEO digest — 5 North Star metrics, today's meetings, top priorities, client alerts, and the single most important action for the day.
---

# CEO Morning Briefing Workflow

## When to Use
Triggered by `/briefing`, "morning briefing", "what's the status", or automatically at session start on weekday mornings. Also triggered when CC asks "how are we doing?" or "what should I focus on today?"

## Step 1: Run the Dashboard Script

Pull live KPI data:

```bash
python scripts/ceo_dashboard.py briefing
```

If the script fails or returns zeroes (Stripe unavailable), fall back to:
1. `python scripts/revenue_engine.py mrr --json` for MRR
2. `memory/ACTIVE_TASKS.md` for last known MRR + active priorities
3. `brain/STATE.md` for current operational state

Capture the output — it contains the 5 North Star metrics.

## Step 2: Check Active Tasks and Priorities

Read `memory/ACTIVE_TASKS.md` and identify:
- Tasks marked `[OVERDUE]` or with a due date in the past
- Tasks marked `[BLOCKED]` — note what they're waiting on
- Top 3 in-progress items by impact
- Any task tagged as critical or revenue-blocking

## Step 3: Check Today's Calendar

Pull today's external meetings:

```bash
gws calendar events list --params '{"calendarId":"primary","singleEvents":true,"orderBy":"startTime","maxResults":10,"timeMin":"[TODAY_START_ISO8601]","timeMax":"[TODAY_END_ISO8601]"}'
```

For each external meeting, note:
- Who it's with and at what time
- Whether a pre-meeting brief exists (if not, flag it — CC may want to run `/meeting-prep [name]`)

## Step 4: Check Client Health Alerts

```bash
python scripts/client_health.py alerts --json
```

If the script is unavailable, scan `memory/ACTIVE_TASKS.md` for any client-flagged items.

Pull out:
- Any client with score below 55 (RED tier)
- Any client with score 55-74 (YELLOW tier) — recommend a proactive check-in
- Any client with an overdue deliverable

## Step 5: Compile the Digest

Assemble the full briefing using the CEO Digest Template from `skills/ceo-dashboard/SKILL.md`:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CEO BRIEFING — [Weekday, Date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXECUTIVE SUMMARY
[Net MRR vs target — one sentence. Highest-leverage thing happening right now.
Biggest open risk or action item needing attention today.]

NORTH STAR
  Net MRR:        $[X] / $10,000  ([X]%) — [X] days to target [↑↓→]
  Pipeline:        $[X] potential ([N] warm leads) [↑↓→]
  Client Health:   [X]/100 avg ([N] at risk) [↑↓→]
  Cash Position:   $[X] Stripe + bank (manual) [↑↓→]
  Content:         [N] posts / [target] target this week [↑↓→]

TODAY'S MEETINGS
  [Time] — [Name / Company] — [relationship: prospect/client/partner]
  [Time] — [Name / Company] — [relationship]
  [None if calendar is clear]

TOP PRIORITIES
  1. [Highest-impact task from ACTIVE_TASKS — why it matters for MRR]
  2. [Second priority]
  3. [Third priority]

ALERTS
  [Client at risk: Name — score/100 — reason — recommended action]
  [Overdue deliverable: Project — item — days late]
  [Pipeline item needs action: Lead — stage — last contact — days since]
  [NONE if all clear]

TODAY'S #1 PRIORITY
→ [Single most important action that moves the needle most right now]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Step 6: Determine Today's #1 Priority

Use this decision hierarchy to select the single most important action:

1. **Client emergency** (RED health score + no contact in >7 days) → reach out immediately
2. **Revenue recovery** (churned client or missed invoice due) → handle before anything else
3. **Close-ready deal** (lead in Negotiation stage + CC is the bottleneck) → follow up today
4. **Overdue deliverable** (client is waiting and deadline passed) → ship it
5. **Active pipeline** (discovery call booked or proposal due) → prepare
6. **Content** (no posts in 3+ days) → create one piece of content
7. **Backlog** (highest-impact task from ACTIVE_TASKS) → execute

Present it as a single clear action: "Today's #1 priority: [specific action]"

## Step 7: Update State (If New Information Was Found)

If the briefing revealed new information that changes the operational state (new client at risk, MRR changed, pipeline shifted), update `brain/STATE.md` with the current facts.

If any tasks need to be added based on alerts found, add them to `memory/ACTIVE_TASKS.md`.

## Step 8: Log the Briefing

Append a one-liner to `memory/SESSION_LOG.md`:

```
### [DATE] — Morning Briefing
MRR: $[X] ([X]% of target) | Pipeline: $[X] | Alerts: [N] | Priority: [1-sentence summary of #1 action]
```

## Completion

Present the full digest to CC. Then say: "Ready to go. What do you want to tackle first?"

If CC has a specific meeting today with a high-value prospect or at-risk client, proactively offer: "Your [X:XXam] call with [Name] — want a quick brief before then?"

## Notes

- This workflow should take no more than 90 seconds to run and present
- The executive summary must be 3 sentences max — never dump data without synthesis
- If all North Star metrics are on track and there are no alerts: say that clearly ("All systems green")
- The #1 priority must be one action — not a category, not a theme. One specific thing

## Skill Reference
See `skills/ceo-dashboard/SKILL.md` for:
- Full North Star metric definitions and data sources
- Weekly CEO Digest template
- Dashboard cadence and frequency rules

See `skills/ceo-briefing/SKILL.md` for:
- Extended briefing format with Atlas CFO snapshot
- Revenue breakdown by brand

## Obsidian Links
- [[skills/ceo-dashboard/SKILL]] | [[skills/ceo-briefing/SKILL]]
- [[memory/ACTIVE_TASKS]] | [[brain/STATE]] | [[memory/SESSION_LOG]]
- `scripts/ceo_dashboard.py` | [[skills/client-success/SKILL]]
