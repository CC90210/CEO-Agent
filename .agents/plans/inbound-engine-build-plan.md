---
title: "Inbound Lead Engine — Option B Build Plan"
created: 2026-03-24
target: Tonight (March 24, 2026)
estimated_time: "~2 hours CC+Bravo"
status: READY_TO_EXECUTE
---

# Inbound Lead Engine — Full Build Plan

> **Goal:** Turn on the full inbound flywheel: Content → Lead Magnet → Funnel → Nurture → Book → Close.
> **Timeline:** Tonight, March 24, 2026.
> **Estimated CC+Bravo time:** ~2 hours across 6 phases.

---

## Current State (What Already Exists)

Everything below is BUILT but **turned off or disconnected**:

| Component | Script/App | Status |
|-----------|-----------|--------|
| Lead capture funnel | `C:\Users\User\APPS\cc-funnel` → cc-funnel.vercel.app | ✅ Live but needs UX polish |
| Funnel → CRM sync | `scripts/funnel_sync.py` | ⏸️ Built, not on cron |
| Nurture emails (Day 2 + Day 5) | `scripts/funnel_nurture.py` | ⏸️ Built, not on cron |
| Lead CRM | `scripts/lead_engine.py` | ✅ Working |
| Email engine | `scripts/integrations/email_engine.py` | ✅ Working |
| Booking system | `scripts/booking_engine.py` | ✅ Working |
| Content calendar | `../CMO-Agent/scripts/content_engine.py` | ✅ 21 drafts sitting idle |
| Content generator | `../CMO-Agent/scripts/content_generator.py` | ✅ Claude API powered |
| Content repurposer | `../CMO-Agent/scripts/content_repurposer.py` | ✅ Cross-platform |
| Late API (social posting) | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | ✅ 8 accounts connected |
| Late publisher | `../CMO-Agent/scripts/late_publisher.py` (owned by Maven) | ⏸️ Built, auto-posting DISABLED |
| Scheduler daemon | `scripts/scheduler.py` | ✅ PM2, but content posting stubbed |
| Content cron jobs | 12 jobs in Supabase `cron_jobs` | ⏸️ Seeded but content posting returns "disabled" |
| Instagram DM engine | `../CMO-Agent/scripts/instagram_engine.py` (owned by Maven) | ✅ Running |
| Skool community engine | `scripts/skool_engine.py` | ✅ Running (PID 59248) |

---

## Phase 1: Refine cc-funnel UX (30 min)

**App location:** `C:\Users\User\APPS\cc-funnel`
**Deploy:** Vercel (auto-deploy on git push to CC90210/cc-funnel)

### What to Change in `src/app/page.tsx`:

1. **Step 0 — Hero polish:**
   - Add a micro-headline above "Hey, I'm CC": something like `✦ PICK YOUR FREE RESOURCE` in small caps
   - Make the interest cards feel more interactive: add a subtle checkbox/toggle visual on the left side of each card (replaces the current checkmark on the right)
   - Add a subtle animated border glow on selected cards
   - Add brief social proof line below the cards: `"Trusted by 50+ local businesses in Ontario"` (or similar)

2. **Step 1 — Reduce friction on AI questions:**
   - Replace the textarea for "biggest time-waster" with a **checkbox grid** of common pain points:
     - `[ ] Lead follow-up` `[ ] Scheduling` `[ ] Data entry` `[ ] Social media posting`
     - `[ ] Invoicing` `[ ] Customer support` `[ ] Email management` `[ ] Other`
   - This reduces typing and increases completion rate
   - Keep business name + business type dropdowns as-is (they work)

3. **Step 1 — Reduce friction on Brand questions:**
   - "Who's your audience?" → change from free text to a dropdown/chip selector:
     - Entrepreneurs, Fitness/Wellness, Real Estate, Local Businesses, Creators, Other

