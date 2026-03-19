# ACTIVE TASKS
> Read this FIRST at the start of every session. Priority is marked with [P0] Critical, [P1] High, [P2] Medium.

## Target: $5,000 USD Net MRR by May 15, 2026

> Previous goal ($1,000 USD Net MRR by March 31, 2026) — **ACHIEVED** at $2,691 USD (+169%).

To reach the new target, we need **~5-6 new OASIS clients** at $400-500 USD/mo retainer.

### Current Progress
- **Current Net:** ~$2,691 USD/mo ($191 base + $2,500 Bennett Community Manager) + $3,000 USD upfront cash collected.
- **Gap to Goal:** $2,309 USD/mo
- **Pace Required:** ~1 new client/week for 6 weeks
- **Critical Risk:** 93% revenue concentration in Bennett — diversification is priority #1
- **Pipeline:** 50+ leads researched, 20+ emails sent, 2 warm leads (Cedarwood, Vortex)
- **Next Milestone:** Close first new OASIS retainer client + build Bennett Accelerator Week 2/4 assets.

## This Week (March 19) — Business Operations Engine DEPLOYED + Activation

### Wednesday (March 19) — Business Ops Engine BUILD COMPLETE
- [x] [P0] **Supabase Schema** — 14 new business ops tables deployed (leads, funnels, email, bookings, revenue, content, cron). All RLS enabled.
- [x] [P0] **Lead Engine** — `lead_engine.py` — full CRM: list, add, view, update, score, interact, followups, pipeline, search, funnel
- [x] [P0] **Email Engine** — `email_engine.py` — Gmail SMTP sending, templates, nurture sequences
- [x] [P0] **Booking Engine** — `booking_engine.py` — slot management, booking, reminders (Cal.com replacement)
- [x] [P0] **Content Engine** — `content_engine.py` — calendar, templates, multi-platform, week planning
- [x] [P0] **Revenue Engine** — `revenue_engine.py` — MRR tracking, Stripe sync, forecasting, goal tracking
- [x] [P0] **Cron Engine** — `cron_engine.py` — 12 automated business workflows seeded
- [x] [P0] **Remotion Studio** — `content-studio/` — 4 branded video compositions + 37 Claude AI skills installed
- [x] [P0] **5 New Skills** — lead-management, email-marketing, funnel-management, revenue-operations, booking-management
- [x] [P0] **MRR Goal Sync** — $5,000 USD Net MRR by May 15 updated across 15+ files

### Activation (Next Steps)
- [x] [P0] **Gmail App Password** — Already in .env.agents as GMAIL_USER. email_engine.py patched to read both key names.
- [x] [P0] **Generate first week's content** — 21 draft entries created for March 20-26 (quote_drop, ceo_log/educational, sobriety_log). Need body text.
- [ ] [P0] **Fill content body text** — 21 drafts exist in content_calendar, each needs actual post copy. Use `content_engine.py edit <id> --body '...'`
- [ ] [P0] **Import remaining leads to CRM** — 3 added (Bennett, Cedarwood, Vortex). 47+ more from research pipeline to import.
- [x] [P0] **Create first nurture sequence** — OASIS New Lead Nurture: Welcome (0h) → Value Add (72h) → CTA (168h). 3 NEPQ-style templates created.
- [ ] [P1] **Open booking slots** — `python scripts/booking_engine.py slots open-week` for next week
- [ ] [P1] **Sync Stripe revenue history** — `python scripts/revenue_engine.py sync-stripe`
- [ ] [P1] **Create Google Meet link** — Store in .env.agents for booking confirmations
- [ ] [P1] **Wire n8n to cron_engine** — Connect n8n workflows to execute cron job actions
- [ ] [P2] **Render first Remotion video** — Test OasisPromo composition end-to-end
- [ ] [P2] **LinkedIn Chrome Auth** — Needed for automated outreach engine

## TIKTIK (Ongoing)
- [ ] [P1] **WAITING: Midas Network Spec** — Need NVR IP/credentials/channels for go2rtc deployment
- [ ] [P1] **Verify Camera Feed in Smart Mode** — Once go2rtc running, test face recognition with IP camera

## Blocked / Waiting

| Task | Blocked By | Since | Notes |
|------|-----------|-------|-------|
| TIKTIK Camera Feed Deployment | Midas camera system spec | 2026-03-17 | Built system, waiting for NVR IP/credentials/channels |
| TIKTIK Smart Mode Camera Testing | go2rtc Docker deployment | 2026-03-17 | Once running on Midas network, test face recognition with IP camera |
| PropFlow development | Monitoring — pivoting dev hours to OASIS | 2026-03-01 | — |
| LinkedIn automation | Need local Chrome auth hookup | 2026-03-04 | — |
| On The Bay Painting software | Client not ready to switch — revisit in weeks/months | 2026-03-16 | — |

*Last updated: 2026-03-19*
