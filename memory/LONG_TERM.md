---
description: "Quarterly-verified persistent facts on architecture, business, and technical systems with confidence scores — agents reference for established truths"
tags: [memory, persistent]
last_updated: 2026-08-08
freshness_threshold_days: 90
---
# LONG-TERM MEMORY — High-Confidence Persistent Facts

> Only facts with confidence >= 0.8 belong here. Reviewed quarterly (90-day threshold — this file is meant to be slow-moving).
>
> ⚠️ **Per-entry freshness still applies.** Each entry has its own date — `memory_aging.py` decays confidence per-entry by category. Even within this file, an entry > 90 days without re-verification is suspect. Run `python scripts/core/memory_aging.py stale --days 30` before quoting business facts.
>
> **Last full re-validation:** 2026-08-08 (harness cleanup sweep — all 28 stale entries verified against live state: harness_eval, USER.md 2026-07-07, STATE.md, APP_REGISTRY.md, live curls). Superseded/obsolete rows struck through in place; unverifiable rows moved to the archive section at the bottom.
>
> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[brain/STATE]]

## Architecture Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| Bravo uses 6-entry-point architecture: CLAUDE.md (Claude Code), AGENTS.md (Codex/Cursor/OpenCode-GPT), GEMINI.md (Gemini CLI), ANTIGRAVITY.md (Antigravity IDE), OPENCODE.md (OpenCode terminal), ZCODE.md. All converge on `brain/AGENT_ROUTER.md`. | 0.95 | harness_eval lockstep check: 6 entry points carry the lockstep line, mirrors byte-identical | 2026-08-08 |
| All entry points share `brain/`, `memory/`, `.env.agents` — single source of truth for identity + state | 0.95 | Confirmed across entry points | 2026-08-08 |
| Identity is agent-first, not model-driven. Whoever opens this repo is Bravo (identity seed: `PERSONAL.md` + `brain/SOUL.md`); the runtime (Claude / GPT / Gemini / local) is implementation plumbing. Sole exception: an explicit `codex-companion task --write` delegation steers that invocation into the Codex backend-executor lane. | 0.95 | AGENTS.md Identity section (canonical) — supersedes the 2026-05-06 "model-driven" row | 2026-08-08 |
| Supabase MCP for Claude Code: use `npx @supabase/mcp-server-supabase` in `.claude/mcp.json` (not HTTP plugin). **LEGACY — Turso is now primary; Supabase MCP retained only for event bus and legacy apps.** | 0.70 | Still in .claude/mcp.json but deprecated; Turso is the primary backend since 2026-08 | 2026-08-19 |
| **Turso migration COMPLETE (2026-08).** Turso is the primary backend: 191 tables, 132 tenant-scoped (`turso_tool.py status` verified). Supabase retained only for: Event Bus (Postgres LISTEN/NOTIFY), Command Center (Supabase SSR), Breeze (own project). Cancel-readiness: `python scripts/migration_completeness_audit.py`. | 0.95 | turso_tool.py status: 191 tables, 132 tenant-scoped | 2026-08-19 |
| Supabase orgs: CC (oktipozhyojufxsytrse), oasis-ai-platform (sajanpiqysuwviucycjh) — LEGACY, being decommissioned | 0.80 | Historical reference; projects being cut over to Turso | 2026-08-19 |
| PowerShell `>` redirection produces UTF-16LE which breaks Node parsers — use `Out-File -Encoding utf8` instead | 0.95 | Permanent OS quirk | 2026-08-08 |
| X/Twitter has 280 character limit (including spaces, URLs, mentions) | 0.95 | Permanent API limit | 2026-08-08 |
| Outbound chokepoint: every email/DM goes through `scripts/integrations/send_gateway.py` (CASL + cooldown + caps + draft critic + DNS doctor). Direct `smtplib` calls from engines = regression. | 0.95 | V5.6 architecture; AGENTS.md RULE 5 current | 2026-08-08 |
| **Fable 5 model lineup (2026-06-12 standard).** Top-tier reasoning + general agent: `claude-fable-5`. Heavy code/reasoning: `claude-opus-4-8`. General work: `claude-sonnet-4-6`. Cheap classification: `claude-haiku-4-5`. Vision (statement_parser): Sonnet 4.6 vision is the proven choice. Single source of truth for model IDs lives in `scripts/lib/model_registry.py`. | 0.95 | Anthropic model lineup current as of 2026-06-12 | 2026-06-12 |
| **Windows subprocess spawning canonical pattern.** Every `subprocess.Popen/run/call/check_*` in BEA must pass `creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo()` from `scripts/lib/subprocess_helpers.py` (or `bravo_cli/_subprocess_helpers.py`). Audit enforced by `scripts/audit_no_visible_subprocess.py` — 227 files audited, zero violations as of 2026-06-12. Without both flags, daemon-spawned subprocesses pop a visible console window on Windows. | 0.95 | Audit tool + verified end-to-end fix 2026-06-12 | 2026-06-12 |
| **SunBiz operator portal at 100% turnkey state (2026-06-12).** Adon MCA SOP §§3,4,6,7 implemented end-to-end: shop-out subject/body/CC/attachments + recipient picker; SOP §4 restricted_states/restricted_industries match-fitness scoring; SOP §7 sales metric card UI rendering grade/recommendation/positions/leverage from `application_underwriting.debt_analysis.metric_card`. Bridge reliability chain: warm-pool 30min wall-clock + 600s inactivity, Vercel Fluid Compute 800s ceiling, fire-and-forget for long-running underwriting. Per-operator email signing wired for Matt-alias (Ezra) / Jordan / Alex. | 0.95 | Retrospective `memory/RETROSPECTIVE_2026-06-12_sunbiz_finalization.md` | 2026-06-12 |

