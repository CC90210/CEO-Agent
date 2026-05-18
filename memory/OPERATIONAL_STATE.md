---
tags: [operational-state, ephemeral]
last_updated: 2026-05-18
freshness_threshold_days: 7
---

# OPERATIONAL STATE — Live Infrastructure & Known Issues

> Split out of `brain/STATE.md` on 2026-05-07 per Architecture Certification finding C5. Ephemeral content (PIDs, version-specific deploy state, daily-shifting issue queue, last-heartbeat) lives here under a 7-day freshness gate. Stable identity / North Star / capability architecture stays in `brain/STATE.md`.
>
> ⚠ **Read the freshness gate first.** If `last_updated` above is older than 7 days, treat every claim below as archived. Re-verify with `python scripts/self_audit.py --json`, `git log --since="7 days ago"`, and direct tool calls (`revenue_engine.py mrr`, `lead_engine.py pipeline`) before quoting anything as truth.
>
> ⚠ **Never state the day of the week** without computing it: `python -c "from datetime import date; print(date.today().strftime('%A'))"`.

---

## Skool Automation Status — ARCHIVED 2026-05-18

**Status: ARCHIVED — not running, not live.**

Daemon terminated (PID 43252) and code moved to `scripts/_archive/skool/`. Windows scheduled task `\SkoolWatchdog` still fires every 5 min but lands on a no-op (admin rights needed to disable the task itself). Skill at `skills/_archive/skool-automation/`. Workflows at `.agents/workflows/_archive/skool-{edit,push}.md`.

**Why archived:** CC no longer manages the Skool community the daemon was posting into. Code is preserved for revival when CC launches their own Skool community — full revival steps in `scripts/_archive/skool/README.md`.

**State files left in place (gitignored, harmless):** `tmp/skool_*.json`, `tmp/skool_daemon.{pid,heartbeat}`, `tmp/skool-browser/`. Delete for a clean slate before revival if desired.

---

## Active Infrastructure (last verified 2026-05-06)

