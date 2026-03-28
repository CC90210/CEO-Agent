---
tags: [tasks, active]
---
# ACTIVE TASKS
> Read this FIRST at the start of every session. Priority: [P0] Critical, [P1] High, [P2] Medium.

> [[brain/DASHBOARD]] | [[brain/STATE]] | [[memory/SESSION_LOG]]

## Target: $5,000 USD Net MRR by May 15, 2026

- **Current Net:** ~$2,982 USD/mo ($191 base + $2,500 Bennett flat + $291 Bennett 15% rev share on $1,940 community MRR) + $3,000 USD upfront collected.
- **Gap:** ~$2,018 USD/mo (~4-5 new OASIS clients at $400-500/mo)
- **Critical Risk:** 94% revenue from Bennett — diversification is #1 priority
- **Pipeline:** Cedarwood/Vortex deprioritized. Focus shifted to inbound funnel via content. Bennett coaching referral: $10K opportunity (2 companies).

---

## P0 — Revenue-Generating Work (CC's Morning Priorities)

- [ ] [P0] **Bennett Coaching Deal — $10K upfront** — Two companies (tugboat + real estate) referred by Bennett. $5K each, 16 sessions, 1hr/session. Structure the offering, set pricing, schedule sessions. This is immediate cash.
- [ ] [P0] **Content Engine: CC's #1 Priority** — Build daily content routine for Kona Makana personal brand. Content is the inbound funnel. CC creates, Bravo handles scheduling/distribution/repurposing.
- [ ] [P0] **Close first OASIS retainer client** — Cedarwood/Vortex deprioritized (effectively dead). Focus on inbound funnel via content.
- [ ] [P0] **Import 47+ leads to CRM** — Only 3 in system (Bennett, Cedarwood, Vortex). Run bulk import from research pipeline.
- [x] [P0] **Open booking slots** — 40 slots opened (March 30 - April 10, weekdays 3-5pm). Done 2026-03-26.
- [x] [P0] **BUILD: Inbound Lead Engine (Option B)** — 6 phases COMPLETE. Content auto-posting LIVE (5 posts published to X). CTA rotation active. IG DM → CRM bridge wired. Nurture emails have booking links. cc-funnel has booking CTA on success screen. E2E verified 2026-03-24. **Remaining:** Set `NEXT_PUBLIC_BOOKING_LINK` and `BOOKING_MEET_LINK` env vars once CC creates Google Meet link.

## P1 — CEO Operations Tools (New 2026-03-28)

- [ ] [P1] **Run first client health report** — `python scripts/client_health.py report`. All active clients scored. Set up `client_health_snapshots` table in Supabase for trend tracking.
- [ ] [P1] **Generate Bennett proposal (optional)** — Test `proposal_generator.py create --client "Bennett" --type retainer --tier scale` to verify output quality before using with new prospects.
- [ ] [P1] **Populate competitor intelligence** — `data/competitors.json` has schema + 2 seed entries (Make.com, Lindy AI). Add Zapier, SingleKey, and any other active competitors CC tracks. Run `/knowledge-maintenance` weekly to flag stale entries.
- [ ] [P1] **Run first investor/advisor update** — `/investor-update` command. Draft the March 2026 monthly update for any current advisors. Good practice for investor-readiness at $5K MRR.
- [ ] [P1] **Identify first hire** — Use `skills/scaling-playbook/SKILL.md` First Hire Framework. At $2.9K MRR the constraint is pipeline work eating delivery time. VA hire at $5K MRR trigger. Start shortlisting candidates on Upwork now.
- [ ] [P2] **Fill `data/market_research/`** — HVAC automation market (Canada), PropFlow proptech landscape, AI agency market sizing. Use `/research` command. Inform pitch deck and pricing strategy.
- [ ] [P2] **Run first weekly knowledge maintenance** — `/knowledge-maintenance` — compress SESSION_LOG, check patterns, verify wiki-links. Best run Sunday mornings.
- [ ] [P1] **Import 47+ leads** — Prerequisite for health scoring to work at scale. Only 3 leads in system now.

## P1 — Infrastructure (Stable)

- [x] [P1] **Skool daemon: heartbeat watchdog** — Rewrote watchdog with heartbeat-first liveness (2026-03-26). wmic was unreliable on Win11, causing constant restart cycles. Now daemon writes heartbeat every cycle, watchdog checks freshness.
- [x] [P1] **Telegram Bridge V11.0** — Full-context parity (2026-03-26). Loads CLAUDE.md, brain files, APP_REGISTRY. Removed --model sonnet, increased --max-turns to 25. PM2 restarted.
- [x] [P1] **Content pipeline: LIVE** — Auto-posting enabled via `late_publisher.py`. 5 posts published to X (2026-03-24). Scheduler calls `late_publisher.py publish-due` on cron. 16 scheduled + 21 drafts remaining in calendar.
- [ ] [P1] **Create Google Meet link** — Store in .env.agents for booking confirmations
- [ ] [P1] **Wire n8n to cron_engine** — Connect n8n workflows to execute cron job actions

## P2 — Blocked / Waiting

| Task | Blocked By | Since |
|------|-----------|-------|
| TIKTIK Camera Feed | Midas network spec (NVR IP/creds/channels) | 2026-03-17 |
| LinkedIn automation | Need local Chrome auth hookup | 2026-03-04 |
| On The Bay Painting | Client not ready — revisit in weeks/months | 2026-03-16 |

## Recently Completed (March 25)
- [x] **PropFlow production hardening** — 4 waves, 20+ commits, 50+ files. All API routes, mutations, queries company_id-scoped. RLS migration applied (10 tables). 7/7 audit PASS. Production-ready for multi-tenant use.
- [x] **PropFlow automation engine** — Python FastAPI → inline Next.js TypeScript. E2E tested. error/loading boundaries added to 5 routes.

*Last updated: 2026-03-28*
