---
description: "Quarterly-verified persistent facts on architecture, business, and technical systems with confidence scores — agents reference for established truths"
tags: [memory, persistent]
last_updated: 2026-06-12
freshness_threshold_days: 90
---
# LONG-TERM MEMORY — High-Confidence Persistent Facts

> Only facts with confidence >= 0.8 belong here. Reviewed quarterly (90-day threshold — this file is meant to be slow-moving).
>
> ⚠️ **Per-entry freshness still applies.** Each entry has its own date — `memory_aging.py` decays confidence per-entry by category. Even within this file, an entry > 90 days without re-verification is suspect. Run `python scripts/core/memory_aging.py stale --days 30` before quoting business facts.
>
> **Last full re-validation:** 2026-05-06 (finalization audit). All entries below were either verified against current state files (`brain/STATE.md`, `brain/USER.md`) or removed if obsolete.
>
> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[brain/STATE]]

## Architecture Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| Bravo uses 5-entry-point architecture: CLAUDE.md (Claude Code), AGENTS.md (Codex/Cursor/OpenCode-GPT), GEMINI.md (Gemini CLI), ANTIGRAVITY.md (Antigravity IDE), OPENCODE.md (OpenCode terminal). All converge on `brain/AGENT_ROUTER.md`. | 0.95 | All 5 files synced 2026-05-06 | 2026-05-06 |
| All entry points share `brain/`, `memory/`, `.env.agents` — single source of truth for identity + state | 0.95 | Confirmed across the V6.1 finalization audit | 2026-05-06 |
| Identity is model-driven, not tool-driven. Claude/big-pickle = Bravo; GPT/Codex = Codex backend executor; Gemini/other = honest model name + read-only default | 0.95 | AGENTS.md lines 13-15 canonical | 2026-05-06 |
| Supabase MCP for Claude Code: use `npx @supabase/mcp-server-supabase` in `.claude/mcp.json` (not HTTP plugin) | 0.90 | Working since 2026-02-28; still current in .claude/mcp.json | 2026-06-06 |
| Supabase projects: Bravo (agent DB + business ops, 28 tables), nostalgic-requests, oasis-ai-platform — all us-west-2 | 0.95 | self_audit confirms via supabase_tool list-projects | 2026-05-06 |
| Supabase orgs: CC (oktipozhyojufxsytrse), oasis-ai-platform (sajanpiqysuwviucycjh) | 0.95 | Confirmed | 2026-06-06 |
| PowerShell `>` redirection produces UTF-16LE which breaks Node parsers — use `Out-File -Encoding utf8` instead | 0.95 | Permanent OS quirk | 2026-05-06 |
| X/Twitter has 280 character limit (including spaces, URLs, mentions) | 0.95 | Permanent API limit | 2026-05-06 |
| Outbound chokepoint: every email/DM goes through `scripts/integrations/send_gateway.py` (CASL + cooldown + caps + draft critic + DNS doctor). Direct `smtplib` calls from engines = regression. | 0.95 | V5.6 architecture, 48 tests green | 2026-05-06 |
| **Fable 5 model lineup (2026-06-12 standard).** Top-tier reasoning + general agent: `claude-fable-5`. Heavy code/reasoning: `claude-opus-4-8`. General work: `claude-sonnet-4-6`. Cheap classification: `claude-haiku-4-5`. Vision (statement_parser): Sonnet 4.6 vision is the proven choice. Single source of truth for model IDs lives in `scripts/lib/model_registry.py`. | 0.95 | Anthropic model lineup current as of 2026-06-12 | 2026-06-12 |
| **Windows subprocess spawning canonical pattern.** Every `subprocess.Popen/run/call/check_*` in BEA must pass `creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo()` from `scripts/lib/subprocess_helpers.py` (or `bravo_cli/_subprocess_helpers.py`). Audit enforced by `scripts/audit_no_visible_subprocess.py` — 227 files audited, zero violations as of 2026-06-12. Without both flags, daemon-spawned subprocesses pop a visible console window on Windows. | 0.95 | Audit tool + verified end-to-end fix 2026-06-12 | 2026-06-12 |
| **SunBiz operator portal at 100% turnkey state (2026-06-12).** Adon MCA SOP §§3,4,6,7 implemented end-to-end: shop-out subject/body/CC/attachments + recipient picker; SOP §4 restricted_states/restricted_industries match-fitness scoring; SOP §7 sales metric card UI rendering grade/recommendation/positions/leverage from `application_underwriting.debt_analysis.metric_card`. Bridge reliability chain: warm-pool 30min wall-clock + 600s inactivity, Vercel Fluid Compute 800s ceiling, fire-and-forget for long-running underwriting. Per-operator email signing wired for Matt-alias (Ezra) / Jordan / Alex. | 0.95 | Retrospective `memory/RETROSPECTIVE_2026-06-12_sunbiz_finalization.md` | 2026-06-12 |