| Tool | Status | Purpose |
|--------|--------|---------|
| **Send Gateway** | ✅ V5.6 HARDENED (2026-04-23) | `scripts/send_gateway.py` — single outbound chokepoint. CASL + cooldown + daily cap + hourly cap + domain cap + bounce breaker + draft critic gate + reservation guard + DNS doctor. `scripts/dns_reputation.py` added. 48 tests green. Business engines rewired through it: `outreach_engine`, `email_engine`, `funnel_nurture`, `booking_engine`, `contract_generator`. (Sixth caller `outreach_batch` retired 2026-05-16.) |
| **Unified Interaction Ledger** | ✅ V5.6 LIVE | `lead_interactions` table extended (cooldown_until + agent_source + metadata + 4 indexes) via migration 003. Shared memory across every outbound + N8N inbound. |
| **Context Builder** | ✅ V5.6 LIVE | `scripts/context_builder.py` — relationship stage + sentiment + prompt composition. Feeds persona-aware drafts. |
| **Inbound Classifier** | ✅ V5.6 LIVE | `scripts/inbound_classifier.py` — Claude Haiku intent/sentiment/priority classifier + keyword fallback. Writes to `lead_interactions` + publishes `agent_events.inbound.classified`. |
| **Draft Critic** | ✅ V5.6 LIVE | `scripts/draft_critic.py` — adversarial review of Claude-drafted outbound before gateway. Catches AI-slop, stage mismatch, ungrounded claims. 25+ hardcoded slop patterns + Haiku critic. |
| **Autonomous Reasoning Loop** | ✅ V5.6 LIVE | `scripts/autonomous_agent.py tick|daemon|status|decisions` — 7-phase brain loop (orient/recall/assess/plan/verify/execute/reflect). Hot-inbound escalation, due-followup detection, dormancy flagging. 8 policy gates. Shadow/dry-run modes. |
| **Migration Runner** | ✅ V5.6 LIVE | `scripts/apply_migration.py` — RPC path (never-expiring) + Management API fallback. exec_sql + exec_sql_ddl RPCs installed. 10 migrations applied (003-012). |
| **Skill Registry + Audit** | ✅ V5.6 LIVE | `scripts/register_skill.py` — create/register/list/audit/validate. Found 144 folder skills vs 7 registry vs 23 in CAPABILITIES.md — full drift report available. Zero invalid skills as of 2026-04-20. |
| **Inbound RPC (Python route)** | ✅ V5.6 LIVE (closed 2026-04-20) | `record_inbound_from_n8n()` Postgres function installed. `email_engine.py check-inbox` (scheduler polls every 5 min) now calls inbound_classifier + this RPC on every unread email. Blind spot closed via Python path; N8N workflow `1cGIN32alM8sf8OV` untouched. Optional N8N-side wiring preserved at `docs/N8N_INBOUND_INTEGRATION.md` for dual-path redundancy if CC wants it later. |
| **OASIS AI · Agent Command Center** | ✅ V4 LIVE (2026-04-30 PM) | https://agent-dashboard-cc90210.vercel.app · Next.js 15 + React 19 + Tailwind + recharts. OASIS BLUE (#3b82f6). Auth: Supabase email+password + Google OAuth. Multi-tenant via tenants + RLS (migrations 017+018+019). **Today page** has 6 hero metrics (Net MRR · Gap · Days Left · Outreach Today · Hot Inbound · Top Client Share with concentration risk warning >60%) + 4 secondary (Active Pipeline · Reply Rate 7d · Decisions Today · Pipeline All) + auto-promoting Primary Lead. **Pipeline page** hides lost/archived/null-email by default, ?show=all toggle. **Reasoning page** is an Agent Command Palette: 35 Bravo + 11 Maven + 5 Atlas + 5 Codex commands, profile-gated by agents_enabled, search/filter/copy-paste-ready. **Settings page**: ProfileEditor + PlanTemplateEditor (weekday/weekend with auto-materialize) + ChangePasswordForm + IntegrationDot grid. CRM cleaned 2026-04-30: 219 → 3 leads (primary retainer · Jonathan Hutton · Bev Drexler @ Tremont Cafe), 216 archived (soft-delete via tags), 279 interactions preserved. Tools: scripts/crm_reset.py, scripts/sync_slash_commands.py, scripts/supabase_admin.py, scripts/cloudflare_admin.py. NO realtime websocket. NO cross-Supabase / Stripe bridge — separate from oasis-ai-platform by design. |
| **OASIS AI Platform (oasisai.work)** | ✅ LIVE (separate product) | Vite/React marketing + checkout + client portal for one-off N8N automations. Separate Vercel project (oasis-ai-platform), separate Supabase project (oasis-ai-platform DB), separate repo (CC90210/oasis-ai-platform). DOES NOT cross-talk with the Command Center per CC's 2026-04-30 PM clarification. Bridge from Stripe -> Command Center was REVERTED. |
| **Telegram Bridge** | ✅ V15.4 LIVE | Full computer control (60+ cmds): apps, windows, browser, files, mouse. mousetool C binary. Tier classifier 24/24. PM2 online. |
| **macOS Computer Control** | ✅ V2.2 LIVE | `scripts/macos_control.py` — 65+ commands. `scripts/mousetool` native CoreGraphics binary. youtube-play, mouse-animate, drag, open --wait. |
| **Scheduler** | ✅ LIVE (Mac fixed) | `scheduler.py` — Python 3.9 compat fixed (was crashing since day 1 on Mac). All 12 cron jobs now running. PM2 online. |
| **Google Workspace CLI** | ✅ FULLY CONNECTED | `scripts/google_tool.py` wraps gws v0.18.1 + SMTP fallback. oasisaisolutions@gmail.com authenticated. 14 OAuth scopes. 5 integration tests passing. |
| **Skool Community Engine** | ⛔ ARCHIVED 2026-05-18 | Daemon stopped. Code at `scripts/_archive/skool/`. Revive for CC's own community per `scripts/_archive/skool/README.md`. |
| **Skool Watchdog** | ⛔ ARCHIVED 2026-05-18 | Watchdog launcher neutralized to no-op. Scheduled task `\SkoolWatchdog` still fires every 5 min (admin needed to disable) but lands on no-op. Harmless. |
| **cc-funnel** | ✅ LIVE | Lead capture form → Supabase → Telegram notify → Booking CTA on success screen. |
| **Semi-Auto Outreach Loop** | ⛔ RETIRED 2026-05-16 | Cold-outreach Telegram-approval cron + `scripts/outreach_batch.py` removed. CC opted out of auto-drafted cold outreach; inbound alerts now flow through `funnel_fast_poll`. |
| **Stripe SDK** | ✅ LIVE | Multi-account (OASIS, PropFlow, Nostalgic) |
| **Supabase SDK** | ✅ LIVE | Bravo, OASIS, Nostalgic projects |
| **Zernio (Late) CLI** | ⚠️ FREE PLAN LIMIT | 20 posts/month limit hit. Needs upgrade or frequency reduction. `late_tool.py` operational. |
| **n8n CLI** | ✅ WORKING | 47 workflows via `n8n_tool.py` REST API |
| **Lead CRM** | ✅ AUDITED | `lead_engine.py` — scoring, pipeline, funnel tracking |
| **Email Engine** | ✅ AUDITED | `email_engine.py` — Gmail SMTP, templates, nurture sequences |
| **Booking System** | ✅ AUDITED | `booking_engine.py` — slot management |
| **Content Calendar** | ✅ LIVE | Auto-posting via `late_publisher.py`. 5 published, 16 scheduled, 21 drafts. |
| **Revenue Dashboard** | ✅ AUDITED | `revenue_engine.py` — MRR tracking, Stripe sync |
| **Instagram Automation** | ✅ AUDITED | `instagram_engine.py` — Claude API replies (Windows only — Playwright) |
| **Outreach Engine** | ✅ AUDITED | `outreach_engine.py` — Gmail SMTP personalized outreach with .ics invites |
| **Obsidian Vault** | ✅ GRAPH-INDEXED | Knowledge Graph MCP live: 2,117 nodes, 3,725 edges, 696 communities. |
| **Browser Harness** | ✅ LIVE | Daemon attached to Chrome 147 via CDP port 9222. Skills: `skills/browser-harness/SKILL.md`, `browser/` dir. Doctor: `scripts/browser_harness_doctor.py`. Auto-start shortcut in Startup folder. |
| **Content Studio** | 🔀 MOVED TO MAVEN | Remotion + edit_content_v2.py + content-studio now live in `C:\Users\User\CMO-Agent`. Route all video/content tasks there. |
| **Semantic Memory** | ✅ LIVE | `scripts/mem0_tool.py` — Qdrant embedded, fastembed, Claude Haiku extraction. |
| **OpenCLI** | ✅ INSTALLED | v1.1.1 globally. 46 platforms, 345+ commands. |
| **Atlas (CFO Agent)** | ✅ LIVE | Separate project (CFO-Agent/). 16 skill playbooks, 8 CFO modules, 59 tax docs. Live Telegram bot (PM2). Pulse: `data/pulse/cfo_pulse.json`. |
| **Maven (CMO Agent)** | 🔄 INITIALIZING | Separate project (CMO-Agent/). Identity transformation from single-client AdVantage → multi-client Maven. 16 agents, 19 skills, Meta+Google Ads. Pulse: `data/pulse/cmo_pulse.json`. |
| **Firecrawl** | ✅ LIVE | `scripts/firecrawl_tool.py` + MCP server. Web scraping and structured extraction. |

