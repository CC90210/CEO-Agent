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

- [ ] [P0] **Bennett Coaching Deal — $10K upfront** — Two companies (tugboat + real estate) referred by Bennett. $5K each, 16 sessions, 1hr/session. Structure the offering, set pricing, schedule sessions.
- [ ] [P0] **Content Engine: CC's #1 Priority** — Build daily content routine for Kona Makana personal brand. Content is the inbound funnel. CC creates, Bravo handles scheduling/distribution/repurposing.
- [ ] [P0] **Close first OASIS retainer client** — Focus on inbound funnel via content. Cedarwood/Vortex effectively dead.
- [ ] [P0] **Import 47+ leads to CRM** — Only 3 in system. Run bulk import from research pipeline. Prerequisite for health scoring at scale.

## P1 — Weekly Recurring

- [ ] [P1] **Grade Q2 OKRs weekly** — Every Monday, update confidence scores in `brain/OKRs.md`. First check-in: 2026-04-07.
- [ ] [P1] **Review R-001 + R-010 weekly** — Bennett churn risk and scope creep. Check during briefing each Monday.

## P1 — CEO Operations Tools

- [ ] [P1] **Run first client health report** — `python scripts/client_health.py report`
- [ ] [P1] **Generate Bennett proposal** — Test `proposal_generator.py create --client "Bennett" --type retainer --tier scale`
- [ ] [P1] **Populate competitor intelligence** — Add Zapier, SingleKey to `data/competitors.json`
- [ ] [P1] **Run first investor/advisor update** — `/investor-update` for March 2026
- [ ] [P1] **Identify first hire** — VA hire at $5K MRR trigger. Start shortlisting on Upwork.

## P1 — Infrastructure

- [ ] [P1] **Create Google Meet link** — Store in .env.agents for booking confirmations
- [ ] [P1] **Wire n8n to cron_engine** — Connect n8n workflows to execute cron job actions
- [x] [P1] **Codex dual-AI integration** — Codex (GPT-5.4) integrated as Agent #17. Global + project-local. Context injection + failure recovery. Done 2026-04-02.

## P2 — Blocked / Waiting

| Task | Blocked By | Since | Action |
|------|-----------|-------|--------|
| TIKTIK Camera Feed | Midas network spec (NVR IP/creds/channels) | 2026-03-17 | Revisit when Midas provides spec |
| On The Bay Painting | Client not ready | 2026-03-16 | Revisit in weeks/months |

## P2 — Backlog

- [ ] [P2] **Fill `data/market_research/`** — HVAC automation market, PropFlow proptech landscape, AI agency sizing
- [ ] [P2] **Run first weekly knowledge maintenance** — `/knowledge-maintenance`

## Recently Completed
- [x] **Codex dual-AI integration** — Full integration: plugin, 7 skills, agent #17, context injection, failure recovery, global availability. Done 2026-04-02.
- [x] **CEO Operating System** — 3-wave parallel build. 50+ files. Done 2026-03-28.
- [x] **PropFlow production hardening** — 4 waves, 50+ files. RLS migration, multi-tenant. Done 2026-03-25.
- [x] **Inbound Lead Engine** — 6 phases. Content auto-posting LIVE. Done 2026-03-24.

*Last updated: 2026-04-03*