## Business Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| ~~OASIS AI Solutions at ~$3,322 USD/mo Net MRR ($180 Stripe + $191 base + $2,500 primary-retainer flat + $451 rev share). Target: $5K USD by June 18, 2026.~~ **SUPERSEDED 2026-08-08:** MRR/revenue figures are owned by Atlas (CFO-Agent) — Bravo memory no longer carries dollar figures. Route money questions to Atlas. | 1.00 | brain/STATE.md "Finance is not Bravo's domain" + USER.md Primary Objective | 2026-08-08 |
| **BreezeAdvance deal closed 2026-06-20 (David + Adon): $8K trial month ($4K up front + $4K month-end on delivery) → $10K/mo recurring (Breeze + SunBiz, $5K each). CC net $5,600 trial (70/30) → $6,000/mo recurring (60/40). $5K North Star ACHIEVED; new target $10K USD Net MRR by Sept 30, 2026.** Supersedes the 2026-05-06 row above (primary retainer ended 2026-05-18). Current figures live with Atlas. | 0.95 | brain/STATE.md + Telegram deal screenshots | 2026-06-20 |
| CC's partner Adon handles networking, connections, marketing. Owns 50% of PropFlow only. CC owns 100% of OASIS AI. | 0.90 | brain/USER.md (2026-07-07 revision) | 2026-08-08 |
| **Content pipeline:** Maven (CMO-Agent) owns scheduling/distribution across channels via Zernio; content creation itself is CC's non-delegable role. | 0.90 | brain/USER.md CC's Role table + APP_REGISTRY | 2026-08-08 |
| ~~Primary retainer is ~93% of revenue — diversification is critical risk #1~~ **SUPERSEDED 2026-05-18:** Primary retainer ended; confirmed MRR is now ~$371. R-001 materialized — see brain/RISK_REGISTER.md | 1.00 | brain/STATE.md, docs/handovers/2026-05-18-primary-retainer-revenue-shift-handoff.md | 2026-05-18 |
| Atlas (CFO agent) at `C:\Users\User\APPS\CFO-Agent` — finance, tax, trading, FIRE. Pulse: `data/pulse/cfo_pulse.json`. Read-only from Bravo. | 0.95 | brain/APP_REGISTRY.md + C_SUITE_ARCHITECTURE.md | 2026-08-08 |
| Maven (CMO agent) at `C:\Users\User\CMO-Agent` — content, ads, brand, funnels, growth. Pulse: `data/pulse/cmo_pulse.json`. Read-only from Bravo. | 0.95 | brain/APP_REGISTRY.md + C_SUITE_ARCHITECTURE.md | 2026-08-08 |
| Aura (life/home agent) at `C:\Users\User\AURA` — habits, smart home, RPi5 hub. Pulse: `data/pulse/aura_pulse.json`. | 0.90 | brain/APP_REGISTRY.md + C_SUITE_ARCHITECTURE.md | 2026-08-08 |
| Hermes is a client product (commerce agent), NOT a peer C-Suite agent. Repo: `~/hermes`. First client: Emmanuel Lowinger. | 0.95 | brain/APP_REGISTRY.md | 2026-08-08 |
| CC Funnel at cc-funnel.vercel.app — **RETURNING 404 as of 2026-08-08** (was lead capture → Supabase → Telegram notify, deployed 2026-03-24). Deployment down or renamed — needs CC decision. | 0.90 | live curl probe | 2026-08-08 |
| ~~Primary-retainer relationship is friend-based, contract formalized 2026-04-10. $2,500/mo flat + 15% rev share on community MRR. CC = Head Coach.~~ **ENDED 2026-05-18** — Client brought a full-time coach on with equity. CC retains IP. Relationship amicable. Client indicated he'd bring CC back as smaller coach later (no terms). | 1.00 | brain/STATE.md, APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE.md | 2026-05-18 |
| ~~Primary-retainer $10K coaching referral DEFERRED — partner currently overcommitted to their own clients. Revisit Q3 2026.~~ **OBSOLETE 2026-05-18** — primary retainer relationship ended. (Re-confirmed OBSOLETE 2026-08-20 — no referral materialized; date bump clears aging flag only, content unchanged.) | 0.90 | memory/ACTIVE_TASKS.md | 2026-08-20 |
| CC's primary objective: build the empire through AI automation — multiply CC's time, close every loop, ship the systems that scale OASIS. Content creation (personal brand, inbound funnel) remains CC's non-delegable role. | 0.95 | brain/USER.md Primary Objective + CC's Role (2026-07-07) | 2026-08-08 |
| CC's role: content creation, marketing, sales, face-to-face. Everything else = Bravo handles autonomously. | 0.95 | brain/USER.md CC's Role table | 2026-08-08 |
| ~~Skool community: 158 members, 63% engagement, 100% retention as of last reading. Rev share grows as community grows.~~ **OBSOLETE 2026-05-18** — primary retainer ended; Skool daemon archived (`scripts/_archive/skool/`). | 1.00 | brain/STATE.md | 2026-08-08 |

