---
tags: [state, ephemeral]
---

# STATE — Current Operational State

> Updated 2026-04-21 | **V5.7 — SELF-AWARE BRAIN + OBSIDIAN FUSION + TOOL SHED.** Self-audit tool live (`scripts/self_audit.py`) — runs in <2s, emits 0-100 health score across orphans, skill frontmatter, script registration, MCP sync. **Current score: 100/100.** Obsidian MCP wired (9 servers synced across 3 configs), giving Bravo direct read/write access to the Obsidian vault. Tool Shed catalog (`brain/TOOL_SHED.md`) created as client-shareable GitHub repo inventory. PERSONALITY.md written — Bravo now has a defined voice, opinions, and growth edges separate from SOUL. Claudekit hooks active (file-guard, create-checkpoint, self-review). 5 VoltAgent subagent personas dropped in (security-auditor, code-reviewer, competitive-analyst, market-researcher, api-designer). 4 legacy handoff files deleted, 9 valuable orphans reconnected, 7 governance scripts registered in CAPABILITIES. Previous V5.6 foundation intact: unified interaction ledger, send_gateway chokepoint, context_builder, inbound_classifier, draft_critic, autonomous_agent reasoning loop. 147 skills, 62 scripts, 34 workflows.

## Operational Status

| Dimension | Level | Notes |
|-----------|-------|-------|
| **Version** | V5.6 | Outbound Chokepoint + Reasoning Loop Era (2026-04-20) |
| **Position**| ACTIVE | Community Manager for Bennett's Agency Accelerator + Lead Gen Funnel Operator |
| **Confidence** | 0.97 | Core automations production-grade. Telegram V15.4 live. Scheduler fixed. Semi-auto outreach deploying. Bennett concentration risk unresolved. |
| **Focus Area** | **DIVERSIFY REVENUE + CONTENT-FIRST FUNNEL** | #1 risk: 93% revenue in Bennett. Semi-auto outreach loop (daily scrape → score → Telegram approve) is the primary lever. CC creates content, Bravo runs pipeline. |
| **Energy** | MAXIMUM | Scheduler live on Mac. Telegram V15.4 full computer control. Elite video pipeline deployed. Outreach loop in build. |
| **Memory Health** | GOOD | Files current. Knowledge wiki seeded. mem0 live. Fragmentation acknowledged — single-write sync in progress. |

## Skool Automation Status (2026-04-04)

**Bot Mode — POST-REPLY ONLY, V2 RESEARCH-ENHANCED**
- **V2 upgrade:** Before replying, agent now identifies specific tools/products/frameworks in posts, web-searches them via DuckDuckGo (free, no API key), and injects research context into the reply prompt
- **Knowledge rules:** Agent will NEVER admit ignorance ("I don't know", "what is X?"). Either responds knowledgeably with research, or pivots to broader principles
- **Current functionality:** `_identify_research_topics()` → `_web_search()` → `_research_post()` → `generate_post_reply()` pipeline
- **Daemon:** Running (PID tracked in `tmp/skool_daemon.pid`). 108 posts replied all-time.
- **Heartbeat:** Working. `tmp/skool_daemon.heartbeat` written every cycle (5 min interval).
- **DMs:** Permanently disabled. CC handles all DMs manually.

---

## North Star: $5,000 USD Net MRR by May 15, 2026

> Previous goal ($1,000 USD Net MRR by March 31, 2026) — **ACHIEVED** at $2,691 USD (+169% surplus).

1. **Revenue:** ~$3,322 USD/mo Net MRR ($180 Stripe + $191 base + $2,500 Bennett flat + $451 Bennett 15% rev share on $3,007 Skool MRR).
2. **Gap:** ~$1,678 USD/mo (~2 new OASIS clients at $800-1,000/mo, or 4 at $400-500/mo).
3. **Pace:** ~1 new client/week for 5 weeks to hit target by May 15.
4. **Strategy:** Semi-auto outreach loop (daily batch) + CC Funnel inbound. Diversify beyond Bennett.
5. **Risk:** Bennett loss = drop to ~$822/mo. Diversification is the #1 operational priority.

## Active Infrastructure