## Business Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| OASIS AI Solutions at ~$3,322 USD/mo Net MRR ($180 Stripe + $191 base + $2,500 primary-retainer flat + $451 primary-retainer 15% rev share on $3,007 community MRR). Target: $5K USD by June 18, 2026. Live: `python scripts/revenue_engine.py mrr --json` | 0.95 | brain/STATE.md current | 2026-05-06 |
| **BreezeAdvance deal closed 2026-06-20 (David + Adon): $8K trial month ($4K up front + $4K month-end on delivery) → $10K/mo recurring (Breeze + SunBiz, $5K each). CC net $5,600 trial (70/30) → $6,000/mo recurring (60/40). $5K North Star ACHIEVED; new target $10K USD Net MRR by Sept 30, 2026.** Supersedes the 2026-05-06 row above (primary retainer ended 2026-05-18). | 0.95 | brain/STATE.md + Telegram deal screenshots | 2026-06-20 |
| CC's partner Adon handles content + client relations. Owns 50% of PropFlow only. CC owns 100% of OASIS AI. | 0.90 | brain/USER.md | 2026-05-06 |
| PropFlow is pre-revenue, in active development | 0.85 | brain/USER.md current | 2026-05-06 |
| CC works weekends at Nicky's Donuts | 0.90 | brain/USER.md | 2026-05-06 |
| **Content Strategy:** Wednesday is "Content Day". CC uploads batch video/files, Maven schedules 1 piece/day across all channels via Zernio. | 0.90 | CC stated 2026-03-05, content pipeline now owned by Maven | 2026-05-06 |
| ~~Primary retainer is ~93% of revenue — diversification is critical risk #1~~ **SUPERSEDED 2026-05-18:** Primary retainer ended; confirmed MRR is now ~$371. R-001 materialized — see brain/RISK_REGISTER.md | 1.00 | brain/STATE.md, docs/handovers/2026-05-18-primary-retainer-revenue-shift-handoff.md | 2026-05-18 |
| Atlas (CFO agent) at `C:\Users\User\APPS\CFO-Agent` — finance, tax, trading, FIRE. Pulse: `data/pulse/cfo_pulse.json`. Read-only from Bravo. | 0.95 | brain/APP_REGISTRY.md + C_SUITE_ARCHITECTURE.md | 2026-05-06 |
| Maven (CMO agent) at `C:\Users\User\CMO-Agent` — content, ads, brand, funnels, growth. Pulse: `data/pulse/cmo_pulse.json`. Read-only from Bravo. | 0.95 | brain/APP_REGISTRY.md + C_SUITE_ARCHITECTURE.md | 2026-05-06 |
| Aura (life/home agent) at `C:\Users\User\AURA` — habits, smart home, RPi5 hub. Pulse: `data/pulse/aura_pulse.json`. | 0.90 | brain/C_SUITE_ARCHITECTURE.md | 2026-05-06 |
| Hermes is a client product (commerce agent), NOT a peer C-Suite agent. Repo: `~/hermes`. First client: Emmanuel Lowinger. | 0.95 | brain/APP_REGISTRY.md, AGENT_ROUTER.md updated 2026-05-06 | 2026-05-06 |
| CC Funnel live at cc-funnel.vercel.app — lead capture → Supabase → Telegram notify | 0.90 | Deployed 2026-03-24, still live | 2026-05-06 |
| ~~Primary-retainer relationship is friend-based, contract formalized 2026-04-10. $2,500/mo flat + 15% rev share on community MRR. CC = Head Coach.~~ **ENDED 2026-05-18** — Client brought a full-time coach on with equity. CC retains IP. Relationship amicable. Client indicated he'd bring CC back as smaller coach later (no terms). | 1.00 | brain/STATE.md, APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE.md | 2026-05-18 |
| ~~Primary-retainer $10K coaching referral DEFERRED — partner currently overcommitted to their own clients. Revisit Q3 2026.~~ **OBSOLETE 2026-05-18** — primary retainer relationship ended. | 0.90 | memory/ACTIVE_TASKS.md | 2026-05-18 |
| CC's #1 priority is CONTENT CREATION for personal brand (Conaugh McKenna) to build inbound funnel | 0.95 | brain/USER.md | 2026-05-06 |
| CC's role: content creation, marketing, sales, face-to-face. Everything else = Bravo handles autonomously. | 0.95 | brain/USER.md | 2026-05-06 |
| Monthly overhead: ~$184 USD (Claude $140, Supabase $25, Hostinger/n8n $14, ElevenLabs ~$5) | 0.90 | brain/STATE.md | 2026-05-06 |
| Skool community: 158 members, 63% engagement, 100% retention as of last reading. Rev share grows as community grows. | 0.85 | brain/USER.md | 2026-05-06 |

