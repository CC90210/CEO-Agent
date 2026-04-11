---
tags: [state, ephemeral]
---

# STATE — Current Operational State

> Updated 2026-04-07 | **V15.4 macOS bridge live. Scheduler crash fixed (Python 3.9 compat). Semi-auto outreach loop deploying. All 12 cron jobs now running on Mac.**

## Operational Status

| Dimension | Level | Notes |
|-----------|-------|-------|
| **Version** | V5.5 | Self-Evolving Super-Intelligence (Bravo) |
| **Position**| ACTIVE | Community Manager for the primary retainer's Agency Accelerator + Lead Gen Funnel Operator |
| **Confidence** | 0.97 | Core automations production-grade. Telegram V15.4 live. Scheduler fixed. Semi-auto outreach deploying. primary retainer concentration risk unresolved. |
| **Focus Area** | **DIVERSIFY REVENUE + CONTENT-FIRST FUNNEL** | #1 risk: 93% revenue in primary retainer. Semi-auto outreach loop (daily scrape → score → Telegram approve) is the primary lever. CC creates content, Bravo runs pipeline. |
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

1. **Revenue:** ~$3,322 USD/mo Net MRR ($180 Stripe + $191 base + $2,500 primary retainer flat + $451 primary retainer 15% rev share on $3,007 Skool MRR).
2. **Gap:** ~$1,678 USD/mo (~2 new OASIS clients at $800-1,000/mo, or 4 at $400-500/mo).
3. **Pace:** ~1 new client/week for 5 weeks to hit target by May 15.
4. **Strategy:** Semi-auto outreach loop (daily batch) + CC Funnel inbound. Diversify beyond primary retainer.
5. **Risk:** primary retainer loss = drop to ~$822/mo. Diversification is the #1 operational priority.

## Active Infrastructure

| Tool | Status | Purpose |
|--------|--------|---------|
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
| **Content Studio** | ✅ READY | Remotion 4.0.436. Elite video pipeline V3 (`edit_content_v2.py`). |
| **Semantic Memory** | ✅ LIVE | `scripts/mem0_tool.py` — Qdrant embedded, fastembed, Claude Haiku extraction. |
| **OpenCLI** | ✅ INSTALLED | v1.1.1 globally. 46 platforms, 345+ commands. |
| **Atlas (CFO Agent)** | ✅ SILENT | Separate project. 12 strategies, live on Kraken + OANDA. Windows only. |
| **Firecrawl** | ✅ LIVE | `scripts/firecrawl_tool.py` + MCP server. Web scraping and structured extraction. |

## Known Issues (Priority Order)

| Issue | Severity | Action |
|-------|----------|--------|
| primary retainer revenue concentration (93%) | CRITICAL | Semi-auto outreach loop deploying. 2 new clients needed. |
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

## Capability Counts (2026-04-07)

- **Skills:** 187+ (added elite-video-production)
- **Agents:** 17 (all upgraded to V5.5+ standard)
- **Workflows:** 33 (.agents/workflows/)
- **Scripts:** 47 CLI engines
- **Supabase tables:** 28 (14 agent + 14 business ops)
- **MCP servers:** 8 working + 4 replaced by CLI + claude-mem plugin
- **Hooks:** 4 active safety/audit hooks

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
- **the prior community (Skool)** — the prior client coaching partnership. CC = Head Coach, $2,500/mo + 15% rev share. Contract formalized 2026-04-10. Context: [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]

## Last Heartbeat

- **Date:** 2026-04-11
- **Agent:** BRAVO via Claude Code (claude-opus-4-6"              # Lead architect (Bravo))
- **Result:** hyperthink skill + production hardening session (audit + 10 engines reviewed + 6 critical fixes + CASL compliance module)

*Last updated: 2026-04-11*

## Obsidian Links
> Connected notes for graph navigation

- [[brain/SOUL]] | [[brain/USER]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]]
- [[brain/APP_REGISTRY]] | [[brain/CEO_OPERATING_SYSTEM]] | [[brain/OKRs]]
- [[brain/BRAIN_LOOP]] | [[brain/GROWTH]] | [[brain/CHANGELOG]]
- [[brain/RISK_REGISTER]] | [[brain/INTERACTION_PROTOCOL]] | [[brain/ORCHESTRATION]]
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/DECISIONS]]
- [[memory/PATTERNS]] | [[memory/MISTAKES]] | [[memory/SELF_REFLECTIONS]]
- [[memory/content-strategy]] | [[memory/PROPOSED_CHANGES]]
- [[APPS_CONTEXT/INDEX]] | [[APPS_CONTEXT/GRITLY_CLAUDE]] | [[APPS_CONTEXT/IG_SETTER_PRO_CLAUDE]] | [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]
- [[skills/skool-automation/SKILL]] | [[skills/codex-delegation/SKILL]] | [[skills/elite-video-production/SKILL]]
- [[knowledge/index]] | [[knowledge/SCHEMA]]
- [[brain/DASHBOARD]]

## Last Heartbeat

- **Date:** 2026-04-11
- **Agent:** BRAVO via Claude Code (claude-opus-4-6"              # Lead architect (Bravo))
- **Result:** hyperthink skill + production hardening session (audit + 10 engines reviewed + 6 critical fixes + CASL compliance module)

*Last updated: 2026-04-11*

## Last Heartbeat

- **Date:** 2026-04-11
- **Agent:** BRAVO via Claude Code (claude-opus-4-6"              # Lead architect (Bravo))
- **Result:** hyperthink skill + production hardening session (audit + 10 engines reviewed + 6 critical fixes + CASL compliance module)

*Last updated: 2026-04-11*
