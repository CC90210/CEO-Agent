# ACTIVE TASKS
> Read this FIRST at the start of every session. Priority: [P0] Critical, [P1] High, [P2] Medium.

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

- [ ] [P1] **Content pipeline: build real structure** — 21 draft posts exist in Supabase but auto-posting is DISABLED. Need CC to review content strategy before enabling. No posts will auto-publish.
- [ ] [P1] **Create Google Meet link** — Store in .env.agents for booking confirmations
- [ ] [P1] **Wire n8n to cron_engine** — Connect n8n workflows to execute cron job actions

## P2 — Blocked / Waiting

| Task | Blocked By | Since |
|------|-----------|-------|
| TIKTIK Camera Feed | Midas network spec (NVR IP/creds/channels) | 2026-03-17 |
| LinkedIn automation | Need local Chrome auth hookup | 2026-03-04 |
| On The Bay Painting | Client not ready — revisit in weeks/months | 2026-03-16 |
| PropFlow | Pivoted dev hours to OASIS | 2026-03-01 |

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

*Last updated: 2026-03-20*
