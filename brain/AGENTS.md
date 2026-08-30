---
description: "Subagent registry mapping tasks to specialized agents (Coder/Reviewer/Architect/Researcher); includes routing rules, complexity tiers, and orchestration matrix"
tags: [agents, orchestration]
last_updated: 2026-08-18
freshness_threshold_days: 30
verified: 2026-06-09
---
# AGENTS — Subagent Registry & Orchestration Protocol

> **PURPOSE:** Single source of truth for all specialized subagents. Every AI interface (Claude, Gemini, Antigravity) references this file to determine delegation strategy.
> **RULE:** When a task matches a subagent's domain, adopt that subagent's mindset and principles. For Claude Code, delegate to the actual `agents/*.md` files.
>
> **Read first for any non-trivial delegation:** [[brain/ORCHESTRATION#PART 1 — DELEGATION & ORCHESTRATION PROTOCOL (V5.7, 2026-04-21)]] — risk-weighted routing score, layer selection matrix (agents/ vs .claude/agents/ vs voltagent/ vs Codex), handoff contract, result schema, Validator pattern, per-domain verification contracts, model routing per `scripts/lib/model_registry.py` (fable-5 standard · opus-4-8 heavy code · sonnet-4-6 general · haiku-4-5 cheap).
>
> **Related:** [[brain/CROSS_AGENT_AWARENESS]] — how Bravo/Atlas/Maven/Aura stay in sync via pulse files. [[brain/HOW_TO_USE_THE_4_AGENTS]] — CC's operating manual. [[brain/AGENT_SELF_IMPROVEMENT_PROMPTS]] — paste-into-IDE prompts to level up sibling agents.

## Task Routing (Auto-Assignment)

**All non-trivial tasks are routed automatically** via the task routing skill (`skills/task-routing/SKILL.md`).
Config: `.agents/config.toml` [routing] section.

**⚠ V5.7 update (2026-04-21):** file-count tiering below is the LEGACY classifier. The primary decision is now **risk-weighted routing** per [[brain/ORCHESTRATION#Risk-Weighted Routing (replaces file-count tiering)]] — a 1-file irreversible Stripe edit is higher risk than a 10-file CSS cleanup. Use the risk-weighted score to decide reviewer/Codex/CC-approval gates; use the file-count tier below only as a secondary sanity check on team size.

| Complexity | Agent Assignment | Approval |
|-----------|-----------------|----------|
| **TRIVIAL** (1 file, 1-2 steps) | Inline — no delegation | None |
| **SIMPLE** (1-2 files, 3-5 steps) | Single domain agent | None |
| **MODERATE** (3-5 files, 5-15 steps) | Primary agent + reviewer gate | None |
| **COMPLEX** (6-15 files, 15-30 steps) | Full team (architect → writer → reviewer → debugger) | CC approves plan |
| **ARCHITECTURAL** (15+ files, 30+ steps) | Full team + documenter, SPARC methodology required | CC approves spec + arch |

For COMPLEX+ tasks, use SPARC methodology (`skills/sparc-methodology/SKILL.md`).

## Orchestration Decision Matrix

> **V7.4 (ADR-0012):** per-persona spawn routing is now GENERATED from agent frontmatter → **[[brain/WHEN_TO_USE_AGENTS]]** (regenerated on every graph build, freshness-tested; can't drift). Resolve at runtime: `python scripts/capability_query.py resolve "<intent>" --kind agent`. This matrix keeps only what frontmatter can't express: **cross-agent delegation** (to sibling agents / apps) and the coarse signal→owner map. The V5.5 rows below that named fictional agents (Coder/Planner/Content Creator/Reviewer) are corrected to real personas.

| Task Signal | Route to | Trigger / how |
|---|---|---|
| System design, schema, cross-service planning, financial-model architecture | **architect** (.claude/agents) | architectural questions; advisory-only, hands to writer |
| Code implementation, bug fixes, TDD | **writer** | approved plans; feature/bugfix work |
| Code review, security audit, quality, pre-ship | **code-reviewer** (.claude/agents) | `/review`, `/commit` gate; two-pass |
| Debugging, error resolution, root cause | **debugger** (.claude/agents) | build failures, stack traces; Codex-delegates deep chains |
| Market/competitive research, documentation lookup | **researcher** (.claude/agents) | unknown APIs, competitor questions; 3-source |
| Authenticated web app control, screenshots, domain-skill learning | **Browser Harness + owning agent** | `skills/browser-harness`, owner gates below |
| Debug/build/deploy/migrate/incident/a11y/MCP/PM specialists | **V7.2 agency bench** | see [[brain/WHEN_TO_USE_AGENTS]] + rows below |
| Git operations, PR management | **git-ops** | `/commit`, branch management |
| Client comms drafts, follow-ups, meeting prep, churn | **chief-of-staff** | client emails (drafts → send_gateway) |
| INBOUND pipeline motion, nurture, lead scoring | **revenue-hunter** | funnel leads; cold outbound operator-approved only |
| n8n automation creation | **workflow-builder** | `/build-workflow`, automation tasks |
| Documentation, changelogs, memory files | **documenter** | `/update-docs`, post-feature docs |
| File search, codebase navigation | **explorer** | "find X", "where is Y"; read-only |
| Generate a new subagent | **meta-agent** | "I need an agent that…"; emits ADR-0012 contract |
| Morning briefing, pipeline check, client health, strategy/OKRs/QBRs | **Bravo (self)** | `/briefing`, `/qbr` — MRR excluded (Atlas owns it) |
| **Content, brand voice, ads, social, funnels, SEO, video, proposals/investor decks** | **Maven (CMO)** → `~/CMO-Agent` | Bravo never writes content — route to Maven |
| **Tax, accounting, revenue/MRR reporting, financial advisory, FIRE** | **Atlas (CFO)** → `~/APPS/CFO-Agent` | all money questions |
| **Legal, contracts, NDAs, risk review** | **Lex** → `~/APPS/Lex-Agent` | UPL-gated; not legal advice |
| **Home / ambient / voice** | **Aura** → `~/AURA` | peer agent |
| Backend implementation, deep debugging, adversarial review (2nd opinion) | **Codex Agent** | `python scripts/core/codex_review.py` / codex-companion (Rule 8) |
| Second-opinion code review | **Codex Agent** | `/codex:review`, `/codex:adversarial-review` |
| Deep debugging, root-cause analysis | **Codex Agent** | `/codex:rescue investigate [bug]` |
| Pre-ship design challenge | **Codex Agent** | `/codex:adversarial-review --background` |
| Post-execution gate / silent-failure detection | **Validator** (`.claude/agents/validator.md`) | After every parallel sub-agent spawn, every Codex file-modifying task, every risk-3 or blast_radius-3 op, before `/ship` and `/commit`. Read-only Haiku; returns APPROVE/WARN/REJECT. See [[brain/ORCHESTRATION#Validator Pattern]]. |
| Flaky tests, new/broken E2E suites, CI test architecture | **testing-test-automation-engineer** (V7.2.0) | test failures beyond one file, "tests are flaky", suite design |
| Accessibility audit of a live site/component | **testing-accessibility-auditor** (V7.2.0) | WCAG/508 questions, pre-launch a11y pass on client sites |
| Migration design, RLS-safe schema change, DB backup/DR | **engineering-database-reliability-engineer** (V7.2.0) | Supabase schema evolution, zero-downtime migration, recurring RLS pain |
| CI/CD pipeline or deploy-gate design | **engineering-devops-automator** (V7.2.0) | GitHub Actions work, promotion/rollback strategy, "push ≠ live" gates |
| Incident spanning multiple services | **engineering-incident-response-commander** (V7.2.0) | cron+PM2+Vercel+DB cascades; coordinates, never applies fixes |
| Audit an AI-authored diff before ship | **security-ai-generated-code-auditor** (V7.2.0) | Rule 8 pre-ship on Claude/Codex diffs; read-only |
| Roadmap, PRD, feature prioritization across apps | **product-manager** (V7.2.0) | "what should we build next", portfolio roadmap artifacts |
| Cross-project status rollup, stalled-item sweep | **project-management-project-shepherd** (V7.2.0) | 15+ open projects, dependency tracking; read-only |
| Design/build/audit an MCP integration | **specialized-mcp-builder** (V7.2.0) | new MCP server, Rule 4 config-sync work |
| Prep for an inbound qualification/discovery call | **sales-discovery-coach** (V7.2.0) | call tomorrow with a funnel lead; advisory only, INBOUND-first policy holds |

## Subagent Definitions

> **V7.4 (ADR-0012):** the per-persona detail for the CORE BENCH (architect, writer, code-reviewer, debugger, researcher, chief-of-staff, revenue-hunter, workflow-builder, git-ops, documenter, explorer, meta-agent, codex-agent) is now the persona files themselves + the GENERATED **[[brain/WHEN_TO_USE_AGENTS]]** (frontmatter-derived, freshness-tested). Human hub with one-liners + tiers: **[[agents/INDEX]]**. This section keeps ONLY the entries that carry context frontmatter can't express: the Validator gate, Codex external-executor contract, and the client-product / import records.

### 17.5 Validator (Silent-Failure Detector — NEW 2026-04-21)
- **Model Tier:** Haiku (fast, deterministic, cheap)
- **File:** `.claude/agents/validator.md` (Claude Code native — spawned via Task tool)
- **Purpose:** Post-execution quality gate for any multi-agent or high-risk operation. Scores sub-agent outputs against success criteria; catches hallucinated claims, silent failures, and scope violations BEFORE results reach CC. Closes Anthropic's named "Observability-Evaluation Gap" (arXiv:2604.14228).
- **Key upgrades:** Structured claim verification (VERIFIED/REFUTED/UNVERIFIABLE). Scope violation detection. Test re-run with exit-code diffing. Three-tier verdict (APPROVE ≥85 / WARN 70-84 / REJECT <70). Recommendation string for orchestrator.
- **Principles:** READ-ONLY. Never spawn sub-agents. Never invent success criteria. Max 2-min runtime. Output-schema-only response (no narration).
- **When to fire:** after every parallel spawn, every Codex file-modifying task, every risk-3 or blast_radius-3 operation.
- **Originating lesson:** session 2026-04-21, orphan-audit returned 3 false-positive claims. Bravo caught them via manual verification. Validator codifies that verification step.

### 18. Codex Agent (External AI Executor)
- **Model Tier:** External (OpenAI GPT-5.4 via Codex CLI)
- **File:** [[agents/codex-agent]]
- **Purpose:** Backend-heavy implementation, deep debugging, adversarial code review, and parallel task execution via OpenAI's Codex runtime.
- **Key upgrades:** Context injection protocol standardized. Failure recovery (3-strike rule with model switching). Verbatim output requirement. Pre-flight check before every delegation.
- **Principles:** Bravo orchestrates, Codex executes. Never delegate frontend/content/memory. Background by default. Present output verbatim.
- **Commands:** `/codex:review`, `/codex:adversarial-review`, `/codex:rescue`, `/codex:status`, `/codex:result`, `/codex:cancel`, `/codex:setup`
- **Plugin location:** `.claude/plugins/codex/`

### 19. Sun Biz Agent (Funding Operations — Separate Client Product, corrected 2026-05-11)
- **Model Tier:** Sonnet (per-agent runtime in its own repo, like Atlas/Maven)
- **Project:** `C:\Users\User\SunBiz-Agent` (canonical Windows clone; VPS runtime at `/srv/sunbiz/sunbiz-agent`)
- **GitHub:** `CC90210/SunBiz-Agent` (operator-provided target URL; local remote rename/push still pending authorization)
- **Purpose:** CC's first **client backend operations product**. Runs Sun Biz Funding LLC's day-to-day funding operations — lead sourcing, multi-provider SMS + email outreach, application/offer/funded-deal lifecycle, renewal triggers, commission tracking, and lender CRM — as a separate client-facing agent, not as a permanent row-level tenant of CC's own ops product.
- **Capabilities (V1):** Kixie (voice) + TextTorrent (SMS), Gmail SMTP bulk email (inherited from AdVantage V2.0 production engine), funding-intel (factor rates, commission math, TAR-band classification), deal_tracker lifecycle helpers, renewal_scanner cron, native /forms designer lead ingestion. 16 sub-agents preserved from AdVantage rebrand — ads remain a lead-gen sub-capability.
- **Heartbeat:** `scripts/state_bridge.py` daemon pings shared V6 state DB every 15s under `agent="sunbiz"`. Visible in dashboard `/agents` page and `state_api:8500/status` response.
- **Events:** Emits the `SUNBIZ_*` family — registered in [[brain/EVENT_BUS_CONTRACT]] §Standard event-type registry (LEAD_SOURCED, SMS_SENT, APPLICATION_SUBMITTED, OFFER_PRESENTED, DEAL_FUNDED, RENEWAL_DUE, COMMISSION_BOOKED, EMAIL_BLAST_DISPATCHED, SESSION_LOG_APPENDED).
- **Data topology:** Sun client data is **Turso/libSQL-first**. Shared infra may still use Business-Empire-Agent's V6 substrate (state DB mirror, event bus, dashboard shell), but leads/applications/offers/funded deals/renewals/commissions/SMS audit are NOT assumed to live in CC's shared Supabase tables.
- **Dashboard connection:** the Agent Command Center may render a Sun-specific sidebar/profile shell, but that shell is a reusable client-facing surface — not proof that Sun should live forever as a row-level tenant inside CC's internal dashboard deployment.
- **Relationship to Bravo:** Bravo is CC's architect — owns shared substrate (state_manager, event_bus, dashboard chrome, onboarding rails). Sun Biz Agent owns Sun's runtime and business logic. Bravo MAY read Sun Biz pulse/state and mutate shared substrate files here; Sun product/data architecture lives in the Sun Biz repo/runtime.
- **Relationship to Atlas/Maven:** Atlas approves spend gates on any paid Sun outreach (SMS/email volume budget); Maven owns CC's empire content but does NOT touch Sun Biz content (that's the tenant's own brand voice).
- **Client-facing personas (2026-07):** inside the Command Center this product presents as a two-agent team — **Solara** (ops: pipeline reporting, application packaging, lender matching, template production) and **Helios** (sales: SMS outreach voice, NEPQ qualification, TCPA guardrails). Persona definitions: `oasis-command-center:lib/agent-personas.ts`. See CONTEXT.md § People & agents.
- **Routing rule:** Anything labeled "for Sun", "Sun Biz Funding", lead sourcing inside the Sun tenant, MCA/funding deal lifecycle, multi-provider SMS, or commission tracking → route to Sun Biz Agent repo.
- **Key files:** `brain/SOUL.md` (identity), `brain/CLIENT.md` (Sun Biz Funding profile + ICP), `scripts/sms_engine.py`, `scripts/funding_intel.py`, `scripts/deal_tracker.py`, `scripts/renewal_scanner.py`, `scripts/email_blast.py` (preserved from AdVantage V2.0).

### 20. Suga Sean O'Malley Agent — RETIRED (scaffold removed 2026-07; recorded 2026-07-19)
- **Status:** RETIRED. The Suga client-product scaffold (SUGA_PROFILE, SUGA_NAV, Crown brand shell) was removed from the live agent catalog; the standalone runtime was never built. No routing rule — anything referencing "Suga" is historical.
- **Superseded by:** the client-persona pattern now proven on Sun Biz Funding — **Solara (ops) + Helios (sales)**, defined in `oasis-command-center:lib/agent-personas.ts` (see §19). New client products follow that two-persona shape.
- **History:** original scaffold spec preserved in git history (this section, pre-2026-07-19) and `_archive/` handovers.

### 21. V7.2 Agency-Import Bench (10 specialist personas, 2026-07-18)
- **What:** 10 hand-scoped specialist subagents imported from msitarzewski/agency-agents (MIT): QA/test engineering, accessibility, DB reliability, DevOps, incident command, AI-code audit, product management, project shepherding, MCP building, inbound discovery coaching.
- **Registry:** [[agents/INDEX]] § Agency Imports is the single source for the roster + per-persona tool scoping — deliberately NOT duplicated here (copies are how counts rot). Live count: `CAPABILITY_GRAPH.json` totals (32 agent nodes).
- **Routing:** rows in the Orchestration Decision Matrix above + [[brain/ORCHESTRATION_DECISION_TABLE]] §A.

## V6.0 Cross-Agent Contract (added 2026-05-10)

When a sibling agent (Atlas, Maven, Aura, Hermes, Lex) reads from this repo, the V6.0 substrate changes nothing about WHERE to read — but adds new fields they can use if they want.

**Sibling read paths — UNCHANGED:**

| What sibling wants | Path (still valid in V6.0) | Notes |
|--------------------|-----------------------------|-------|
| Bravo's recent activity | `memory/SESSION_LOG.md` | Auto-generated mirror of `state/empire_state.db` when `EMPIRE_V6_MODE=on`. Same path, fresher data. |
| Bravo's operational state | `brain/STATE.md` | Heartbeat block auto-generated; rest is human-curated. |
| Bravo's tasks | `memory/ACTIVE_TASKS.md` | Still human-curated (DB tracks programmatic tasks separately). |
| Bravo's pulse snapshot | `data/pulse/ceo_pulse.json` | **Now includes a `v6` block** — see `data/pulse/README.md` for schema. |

**New `v6` field in `ceo_pulse.json`** stamps every publish with:
- `mode` (`off` / `shadow` / `on`)
- `hook_modes.{secret_guard,exec_guard,state_guard}` (`enforce` / `report` / `off`)
- `state_db.{session_log_count,transaction_count,size_kb,last_heartbeat}`
- `fts5.{sources,chunks,last_indexed,size_kb}`

**What sibling agents should do:**
- **V5.5-era siblings:** ignore the `v6` field (JSON additive — no breaking change). Read the existing fields as before.
- **V6.0-aware siblings:** prefer `pulse.v6.state_db.last_heartbeat` for Bravo liveness checks (sub-second precision; the markdown frontmatter is rounded to the day). When `pulse.v6.mode == "on"`, Bravo's flat-file mirrors are auto-generated, so DON'T attempt to write to them — write to the cross-agent inbox instead (`scripts/core/agent_inbox.py`).
- **All siblings:** still use `data/pulse/cfo_pulse.json` etc. for THEIR pulse handoff back. Bravo reads sibling pulses unchanged.

**Hard rule (unchanged from V5.5):** Bravo NEVER writes to a sibling repo. Siblings NEVER write to Business-Empire-Agent. Cross-agent state moves only through pulse files + agent_inbox.

**Adoption sequence:** Bravo is V6.0 first. Atlas, Maven, Aura, Hermes adopt V6.0 in their own repos when their operators are ready — this contract works whether they're on V5.5 or V6.0.

**Push-mode coordination (BUILD 3, 2026-05-10):** sibling agents can subscribe to Bravo's events via the shared Supabase `agent_events` table — see `brain/EVENT_BUS_CONTRACT.md` for the canonical event-type registry and the subscribe contract. Bravo currently emits `BRAVO_SESSION_LOG_APPENDED`, `BRAVO_PULSE_REFRESHED`, `BRAVO_CHAT_INTERACTION`. Reserved sibling-emitted types (when those agents adopt V6.0): `MAVEN_POST_COMPLETE`, `ATLAS_BUDGET_LOCKED` / `ATLAS_BUDGET_RELEASED`, `AURA_PRESENCE_HOME` / `AURA_PRESENCE_AWAY`, `HERMES_INVOICE_SHIPPED`. Pulse files remain the snapshot-of-truth; the bus carries change notifications between snapshots.

## Shared Browser Harness Layer

Browser Harness is a shared capability, not a new sovereign agent. Bravo owns the repo-level installation, diagnostics, safety rules, and `browser/domain-skills/` seed library. Each agent may use the layer only inside its domain:

| Agent | Browser Harness Scope | Approval Gate |
|---|---|---|
| Bravo | GitHub, Supabase, Vercel, n8n, Stripe read-only, Google Workspace, client portals | approval before send/publish/billing/admin/destructive/production actions |
| Atlas | finance dashboards, Stripe/accounting/tax portals | approval before money movement, filings, refunds, bank/billing changes |
| Maven | LinkedIn, X/Twitter, Meta Ads, Google Ads, Canva, schedulers, analytics | approval before publishing, messaging, ad budget, campaign changes |
| Aura | Home Assistant, router/device dashboards, local home services | approval before locks, cameras, alarms, resets, privacy-sensitive views |
| Hermes/client agents | supplier/client portals and browser-only workflows | per-client approval profile and audit trail required |

Outbound communication still goes through `scripts/integrations/send_gateway.py`. Browser domain skills must never store secrets, cookies, tokens, raw coordinates, private screenshots, or task diaries.

## Agent Permissions (Claims-Based Access Control)

Each agent operates under a permission level. See `skills/agent-permissions/SKILL.md` and `.agents/config.toml` [permissions].

| Level | Claims | Agents |
|-------|--------|--------|
| **minimal** | read | explorer, researcher, revenue-hunter |
| **standard** | read, write, execute | writer, reviewer, chief-of-staff, git-ops, documenter |
| _(Maven sub-agents)_ | _delegated_ | content-creator, social-publisher, video-editor — live in `../CMO-Agent/agents/`, not local |
| **elevated** | standard + spawn, memory | architect, debugger, workflow-builder, meta-agent, codex-agent |
| **admin** | all | Bravo lead agent only |

**Universal blocked:** `.env*`, `*.pem`, `*.key`, `credentials*.json`, `.obsidian/**`

## Anti-Drift Protocol

Multi-agent tasks use drift detection. See `skills/anti-drift/SKILL.md` and `.agents/config.toml` [anti_drift].

- **Checkpoint** every 5 task steps — agent validates alignment with original intent
- **Scope creep detector** — flags when >3 files touched beyond plan
- **Error cascade detector** — stops after 2 consecutive failures, forces approach switch
- **Max concurrent agents:** 4 (prevents coordination overhead)

## Security Protocol (All Subagents)

1. **NEVER** hardcode API keys, tokens, or database passwords. All credentials in `.env.agents`.
2. If an exposed secret is detected → **STOP** → initiate rotation immediately.
3. Validate all inputs at system boundaries. Sanitize external API payloads.
4. Enforce Supabase RLS. Never leave tables publicly accessible without explicit authorization.
5. Sandbox risky scripts in `tmp/`. Require CC's consent for destructive operations.

## Self-Improvement Protocol (All Subagents)

1. **Mistakes** → Log to `memory/MISTAKES.md` with root cause and prevention strategy.
2. **Patterns** → Log to `memory/PATTERNS.md` (tag `[PROBATIONARY]` until verified across 3+ sessions).
3. **Decisions** → Log to `memory/DECISIONS.md` with date, rationale, and alternatives considered.
4. **Reflections** → Log failures to `memory/SELF_REFLECTIONS.md` using Reflexion framework.

## AI Entry Points

Six lockstep entry points — same Bravo identity, runtime-specific routing only (CLAUDE.md Rule 4 keeps them in sync):
- [[CLAUDE]] — Claude Code CLI entry point (CEO/COO/CTO; primary strategy/ops/refactor/debug/architecture chassis)
- [[GEMINI]] — Gemini CLI entry point (Bravo Inference Engine)
- [[ANTIGRAVITY]] — Antigravity IDE entry point (Bravo Infantry / Architect Hybrid)
- [[AGENTS]] — AGENTS.md-convention chassis (Codex CLI / Cursor / Windsurf / Aider)
- [[OPENCODE]] — OpenCode terminal entry point (model-swap chassis, added 2026-05-03)
- [[ZCODE]] — ZCode local CLI entry point (GLM-5 Turbo runtime from `.zcode/`, CLI-only tool surface, added 2026-06-17)
- [[.gemini/rules/GEMINI]] — Gemini-specific rules copy
- [[.gemini/rules/ANTIGRAVITY]] — Antigravity-specific rules copy

## Obsidian Links
- [[brain/SOUL]] | [[brain/CAPABILITIES]] | [[brain/BRAIN_LOOP]]
- [[memory/MISTAKES]] | [[memory/PATTERNS]] | [[memory/SELF_REFLECTIONS]]
- [[skills/task-routing/SKILL]] | [[skills/anti-drift/SKILL]] | [[skills/agent-permissions/SKILL]]
- [[skills/sparc-methodology/SKILL]] | [[skills/hooks-automation/SKILL]] | [[skills/background-workers/SKILL]]
