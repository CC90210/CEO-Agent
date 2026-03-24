---
tags: [tasks, active]
---
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
- [x] [P0] **BUILD: Inbound Lead Engine (Option B)** — 6 phases COMPLETE. Content auto-posting LIVE (5 posts published to X). CTA rotation active. IG DM → CRM bridge wired. Nurture emails have booking links. cc-funnel has booking CTA on success screen. E2E verified 2026-03-24. **Remaining:** Set `NEXT_PUBLIC_BOOKING_LINK` and `BOOKING_MEET_LINK` env vars once CC creates Google Meet link.

## P1 — Infrastructure (Stable)

- [x] [P1] **Skool daemon: watchdog fixed** — Was spawning 67+ zombie processes. New Python watchdog with tasklist detection + CREATE_NO_WINDOW. Single instance running headless (2026-03-23).
- [x] [P1] **Content pipeline: LIVE** — Auto-posting enabled via `late_publisher.py`. 5 posts published to X (2026-03-24). Scheduler calls `late_publisher.py publish-due` on cron. 16 scheduled + 21 drafts remaining in calendar.
- [ ] [P1] **Create Google Meet link** — Store in .env.agents for booking confirmations
- [ ] [P1] **Wire n8n to cron_engine** — Connect n8n workflows to execute cron job actions

## P2 — Blocked / Waiting

| Task | Blocked By | Since |
|------|-----------|-------|
| TIKTIK Camera Feed | Midas network spec (NVR IP/creds/channels) | 2026-03-17 |
| LinkedIn automation | Need local Chrome auth hookup | 2026-03-04 |
| On The Bay Painting | Client not ready — revisit in weeks/months | 2026-03-16 |
| PropFlow | Pivoted dev hours to OASIS | 2026-03-01 |

## Recently Completed (March 23)
- [x] **Stripe webhook fix** — All Stripe serverless functions on OASIS platform fixed (Node v24 crash, inline imports)
- [x] **Watchdog zombie fix** — 67 Python processes killed, new Python-based watchdog with headless daemon
- [x] **OASIS framework rebranded** — Agency Accelerants → OASIS AI Solutions for hometown friends
- [x] **Skool DM strategy** — Conversion-focused prompts, paid member skip, double-message bug fixed
- [x] **Payment links created** — 2 Stripe links ($300 + $200/mo each) for new clients

*Last updated: 2026-03-24*
