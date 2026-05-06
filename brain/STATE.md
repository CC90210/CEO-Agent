---
tags: [state, ephemeral]
---

# STATE — Current Operational State

> Updated 2026-05-06 | **V6.1 — SCAFFOLDING MECHANISM live on top of V6.0.3 polish + V6.0 foundation.** Self-audit health: 97/100 (`python scripts/self_audit.py`). Counts are auto-emitted by self_audit and the MANIFEST block at the bottom of this file — do NOT hardcode them in the header.
>
> **What V6.1 adds (fork mechanism):** `brain/operator.profile.json` (gitignored single source of truth), `scripts/personalize.py` (renders `brain/USER.md` + memory templates from `*.template.md` placeholders, skip-on-exists), `scripts/scaffold.py` (token-replaces operator identifiers across tracked files at fork-time, refuses to run on the original operator's repo, `--backup` snapshots first). Wizard `step_finalize` always runs personalize; prompts for scaffold on new operators. `self_audit.check_personalization()` warns when profile missing. CC's working copy is preserved via the safety guard + gitignored personal files.
>
> **V6.0 base (intact):** multi-provider model router (Claude/OpenAI/OpenRouter/Groq/DeepSeek/local), autonomous skill synthesizer with `[NEW]→[VALIDATED]` lifecycle, 3-layer memory (working → episodic → semantic) with nightly Haiku-scored consolidation, multi-platform messaging gateway (Telegram + Discord + Slack), DL stack (GNN skill router, RLHF/DPO outreach, NTM, MAML, TFT MRR forecast, neuro-symbolic compliance gate), public-repo installer (`install.sh` / `install.ps1`), PII protection in `.gitignore`. **V5.7 foundation:** self_audit, send_gateway hardened (CASL + cooldown + caps + draft critic + DNS doctor), autonomous reasoning loop, Obsidian MCP.

## Operational Status

| Dimension | Level | Notes |
|-----------|-------|-------|
| **Version** | V6.1 | Scaffolding mechanism on top of V6.0 multi-provider + DL stack + V5.6 outbound chokepoint |
| **Position**| ACTIVE | Community Manager for the primary retainer's Agency Accelerator + Lead Gen Funnel Operator |
| **Confidence** | 0.97 | Core automations production-grade. Telegram V15.4 live. Scheduler fixed. Semi-auto outreach deploying. primary retainer concentration risk unresolved. |
| **Focus Area** | **RESET AND DIVERSIFY REVENUE** | CC is doing a physical/mental reset (quitting weed). Focus is on daily minimums: content creation and cold outreach volume. Target is still $5k MRR by May 15. |
| **Energy** | RECOVERING | CC reported being in a bad state recently. Reset protocol initiated. Baseline execution only. |
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
| **Send Gateway** | ✅ V5.6 HARDENED (2026-04-23) | `scripts/send_gateway.py` — single outbound chokepoint. CASL + cooldown + daily cap + hourly cap + domain cap + bounce breaker + draft critic gate + reservation guard + DNS doctor. `scripts/dns_reputation.py` added. 48 tests green. All 6 business engines (outreach_engine, outreach_batch, email_engine, funnel_nurture, booking_engine, contract_generator) rewired through it. |
| **Unified Interaction Ledger** | ✅ V5.6 LIVE | `lead_interactions` table extended (cooldown_until + agent_source + metadata + 4 indexes) via migration 003. Shared memory across every outbound + N8N inbound. |
| **Context Builder** | ✅ V5.6 LIVE | `scripts/context_builder.py` — relationship stage + sentiment + prompt composition. Feeds persona-aware drafts. |
| **Inbound Classifier** | ✅ V5.6 LIVE | `scripts/inbound_classifier.py` — Claude Haiku intent/sentiment/priority classifier + keyword fallback. Writes to `lead_interactions` + publishes `agent_events.inbound.classified`. |
| **Draft Critic** | ✅ V5.6 LIVE | `scripts/draft_critic.py` — adversarial review of Claude-drafted outbound before gateway. Catches AI-slop, stage mismatch, ungrounded claims. 25+ hardcoded slop patterns + Haiku critic. |
| **Autonomous Reasoning Loop** | ✅ V5.6 LIVE | `scripts/autonomous_agent.py tick|daemon|status|decisions` — 7-phase brain loop (orient/recall/assess/plan/verify/execute/reflect). Hot-inbound escalation, due-followup detection, dormancy flagging. 8 policy gates. Shadow/dry-run modes. |
| **Migration Runner** | ✅ V5.6 LIVE | `scripts/apply_migration.py` — RPC path (never-expiring) + Management API fallback. exec_sql + exec_sql_ddl RPCs installed. 10 migrations applied (003-012). |
| **Skill Registry + Audit** | ✅ V5.6 LIVE | `scripts/register_skill.py` — create/register/list/audit/validate. Found 144 folder skills vs 7 registry vs 23 in CAPABILITIES.md — full drift report available. Zero invalid skills as of 2026-04-20. |
| **Inbound RPC (Python route)** | ✅ V5.6 LIVE (closed 2026-04-20) | `record_inbound_from_n8n()` Postgres function installed. `email_engine.py check-inbox` (scheduler polls every 5 min) now calls inbound_classifier + this RPC on every unread email. Blind spot closed via Python path; N8N workflow `1cGIN32alM8sf8OV` untouched. Optional N8N-side wiring preserved at `docs/N8N_INBOUND_INTEGRATION.md` for dual-path redundancy if CC wants it later. |
| **OASIS AI · Agent Command Center** | ✅ V4 LIVE (2026-04-30 PM) | https://agent-dashboard-cc90210.vercel.app · Next.js 15 + React 19 + Tailwind + recharts. OASIS BLUE (#3b82f6). Auth: Supabase email+password + Google OAuth. Multi-tenant via tenants + RLS (migrations 017+018+019). **Today page** has 6 hero metrics (Net MRR · Gap · Days Left · Outreach Today · Hot Inbound · Top Client Share with concentration risk warning >60%) + 4 secondary (Active Pipeline · Reply Rate 7d · Decisions Today · Pipeline All) + auto-promoting Primary Lead. **Pipeline page** hides lost/archived/null-email by default, ?show=all toggle. **Reasoning page** is an Agent Command Palette: 35 Bravo + 11 Maven + 5 Atlas + 5 Codex commands, profile-gated by agents_enabled, search/filter/copy-paste-ready. **Settings page**: ProfileEditor + PlanTemplateEditor (weekday/weekend with auto-materialize) + ChangePasswordForm + IntegrationDot grid. API routes (session-gated): /api/profile, /api/plan-templates, /api/daily-plan, /api/daily-plan/materialize. Bearer-auth API: /api/auth/provision-cli (multi-agent: passes `agent` slug, idempotently extends agents_enabled), /api/inbound/n8n. Middleware: 401 JSON for /api/*, 307 redirects for pages. **CRM cleaned 2026-04-30: 219 → 3 leads** (primary retainer Agency · Jonathan Hutton · Bev Drexler @ Tremont Cafe), 216 archived (soft-delete via tags), 279 interactions preserved. Tools: scripts/crm_reset.py, scripts/sync_slash_commands.py (drift detector), scripts/supabase_admin.py, scripts/cloudflare_admin.py. Top-client concentration tile reads profile.custom_fields.top_client_mrr_usd (CC's seeded: $2,951 primary retainer = 89%). NO realtime websocket (server-rendered). NO cross-Supabase / Stripe bridge — separate from oasis-ai-platform by design. |
| **OASIS AI Platform (oasisai.work)** | ✅ LIVE (separate product) | Vite/React marketing + checkout + client portal for one-off N8N automations. Separate Vercel project (oasis-ai-platform), separate Supabase project (oasis-ai-platform DB), separate repo (CC90210/oasis-ai-platform). DOES NOT cross-talk with the Command Center per CC's 2026-04-30 PM clarification: 'OASIS AI's client portal is for one-off N8N automations, and the agent dashboard is a completely separate tool.' Bridge from Stripe -> Command Center was REVERTED (commit pending). |
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

## Capability Counts (live — auto-emitted by self_audit + MANIFEST)

> **Do NOT hardcode counts here.** They drift the moment a script lands. Read live:
>
> - `python scripts/self_audit.py --json | jq '{skills_total, scripts_total, mcp_servers, health_score}'`
> - MANIFEST block at the bottom of this file (synced by `scripts/catalog_sync.py`)
> - `python scripts/capability_query.py drift` for graph drift items

Stable structural facts (change rarely, audit on edit):

- **Supabase tables:** 28 (14 agent + 14 business ops)
- **MCP servers:** 9 active in Claude Code config (verified via `mcp_configs_in_sync` in self_audit)
- **Hooks:** 4 active safety/audit hooks in `.claude/settings.local.json`
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
- **the prior community (Skool)** — the prior client coaching partnership. CC = Head Coach, $2,500/mo + 15% rev share. Contract formalized 2026-04-10. Context: [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]

## Agent Runner Backend (2026-05-05)

**Design + scaffold shipped, not deployed yet**
- `docs/AGENT_RUNNER_DESIGN.md` written â€” direct `runner.oasisai.work` architecture for the Command Center chat widget. Decision set: Node/TypeScript runner, session-scoped workers, SSE streaming, Supabase JWT verification on-runner, libsodium app-layer key encryption, BYOK enforcement for non-CC tenants, read-only file tree with approval-gated writes.
- `apps/agent-runner/` scaffold added â€” `server.ts`, `sessions.ts`, `spawner.ts`, `auth.ts`, `files.ts`, `sse.ts`, plus isolated `package.json` + `tsconfig.json`.
- `database/020_agent_runner.sql` added â€” `agent_model_config`, `chat_sessions`, `chat_messages`, `audit_log`, plus managed-auth guardrail on `tenants.custom_fields.managed_auth_allowed`.
- **Operator note:** local worktree already contains untracked `database/020_chat_widget_and_pairings.sql`; it overlaps migration numbering and scope. Choose one migration lineage before applying anything to Supabase.

## Obsidian Links
> Connected notes for graph navigation

- [[brain/SOUL]] | [[brain/USER]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]]
- [[brain/APP_REGISTRY]] | [[brain/CEO_OPERATING_SYSTEM]] | [[brain/OKRs]] | [[brain/CLIENT_READY]]
- [[brain/BRAIN_LOOP]] | [[brain/GROWTH]] | [[brain/CHANGELOG]]
- [[brain/RISK_REGISTER]] | [[brain/INTERACTION_PROTOCOL]] | [[brain/ORCHESTRATION]]
- [[brain/MODEL_CONFIG]] (V6.0 multi-provider routing) | [[brain/USER.template]] (public-clone profile template)
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/DECISIONS]] | [[memory/CLAUDE_HANDOVER]]
- [[memory/WORKING]] (V6.0 ephemeral working memory) | [[memory/ACTIVE_TASKS.template]] | [[memory/SESSION_LOG.template]]
- [[docs/V6_ARCHITECTURE]] | [[infra/README]]
- [[memory/PATTERNS]] | [[memory/MISTAKES]] | [[memory/SELF_REFLECTIONS]]
- [[memory/content-strategy]] | [[memory/PROPOSED_CHANGES]]
- [[memory/poems/sub_agents_collective_intelligence]] | [[skills/sales-closing/COLD_CALL_SCRIPT_V1]]
- [[APPS_CONTEXT/INDEX]] | [[APPS_CONTEXT/GRITLY_CLAUDE]] | [[APPS_CONTEXT/IG_SETTER_PRO_CLAUDE]] | [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]
- [[skills/skool-automation/SKILL]] | [[skills/codex-delegation/SKILL]] | [[../CMO-Agent/skills/elite-video-production/SKILL]]
- [[skills/ethical-hacking/SKILL]] | [[skills/sales-closing/SKILL]]
- [[knowledge/index]] | [[knowledge/SCHEMA]]
- [[brain/DASHBOARD]]
- **Hubs (graph spine):** [[skills/INDEX]] · [[docs/INDEX]] · [[browser/README]] · [[browser/domain-skills/README]] · [[browser/interaction-skills/INDEX]] · [[apps/command-center/README]] · [[data/pulse/README]] · [[memory/outreach_archive/INDEX]] · [[memory/daily/INDEX]] · [[.gemini/INDEX]] · [[templates/agent-scaffold/README]]
- **Top-level:** [[PLAYBOOK]] · [[SECURITY]] · [[CLIENT_READY]]

