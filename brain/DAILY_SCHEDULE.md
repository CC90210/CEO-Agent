---
tags: [schedule, accountability, daily, non-negotiable]
purpose: CC's optimized daily schedule starting April 13, 2026. Last shift at Nicky's Donuts was April 12. Free-range now. This is the structure.
owner: CC (Conaugh McKenna)
created: 2026-04-12
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# CC'S DAILY SCHEDULE

> This is the default day. Not every day will follow it perfectly. That's fine.
> The point is: when you wake up and don't know what to do, open this file.
> Weekends are lighter. Bad days happen. The structure survives the cheat days.

---

## WEEKDAY (Mon-Fri)

### 6:30 AM - WAKE + PRIME (30 min)
- Wake up. No phone for 10 minutes. Water first.
- 6:40: Open Telegram. Read Bravo's morning briefing (auto-sent at 7am).
- Briefing shows: overnight leads, MRR status, today's priority, calendar.
- **Decision point:** What's the ONE thing that moves revenue today?

### 7:00 AM - MOVEMENT (60 min)
- Gym, run, walk. Non-negotiable. This is the anchor.
- No business during movement. Just move.

### 8:00 AM - DEEP WORK BLOCK 1: OUTREACH + SALES (90 min)
- Check CRM for follow-ups due today.
- Draft and send 5-10 personalized outreach emails (quality over quantity).
- Follow up with any warm leads from yesterday.
- Prep for any discovery calls on the calendar.
- **This block closes deals. Protect it.**

### 9:30 AM - BREAK (15 min)
- Coffee, snack, step outside. Reset.

### 9:45 AM - DEEP WORK BLOCK 2: CLIENT DELIVERY (90 min)
- Work on active client projects (OASIS retainers).
- Build features, fix bugs, deliver value to paying clients.
- If no active clients yet: work on the CC Funnel, Gritly, or OASIS platform.

### 11:15 AM - CONTENT CREATION (60 min)
- This is your dedicated content window.
- Record 1 raw video (phone, tripod, talking head).
- Transfer to media/raw/ on desktop.
- Tell Bravo "process this video" in Claude Code.
- Review output, approve, schedule to TikTok/IG/YouTube.
- **If you don't record during this block, it doesn't happen.**

### 12:15 PM - LUNCH + PERSONAL TIME (60 min)
- Eat. Rest. Don't work. Don't scroll LinkedIn.
- Call a friend, watch something, decompress.

### 1:15 PM - DEEP WORK BLOCK 3: BUILDING (120 min)
- Code on Gritly, OASIS Platform, Real Estate App, AURA, or whatever's priority.
- This is the innovation block. Build things.
- Use Claude Code / Bravo for pair programming.

### 3:15 PM - BREAK (15 min)

### 3:30 PM - LEARNING + STRATEGY (60 min)
- Study: sales (NEPQ, closing), cybersecurity (TryHackMe), financial literacy.
- Review competitor content. Study chase.h.ai hooks.
- Read Atlas CFO reports on investment positions.
- Plan tomorrow's outreach targets *(inbound-first: review inbound funnel + nurture queue; outbound only if CC directed)*.

### 4:30 PM - ADMIN + CLEANUP (30 min)
- Respond to emails, DMs.
- Update ACTIVE_TASKS.md if priorities shifted.
- Handle any loose ends from the day.

### 5:00 PM - FREE TIME (4-5 hours)
- DJ practice, music, social life, relaxation.
- This time is YOURS. No guilt. You earned it by working 7am-5pm.

