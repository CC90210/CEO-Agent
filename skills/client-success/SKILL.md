---
name: client-success
description: Client health scoring, churn prediction, retention playbooks, NPS framework, and expansion signals. Keeps OASIS AI clients healthy, growing, and referring.
tags: [skill, client-success, retention]
---

# Client Success — Health Scoring and Retention System

## Overview

Lost clients cost twice what new ones earn. This skill gives CC a repeatable system to measure every client relationship as a live number, predict churn before it happens, and take the right action at the right time.

**Primary tool:** `python scripts/client_health.py`
**Data source:** Supabase `leads` table (project: bravo), filtered to status = `client`

---

## Health Score Algorithm (0–100)

Each client is scored across five weighted dimensions every time the report runs.

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Payment Timeliness | 25% | Days between due date and receipt |
| Engagement Frequency | 25% | Messages and calls vs. expected baseline |
| Scope Satisfaction | 20% | Deliverables on track vs. delayed |
| Revenue Trajectory | 15% | MRR growing, stable, or declining |
| Relationship Signals | 15% | Referrals given, upsell interest, response speed |

### Scoring Rubric Per Dimension

**Payment Timeliness (25 pts max)**
- Paid on time or early: 25
- 1–7 days late: 17
- 8–14 days late: 10
- 15+ days late: 2
- Two late payments in a row: subtract 5 from final score (floor 0)

**Engagement Frequency (25 pts max)**
- 4+ touchpoints/month (meetings, replies, check-ins): 25
- 2–3 touchpoints/month: 18
- 1 touchpoint/month: 10
- No contact in 14+ days: 0

**Scope Satisfaction (20 pts max)**
- All deliverables on schedule: 20
- 1 item delayed, acknowledged: 14
- 2+ items delayed or unacknowledged: 6
- Active scope dispute: 0

**Revenue Trajectory (15 pts max)**
- Upsell in last 60 days, or MRR grew: 15
- Stable MRR, no change in 90 days: 11
- Downgrade or partial cancellation discussed: 5
- Active cancellation discussion: 0

**Relationship Signals (15 pts max)**
- Gave a referral or case study in last 90 days: 15
- Responds within 24 hours consistently: 11
- Slow to respond (48–72 hours average): 6
- Unresponsive or mentions "pausing" / "budget review": 0

### Final Score Calculation

```
health_score = (payment × 0.25) + (engagement × 0.25) + (scope × 0.20) + (revenue × 0.15) + (relationship × 0.15)
```

Scores are normalized to 0–100. No rounding — show one decimal.

---

## Risk Tiers

| Tier | Score | Color Code | Meaning |
|------|-------|------------|---------|
| GREEN | 80–100 | ✅ | Healthy. Expansion opportunity window. |
| YELLOW | 60–79 | ⚠️ | Friction present. Proactive contact required. |
| ORANGE | 40–59 | 🔶 | At-risk. Intervention within 48 hours. |
| RED | 0–39 | 🚨 | Critical. Executive-level save attempt required now. |

---

## Churn Prediction Triggers

Any single trigger moves a client one tier toward RED. Two or more triggers = immediate ORANGE minimum.

- No communication for 14+ consecutive days
- Payment 7+ days late for the second consecutive month
- Client declines a scope expansion or renewal discussion
- Client's response time has increased by 2x over 30 days
- Client uses phrases: "budget review", "pausing for now", "not the right time", "re-evaluating", "tightening up"
- Client cancels a scheduled meeting without rescheduling
- Deliverable missed by more than 7 days with no client acknowledgement
- Client stops reacting to content or engaging on social (if tracked)

When a churn trigger fires: log it immediately under the client's Supabase record and recompute health score.

---

## Retention Playbooks

### GREEN Tier (80–100): Expand and Protect

Goal: Deepen the relationship before complacency sets in.

1. Schedule quarterly business review (QBR) — review wins, preview next quarter
2. Share specific ROI evidence: automations run, time saved, revenue influenced
3. Introduce one upsell concept — frame it as "the natural next step"
4. Ask for a referral: "Do you know one other business owner who'd benefit from what we've done together?"
5. Send a handwritten note or unexpected value-add (relevant article, template, introduction)
6. Confirm contract renewal dates 60 days in advance

### YELLOW Tier (60–79): Proactive Reconnection

Goal: Surface friction before it becomes a decision to leave.

1. Send a warm, non-salesy check-in within 48 hours of scoring YELLOW
2. Ask one open question: "What's the biggest thing slowing you down right now?"
3. Share a recent win from their account — remind them of the value being delivered
4. Review deliverable status and proactively update them, even if nothing is overdue
5. Offer one concrete addition to scope at no extra cost (if the friction point is perceived value)
6. Reschedule any lapsed standing calls — block time that works for them

### ORANGE Tier (40–59): Intervention Within 48 Hours

Goal: Identify the specific issue and address it directly.

1. Call first — do not email. Text to schedule if needed.
2. Open with: "I want to make sure we're delivering the right things for you. Can we sync for 15 minutes?"
3. Listen for the real concern — don't defend, don't pitch. Ask and reflect back.
4. If it's budget: offer a modified scope that retains the relationship at lower MRR rather than full churn
5. If it's results: produce a results audit within 24 hours showing impact
6. If it's communication: create a standing weekly update and send the first one immediately
7. Log every detail of the conversation in Supabase