| Tool | Status | Purpose |
|--------|--------|---------|
| **Send Gateway** | ✅ V5.6 HARDENED (2026-04-23) | `scripts/send_gateway.py` — single outbound chokepoint. CASL + cooldown + daily cap + hourly cap + domain cap + bounce breaker + draft critic gate + reservation guard + DNS doctor. `scripts/dns_reputation.py` added. 48 tests green. All 6 business engines (outreach_engine, outreach_batch, email_engine, funnel_nurture, booking_engine, contract_generator) rewired through it. |
| **Unified Interaction Ledger** | ✅ V5.6 LIVE | `lead_interactions` table extended (cooldown_until + agent_source + metadata + 4 indexes) via migration 003. Shared memory across every outbound + N8N inbound. |
| **Context Builder** | ✅ V5.6 LIVE | `scripts/context_builder.py` — relationship stage + sentiment + prompt composition. Feeds persona-aware drafts. |
| **Inbound Classifier** | ✅ V5.6 LIVE | `scripts/inbound_classifier.py` — Claude Haiku intent/sentiment/priority classifier + keyword fallback. Writes to `lead_interactions` + publishes `agent_events.inbound.classified`. |
| **Draft Critic** | ✅ V5.6 LIVE | `scripts/draft_critic.py` — adversarial review of Claude-drafted outbound before gateway. Catches AI-slop, stage mismatch, ungrounded claims. 25+ hardcoded slop patterns + Haiku critic. |
| **Autonomous Reasoning Loop** | ✅ V5.6 LIVE | `scripts/autonomous_agent.py tick|daemon|status|decisions` — 7-phase brain loop (orient/recall/assess/plan/verify/execute/reflect). Hot-inbound escalation, due-followup detection, dormancy flagging. 8 policy gates. Shadow/dry-run modes. |
| **Migration Runner** | ✅ V5.6 LIVE | `scripts/apply_migration.py` — RPC path (never-expiring) + Management API fallback. exec_sql + exec_sql_ddl RPCs installed. 10 migrations applied (003-012). |
| **Skill Registry + Audit** | ✅ V5.6 LIVE | `scripts/register_skill.py` — create/register/list/audit/validate. Found 144 folder skills vs 7 registry vs 23 in CAPABILITIES.md — full drift report available. Zero invalid skills as of 2026-04-20. |
| **Inbound RPC (Python route)** | ✅ V5.6 LIVE (closed 2026-04-20) | `record_inbound_from_n8n()` Postgres function installed. `email_engine.py check-inbox` (scheduler polls every 5 min) now calls inbound_classifier + this RPC on every unread email. Blind spot closed via Python path; N8N workflow `1cGIN32alM8sf8OV` untouched. Optional N8N-side wiring preserved at `docs/N8N_INBOUND_INTEGRATION.md` for dual-path redundancy if CC wants it later. |
| **OASIS AI · Agent Command Center** | ✅ V2.1 LIVE (2026-04-30) | Canonical URL: https://oasisai.work/app · backup: https://agent-dashboard-cc90210.vercel.app · Next.js 15 + React 19 + Tailwind + recharts. Auth: Supabase email+password + Google OAuth (login/signup/forgot/reset/signout). Multi-tenant via tenants + RLS (migrations 017+018+019). 11 pages (Today w/ weekday/weekend templates + carryover, Pipeline merged, Reasoning, Playbook /script with 4 prospect tracks + 10 objections, Playbook /deals V2, Playbook /drills V2, Agents w/ telemetry, Analytics, Integrations, Settings). Bridge to oasis-ai-platform: POST /api/auth/provision-from-stripe (Bearer auth, idempotent, inviteUserByEmail for new users, creates tenant + profile + auth user, stamps Stripe IDs). n8n inbound bridge: POST /api/inbound/n8n. Vercel cron: /api/cron/materialize-plans (3am UTC, materializes tomorrow's plan from weekday/weekend template). VPS artifacts shipped at infra/inbound-poller/ (Dockerfile + compose + README, awaits Hetzner provisioning). Env: BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, OPERATOR_EMAIL=conaugh@oasisai.work, BRIDGE_SECRET, PUBLIC_APP_URL, CRON_SECRET. |
| **OASIS AI Platform <-> Command Center bridge** | ✅ LIVE (2026-04-30) | One-way bridge: oasisai.work Stripe webhook (`api/stripe/webhook.ts` checkout.session.completed) -> oasisai.work/app/api/auth/provision-from-stripe -> creates tenant in bravo Supabase. Gated on Stripe Price metadata `command_center=true` (or `product_type=command_center`/`includes_dashboard=true`) so non-Command-Center purchases don't trigger. Bearer-auth via shared `BRIDGE_SECRET` (rotate by setting new value in BOTH Vercel projects' env). Verified end-to-end with simulated checkout 2026-04-30. Welcome email = Supabase inviteUserByEmail (real send). Existing users skip email. Two Vercel projects + two Supabase DBs preserved by design — bridge crosses on payment events only. |
| **Telegram Bridge** | ✅ V15.4 LIVE | Full computer control (60+ cmds): apps, windows, browser, files, mouse. mousetool C binary. Tier classifier 24/24. PM2 online. |
| **macOS Computer Control** | ✅ V2.2 LIVE | `scripts/macos_control.py` — 65+ commands. `scripts/mousetool` native CoreGraphics binary. youtube-play, mouse-animate, drag, open --wait. |
| **Scheduler** | ✅ LIVE (Mac fixed) | `scheduler.py` — Python 3.9 compat fixed (was crashing since day 1 on Mac). All 12 cron jobs now running. PM2 online. |
| **Google Workspace CLI** | ✅ FULLY CONNECTED | `scripts/google_tool.py` wraps gws v0.18.1 + SMTP fallback. oasisaisolutions@gmail.com authenticated. 14 OAuth scopes. 5 integration tests passing. |
| **Skool Community Engine** | ✅ V2 RESEARCH-ENHANCED | Post-reply only (DMs disabled). V2: web research before replying. Never admits ignorance. 108 posts replied all-time. |
| **Skool Watchdog** | ⚠️ NEEDS ADMIN FIX (Windows only) | Task uses bare `pythonw.exe` — needs full path. Run `scripts/fix_watchdog_task.ps1` as admin. Daemon manually started. |
| **cc-funnel** | ✅ LIVE | Lead capture form → Supabase → Telegram notify → Booking CTA on success screen. |
| **Semi-Auto Outreach Loop** | 🔄 DEPLOYING | `scripts/outreach_batch.py` — daily scrape → score → draft → Telegram approve buttons. In build. |
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

