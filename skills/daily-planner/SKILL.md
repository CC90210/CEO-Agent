---
name: daily-planner
description: Structured daily plan for CC — content creation priorities, scheduled tasks, and revenue-moving actions. Generated each morning.
tags: [skill, ceo, planning, daily]
triggers: ["daily planner", "use daily planner", "run daily planner", "structured daily plan for cc \u2014 content creation priorities"]
tier: core
---

# Daily Planner — CC's Morning Operating System

## Overview

When CC opens his day ("morning", "coffee time", "let's go", "what's the plan"), generate a structured daily plan that tells him exactly what to do and in what order. CC's job is content, sales, and face-to-face. Everything else is Bravo's job.

**Trigger:** Morning greeting, "what should I do today", "daily plan", `/briefing` (planner is section 2 of the briefing)

## The Daily Plan Format

```
## Today's Plan — [Day, Month DD]

### THE ONE THING (do this first)
[Single most revenue-impactful action for today]
Why: [1 sentence]

### Content Block (60-90 min)
1. [ ] [Specific content piece — topic, platform, format]
2. [ ] [Second piece if applicable]
3. [ ] [Distribution/scheduling task Bravo preps]

### Revenue Actions (30-60 min)
1. [ ] [Sales call, follow-up, proposal, invoice — whatever moves money]
2. [ ] [Pipeline action]

### Admin (Bravo handles — CC reviews)
- [x] [Things Bravo already did overnight/automated]
- [ ] [Things that need CC's 2-minute approval]

### Tomorrow Prep (5 min at EOD)
- [ ] Tell Bravo what content you want to create tomorrow
- [ ] Flag any calls/meetings on tomorrow's calendar
```

## Plan Generation Logic

### Step 1: Check Calendar
- Read Google Calendar via `gws calendar events list --params '{"calendarId":"primary","timeMin":"TODAY_ISO","timeMax":"TOMORROW_ISO","singleEvents":true,"orderBy":"startTime"}'`
- Any meetings, calls, or deadlines block time first

### Step 2: Content Priority
CC said content is #1. Every day should have a content block:
- Check `python ../CMO-Agent/scripts/content_engine.py due --json` for scheduled content
- Check content calendar in Supabase for what's planned
- If nothing planned: suggest a topic from CC's content pillars:
  1. Sobriety Log (daily transformation story)
  2. Quote Drop (wisdom + personal take)
  3. CEO Log (building in public, business updates)
  4. AI Education (demystifying AI for business owners)
  5. Music/DJ culture (authenticity, lifestyle)
- Format: "Record a 60-second video about [topic]. Post to [platforms]."
- Bravo handles: writing captions, scheduling via Zernio (formerly Late), repurposing across platforms

### Step 3: Revenue Actions
Priority order:
1. **Coaching sessions** — If a coaching deal is active, prep/deliver sessions
2. **Invoices/payments** — Anything due or overdue
3. **Warm lead follow-up** — Anyone who responded but hasn't been closed
4. **New outreach** — Only if pipeline is empty and content engine is running

### Step 4: Admin (Bravo's Domain)
Things Bravo does WITHOUT CC:
- Content scheduling and distribution
- CRM updates, lead scoring
- Email nurture sequences
- Supabase/Stripe monitoring
- Memory sync, state updates
- Social media engagement replies (IG engine)

Things that need CC's quick approval:
- Outgoing emails to clients (draft → CC approves → send)
- Content that mentions specific people or sensitive topics
- Any payment or financial decision

### Step 5: Tomorrow Prep
At end of day (or when CC says "wrapping up"):
- Ask: "What content do you want to create tomorrow?"
- Ask: "Any calls or meetings tomorrow I should know about?"
- Save answers to memory for next morning's plan generation

## Day Templates

### Monday (Strategy Day)
- Morning briefing (full /briefing with revenue pulse)
- Weekly content calendar review
- Pipeline review (SOP-009)
- Batch content ideas for the week

### Tuesday-Thursday (Execution Days)
- Content creation block (60-90 min)
- Revenue actions (calls, follow-ups, coaching)
- Admin approvals (5-10 min)

### Friday (Close & Prep)
- Any overdue follow-ups — close the week clean
- Content batch if ahead of schedule
- Week review (what shipped, what's pending)
- Plan next week's priorities

### Wednesday (Content Day — Special)
CC's batch upload day. CC uploads video/files, Bravo schedules 1 piece/day across all channels via Zernio (formerly Late).
- Content block is 2-3 hours (filming, recording)
- Bravo handles all post-production scheduling

### Weekend (Nicky's Donuts + Rest)
- Automated systems run (IG engine, content calendar, nurture sequences)
- Bravo logs any overnight events for Monday briefing
- No active tasks pushed to CC unless CRITICAL

## Persistence

- Save today's plan to `memory/daily/YYYY-MM-DD.md` (Obsidian daily note)
- At EOD, mark completed items and carry forward incomplete ones
- Use CC's "tomorrow prep" answers to seed next day's plan
- Track content creation frequency: flag if CC hasn't created content in 3+ days

## Integration

- **CEO Briefing:** Daily planner is part of the /briefing output (Section 2)
- **Content Engine:** `../CMO-Agent/scripts/content_engine.py` for calendar and scheduling
- **Zernio Publisher:** `../CMO-Agent/scripts/late_publisher.py` (owned by Maven) for distribution (filename keeps the historical `late_` prefix; the SaaS rebranded to Zernio in 2026-03)
- **Google Workspace:** `gws calendar events list` for calendar events (REST-style, use --params)
- **Booking Engine:** `scripts/booking_engine.py` for scheduled calls

## The Philosophy

CC should never wonder "what should I be doing right now?" The planner answers that question before he asks it. His time is worth $200+/hr — every minute spent deciding what to do is a minute not doing the thing.

**CC creates. Bravo operates. Atlas manages capital.**

Three agents, one empire.


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[skills/ceo-briefing/SKILL.md]] | [[brain/STATE]] | [[memory/ACTIVE_TASKS]] | [[brain/CAPABILITIES]]
- [[../../../CMO-Agent/skills/content-engine/SKILL]] | [[brain/USER]]
