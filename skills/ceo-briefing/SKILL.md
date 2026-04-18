---
name: ceo-briefing
description: Executive morning briefing — revenue, pipeline, clients, Atlas financial snapshot, blocked items, and today's #1 priority
tags: [skill, ceo, revenue, briefing]
---

# CEO Morning Briefing

## Overview

One command to give CC a complete picture of his empire in 30 seconds. Pulls live data from Stripe, Supabase, Atlas, and memory files. No fluff — just signal.

**Trigger:** `/briefing`, "morning briefing", "what's the status", session start on Monday mornings

## The Briefing Structure

When triggered, generate this exact format:

### Section 1: Revenue Pulse
```
MRR: $X,XXX / $5,000 target (XX% — Y days remaining)
[████████░░] XX%
```
**Data source:** `python scripts/revenue_engine.py mrr --json` OR `python scripts/stripe_tool.py balance --json`
**Fallback:** Read memory/ACTIVE_TASKS.md for last known MRR figure.

### Section 2: Pipeline Health
```
Leads: X total | Y warm | Z calls booked
Top prospects: [Name — stage — last contact — next action]
Overdue follow-ups: X leads haven't been contacted in 7+ days
```
**Data source:** `python scripts/lead_engine.py pipeline --json` and `python scripts/lead_engine.py followups --json`
**Fallback:** Read memory/ACTIVE_TASKS.md pipeline section.

### Section 3: Client Health
```
[CLIENT NAME] — [HEALTHY/AT-RISK/CRITICAL]
  Revenue: $X/mo | Contract: [status] | Last deliverable: [date]
  Risk: [any risk factors]
```
**Data source:** Supabase `leads` table (status=client) + revenue_events.
**Rule:** Flag as AT-RISK if: no interaction in 14+ days, deliverable overdue, or revenue >50% of total MRR.

### Section 4: Atlas Financial Snapshot
```
Trading: $X portfolio (Kraken) | Today P&L: +/-$X
Tax: [Next deadline] in [X days] | Status: [filed/pending/prep needed]
FIRE: $X / $900K target (X%)
```
**Data source:** Read `C:\Users\User\APPS\trading-agent\brain\STATE.md` (READ ONLY — never write).
**Fallback:** If file unreadable, show "Atlas: check trading-agent/ for latest."

### Section 5: Blocked Items
```
Waiting on CC:
- [Item] — blocked since [date] — impact: [what's stalled]

Waiting on others:
- [Person]: [Item] — since [date]
```
**Data source:** memory/ACTIVE_TASKS.md (items marked blocked or with "waiting" in description).

### Section 6: Today's #1 Priority
```
>> [THE ONE THING that moves the needle most today]
   Why: [1 sentence — revenue impact or risk reduction]
   First step: [Exact action CC should take right now]
```
**Logic for selecting the #1 priority:**
1. Overdue revenue-generating items (closing deals, sending invoices) — always first
2. At-risk client situations (retention > acquisition)
3. Pipeline advancement (warm leads ready to close)
4. Infrastructure fixes only if they block revenue
5. Never suggest "planning" or "organizing" as the priority — always action

## Execution Protocol

1. Run data collection in parallel (revenue, pipeline, client, Atlas)
2. Assemble briefing in the exact format above
3. Keep total output under 30 lines — CC should read it in 30 seconds
4. Highlight anomalies (revenue drop, lead gone cold, overdue item)
5. End with the #1 priority — make it impossible to ignore

## When NOT to Brief

- If CC opens with a specific urgent request, handle that first — brief after
- If CC says "skip the briefing", respect it
- Mid-session: only re-brief if CC asks or if a significant state change occurred

## Integration

- **Revenue Engine:** `scripts/revenue_engine.py` — MRR, Stripe sync, forecasting
- **Lead Engine:** `scripts/lead_engine.py` — pipeline, scoring, follow-ups
- **Atlas (CFO):** `C:\Users\User\APPS\trading-agent\brain\STATE.md` — READ ONLY
- **Active Tasks:** `memory/ACTIVE_TASKS.md` — blocked items, priorities
- **Booking Engine:** `scripts/booking_engine.py` — upcoming calls

## Obsidian Links
- [[brain/STATE]] | [[memory/ACTIVE_TASKS]] | [[brain/DASHBOARD]] | [[brain/CAPABILITIES]]
- [[skills/revenue-operations/SKILL]] | [[../../Marketing-Agent/skills/lead-management/SKILL]]