## Known Issues (Priority Order)

| Issue | Severity | Action |
|-------|----------|--------|
| Bennett revenue concentration (93%) | CRITICAL | Semi-auto outreach loop deploying. 2 new clients needed. |
| Zernio free plan limit | HIGH | Upgrade plan OR reduce posting to 20/month. CC decision needed. |
| Memory fragmentation (5 systems) | MEDIUM | `scripts/state_sync.py` — single-write protocol deploying. |
| SkoolWatchdog task path | LOW | Windows only. Run `scripts/fix_watchdog_task.ps1` as admin (one-time). |
| TIKTIK IP Camera | LOW | Waiting on Midas for NVR spec. |
| LinkedIn Auth | LOW | Need Chrome auth hookup. |
| 3 apps missing CLAUDE.md | LOW | Grape Vine, Mindset, On The Hill. |

## CEO Operating System (2026-03-28)

**FULLY BUILT — 3-Wave Session Complete**
- **Skills:** 15 (strategic-planning, competitive-intelligence, financial-modeling, client-success, proposal-generation, team-management, meeting-automation, project-management, ceo-dashboard, investor-communications, knowledge-management, scaling-playbook, risk-management, crisis-response, sales-methodology)
- **Workflows:** 10 (.agents/workflows/ — strategic-review, competitive-report, qbr, client-health-report, generate-proposal, onboard-team-member, meeting-prep, ceo-briefing, investor-update, knowledge-maintenance)
- **CLI Scripts:** 5 (competitive_intel.py, financial_model.py, client_health.py, proposal_generator.py, ceo_dashboard.py)
- **Note:** CEO OS scripts use Windows Python path conventions — verify on Mac before running.

## Knowledge Compilation System (2026-04-06)

**LIVE — Karpathy-style, no RAG**
- `knowledge/index.md` — 4 wiki pages: ai-automation-agency, revenue-model, tech-stack, client-playbook + video-production-bible
- Skill: `skills/knowledge-compilation/SKILL.md`
- Workflows: `/ingest`, `/query-knowledge`, `/lint-knowledge`

## Capability Counts (2026-04-11, verified via find)

- **Skills:** 152 (verified `find skills -name SKILL.md | wc -l`)
- **Agents:** 17 (all upgraded to V5.5+ standard)
- **Workflows:** 35 (.agents/workflows/, includes close-review)
- **Scripts:** 56 Python engines in scripts/
- **Supabase tables:** 28 (14 agent + 14 business ops)
- **MCP servers:** 8 working + 4 replaced by CLI + claude-mem plugin
- **Hooks:** 4 active safety/audit hooks
- **Cross-machine sync:** Windows (CCPC, 192.168.2.133) production + Mac (Conaughs-MacBook-Air, 192.168.2.196) cold-standby via `ssh cc-mac`
- **PM2 state:** Windows runs bravo-scheduler + telegram-bot (standalone) + skool daemon (standalone). Mac has bravo-telegram registered but stopped.

## Context Optimization (2026-03-31)

**7 patterns from Claude Code internal harness:**
1. Tiered context loading — T1/T2/T3 (default T2)
2. Transcript compaction — auto-archive SESSION_LOG > 14 days
3. Tool pool simple mode — RULE -1 in CLAUDE.md
4. Cost tracking — SQLite-backed per-operation
5. Memory aging — exponential confidence decay
6. Deferred init — heavy resources load only when needed
7. Deny-list permissions — config-driven

## Active App Portfolio (2026-04-10 update)

