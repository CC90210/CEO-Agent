---
name: Generate Proposal
trigger: /proposal
description: Gather client context, select proposal type and tier, generate the proposal file, and prepare the follow-up cadence.
---

# Proposal Generation Workflow

## When to Run

- When CC says "/proposal" or "generate a proposal for [client]"
- After a discovery call where the client expressed interest in moving forward
- When a lead reaches "qualified" or "proposal" stage in the pipeline

## Pre-Flight: Required Information

Before generating, confirm these are known. If any are missing, ask CC before proceeding.

| Field | Required | Source |
|-------|----------|--------|
| Client name | Yes | CC provides |
| Proposal type (discovery/retainer/project) | Yes | CC provides or infer from context |
| Pricing tier (starter/growth/scale) or budget | Yes for retainer/project | CC provides |
| Client industry / pain points | Helpful | Supabase leads table or CC |
| Preferred start date | Helpful | CC |

If CC says "generate a proposal for [name]" without a type, default to **retainer** and **growth tier**, then confirm before saving.

## Execution Steps

### Step 1: Look Up Client Context

```bash
python scripts/lead_engine.py search "[client name]"
```

Or view the full lead record if the ID is known:

```bash
python scripts/lead_engine.py view <lead_id>
```

Note: industry, pain points, notes from discovery call, and current pipeline stage.

If the client is not in Supabase, ask CC for the key context: industry, main pain point, budget range.

### Step 2: Select Proposal Type and Tier

If CC hasn't specified, infer from the conversation context:

- First engagement with unknown client → **discovery**
- Ongoing automation work with known client → **retainer**
- Single defined deliverable → **project**

For tier, default to **growth** for retainer and **complete** for project unless CC specifies otherwise.

Confirm before generating:
> "Generating a [type] proposal for [client] — [tier] tier at [price range]. Should I proceed?"

### Step 3: Generate the Proposal

```bash
python scripts/proposal_generator.py create --client "[Name]" --type [retainer|project|discovery] --tier [tier]
```

If CC specified a custom budget:

```bash
python scripts/proposal_generator.py create --client "[Name]" --type project --budget [amount]
```

The proposal will be saved to `proposals/YYYY-MM-DD-[type]-[client].md`.

### Step 4: Review Against Proposal Checklist

Open the generated file and verify:

```
[ ] Executive summary uses client's specific pain point (not generic "AI transformation")
[ ] Solution section names specific tools/platforms (not generic "automations")
[ ] Every deliverable has an explicit acceptance criterion (retainer/project proposals)
[ ] Three pricing tiers are shown with the selected one marked
[ ] Payment schedule is explicit (upfront % and timing)
[ ] Proposal expiry date is 14 days from today
[ ] About OASIS AI is one paragraph or less
[ ] Next steps have a single, clear call to action
[ ] No placeholder text like "[describe the specific system here]" left unfilled
```

If any checklist item fails: edit the generated file before presenting to CC.

For the items marked with `[describe...]` — ask CC for the specifics or infer from the lead notes, then fill them in.

### Step 5: Present to CC

Output the proposal file path and a brief summary:

```
Proposal ready: proposals/[filename]

Summary:
  Client:  [Name]
  Type:    [type]
  Tier:    [tier] — [price range]
  Expires: [date]
  File:    [full path]

Key customisations made:
  - [Any specific pain points or context incorporated]

Checklist: [X/9 items passed — note any that need CC's input]

Send when ready. Follow-up cadence:
  Day 1:  Text/Slack — confirm receipt
  Day 3:  Email — share relevant result
  Day 7:  Call — direct ask
  Day 14: Email — expiry reminder
```

### Step 6: Update Lead Record

After CC approves and sends the proposal:

```bash
python scripts/lead_engine.py update <lead_id> --status proposal --notes "Proposal sent [date] — [tier] tier"
python scripts/lead_engine.py interact <lead_id> --type proposal_sent --channel email --subject "Proposal from OASIS AI"
```

Log the proposal send date so the follow-up cadence can be tracked.

### Step 7: Schedule Follow-Ups

Create follow-up reminders in `memory/ACTIVE_TASKS.md`:

```
[ ] [Client] Day 3 follow-up — share result/case study — due [date]
[ ] [Client] Day 7 follow-up call — direct ask — due [date]
[ ] [Client] Day 14 final touch — expiry reminder — due [date]
```

## Outcome Logging

When the proposal closes (won or lost), log to Supabase `proposals` table:

**Won:**
```bash
python scripts/lead_engine.py update <lead_id> --status won --notes "Accepted [tier] retainer at $[amount]/mo"
```

Then trigger the client onboarding workflow (`.agents/workflows/client-onboard.md`).

**Lost:**
```bash
python scripts/lead_engine.py update <lead_id> --status lost --notes "Lost — reason: [price/timing/competitor/budget/no_fit]"
```

Add a row to the win/loss log mentally: proposal type, tier, loss reason. This feeds the monthly win/loss review from `skills/proposal-generation/SKILL.md`.

## Skill Reference

- Full proposal templates: `skills/proposal-generation/SKILL.md`
- Pricing matrix details: `skills/proposal-generation/SKILL.md` — Pricing Matrix Templates
- Follow-up cadence: `skills/proposal-generation/SKILL.md` — Follow-Up Cadence section
- SOW template: `skills/proposal-generation/SKILL.md` — SOW Template section

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