### 10:00 PM - WIND DOWN
- Bravo sends evening check-in via Telegram: "What moved the needle today?"
- Quick reflection (even mental, doesn't have to be written).
- Prep for tomorrow: check calendar, set alarm.

### 12:00 AM - SLEEP
- Hard cutoff. Phone on silent. Sleep is the foundation.

---

## WEEKEND (Sat-Sun)

### Saturday — LIGHT WORK + LIFE
- Wake 8-9am (flexibility).
- Morning: 1 hour of content review/creation (batch for the week if possible).
- Rest of day: personal life, DJ gigs, social, gym.
- No outreach. No cold emails on weekends.

### Sunday — PREP + RECHARGE
- Wake 8-9am.
- Morning: `/briefing` from Bravo. Review the week. Plan next week.
- Afternoon: light building if inspired. No pressure.
- Evening: prep Monday's outreach targets, review calendar.
- Bravo sends weekly retro prompt at 8pm Sunday.

---

## WEEKLY RITUALS (Non-Negotiable)

| Day | Time | Ritual | Bravo Supports |
|---|---|---|---|
| Monday | 7:00 AM | Morning briefing (MRR, pipeline, priorities) | Auto-sent via Telegram |
| Monday | 10:00 AM | Grade Q2 OKRs | `python scripts/ceo_dashboard.py briefing` |
| Wednesday | 11:15 AM | Content batch (record 2-3 videos for the week) | Process via content_pipeline.py |
| Friday | 4:30 PM | Weekly retro (what worked, what didn't) | `/retro` workflow |
| Sunday | 8:00 PM | Week-ahead plan | Bravo sends prep prompt via Telegram |

---

## ACCOUNTABILITY SYSTEM

### Bravo's role:
1. **Morning briefing (7:00 AM):** Telegram message with: overnight leads, MRR, today's calendar, the ONE priority.
2. **Evening check-in (10:00 PM):** "What moved the needle today? Reply with 1 sentence."
3. **Weekly retro (Sunday 8:00 PM):** "How was this week? What would you change?"
4. **Gentle pushback:** If CC spends a day building instead of selling, Bravo notes it in the next morning briefing: "Yesterday was a build day. Today needs to be an outreach day. 5 emails minimum."

### CC's role:
1. Reply to the morning briefing (even "got it" is enough).
2. Reply to the evening check-in (1 sentence, real answer).
3. Record at least 2 videos per week.
4. Send at least 5 personalized outreach emails per weekday.
5. Paste every sales call transcript to Bravo for `/close-review`.

### The pact:
CC builds the empire. Bravo runs the machine. Neither works without the other.
The schedule is the minimum. On fire days, CC will blow past it. On hard days, CC follows the minimum and that's enough. The only failure is not showing up at all.

---

## CRON JOB ALIGNMENT (Updated 2026-04-12)

These are the active automated jobs, timed to CC's schedule:

| Time | Job | What CC Sees |
|---|---|---|
| 6:00 AM | Stripe Revenue Sync | Silent unless new revenue |
| 7:00 AM | Morning Briefing (TODO: implement) | Telegram: MRR, leads, calendar, priority |
| 8:00 AM | Lead Follow-up Check | Telegram if follow-ups are due |
| 10:00 AM | Nurture Sequence Check | Silent unless Day-2/Day-5 email sent |
| 6:00 PM | Booking Reminders | Telegram if bookings tomorrow |
| 10:00 PM | Evening Check-in (TODO: implement) | Telegram: "What moved the needle?" |

**Every-5-min jobs (silent unless action):**
- Funnel Fast-Poll (every 1 min) — alerts within 60s of new form submission
- Funnel Lead Sync (every 5 min) — backstop
- Email Inbox Monitor (every 5 min) — alerts on real emails, silent on spam

**Retired permanently 2026-05-16:**
- Daily Outreach Batch — cron row deleted, `scripts/outreach_batch.py` removed, scheduler dispatch stubbed, Telegram approval callbacks pulled from `telegram_agent.js` and `gateway/adapters/telegram.js`. CC opted out of auto-drafted cold outreach; inbound funnel alerts are already covered by Funnel Fast-Poll. See `memory/feedback_no_cold_outreach_cron.md`.

**Disabled (by CC's request 2026-04-12):**
- Morning/Afternoon/Evening Content Post — n8n handles text content
- Content Week Plan — same

## Obsidian Links
- [[brain/USER]]
- [[brain/STATE]]
- [[brain/CEO_OPERATING_SYSTEM]]
- [[memory/ACTIVE_TASKS]]
- [[brain/OKRs]]