Three projects added to formal routing (APP_REGISTRY + APPS_CONTEXT):
- **Gritly** — Field Service Management SaaS. Next.js 15, Drizzle, Turso, Stripe, Better Auth. Foundation built (auth+onboarding+dashboard+marketing site). Context: [[APPS_CONTEXT/GRITLY_CLAUDE]]
- **IG Setter Pro** — Instagram DM automation (ManyChat replacement). Next.js 14, Turso, n8n, Claude API. Live at `ig-setter-pro.vercel.app`. Context: [[APPS_CONTEXT/IG_SETTER_PRO_CLAUDE]]
- **Agency Accelerance (Skool)** — Bennett Spooner coaching partnership. CC = Head Coach, $2,500/mo + 15% rev share. Contract formalized 2026-04-10. Context: [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]

## Obsidian Links
> Connected notes for graph navigation

- [[brain/SOUL]] | [[brain/USER]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]]
- [[brain/APP_REGISTRY]] | [[brain/CEO_OPERATING_SYSTEM]] | [[brain/OKRs]] | [[brain/CLIENT_READY]]
- [[brain/BRAIN_LOOP]] | [[brain/GROWTH]] | [[brain/CHANGELOG]]
- [[brain/RISK_REGISTER]] | [[brain/INTERACTION_PROTOCOL]] | [[brain/ORCHESTRATION]]
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/DECISIONS]] | [[memory/CLAUDE_HANDOVER]]
- [[docs/V6_ARCHITECTURE]] | [[infra/README]]
- [[memory/PATTERNS]] | [[memory/MISTAKES]] | [[memory/SELF_REFLECTIONS]]
- [[memory/content-strategy]] | [[memory/PROPOSED_CHANGES]]
- [[APPS_CONTEXT/INDEX]] | [[APPS_CONTEXT/GRITLY_CLAUDE]] | [[APPS_CONTEXT/IG_SETTER_PRO_CLAUDE]] | [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]
- [[skills/skool-automation/SKILL]] | [[skills/codex-delegation/SKILL]] | [[../CMO-Agent/skills/elite-video-production/SKILL]]
- [[skills/ethical-hacking/SKILL]] | [[skills/sales-closing/SKILL]]
- [[knowledge/index]] | [[knowledge/SCHEMA]]
- [[brain/DASHBOARD]]
- **Hubs (graph spine):** [[skills/INDEX]] · [[docs/INDEX]] · [[browser/README]] · [[browser/domain-skills/README]] · [[browser/interaction-skills/INDEX]] · [[apps/command-center/README]] · [[data/pulse/README]] · [[memory/outreach_archive/INDEX]] · [[memory/daily/INDEX]] · [[.gemini/INDEX]] · [[templates/agent-scaffold/README]]
- **Top-level:** [[PLAYBOOK]] · [[SECURITY]] · [[CLIENT_READY]]

## Last Heartbeat

- **Date:** 2026-04-30
- **Agent:** BRAVO via Claude Code (claude-opus-4-6"              # Lead architect (Bravo))
- **Result:** OASIS AI Agent Command Center V1 shipped. Multi-agent rebrand, profile system (user_profiles + daily_plans + integrations_health + n8n_webhook_secrets via migration 017), full UI rebuild (sidebar nav, 9 pages, recharts charts, framer-motion), POST /api/inbound/n8n route handler with sha256 auth, scripts/n8n_webhook_secret.py for issue/list/revoke, scripts/seed_profile.py idempotent operator+plan seeder, install/bootstrap.py wired for --create-command-center-account, docs/N8N_INBOUND_WEBHOOK.md 5-min copy-paste fix. Build clean (14 routes, 102kB shared), CC's profile seeded with Jonathan as primary lead. Pushed to main bf9af7f, Vercel auto-deploying. CC manual followups: (1) run database/017_user_profiles_grants.sql in Supabase SQL editor, (2) set OPERATOR_EMAIL=konamak@icloud.com in Vercel env, (3) issue n8n webhook secret + paste into workflow.

*Last updated: 2026-04-30*

## Manifest

<!-- MANIFEST:BEGIN -->
_Auto-generated by `scripts/catalog_sync.py` — do not edit this block manually._
_Last synced: 2026-04-24T22:32:45.830255+00:00_

| Type | Count |
|---|---:|
| Python scripts | 69 |
| PowerShell scripts | 9 |
| Shell scripts | 4 |
| **Total scripts** | **82** |
| Skills | 149 (7 destructive) |
| Agents | 20 |
| Workflows | 35 |

**Scripts by category:**

- Other: 28
- Data & Memory: 15
- System: 9
- Communication: 8
- Content: 8
- Governance: 5
- Browser & Web: 4
- Finance: 4
- Google: 1

<!-- MANIFEST:END -->
