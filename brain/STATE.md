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
| **Position**| ACTIVE | Community Manager for Bennett's Agency Accelerator + Lead Gen Funnel Operator |
| **Confidence** | 0.97 | Core automations production-grade. Telegram V15.4 live. Scheduler fixed. Semi-auto outreach deploying. Bennett concentration risk unresolved. |
| **Focus Area** | **RESET AND DIVERSIFY REVENUE** | CC is doing a physical/mental reset (quitting weed). Focus is on daily minimums: content creation and cold outreach volume. Target is still $5k MRR by May 15. |
| **Energy** | RECOVERING | CC reported being in a bad state recently. Reset protocol initiated. Baseline execution only. |
| **Memory Health** | GOOD | Files current. Knowledge wiki seeded. mem0 live. Fragmentation acknowledged — single-write sync in progress. |

> **Ephemeral state lives in `memory/OPERATIONAL_STATE.md`** (split out 2026-05-07 per Architecture Certification finding C5). That file carries Active Infrastructure, Known Issues, Skool daemon status, Last Heartbeat — under a 7-day freshness gate. Read it for live ops; this file is for stable identity / North Star / capability architecture.

---

## North Star: $5,000 USD Net MRR by May 15, 2026

> Previous goal ($1,000 USD Net MRR by March 31, 2026) — **ACHIEVED** at $2,691 USD (+169% surplus).

1. **Revenue:** ~$3,322 USD/mo Net MRR ($180 Stripe + $191 base + $2,500 Bennett flat + $451 Bennett 15% rev share on $3,007 Skool MRR).
2. **Gap:** ~$1,678 USD/mo (~2 new OASIS clients at $800-1,000/mo, or 4 at $400-500/mo).
3. **Pace:** ~1 new client/week for 5 weeks to hit target by May 15.
4. **Strategy:** Semi-auto outreach loop (daily batch) + CC Funnel inbound. Diversify beyond Bennett.
5. **Risk:** Bennett loss = drop to ~$822/mo. Diversification is the #1 operational priority.

## Active Infrastructure

> **Moved to `memory/OPERATIONAL_STATE.md`** (2026-05-07). The full table is preserved there with a 7-day freshness gate. Read that file for live infra status.
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
- **Agency Accelerance (Skool)** — Bennett Spooner coaching partnership. CC = Head Coach, $2,500/mo + 15% rev share. Contract formalized 2026-04-10. Context: [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]

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

> Moved to `memory/OPERATIONAL_STATE.md` (last-heartbeat is ephemeral — 7-day freshness gate).

*Last updated: 2026-05-07*

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
