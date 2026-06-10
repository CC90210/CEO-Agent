---
tags: [state, ephemeral]
architecture_version: V7.0.0
last_updated: 2026-06-10
freshness_threshold_days: 30
verified: 2026-06-09
---
# STATE — Current Operational State

<!-- CANONICAL VERSION: `architecture_version` above is the SINGLE SOURCE OF TRUTH
     for the empire's architecture version. The five entry points (CLAUDE/GEMINI/
     ANTIGRAVITY/AGENTS/OPENCODE.md) are version-agnostic and do NOT hardcode it,
     so a version bump is a one-line edit here. Enforced by
     scripts/tests/test_entrypoint_parity.py. Released versions live in CHANGELOG.md. -->


> Updated 2026-06-06 (system re-engineering pass — tmp/ 6 GB→5 MB, retriever_postedit silent-failure fixed, 3 hygiene crons added, 5 entry points re-synced; see [memory/ACTIVE_TASKS#system-re-engineering-2026-06-06](../memory/ACTIVE_TASKS.md)) | **V6 OPTIMIZATION PROJECT — 100% COMPLETE.** Apex Phases 1-3 shipped 2026-05-10. V6.1 scaffolding mechanism + V6.0.3 polish + V6.0 foundation all intact. Self-audit health: 97/100 (`python scripts/core/self_audit.py`). Counts are auto-emitted by self_audit and the MANIFEST block at the bottom of this file — do NOT hardcode them in the header.
>
> **V6 Apex (2026-05-10 — closes the V6 architecture epic):**
>   - **Phase 1** — `/api/state-health` two-tier read path: state-api passthrough preferred, Supabase mirror fallback for Vercel. The page renders a `via state-api` / `via supabase-mirror` tag so operators see which side served the payload.
>   - **Phase 2** — ~~Dashboard-driven override approvals~~ **DELETED 2026-05-22 per CC.** The `exec_guard` block on destructive operations (DROP TABLE / rm -rf / git push --force) stands — the block IS the protection. No approval-request rows, no `/overrides` page. When blocked, the agent picks a different approach. (See brain/V6_ARCHITECTURE.md "V6 Apex" for the canonical removal rationale.)
>   - **Phase 3** — Cross-agent event feed. `scripts/core/event_router.py loop` is a cursor-based, lossless observability tail; `state/event_router.log` carries the on-host audit projection. `/feed` page is the cloud-side view of the same `agent_events` stream with 5s `router.refresh()` (no websockets).
>
> Bravo is officially out of the architecture phase. The next epic is business execution: $5K Net MRR by June 18, 2026 (deadline extended 2026-05-18 from May 30 after primary retainer ended — gives 31 days to rebuild $4,629 from $371 baseline).
>
> **What V6.1 added (fork mechanism, intact):** `brain/operator.profile.json` (gitignored single source of truth), `scripts/personalize.py` (renders `brain/USER.md` + memory templates from `*.template.md` placeholders, skip-on-exists), `scripts/scaffold.py` (token-replaces operator identifiers across tracked files at fork-time, refuses to run on the original operator's repo, `--backup` snapshots first). Wizard `step_finalize` always runs personalize; prompts for scaffold on new operators. `self_audit.check_personalization()` warns when profile missing. CC's working copy is preserved via the safety guard + gitignored personal files.
>
> **V6.0 base (intact):** multi-provider model router (Claude/OpenAI/OpenRouter/Groq/DeepSeek/local), autonomous skill synthesizer with `[NEW]→[VALIDATED]` lifecycle, 3-layer memory (working → episodic → semantic) with nightly Haiku-scored consolidation, multi-platform messaging gateway (Telegram + Discord + Slack), DL stack (GNN skill router, RLHF/DPO outreach, NTM, MAML, TFT MRR forecast, neuro-symbolic compliance gate), public-repo installer (`install.sh` / `install.ps1`), PII protection in `.gitignore`. **V5.7 foundation:** self_audit, send_gateway hardened (CASL + cooldown + caps + draft critic + DNS doctor), autonomous reasoning loop, Obsidian MCP.

## Operational Status

| Dimension | Level | Notes |
|-----------|-------|-------|
| **Version** | V6 Apex (P1+P2+P3) | V6 Optimization Project 100% complete (2026-05-10). Architecture phase closed. |
| **Position**| PIVOTING | Primary retainer ENDED 2026-05-18. SunBiz salary opportunity pending confirmation. |
| **Confidence** | 0.65 | Core automations production-grade but revenue base collapsed. Must land SunBiz salary + diversify ASAP. |
| **Focus Area** | **REVENUE RECOVERY + SUNBIZ SALARY** | primary retainer ended. SunBiz salary is the primary near-term revenue play. Outreach for new OASIS clients remains critical. |
| **Energy** | PIVOTING / DETERMINED | Major client shift. CC handling it well — already has SunBiz lined up as replacement. Strategy session with Atlas + Bravo scheduled. |
| **Memory Health** | GOOD | Files current. Knowledge wiki seeded. mem0 live. |

> **Ephemeral state lives in `memory/OPERATIONAL_STATE.md`** (split out 2026-05-07 per Architecture Certification finding C5). That file carries Active Infrastructure, Known Issues, Last Heartbeat — under a 7-day freshness gate. Read it for live ops; this file is for stable identity / North Star / capability architecture.

---

## North Star: $5,000 USD Net MRR by June 18, 2026

> Previous goal ($1,000 USD Net MRR by March 31, 2026) — **ACHIEVED** at $2,691 USD (+169% surplus).
> **CRITICAL UPDATE (2026-05-18):** Concentration risk R-001 materialized. Primary retainer ($2,500 flat + ~$451 rev share) ended. $1,300 outstanding AR from the prior client. **Deadline extended:** May 30 → June 18, 2026 (31 days to close $4,629 gap from $371 baseline).

1. **Confirmed Revenue:** ~$371 USD/mo Net MRR ($180 Stripe + $191 base). primary retainer ended.
2. **Pending Revenue:** SunBiz salary — CC expects ~similar to the prior retainer ($2,500 range). NOT confirmed yet. Do not count until signed.
3. **Outstanding AR:** $1,300 outstanding from the prior client. CC is collecting directly.
4. **Gap (from confirmed only):** ~$4,629 USD/mo. If SunBiz lands at ~$2,500: gap drops to ~$2,129.
5. **Strategy (revised):** (a) Lock in SunBiz salary ASAP. (b) Outreach for new OASIS clients. (c) The prior client may return as smaller coaching gig later — do not count on it.
6. **Risk:** Revenue base dropped ~89%. SunBiz salary is the lifeline. Diversification is now existential, not optional.
7. **North Star status:** Goal date **extended 2026-05-18: May 30 → June 18, 2026** (31 days from extension). $4,629 / 31 days ≈ $149/day required, vs $375/day under the May 30 deadline.

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
- **Cross-machine sync:** Windows (CCPC, 192.168.2.133) production + Mac (Conaughs-MacBook-Air, 192.168.2.196) cold-standby via `ssh cc-mac`
- **PM2 state:** Windows runs bravo-scheduler + telegram-bot (standalone). Mac has bravo-telegram registered but stopped. Skool daemon archived 2026-05-18 (preserved at `scripts/_archive/skool/` for revival when CC launches their own community).

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
- **Primary community-management retainer** — **ENDED 2026-05-18.** Client said the retainer was too expensive at full-time hands; brought a full-time coach on. CC may return as smaller coach later. $1,300 outstanding AR. Skool comment/reply daemon archived 2026-05-18 — see `scripts/_archive/skool/`. Context: [[APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE]]

## Agent Runner Backend (2026-05-05)

**Design + scaffold shipped, not deployed yet**
- `docs/AGENT_RUNNER_DESIGN.md` written â€” direct `runner.oasisai.work` architecture for the Command Center chat widget. Decision set: Node/TypeScript runner, session-scoped workers, SSE streaming, Supabase JWT verification on-runner, libsodium app-layer key encryption, BYOK enforcement for non-CC tenants, read-only file tree with approval-gated writes.
- `apps/agent-runner/` scaffold added â€” `server.ts`, `sessions.ts`, `spawner.ts`, `auth.ts`, `files.ts`, `sse.ts`, plus isolated `package.json` + `tsconfig.json`.
- `database/020_agent_runner.sql` added â€” `agent_model_config`, `chat_sessions`, `chat_messages`, `audit_log`, plus managed-auth guardrail on `tenants.custom_fields.managed_auth_allowed`.
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
- **Hubs (graph spine):** [[skills/INDEX]] · [[docs/INDEX]] · [[browser/README]] · [[browser/domain-skills/README]] · [[browser/interaction-skills/INDEX]] · [oasis-command-center](https://github.com/CC90210/oasis-command-center) (external) · [[data/pulse/README]] · [[memory/outreach_archive/INDEX]] · [[memory/daily/INDEX]] · [[.gemini/INDEX]] · [[templates/agent-scaffold/README]]
- **Top-level:** [[PLAYBOOK]] · [[SECURITY]] · [[brain/CLIENT_READY]]

## Last Heartbeat

- **Date:** 2026-06-10
- **Agent:** BRAVO via Claude Code (claude-opus-4-6"              # Lead architect (Bravo))
- **Result:** V7.0 reliability foundation shipped (Fable, freeze lifted): EPIC7 loud-failures (system_health + 8 live path-drift bugs fixed + breadcrumbs), EPIC3 LanceDB 410→1, routing-accuracy gate, state_manager tests, fleet untrusted_content → 3 siblings, system_health/state_compact → harness scaffold. CEO→V7.0.0. EPIC1 reorg + V7.1 research roadmap deferred.

*Last updated: 2026-06-10*

## Manifest

<!-- MANIFEST:BEGIN -->
_Auto-generated by `scripts/catalog_sync.py` — do not edit this block manually._
_Last synced: 2026-05-21T22:23:37.688699+00:00_

| Type | Count |
|---|---:|
| Python scripts | 95 |
| PowerShell scripts | 10 |
| Shell scripts | 2 |
| **Total scripts** | **107** |
| Skills | 149 (7 destructive) |
| Agents | 21 |
| Workflows | 33 |

**Scripts by category:**

- Other: 69
- Communication: 10
- Data & Memory: 9
- System: 6
- Content: 5
- Governance: 4
- Finance: 4

<!-- MANIFEST:END -->