---

## Known Issues (Priority Order, last triaged 2026-05-06)

| Issue | Severity | Action |
|-------|----------|--------|
| Top-client revenue concentration (~93%) | CRITICAL | Semi-auto outreach loop deploying. 2 new clients needed. |
| Zernio free plan limit | HIGH | Upgrade plan OR reduce posting to 20/month. CC decision needed. |
| Memory fragmentation (5 systems) | MEDIUM | `scripts/state_sync.py` — single-write protocol deploying. |
| TIKTIK IP Camera | LOW | Waiting on Midas for NVR spec. |
| LinkedIn Auth | LOW | Need Chrome auth hookup. |
| 3 apps missing CLAUDE.md | LOW | Grape Vine, Mindset, On The Hill. |

---

## Last Heartbeat

- **Date:** 2026-05-06
- **Agent:** BRAVO via Claude Code (claude-opus-4-6 — Lead architect)
- **Result:** Handoff to CMO-Agent for daily content creation.

---

## Update Protocol

This file is the ephemeral half of `brain/STATE.md`. Update when:

1. An infrastructure component changes status (LIVE → DEPRECATED, DEPLOYING → LIVE, etc.).
2. A new known issue is added or an existing one is resolved.
3. End-of-session: bump `last_updated:` if anything in the body changed.

Run `python scripts/state_sync.py --note "<one-line summary>"` after edits. The 7-day freshness gate is enforced by `memory_aging.py` — drift past it and the agent will treat this content as archived.

## Obsidian Links
- [[brain/STATE]] (stable identity / North Star / capability arch)
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/MISTAKES]]
- [[brain/CHANGELOG]] | [[brain/ORCHESTRATION]]


## Related (graph)

- [[memory/INDEX]]
- [[memory/ACTIVE_TASKS]]
- [[memory/ACTIVE_TASKS.template]]
