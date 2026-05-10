---
name: Onboard Team Member
trigger: /onboard-team-member
description: Full contractor onboarding workflow — legal, access, context, and first-30-days schedule.
---

# Team Member Onboarding Workflow

## When to Use
When CC has hired a contractor or is bringing on a new team member. Trigger with `/onboard-team-member` and provide the person's name, role, start date, and tools needed.

## Step 1: Gather Information

Ask CC for the following if not already provided:

```
- Full name:
- Role title: (VA / Developer / Marketer / Sales / Other)
- Brand/team: (OASIS AI / PropFlow / Nostalgic / Cross-brand)
- Start date:
- Weekly hours:
- Compensation: ($X/hr or $X/month)
- Payment method: (Wise / PayPal / Stripe / e-transfer)
- Tools they'll need access to: (GitHub / Supabase / Slack / Google Workspace / Notion / etc.)
- Is this project-based or ongoing?
```

## Step 2: Generate Onboarding Checklist

Using `skills/team-management/SKILL.md` Day 0 through Day 30 protocol, generate a checklist specific to the role:

```
ONBOARDING CHECKLIST — [Name] — [Role]
──────────────────────────────────────

DAY 0 (Before they start)
[ ] NDA generated and sent for signature
[ ] Contractor agreement generated and sent for signature
[ ] Payment terms confirmed in writing
[ ] Compensation rate agreed

DAY 1 — Access Provisioning
[ ] [Tool 1] access granted (minimum permissions)
[ ] [Tool 2] access granted
[ ] [GitHub/repo] access granted (read/write as appropriate)
[ ] Welcome Loom recorded (10 min context walkthrough)

DAY 1 — Context Package
[ ] Brand guide sent
[ ] Relevant SOPs sent (only what applies to their role)
[ ] Key contacts introduced
[ ] First 30-day outcome stated in writing

DAY 3 — First Task Assignment
[ ] Task brief prepared using delegation template from skills/team-management/SKILL.md
[ ] Success criteria defined
[ ] Communication channel preference confirmed

CHECK-INS SCHEDULED
[ ] Day 7 check-in:  [date]
[ ] Day 14 snapshot: [date]
[ ] Day 30 review:   [date]
[ ] Weekly 1:1:      [day of week, recurring]
```

## Step 3: Draft NDA and Contractor Agreement

If the person is working on OASIS AI deliverables, use the contract generator:

```bash
python scripts/contract_generator/generator.py \
  --name "[Full Name]" \
  --email "[email]" \
  --upfront 0 \
  --monthly [monthly_rate]
```

For contractors without a formal contract (small scope, short term), at minimum:
- Confirm scope, rate, and payment terms in a written Slack or email message
- Log the agreement to `memory/DECISIONS.md`

## Step 4: Access Provisioning Checklist

Generate the specific access list based on their role and tools needed:

```
ACCESS PROVISIONING — [Name]
─────────────────────────────
Tool/Resource            | Access Level        | Action
─────────────────────────────────────────────────────────────────
GitHub (if developer)    | Collaborator        | Add to repo: [repo name]
Supabase (if developer)  | Viewer or Editor    | Add via dashboard
Slack/Discord            | Member              | Invite to workspace + channels: [list]
Google Workspace         | Shared credentials  | Via 1Password or Google admin
Notion / Asana / Linear  | Member              | Invite via email
n8n (if automation role) | Viewer              | Add to Hostinger VPS n8n instance
─────────────────────────────────────────────────────────────────
NOTE: Minimum permissions always. If unsure, start with read-only.
```

## Step 5: Context Package

Send this as a single document or Loom. Cover:

1. What CC's business is and which brand this person supports
2. Who the clients are (names and brief description of what they're buying)
3. How CC prefers to communicate (async-first, response time expectations)
4. The most important SOP(s) for their specific role
5. Tools they'll use and how CC wants them used
6. The #1 thing that would make this engagement a success

## Step 6: Schedule Check-Ins

Create calendar reminders for:
- Day 7 check-in (15 min): First deliverable review
- Day 14 snapshot (internal only): Performance snapshot scored 1-5
- Day 30 review (30 min with contractor): Full first-month review
- Weekly recurring 1:1 (15-30 min): Ongoing if >10 hrs/week

Log these to `memory/ACTIVE_TASKS.md` with due dates.

## Step 7: Add to Team Tracking

Update `brain/STATE.md` team section with:
```
Team member: [Name]
Role: [Role]
Brand: [Brand/team]
Start date: [Date]
Hours/week: [N]
Status: Onboarding (Day 0)
Next check-in: [Date]
```

## Step 8: Log to Session Log

Log to the V6.0 state DB (auto-mirrors to `memory/SESSION_LOG.md`):
```bash
python scripts/state_manager.py log --agent bravo \
  --note "Team onboarding: [Name] — [Role] for [Brand], start [Date] @ \$[rate], tools: [list], day-7 check-in: [date]"
```

## Completion

Tell CC: "Onboarding checklist generated for [Name]. Day 0 items are ready — NDA and contract pending your review, access list prepared. First check-in scheduled for [Day 7 date]. Memory updated."

## Skill Reference
See `skills/team-management/SKILL.md` for:
- Full Day 0 through Day 30 protocol
- 1:1 templates
- Performance review framework
- Offboarding protocol

## Obsidian Links
- [[skills/team-management/SKILL]] | [[memory/ACTIVE_TASKS]] | [[brain/STATE]]
