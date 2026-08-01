---
tags: [state, ephemeral, fable-5]
architecture_version: V7.4.1
last_updated: 2026-07-26
freshness_threshold_days: 30
verified: 2026-07-26
model_standard: fable-5
---
# STATE — Current Operational State

> **2026-07-26 — Inbound email automation is LIVE.** The n8n "OASIS Inbound
> Qualifier" is replaced by a native pipeline (classifier + `email_brain` +
> `email_playbook` + Atlas financial hand-off), subscription-CLI only, running
> as the "Inbound Email Sweep" cron (`*/5`) with Hybrid auto-send. Runbook:
> `brain/EMAIL_PIPELINE.md`. Kill switch: `EMAIL_BRAIN_ENABLED`/`_AUTO_SEND` in
> `ecosystem.config.js`. Code is on `feat/native-email-classifier` (CEO-Agent) +
> `feat/inbound-financial-consumer` (CFO-Agent) — landing to main/master is a
> pending CC decision (divergent notify.py on main; Atlas master would pull Qlib).

<!-- CANONICAL VERSION: `architecture_version` above is the SINGLE SOURCE OF TRUTH
     for the empire's architecture version. The five entry points (CLAUDE/GEMINI/
     ANTIGRAVITY/AGENTS/OPENCODE.md) are version-agnostic and do NOT hardcode it,
     so a version bump is a one-line edit here. Enforced by
     scripts/tests/test_entrypoint_parity.py. Released versions live in CHANGELOG.md. -->