## Technical Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| n8n instance: https://n8n.srv993801.hstgr.cloud (Hostinger VPS). CLI: `python scripts/integrations/n8n_tool.py`. Build canonical path uses n8n-mcp SDK. | 0.95 | Config + n8n_tool list verified | 2026-05-06 |
| Telegram bot V15.4 (`telegram_agent.js`) — full computer control (60+ cmds), tier classifier, PM2-managed. Multi-machine arbitration via `scripts/bridge_lock.py`. | 0.95 | brain/STATE.md current | 2026-05-06 |
| Zernio (formerly Late) — social media scheduler. CLI: `../CMO-Agent/scripts/late_tool.py` (owned by Maven). API base: `https://zernio.com/api/v1/`. Free plan limit 20 posts/month. | 0.95 | brain/CAPABILITIES.md current | 2026-05-06 |
| `__future__` imports must be absolute first line in Python files | 0.95 | Permanent Python rule | 2026-05-06 |
| MCP servers in Claude Code config (9 active): Playwright, Context7, Memory, Sequential Thinking, Knowledge Graph, GitHub, Firecrawl, Filesystem, Obsidian. Credential-bearing services (Supabase, Stripe, Late, n8n) use CLI tools instead. | 0.95 | self_audit `mcp_servers` array | 2026-05-06 |
| Self-audit health score baseline: 95-100 in good state. < 90 = drift to investigate. < 70 = STOP and surface to CC. | 0.95 | scripts/core/self_audit.py exit codes | 2026-05-06 |
| Outbound dry-run kill switch: `BRAVO_FORCE_DRY_RUN=1` env var routes every send_gateway send to dry-run | 0.95 | scripts/integrations/send_gateway.py | 2026-05-06 |

## Confidence Decay Rules

- Facts not re-verified in 30 days: confidence -= 0.1
- Facts not re-verified in 90 days: confidence -= 0.3 (review for removal)
- Facts contradicted by new evidence: immediately flag and update
- Facts confirmed by new evidence: confidence += 0.05 (cap at 1.0)

## Removed during 2026-05-06 sweep

- "Bravo uses 3-tier agent architecture (Claude Code Opus, Gemini CLI, Antigravity IDE)" — superseded by 5-entry-point architecture above.
- "Late MCP profileId returns dict not str — requires Pydantic patch" — Late MCP is dead, replaced by `late_tool.py` CLI.
- "Gemini CLI entry point: GEMINI.md (V5.4)" — now V5.5+ identity matrix synced with AGENTS.md.

*Last updated: 2026-05-06*

## Related

- [[memory/INDEX]]
- [[memory/ACTIVE_TASKS]]
- [[memory/ACTIVE_TASKS.template.md]]
