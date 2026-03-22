# ACTIVE TASKS
> Read this FIRST at the start of every session. Priority: [P0] Critical, [P1] High, [P2] Medium.

> [[brain/DASHBOARD]] | [[brain/STATE]] | [[memory/SESSION_LOG]]

## Target: $5,000 USD Net MRR by May 15, 2026

- **Current Net:** ~$2,691 USD/mo ($191 base + $2,500 Bennett CM) + $3,000 USD upfront collected.
- **Gap:** $2,309 USD/mo (~5-6 new OASIS clients at $400-500/mo)
- **Critical Risk:** 93% revenue from Bennett — diversification is #1 priority
- **Pipeline:** 50+ leads researched, 20+ emails sent, 2 warm (Cedarwood, Vortex)

---

## P0 — Revenue-Generating Work (CC's Morning Priorities)

- [ ] [P0] **Close first OASIS retainer client** — Cedarwood and Vortex are warm. Follow up, book calls, close.
- [ ] [P0] **Import 47+ leads to CRM** — Only 3 in system (Bennett, Cedarwood, Vortex). Run bulk import from research pipeline.
- [ ] [P0] **Open booking slots** — `python scripts/booking_engine.py slots open-week`

## P1 — Infrastructure (Stable)

- [ ] [P1] **Skool community automation: activate and monitor** — Built scripts/skool_engine.py. Daemon LIVE (2026-03-21). Register Windows Task Scheduler (requires admin elevation) for persistent operation. Monitor member engagement metrics over 1-week test period. Adjust rate limits if Claude API quota becomes constraint.
- [ ] [P1] **Content pipeline: build real structure** — 21 draft posts exist in Supabase but auto-posting is DISABLED. Need CC to review content strategy before enabling. No posts will auto-publish.
- [ ] [P1] **Create Google Meet link** — Store in .env.agents for booking confirmations
- [ ] [P1] **Wire n8n to cron_engine** — Connect n8n workflows to execute cron job actions
- [x] [P1] **Skool Lead Magnets: emoji fix** — Fixed UTF-8 mojibake across L1, L2, L3 (2026-03-21)
- [x] [P1] **Skool community automation engine** — Built scripts/skool_engine.py with feed scanner, DM responder, new member welcome, Telegram notifications. Daemon operational (2026-03-21).

## P2 — Blocked / Waiting

| Task | Blocked By | Since |
|------|-----------|-------|
| TIKTIK Camera Feed | Midas network spec (NVR IP/creds/channels) | 2026-03-17 |
| LinkedIn automation | Need local Chrome auth hookup | 2026-03-04 |
| On The Bay Painting | Client not ready — revisit in weeks/months | 2026-03-16 |
| PropFlow | Pivoted dev hours to OASIS | 2026-03-01 |

## Recently Completed (March 21)
- [x] **Skool community automation engine** — Built scripts/skool_engine.py with feed scanner, DM responder, new member welcome, Telegram notifications. Daemon running LIVE with 5 post replies + 3 welcome DMs sent in first cycle.
- [x] **Skool automation production launch** — Auto-login, rate limiting (MAX_REPLIES_PER_CYCLE=5, MAX_DMS_PER_CYCLE=3), browser crash recovery, 2-min daemon interval. Windows Task Scheduler ready (skool-cron.cmd).
- [x] **Lead Magnets Lessons 5-6 published** — Notion (L5, +200 XP) and ManyChat (L6, +250 XP) published to Skool Classroom. Course now has 6 lessons.
- [x] **GWS CLI integration** — Installed v0.18.1, authenticated as oasisaisolutions@gmail.com, 93 skills copied, wrapper script created. Email, Calendar, Drive, Sheets, Docs all live.
- [x] **System cleanup: 13 dead scripts deleted** — search_emails.py, send_email.py, calendar_ops.py, google_calendar.py, deploy_lite_repo.py, linkedin_batch_send.py, notebooklm_tool.py, populate_notebooklm.py, post_authority.py, sanitize_repo.py, notion_sync.js, outreach/execute_campaign.js, outreach/sync_supabase_rest.js.
- [x] **Telegram noise reduction** — Category filtering applied (content/instagram/system blocked). Progress updates 2-min cadence.
- [x] **Lead-to-close pipeline designed** — 5 stages identified (Capture → Auto-Reply → Book → Follow-Up → Close). 2 gaps noted: funnel→CRM auto-sync, booking→calendar.
- [x] **Skool emoji fix** — Fixed UTF-8 mojibake across Lead Magnets L1-L3 (garbled 🧲, 🧠, 🛠️ → correct Unicode).
- [x] **SkoolIntro Remotion composition** — 450-frame (15s) intro video created, registered in Root.tsx. Zero TypeScript errors.

## Recently Completed (March 20)
- [x] **Full bug audit across all automations** — 39 bugs found across 4 audits, 20 critical/high/medium fixed
- [x] Instagram engine: 10 bugs fixed (lower/lowered, unbound result x2, JS injection, Claude model ID, date clamping, error logging, calendar import)
- [x] Booking engine: Windows strftime crash fixed (`%-d` → portable), `--upcoming` filter fixed
- [x] Revenue engine: CRITICAL NameError in cmd_clients fixed, annual MRR formula corrected
- [x] Email engine: stats query fixed (removed missing columns), filter order corrected
- [x] Outreach engine: ICS timezone fixed, body_preview added to email_log, timezone import added
- [x] Lead engine: ImportError guard added for supabase
- [x] Scheduler: timestamp format normalized for Supabase Z-suffix matching
- [x] Skool classroom fully restructured (12 courses, all content live)
- [x] Telegram bot fixed (409 conflict, timeout, startTime TDZ bug, system prompt, graceful shutdown)
- [x] DM bot rewritten (conversational voice, no CTAs, only notify on BOOKING)
- [x] Claude API integration for Instagram DM contextual replies
- [x] Content auto-posting DISABLED (21 drafts set to "draft" status, scheduler no-op'd)
- [x] All 8 business engines operational and audited

*Last updated: 2026-03-21*