## Technical Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| n8n instance: https://n8n.srv993801.hstgr.cloud (Hostinger VPS). CLI: `python scripts/integrations/n8n_tool.py`. Build canonical path uses n8n-mcp SDK. | 0.95 | Live curl 200 + n8n_tool present | 2026-08-08 |
| Telegram bot V15.8 (`telegram_agent.js`) — full computer control (60+ cmds), tier classifier, PM2-managed. Multi-machine arbitration via `scripts/bridge_lock.py`. | 0.95 | version string in telegram_agent.js | 2026-08-08 |
| Zernio (formerly Late) — social media scheduler. CLI: `../CMO-Agent/scripts/late_tool.py` (owned by Maven). API base: `https://zernio.com/api/v1/`. Free plan limit 20 posts/month. | 0.95 | Maven-owned — verify in CMO-Agent before relying | 2026-08-08 |
| `__future__` imports must be absolute first line in Python files | 0.95 | Permanent Python rule | 2026-08-08 |
| MCP servers in Claude Code config (9 active): Playwright, Context7, Memory, Sequential Thinking, Knowledge Graph, GitHub, Firecrawl, Filesystem, Obsidian. Credential-bearing services (Supabase, Stripe, Late, n8n) use CLI tools instead. | 0.95 | .claude/mcp.json counted live | 2026-08-08 |
| Self-audit health score baseline: 95-100 in good state. < 90 = drift to investigate. < 70 = STOP and surface to CC. Exit codes verified: 1 = warnings (score 70-99), 2 = degraded (< 70). | 0.95 | scripts/core/self_audit.py exit codes | 2026-08-08 |
| Outbound dry-run kill switch: `BRAVO_FORCE_DRY_RUN=1` env var routes every send_gateway send to dry-run | 0.95 | scripts/integrations/send_gateway.py (3 call sites) | 2026-08-08 |

## Confidence Decay Rules

- Facts not re-verified in 30 days: confidence -= 0.1
- Facts not re-verified in 90 days: confidence -= 0.3 (review for removal)
- Facts contradicted by new evidence: immediately flag and update
- Facts confirmed by new evidence: confidence += 0.05 (cap at 1.0)

## Archived during 2026-08-08 sweep

- "PropFlow is pre-revenue, in active development" — current canon (USER.md 2026-07-07) is silent on revenue stage; revenue status is Atlas's domain. Unverified, not asserted.
- "CC works weekends at Nicky's Donuts" — dropped from USER.md in its 2026-07-07 revision. Unverified; confirm with CC before re-adding.
- "Wednesday is Content Day; Maven schedules 1 piece/day via Zernio" — not carried by current USER.md. Content cadence is Maven's domain (`../CMO-Agent/brain/CONTENT_BIBLE`).
- "Monthly overhead ~$184 USD (Claude $140, Supabase (legacy-ok) $25, Hostinger $19/yr, Domains ~$50/yr)." — Atlas monthly spend gate cap.re Atlas's domain; Bravo memory no longer tracks dollars.

## Removed during 2026-05-06 sweep

- "Bravo uses 3-tier agent architecture (Claude Code Opus, Gemini CLI, Antigravity IDE)" — superseded by 5-entry-point architecture above (now 6).
- "Late MCP profileId returns dict not str — requires Pydantic patch" — Late MCP is dead, replaced by `late_tool.py` CLI.
- "Gemini CLI entry point: GEMINI.md (V5.4)" — now V5.5+ identity matrix synced with AGENTS.md.

*Last updated: 2026-08-08*

## Related

- [[memory/INDEX]]
- [[memory/ACTIVE_TASKS]]
- [[memory/ACTIVE_TASKS.template.md]]