4. **Step 2 — Contact capture improvements:**
   - Make Instagram handle feel more prominent (it's a key conversion channel for CC)
   - Add "I'll personally DM you within 24 hours" next to Instagram field
   - Change submit button text from "Get my free stuff" → **"Send me my free [audit/session/quote]"** (dynamic based on interest)

5. **Success screen improvements:**
   - Add a **clear next step CTA**: "While you wait, join my free Skool community" with link to https://www.skool.com/agency-accelerants
   - Add CC's Instagram handle as a follow CTA
   - Make it feel like a celebration, not just a confirmation

6. **Technical improvements:**
   - Add `<meta>` tags for link preview when shared (og:title, og:description, og:image)
   - Add favicon
   - Error handling: show inline validation errors, not silent failures

### File Changes:
- `src/app/page.tsx` — all UI changes above
- `src/app/globals.css` — animated border glow, checkbox grid styles
- `src/app/layout.tsx` — meta tags, favicon
- `public/og-image.png` — generate an OG image for link previews (use generate_image tool)

### Acceptance Test:
- Navigate through all 3 paths (AI, Music, Brand) on mobile viewport (375px)
- Submit a test lead → verify it appears in Supabase `funnel_leads` table
- Clean up test lead after verification

---

## Phase 2: Content CTA System (20 min)

Every piece of content posted needs a soft CTA driving traffic to the funnel.

### 2A. Create CTA templates in Supabase `content_templates`

Run these commands to insert CTA-enabled templates:

```bash
# Sobriety Log (daily)
python ../CMO-Agent/scripts/content_engine.py templates create \
  --name "Sobriety Log with CTA" \
  --platform x \
  --pillar sobriety_log \
  --template "Day {{day_number}} sober. {{insight}}\n\n🔗 Free AI audit for your business → cc-funnel.vercel.app" \
  --vars '["day_number", "insight"]'

# CEO Log (daily)
python ../CMO-Agent/scripts/content_engine.py templates create \
  --name "CEO Log with CTA" \
  --platform x \
  --pillar ceo_log \
  --template "{{insight}}\n\nIf you're a business owner drowning in manual work, I built something for you → cc-funnel.vercel.app" \
  --vars '["insight"]'

# Quote Drop (daily)
python ../CMO-Agent/scripts/content_engine.py templates create \
  --name "Quote Drop with CTA" \
  --platform x \
  --pillar quote_drop \
  --template "\"{{quote}}\"\n\n— {{author}}\n\nBuilding in public. Free automation audit → cc-funnel.vercel.app" \
  --vars '["quote", "author"]'

# Educational (alternating days)
python ../CMO-Agent/scripts/content_engine.py templates create \
  --name "Educational with CTA" \
  --platform x \
  --pillar educational \
  --template "{{hook}}\n\n{{body}}\n\nWant me to audit YOUR business for free? → cc-funnel.vercel.app" \
  --vars '["hook", "body"]'
```

### 2B. Update content_generator.py to include CTA

In `../CMO-Agent/scripts/content_generator.py`, update the generation prompt to include a soft CTA in every post. The CTA should rotate between:
- `"Free AI audit → cc-funnel.vercel.app"`
- `"DM me 'AUDIT' for a free business review"`
- `"Link in bio for your free automation assessment"`

**Rule:** CTA must be the LAST line. Never more than 1 CTA per post. Keep it conversational, not salesy.

### 2C. LinkedIn/Instagram versions need longer CTAs

For LinkedIn posts, the CTA can be longer:
```
---
I'm offering free AI automation audits for business owners this month.

If you're spending 10+ hours/week on tasks that could be automated, 
I'll personally review your workflow and show you what's possible.

No pitch, no upsell — just the audit.

→ cc-funnel.vercel.app
```

---

## Phase 3: Activate Content Posting Pipeline (30 min)

### 3A. Un-stub the content auto-posting

In `scripts/scheduler.py`, line 201-206, the `run_content_post` function is STUBBED:

```python
def run_content_post(config: dict, env_vars: dict) -> str:
    """Content auto-posting disabled — awaiting CC review of content structure."""
    # TODO: Re-enable by restoring the line below once content strategy is approved by CC.
    # return run_script("../CMO-Agent/scripts/late_publisher.py", ["--json", "publish-due"], timeout=120)
    log("Content auto-posting disabled — awaiting CC review")
    return "Content auto-posting disabled — awaiting CC review"
```

**Change to:**

```python
def run_content_post(config: dict, env_vars: dict) -> str:
    """Publish scheduled content via Late API."""
    return run_script("../CMO-Agent/scripts/late_publisher.py", ["--json", "publish-due"], timeout=120)
```

### 3B. Verify ../CMO-Agent/scripts/late_publisher.py works end-to-end

1. Check `../CMO-Agent/scripts/late_publisher.py` (owned by Maven) exists and has a `publish-due` command
2. Ensure it reads from `content_calendar` table where `status='scheduled'` and `scheduled_for <= now`
3. Ensure it calls `late_tool.py create` to actually post
4. Ensure it marks entries as `status='posted'` after successful publish
5. If `late_publisher.py` is broken or missing logic, fix it

### 3C. Generate this week's content

```bash
# Generate 21 draft slots (3/day x 7 days) in content_calendar
python ../CMO-Agent/scripts/content_engine.py week-plan

# Auto-generate real content for all drafts via Claude API
python ../CMO-Agent/scripts/content_generator.py generate-week

# Repurpose X posts to LinkedIn, Instagram, Threads
python ../CMO-Agent/scripts/content_repurposer.py repurpose-week --platforms linkedin,instagram,threads
```

**Verify:** After running these, check `content_calendar` has entries with status=`scheduled` and real body text (not placeholder `[DRAFT - ...]`).

### 3D. Register funnel_sync and funnel_nurture in cron_jobs

These two scripts are built but NOT registered as cron jobs:

```bash
# Funnel sync: check every 4 hours for new funnel leads → sync to CRM
python scripts/core/cron_engine.py add \
  --name "Funnel Lead Sync" \
  --action-type funnel_sync \
  --schedule "0 */4 * * *" \
  --description "Sync new cc-funnel leads into CRM leads table + send welcome email"

# Funnel nurture: run daily at 10am ET (14:00 UTC)
python scripts/core/cron_engine.py add \
  --name "Funnel Nurture Sequence" \
  --action-type nurture_check \
  --schedule "0 14 * * *" \
  --description "Send Day 2 and Day 5 follow-up emails to funnel leads"
```

### 3E. Ensure scheduler daemon is running

```bash
# Check if bravo-scheduler is running
pm2 list

# If not running, start it
pm2 start scripts/scheduler.py --name bravo-scheduler --interpreter python

# Verify it's picking up cron jobs
pm2 logs bravo-scheduler --lines 20
```

---

## Phase 4: Wire Instagram DM → CRM Bridge (15 min)

### 4A. Update ../CMO-Agent/scripts/instagram_engine.py

When the Instagram engine detects a DM that expresses interest (keywords: "automation", "audit", "help", "business", "pricing", "services", "website"), it should:

1. Auto-reply with CC's voice (already does this)
2. **NEW:** Also insert the person as a lead into the CRM if not already there:

```python
# After generating auto-reply, check if this person should be a lead
if any(keyword in message_text.lower() for keyword in INTEREST_KEYWORDS):
    # Insert into leads table via lead_engine
    subprocess.run([
        sys.executable, str(SCRIPTS_DIR / "lead_engine.py"),
        "add",
        "--name", sender_name,
        "--source", "instagram_dm",
        "--notes", f"DM conversation: {message_text[:200]}",
    ], capture_output=True, timeout=30, cwd=str(PROJECT_ROOT))
    
    # Notify CC
    notify(f"🎯 IG lead captured: {sender_name} — {message_text[:100]}", category="lead")
```

### 4B. Define interest keywords

```python
INTEREST_KEYWORDS = [
    "automation", "automate", "audit", "ai", "help my business",
    "pricing", "services", "how much", "work together", "website",
    "need help", "looking for", "can you", "interested",
]
```

---

## Phase 5: Booking Link Integration (10 min)

### 5A. Add Google Meet link to .env.agents

CC needs to create a Google Meet link and add it:

```
BOOKING_MEET_LINK=https://meet.google.com/xxx-xxxx-xxx
```

**CC action:** Create a recurring/reusable Google Meet link and paste it into `.env.agents`.

### 5B. Update nurture emails with booking link

In `scripts/funnel_nurture.py`, update the Day 2 and Day 5 email templates to include a direct booking CTA:

**Day 2 AI email** — After "Want me to send it over?", add:
```html
<p style="color:#ccc;line-height:1.6">Or if you're ready to talk, grab a free 15-min slot: 
<a href="{{BOOKING_LINK}}" style="color:#e8c547">Book a call →</a></p>
```

**Day 5 AI email** — Replace "reply 'send it'" with a booking link button:
```html
<a href="{{BOOKING_LINK}}" style="display:inline-block;background:#e8c547;color:#0a0a0a;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
Book Your Free Audit Call →
</a>
```

Where `{{BOOKING_LINK}}` reads from `os.environ.get("BOOKING_MEET_LINK")` or falls back to the booking engine's available slots.

### 5C. Update success screen on cc-funnel

After form submission, the success screen should include a "Book a call now" button that goes directly to the booking link (`.env.agents` → `BOOKING_LINK`, currently `https://calendar.app.google/tpfvJYBGircnGu8G8`) or an embedded calendar-style scheduler widget.

---

## Phase 6: Verify End-to-End & Go Live (15 min)

### 6A. Full flow test

1. **Submit test lead** on cc-funnel.vercel.app (use a test email)
2. **Verify Supabase** — `funnel_leads` table has the entry
3. **Run funnel_sync.py** manually — verify lead appears in `leads` table
4. **Run funnel_nurture.py stats** — verify lead shows as "new"
5. **Check content_calendar** — verify posts are scheduled with CTAs
6. **Check pm2 list** — verify scheduler is running
7. **Clean up** test data

### 6B. Verify Late API can post

```bash
# Test a single post (use a real draft from content_calendar)
python scripts/late_tool.py posts --limit 5
python ../CMO-Agent/scripts/content_engine.py due
```

### 6C. Confirm all cron jobs are active

```bash
python scripts/core/cron_engine.py list
```

Should show these as active:
- Morning Content Post (9am ET)
- Afternoon Content Post (1pm ET)  
- Evening Content Post (7pm ET)
- Lead Follow-up Check (weekdays 8am)
- Funnel Lead Sync (every 4 hours) **← NEW**
- Funnel Nurture Sequence (daily 10am ET) **← NEW**  
- Content Week Plan (Sunday 8pm)
- All other existing cron jobs

### 6D. Delete test data and update state

```bash
# Clean test lead from funnel_leads and leads tables
python scripts/integrations/supabase_tool.py delete funnel_leads --filter "email=test@example.com" --project bravo
python scripts/integrations/supabase_tool.py delete leads --filter "email=test@example.com" --project bravo
```

---

## Phase Summary & Checklist

| # | Phase | Time | Deliverable |
|---|-------|------|-------------|
| 1 | Refine cc-funnel UX | 30 min | Polished, high-converting funnel with checkboxes, social proof, Skool CTA |
| 2 | Content CTA system | 20 min | Every post includes a soft CTA → cc-funnel.vercel.app |
| 3 | Activate content pipeline | 30 min | Auto-posting enabled, week's content generated, cron jobs registered |
| 4 | Instagram DM → CRM | 15 min | DM leads auto-captured into CRM |
| 5 | Booking link integration | 10 min | Nurture emails + funnel success screen → booking CTA |
| 6 | End-to-end verification | 15 min | Full flow tested, all crons active, test data cleaned |

**Total: ~2 hours**

---

## CC's Manual Actions (Can't Be Automated)

1. **Create a Google Meet link** → paste into `.env.agents` as `BOOKING_MEET_LINK`
2. **Review the first batch of generated content** before the first auto-post goes out (just a quick scan)
3. **Push cc-funnel to GitHub** after Claude Code makes changes (triggers Vercel deploy)

---

## After Tonight — What the System Does Autonomously

```
Every day:
├── 9am ET:  Quote Drop posts to X/LinkedIn/Instagram/Threads (with CTA)
├── 1pm ET:  CEO Log or Educational post (alternating, with CTA)
├── 7pm ET:  Sobriety Log posts (with CTA)
├── Every 4h: Funnel leads synced to CRM + welcome email sent
├── 10am ET:  Day 2/Day 5 nurture emails sent to qualifying leads
├── 8am ET:  Lead follow-up check (scores + flags due follow-ups)
└── 6pm ET:  Booking reminders sent

Every week:
├── Sunday 8pm: Next week's 21 drafts auto-generated + repurposed
└── Monday 9am: MRR report + pipeline review

24/7:
├── Skool engine: Auto-replies to posts, welcome DMs, nurture sequences
├── Instagram engine: Auto-replies to DMs, captures interested leads to CRM
└── Telegram notifications: CC gets alerted on new leads/bookings only
```

**The flywheel:**
1. Content goes out 3x/day on all platforms → attracts eyeballs
2. Every post has a CTA → drives traffic to cc-funnel.vercel.app
3. Funnel captures lead info → syncs to CRM
4. Welcome email + Day 2/Day 5 nurture → warms the lead
5. Nurture emails include booking link → lead books a call
6. CC just shows up to the call and closes → $400-500/mo retainer

---

## Files Modified (Summary for Claude Code)

| File | Action | Phase |
|------|--------|-------|
| `APPS/cc-funnel/src/app/page.tsx` | Major refactor — UX polish | 1 |
| `APPS/cc-funnel/src/app/globals.css` | New styles | 1 |
| `APPS/cc-funnel/src/app/layout.tsx` | Meta tags | 1 |
| `APPS/cc-funnel/public/og-image.png` | New file (generate) | 1 |
| `../CMO-Agent/scripts/content_generator.py` | Add CTA rotation to generation prompt | 2 |
| `scripts/scheduler.py` (line ~201) | Un-stub `run_content_post` | 3 |
| `../CMO-Agent/scripts/late_publisher.py` (owned by Maven) | Verify/fix publish-due command | 3 |
| `../CMO-Agent/scripts/instagram_engine.py` (owned by Maven) | Add DM → CRM bridge | 4 |
| `scripts/funnel_nurture.py` | Add booking link to email templates | 5 |
| `brain/STATE.md` | Update with new status | 6 |
| `memory/ACTIVE_TASKS.md` | Update tasks | 6 |
| `memory/SESSION_LOG.md` | Log session | 6 |

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/DASHBOARD]]