### RED Tier (0–39): Save or Release

Goal: Make one final, genuine attempt. If it fails, exit cleanly.

1. CC personally reaches out — not Bravo, not automated. A real message.
2. Acknowledge the issue directly: "I know things haven't been where they should. That's on me."
3. Present a save offer: one-month pause, scope reduction, free extension of one deliverable
4. Give a clear decision timeline: "I'd love to know your thinking by [date] so I can plan accordingly."
5. If no response in 7 days: send an offboarding message that leaves the door open
6. Capture the root cause in `memory/MISTAKES.md` — what early signal was missed?
7. Update Supabase lead status to `churned` and log the final health score

---

## NPS Framework

### When to Collect

- Onboarding complete (30 days in): pulse check
- Quarterly: at each QBR touchpoint
- Post-major-deliverable: immediately after a significant project completes
- At renewal: before the contract renewal conversation, not after

### How to Collect

Send a single-question message (email or text, matching the client's preferred channel):

> "Quick question — on a scale of 0-10, how likely are you to recommend OASIS AI to another business owner? No wrong answer."

Follow up with: "What's the main reason for that score?"

### Score Interpretation

| NPS Score | Classification | Action |
|-----------|---------------|--------|
| 9–10 | Promoter | Ask for referral within 72 hours |
| 7–8 | Passive | Ask: "What would make this a 10?" |
| 0–6 | Detractor | Treat as ORANGE tier — immediate outreach |

### NPS → Health Score Adjustment

- Promoter (9–10): +5 bonus to relationship signals dimension
- Passive (7–8): no adjustment
- Detractor (0–6): -10 to final health score, force YELLOW minimum

---

## Expansion Playbook

### Upsell Readiness Signals

A client is ready for an upsell conversation when at least three of these are true:
- Health score above 80 for two consecutive months
- Has referenced a new pain point or project in conversation
- MRR has been stable for 60+ days (not growing — stagnant is an opportunity)
- Recently gave a referral or positive testimonial
- Has asked "can you also do X?" in any channel

### Cross-Sell Opportunities

| Current Service | Natural Cross-Sell |
|----------------|-------------------|
| n8n automation retainer | CRM build-out in Supabase |
| Lead generation automation | Email nurture sequences |
| Social content scheduling | Full content strategy retainer |
| One-time project | Monthly maintenance retainer |
| OASIS AI retainer | PropFlow for real-estate clients |

### Referral Request Script

Only ask when health score is GREEN and at a natural conversation break:

> "We've been getting some great results together. Do you know one or two other business owners — doesn't have to be in your industry — who are still doing things manually that they could be automating? I'd love an introduction. I'll make sure they're taken care of."

---

## Client Lifecycle Stages

Every client exists in exactly one stage. Stage transitions are logged in Supabase.

| Stage | Definition | Primary Action |
|-------|-----------|---------------|
| **Onboarding** | Contract signed, setup in progress (days 1–30) | Complete setup checklist, first win delivery |
| **Ramp** | Systems live, client learning the value (days 31–60) | Weekly check-ins, remove friction, document wins |
| **Steady State** | Delivering consistently, client engaged | Monthly updates, QBR, upsell exploration |
| **Growth** | Client expanding scope or referring others | Prioritize, reward loyalty, increase touchpoints |
| **Renewal** | 60 days before contract end | QBR, renewal proposal, upsell packaging |
| **At-Risk** | Health score YELLOW or below | Retention playbook triggered |
| **Churned** | Contract cancelled | Root cause analysis, 90-day win-back check |
| **Win-Back** | Previously churned, re-engaged | Treat as new client, address original issue first |

---

## Weekly Client Health Report Template

Run every Friday before the week ends. Output format:

```
## Client Health Report — Week of [YYYY-MM-DD]

| Client | MRR | Health Score | Tier | Last Contact | Days Since Contact | Next Action |
|--------|-----|-------------|------|-------------|-------------------|-------------|
| [Name] | $X,XXX | XX.X | 🟢 GREEN | [date] | X days | [action] |
| [Name] | $X,XXX | XX.X | ⚠️ YELLOW | [date] | X days | [action] |

**Portfolio MRR:** $X,XXX | **Average Health:** XX.X | **At-Risk Revenue:** $X,XXX

### Alerts This Week
- 🚨 [Client]: [specific trigger fired]
- ⚠️ [Client]: [specific risk signal]

### Actions Required This Week
1. [Priority action — client — deadline]
2. [Priority action — client — deadline]
```

---

## Integration with CEO Briefing

The `/briefing` skill calls `python scripts/client_health.py report --json` in Section 3.
Any ORANGE or RED clients surface as blocked items in Section 5 (Blocked Items).

## Obsidian Links
- [[brain/STATE]] | [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]]
- [[skills/revenue-operations/SKILL]] | [[skills/lead-management/SKILL]]
- [[skills/ceo-briefing/SKILL]] | [[brain/USER]]