## Last Heartbeat

- **Date:** 2026-05-06
- **Agent:** BRAVO via Claude Code (claude-opus-4-6"              # Lead architect (Bravo))
- **Result:** Finalization audit pass: Rule 11 freshness gate added, AGENT_ROUTER + INTENTS extended with 6 intents, Hermes role disambiguated, GEMINI/ANTIGRAVITY identity matrices synced with AGENTS.md, capability graph drift cleared (28 docstring false positives + auto-generated triggers), STATE/CAPABILITIES counts de-hardcoded, ACTIVE_TASKS sprint roadmap archived, LONG_TERM.md re-validated, SESSION_LOG April entries archived. self_audit 100/100, drift 0, memory health F→C.

*Last updated: 2026-05-06*

## Manifest

<!-- MANIFEST:BEGIN -->
_Auto-generated by `scripts/catalog_sync.py` — do not edit this block manually._
_Last synced: 2026-05-04T21:33:26.379993+00:00_

| Type | Count |
|---|---:|
| Python scripts | 107 |
| PowerShell scripts | 9 |
| Shell scripts | 4 |
| **Total scripts** | **120** |
| Skills | 153 (8 destructive) |
| Agents | 20 |
| Workflows | 35 |

**Scripts by category:**

- Other: 58
- Data & Memory: 19
- System: 11
- Communication: 10
- Content: 7
- Governance: 5
- Finance: 5
- Browser & Web: 4
- Google: 1

<!-- MANIFEST:END -->
