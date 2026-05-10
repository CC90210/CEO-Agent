---
name: Client Health Report
trigger: /client-health
schedule: weekly (Friday)
description: Run full client health scoring, surface at-risk clients, draft retention actions, and log a health snapshot to memory.
---

# Client Health Report Workflow

## When to Run

- Every Friday before end of day
- Any time CC asks "how are my clients doing?"
- Immediately when a churn signal is detected (missed payment, no response, scope dispute)
- Before a client call to brief CC on the relationship health

## Execution Steps

### Step 1: Run the Full Report

```bash
python scripts/client_health.py report
```

Read the output. Note every client's tier. If any client is ORANGE or RED, treat this as urgent — do not defer.

### Step 2: Identify At-Risk Clients

```bash
python scripts/client_health.py alerts
```

For each ORANGE client:
- Review their score breakdown (run `python scripts/client_health.py score "<name>"`)
- Identify the specific dimension driving the low score (payment, engagement, scope, revenue, or relationship)
- Select the correct retention playbook from `skills/client-success/SKILL.md`

For each RED client:
- Alert CC immediately with the client name, score, and top two risk signals
- Do not proceed with other steps until CC is aware

### Step 3: Generate Retention Action Plans

For each client at YELLOW or below, generate a concrete action plan:

```
Client: [Name]
Tier: [YELLOW/ORANGE/RED]
Score: [X]/100
Driving issue: [which dimension scored lowest and why]
Playbook: [GREEN/YELLOW/ORANGE/RED retention playbook section from skill]

Action this week:
1. [Specific, time-bound action — who does what, by when]
2. [Second action if needed]
```

### Step 4: Draft Outreach for YELLOW+ Clients

For each YELLOW client, draft a check-in message (email or text based on preferred channel):

Tone: warm, curious, not transactional. Reference something specific from their account.

Template:
> "Hey [Name] — wanted to check in and make sure everything we're building together is still aligned with what you need. [One specific thing we delivered recently]. Anything coming up on your end I should know about?"

Draft the message and present to CC for review and send.

### Step 5: Log Health Snapshot

Log to the V6.0 state DB (auto-mirrors to `memory/SESSION_LOG.md`):

```bash
python scripts/state_manager.py log --agent bravo \
  --note "Client Health Report — portfolio \$[MRR], avg score [X]/100, tiers G[X]/Y[X]/O[X]/R[X], at-risk \$[X]; actions: [brief list]"
```

If Supabase is available, also insert a row into `client_health_snapshots` for each client:

```
table: client_health_snapshots
fields: client_name, score, tier, snapshot_date, mrr, lead_id
```

This enables trend analysis via `python scripts/client_health.py trends`.

### Step 6: Update brain/STATE.md

Update the "Client Health" section of `brain/STATE.md` with:
- Number of clients at each tier
- Any client that moved tiers since last week
- Total at-risk MRR

### Step 7: RED Client Protocol (if applicable)

If any client is RED:

1. Stop all other steps and alert CC immediately:
   > "🚨 [Client name] is at [score]/100 (RED). Risk signals: [list top 2]. Retention playbook recommends a personal call within 24 hours. Draft save offer?"

2. Wait for CC's response before drafting any outreach to RED clients — this requires CC's personal touch, not automation.

3. Log the red flag in `memory/MISTAKES.md` with the question: "What early signal was missed that let this client reach RED?"

## Output Summary Format

```
## Client Health Report — [YYYY-MM-DD]

Portfolio: $[MRR]/mo | Avg score: [X]/100 | At-risk: $[X]/mo

Tiers:
✅ GREEN ([count]):  [names]
⚠️  YELLOW ([count]): [names]
🔶 ORANGE ([count]): [names]
🚨 RED ([count]):    [names]

Actions queued:
- [Action 1 — client — owner — deadline]
- [Action 2 — client — owner — deadline]
```

## Skill Reference

- Health score algorithm: `skills/client-success/SKILL.md`
- Retention playbooks: `skills/client-success/SKILL.md` — Retention Playbooks section
- Churn triggers: `skills/client-success/SKILL.md` — Churn Prediction Triggers section

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