> Updated 2026-07-20 (V7.4 fleet modernization) | **Architecture is V7.4.0** — V6 (state DB, retrieval, guards, capability graph, vocabulary layer) remains the foundation, and V7.0–V7.4 shipped on top: reliability/observability (Loud Failures, sliced harness eval + history, substrate-eval CI), Free-Tier Radar (`resource:` graph nodes, ADR-0010), the V7.2 persona bench, typed memory (ADR-0011: dedup + memory_diff audits, retriever abstract layer + freshness ranking), and the V7.4 agent-fleet canonical contract (ADR-0012: 13 personas modernized, one schema, generated agent routing, resolver scores agents by trigger). Full narrative: `CHANGELOG.md`. Self-audit health: run `python scripts/core/self_audit.py` for the live score. Counts are auto-emitted by self_audit and the MANIFEST block at the bottom of this file — do NOT hardcode them in the header.
>
> **V6 Apex (2026-05-10 — closes the V6 architecture epic):**
>   - **Phase 1** — `/api/state-health` two-tier read path: state-api passthrough preferred, Supabase mirror fallback for Vercel. The page renders a `via state-api` / `via supabase-mirror` tag so operators see which side served the payload.
>   - **Phase 2** — ~~Dashboard-driven override approvals~~ **DELETED 2026-05-22 per CC.** The `exec_guard` block on destructive operations (DROP TABLE / rm -rf / git push --force) stands — the block IS the protection. No approval-request rows, no `/overrides` page. When blocked, the agent picks a different approach. (See brain/V6_ARCHITECTURE.md "V6 Apex" for the canonical removal rationale.)
>   - **Phase 3** — Cross-agent event feed. `scripts/core/event_router.py loop` is a cursor-based, lossless observability tail; `state/event_router.log` carries the on-host audit projection. `/feed` page is the cloud-side view of the same `agent_events` stream with 5s `router.refresh()` (no websockets).
>
> Bravo is officially out of the architecture phase. The next epic is execution + scale. **Revenue targets / MRR are owned by Atlas (CFO-Agent) — not tracked here.** Bravo's job is to build and run the machine that makes them reachable.
>
> **What V6.1 added (fork mechanism, intact):** `brain/operator.profile.json` (gitignored single source of truth), `scripts/personalize.py` (renders `brain/USER.md` + memory templates from `*.template.md` placeholders, skip-on-exists), `scripts/scaffold.py` (token-replaces operator identifiers across tracked files at fork-time, refuses to run on the original operator's repo, `--backup` snapshots first). Wizard `step_finalize` always runs personalize; prompts for scaffold on new operators. `self_audit.check_personalization()` warns when profile missing. CC's working copy is preserved via the safety guard + gitignored personal files.
>
> **V6.0 base (intact):** multi-provider model router (Claude/OpenAI/OpenRouter/Groq/DeepSeek/local), autonomous skill synthesizer with `[NEW]→[VALIDATED]` lifecycle, 3-layer memory (working → episodic → semantic) with nightly Haiku-scored consolidation, multi-platform messaging gateway (Telegram + Discord + Slack), DL stack (GNN skill router, RLHF/DPO outreach, NTM, MAML, TFT MRR forecast, neuro-symbolic compliance gate), public-repo installer (`install.sh` / `install.ps1`), PII protection in `.gitignore`. **V5.7 foundation:** self_audit, send_gateway hardened (CASL + cooldown + caps + draft critic + DNS doctor), autonomous reasoning loop, Obsidian MCP.

## Operational Status

> [!success] SunBiz finalization sprint complete — 2026-06-12
> Multi-session sprint shipped the SunBiz operator portal at Adon's MCA SOP spec end-to-end. Adon Saturday demo is greenlit. Full retrospective: [[memory/RETROSPECTIVE_2026-06-12_sunbiz_finalization]]. Bridge reliability chain solid browser → Vercel → tunnel → VPS → Claude CLI (30-min warm-pool wall-clock, 600s inactivity, Vercel Fluid 800s). Zero subprocess-popup zombies (audit: 227 files, 0 violations). 552 MB disk reclaimed.

> [!info] Model standard — Fable 5 (2026-06-12)
> Top-tier reasoning + general agent loop = `claude-fable-5`. Heavy code = `claude-opus-4-8`. General = `claude-sonnet-4-6`. Cheap classification = `claude-haiku-4-5`. Vision (statement_parser) = Sonnet 4.6. Canonical source: `scripts/lib/model_registry.py`. Per-tier routing rationale: [[memory/LONG_TERM]] Architecture Facts.

| Dimension | Level | Notes |
|-----------|-------|-------|
| **Version** | **V7.4.0** (frontmatter `architecture_version` is canonical) | V6 foundation + V7.0 reliability + V7.1 Radar + V7.2 persona bench + V7.3 typed memory + V7.4 agent-fleet contract. Released history: CHANGELOG.md. |
| **Position**| EXECUTING — PAID CLIENT WORK | SunBiz + Breeze (BreezeAdvance) are active paying-client development. Deal terms and revenue are tracked by Atlas (CFO). Top priority: deliver the client work that keeps them retained. |
| **Confidence** | 0.80 | Core automations production-grade and verified running (Montreal fleet reset 2026-07-07). SunBiz/Breeze delivered at spec. |
| **Focus Area** | **HARNESS INTEGRITY + ONGOING CLIENT DELIVERY** | Montreal turnkey reset (2026-07-07): fleet persistence + identity truth. SunBiz / Breeze delivery continues. |
| **Energy** | EXECUTING / FOCUSED | Long sprint closed cleanly. Bridge surface as reliable as terminal. Codebase hygiene reset (552 MB, 0 subprocess violations). |
| **Memory Health** | GOOD | Files current. Latest retro 2026-06-12. Long-term re-verified 2026-06-12. |

> **Ephemeral state lives in `memory/OPERATIONAL_STATE.md`** (split out 2026-05-07 per Architecture Certification finding C5). That file carries Active Infrastructure, Known Issues, Last Heartbeat — under a 7-day freshness gate. Read it for live ops; this file is for stable identity / North Star / capability architecture.

---

## Mission (Bravo)

Build and run CC's empire through AI automation: multiply his time, close every loop, and keep the client-delivery machine and the agent fleet healthy.

> **Finance is not Bravo's domain.** Revenue, MRR, deal terms, cash flow, and targets are owned by **Atlas (CFO-Agent)**. Historical deal records live in Atlas / project memory, not in Bravo's state. When a money question arises, route it to Atlas.

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
> - `python scripts/core/self_audit.py --json | jq '{skills_total, scripts_total, mcp_servers, health_score}'`
> - MANIFEST block at the bottom of this file (synced by `scripts/catalog_sync.py`)
> - `python scripts/capability_query.py drift` for graph drift items

Stable structural facts (change rarely, audit on edit):

- **Supabase tables:** 28 (14 agent + 14 business ops)
- **MCP servers:** 9 active in Claude Code config (verified via `mcp_configs_in_sync` in self_audit)
- **Hooks:** 4 active safety/audit hooks in `.claude/settings.local.json`
- **Cross-machine sync:** Windows (CCPC) production + Mac (Conaughs-MacBook-Air) cold-standby via `ssh cc-mac`. LAN IPs changed with the 2026-07 Montreal move — refresh them in brain/CROSS_MACHINE_SYNC.md before relying on `ssh cc-mac`.
- **PM2 state (Windows, 24/7):** bravo-scheduler, bravo-telegram, bravo-coord, claude-bridge, claude-bridge-ping, event-router — plus sibling atlas-telegram + maven-telegram. Reboot-persistent via `pm2 save` + Startup-folder `Bravo PM2 Resurrect.vbs` (runs `pm2 resurrect` at logon). Mac = cold-standby. Skool daemon archived 2026-05-18 (`scripts/_archive/skool/`).

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
- **Primary community-management retainer** — **ENDED 2026-05-18.** Client said the retainer was too expensive at full-time hands; brought a full-time coach on. CC may return as smaller coach later. (Any outstanding AR is tracked by Atlas / CFO.) Skool comment/reply daemon archived 2026-05-18 — see `scripts/_archive/skool/`. Context: [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]

## Agent Runner Backend (2026-05-05)

**Design + scaffold shipped, not deployed yet**
- `docs/AGENT_RUNNER_DESIGN.md` written — direct `runner.oasisai.work` architecture for the Command Center chat widget. Decision set: Node/TypeScript runner, session-scoped workers, SSE streaming, Supabase JWT verification on-runner, libsodium app-layer key encryption, BYOK enforcement for non-CC tenants, read-only file tree with approval-gated writes.
- `apps/agent-runner/` scaffold added — `server.ts`, `sessions.ts`, `spawner.ts`, `auth.ts`, `files.ts`, `sse.ts`, plus isolated `package.json` + `tsconfig.json`.
- `database/020_agent_runner.sql` (planned — never landed; see `apps/agent-runner/`) — `agent_model_config`, `chat_sessions`, `chat_messages`, `audit_log`, plus managed-auth guardrail on `tenants.custom_fields.managed_auth_allowed`.
- **Operator note:** local worktree already contains untracked `database/020_chat_widget_and_pairings.sql`; it overlaps migration numbering and scope. Choose one migration lineage before applying anything to Supabase.

## Obsidian Links
> Connected notes for graph navigation

- [[brain/SOUL]] | [[brain/USER]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]]
- [[brain/APP_REGISTRY]] | [[brain/CEO_OPERATING_SYSTEM]] | [[brain/OKRs]] | [[brain/CLIENT_READY]] | [[brain/CRM_STRATEGY]]
- [[brain/BRAIN_LOOP]] | [[brain/GROWTH]] | [[brain/CHANGELOG]]
- [[brain/RISK_REGISTER]] | [[brain/INTERACTION_PROTOCOL]] | [[brain/ORCHESTRATION]]
- [[brain/METRIC_AUDIT]] — every dashboard metric traced to its source (real vs placeholder)
- [[brain/MODEL_CONFIG]] (V6.0 multi-provider routing) | [[brain/USER.template.md]] (public-clone profile template)
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/DECISIONS]]
- [[memory/WORKING]] (V6.0 ephemeral working memory) | [[memory/ACTIVE_TASKS.template.md]] | [[memory/SESSION_LOG.template.md]]
- [[docs/V6_ARCHITECTURE]] | [[infra/README]] | [[brain/EVENT_BUS_CONTRACT]]
- [[memory/PATTERNS]] | [[memory/MISTAKES]] | [[memory/SELF_REFLECTIONS]]
- [[memory/PROPOSED_CHANGES]]
- [[memory/poems/sub_agents_collective_intelligence]] | [[skills/sales-closing/COLD_CALL_SCRIPT_V1]]
- [[APPS_CONTEXT/INDEX]] | [[APPS_CONTEXT/GRITLY_CLAUDE]] | [[APPS_CONTEXT/IG_SETTER_PRO_CLAUDE]] | [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]
- [[skills/codex-delegation/SKILL]] | [[../CMO-Agent/skills/elite-video-production/SKILL]]
- [[skills/ethical-hacking/SKILL]] | [[skills/sales-closing/SKILL]]
- [[knowledge/index]] | [[knowledge/SCHEMA]]
- [[brain/DASHBOARD]]
- **Hubs (graph spine):** [[skills/INDEX]] · [[docs/INDEX]] · [[browser/README]] · [[browser/domain-skills/README]] · [[browser/interaction-skills/INDEX]] · [oasis-command-center](https://github.com/CC90210/oasis-command-center) (external) · [[data/pulse/README]] · [[memory/daily/INDEX]] · [[.gemini/INDEX]] · [[templates/agent-scaffold/README]]
- **Top-level:** [[PLAYBOOK]] · [[SECURITY]] · [[brain/CLIENT_READY]]

## Last Heartbeat

- **Date:** 2026-08-01
- **Agent:** BRAVO via Claude Code (claude-fable-5)
- **Result:** Car stage: rewrote loft() to indexed+spline-resampled geometry (whole body was flat shaded), AgX tone mapping, removed Hemisphere/Ambient fill, paint to true carbon black. Pushed c1e46f6.

*Last updated: 2026-08-01*

## Manifest

<!-- MANIFEST:BEGIN -->
_Auto-generated by `scripts/catalog_sync.py` — do not edit this block manually._
_Last synced: 2026-07-28T15:15:04.526117+00:00_

| Type | Count |
|---|---:|
| Python scripts | 117 |
| PowerShell scripts | 10 |
| Shell scripts | 4 |
| **Total scripts** | **131** |
| Skills | 152 (45 destructive) |
| Agents | 27 |
| Workflows | 34 |

**Scripts by category:**

- Other: 90
- Communication: 13
- Data & Memory: 9
- System: 6
- Content: 5
- Governance: 4
- Finance: 4

<!-- MANIFEST:END -->
