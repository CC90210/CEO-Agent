---
name: CONTEXT
description: Canonical vocabulary for the Business-Empire-Agent / Bravo OS. Every skill, agent, and entry-point must use these terms with these meanings. If a new domain term needs to enter the codebase, add it here first.
tags: [vocabulary, canonical, context]
last_updated: 2026-08-15
---

# CONTEXT — Canonical Vocabulary

> Single source of truth for OASIS / PropFlow / empire terminology.
> If you find yourself re-deriving what a term means mid-session, the term either belongs here or its existing entry needs tightening. Update this file; don't re-derive.

Pattern adapted from [mattpocock/skills CONTEXT.md](https://github.com/mattpocock/skills) — but our scope is empire-wide, not skill-local.

---

## People & agents

- **CC** — The operator. Owner of Business-Empire-Agent and the empire's systems. **OASIS AI Solutions is owned equally by CC and Adon** (corrected by CC 2026-08-24 — the prior "CC 100%, Adon PropFlow-only" line was wrong; equal split agreed verbally, contracts to be signed soon — Atlas tracks the papering). PropFlow is also CC + Adon 50/50.
- **Bravo** — This agent. CC's right hand and second brain — **CEO, COO, and CTO in one** (Maven owns CMO; Atlas owns CFO). "Lead Architect" is the CTO facet, not the whole role. Spans five runtimes (Claude / Gemini / Antigravity / OpenCode / IDE-agnostic); identity is shared, routing differs per-runtime entry point.
- **Maven** — CMO agent at `~/CMO-Agent`. Owns all content, brand voice, ads, social posting. Bravo NEVER writes content; routes to Maven.
- **Atlas** — CFO agent at `~/APPS/CFO-Agent`. Owns tax/compliance, financial advisory, equity research. Pivoted from autonomous trading 2026-04-14; trading code archived under `archive/trading-automation/`.
- **Hermes** — Messaging/inbox agent at `~/APPS/hermes`.
- **Aura** — Branding/design agent.
- **Lex** — Legal/contracts agent at `~/APPS/Lex-Agent` (`CC90210/Lex-Agent`). In-house counsel: drafts/reviews contracts, ranks legal risk in plain English. Product-first + multi-tenant. **Not a licensed attorney — never gives legal advice** (UPL gate in its `brain/COMPLIANCE.md`). Added 2026-06-18.
- **Codex** — OpenAI's executor, integrated as Bravo's dual-AI backend specialist. Delegated to via `codex-companion.mjs` for backend implementation, deep debugging, adversarial review.
- **Solara** — SunBiz Funding's client-facing **ops agent** in the Command Center: pipeline reporting, application packaging, lender matching, renewal sweeps, HTML template production. Never drafts outreach (that's Helios). Persona: `oasis-command-center:lib/agent-personas.ts`.
- **Helios** — SunBiz Funding's client-facing **sales agent**: the SMS/outreach voice (NEPQ qualification, revival sequences) under hard TCPA guardrails — never promises rates or amounts in writing. Automated sends attribute to Helios via `agent_source`. Replaced the retired Suga scaffold as the second client persona (2026-07).

## Brands

- **OASIS AI Solutions** — CC's primary B2B brand. AI automation consulting + custom agents for local businesses. Montreal, QC (relocated from Collingwood, ON 2026-07; 2026 is a tax transition year — see Atlas).
- **PropFlow** — Tenant-screening + landlord-automation product. CC + Adon 50/50. Runs on Turso (migrated from its own Supabase project, 2026-08). Bucket-list feature: real-estate portal embed.
- **CredPort** — The multi-tenant MCA / business-funding software platform (named 2026-06-15; was working-named "Fundrail"): a merchant-facing portal + funder back-office that many funders run on, each under their own branding. A **separate jointly-owned company** — **60% OASIS AI / 40% David** (equity split). Commercial terms — the monthly engagement fee and the platform-fee split — are owned by **Atlas / CFO**, not tracked here. Has its own Supabase project (trust boundary on merchant financial data). Repo: [CC90210/breeze-portal](https://github.com/CC90210/breeze-portal) (repo name still `breeze-portal`; product brand is CredPort). Platform brand (CredPort) shows on public/landing surfaces; tenant brand (BreezeAdvance etc.) shows inside each funder's portal. MCA domain vocabulary in the "MCA / Lending" section below.
- **BreezeAdvance** — David's **existing MCA funding company** (breezeadvance.com), NOT the platform. It is the **first funder / first tenant** on CredPort. Do not conflate: "BreezeAdvance" = the funder (keeps its own navy/cyan brand inside its portal); "CredPort" = the separate software platform company. Other funders onboard later as additional tenants with their own logos + brand.
- **Nostalgic Requests** — Personal/legacy brand. Lower priority than OASIS and PropFlow.

## Multi-tenancy

- **Tenant** — A customer-facing namespace inside the empire DB. Tenant-scoped data is filtered by `tenant_id`. Examples: OASIS, PropFlow, submissions (SunBiz). (CC-Funnel was a tenant until it retired 2026-06-18 — funnel is now native at `oasisai.work/f/`.)
- **Tenant manifest** — Config object describing a tenant's nav, theme, feature flags. Lives in code under `oasis-command-center:config/tenants/`.
- **Tenant-scoped feature** — A feature that should appear in ONE tenant's nav only (e.g., `/forms` lives in the SunBiz `submissions` tenant, NOT in OASIS). Infrastructure features extrapolate across tenants; product features do not. See `feedback_tenant_scoped_nav.md`.
- **Empire DB** — the tenant_id-scoped store behind all empire + client data. **Turso (libSQL) is the database. Five isolated databases: bravo, breeze, propflow, oasis, nostalgic.** New tables, migrations and queries target Turso; do not add a Supabase table. This REVERSES the 2026-05-15 "Turso-per-tenant deferred" decision; the driver was cost (dropping the Supabase Pro plan). As of 2026-08-09 the data plane is cut over and verified: all 5 databases at parity (no row exists in Supabase that is absent from Turso), 4 Vercel apps, 13 VPS daemons, Atlas, Maven, and the TextTorrent SMS runtime. The Supabase project still EXISTS as legacy — still writing to it: the event bus (`agent_events` LISTEN/NOTIFY — no libSQL equivalent), the `agent_activity` coordination table, the state-health Vercel mirror, and APEX (Adon's agent — a handover item, not ours).
- **Turso mode flags** — Turso is enabled per process and each flag gates a different layer, so setting one is not "on": `EMPIRE_DATA_BACKEND=turso_cloud` switches the server data plane; `EMPIRE_AUTH_BACKEND=turso` + `AUTH_SESSION_SECRET` gate auth AND the `/api/data/bridge` + `/api/data/rpc` routes (they 404 without them). Plus `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN`. Unset any of them and that process falls back to Supabase — which was the safe default DURING the migration and is now a silent misconfiguration. `EMPIRE_DATA_BACKEND` must be a real process env var: the switch reads `os.environ` at interpreter start, so putting it in `.env.agents` does nothing.
- **The Python switch** — `scripts/_bootstrap/sitecustomize.py`, installed by `scripts/install_python_switch.py` as a **`.pth`** (`empire_turso_switch.py` + `zzz_empire_turso_switch.pth`), NOT as `sitecustomize.py`. Debian ships its own `sitecustomize` two `sys.path` entries ahead of any venv, so the obvious install is silently never imported. It resolves the repo from the **running script**, so sibling agents (Bravo / Atlas / Maven) sharing one interpreter each load their own `lib` — pointing `EMPIRE_REPO_ROOT` at another repo shadows theirs and crash-loops them.
- **Unported RPC** — every Postgres stored procedure a live code path calls must exist in `RPC_REGISTRY` (Python: `scripts/lib/turso_supabase_compat.py`) or `TURSO_RPC_SHIM` (TS). Turso is SQLite; there is no PL/pgSQL. An unported name raises, and callers that swallow errors turn that into silent no-work — which is how fleet-wide health monitoring went dark unnoticed. Source SQL for every ported function lives in `database/rpc_sources/`; it exists nowhere else once Supabase is gone. Search for call sites with a MULTILINE regex, not `git grep -o`: `.rpc(` frequently wraps onto the next line and a line-based grep under-reports.
- **Data bridge** — the route that replaces RLS in browser-querying apps (PropFlow). Turso tokens are full-database credentials and can never ship to a browser, so tenant scope is derived from the session and forced AFTER client filters. Prove it with `scripts/verify_tenant_isolation.py` before any flip.

## Sales / CRM vocabulary

- **Inbound-first motion (2026-07-09)** — Bravo's PRIMARY CRM motion: leads arrive via the funnel, DMs, and social content → nurture → **book a call**. Cold outbound is on-demand only, never the default. `lead_engine.py` `pipeline`/`followups` are tenant-scoped to `OASIS_TENANT_ID`; the 156-lead cold-outreach book was purged 2026-07-09 (backup in `state/backups/`).
- **Lead** — A row in the `leads` table. Has a `score` (0-100) and a `status` (cold / warm / contacted / qualified / closed / dead).
- **Interaction** — A single touchpoint with a lead (email sent, email received, call, meeting). Stored in `interactions`.
- **Pipeline** — The ordered set of stages a lead moves through. Stages defined per-tenant.
- **Drip sequence** — A multi-step automated outreach campaign keyed off a trigger (lead created, status changed, manual enrol). Each step is a delay + a template.
- **Outreach Send** — Canonical cold/follow-up email path (ON-DEMAND only under the inbound-first motion). ALL outreach emails route through `skills/outreach-send/SKILL.md` → `scripts/integrations/send_gateway.py`. Never draft+send raw — the gateway is mandatory for deliverability + audit.
- **OASIS Outbound** — Specifically the OASIS-branded cold outreach flow (Welcome / Value Add / Reactivation templates). Templates live in DB; critic gate scores them 0-10 before send.
- **Lead score** — 0-100 composite of fit + intent signals. Recomputed by `scripts/lead_scorer.py` on every interaction.
- **Pulse** — Daily 8am Telegram digest summarizing what shipped, what's stuck, what needs CC's attention. Generated by `cron_engine.py` action `pulse_publish`.
- **Morning Pow Wow Call** — Voice variant of Pulse (Phase 10.2, 2026-05-12+).

## State / substrate

- **State DB** — `state/empire_state.db` (SQLite/WAL). Source of truth for heartbeats, session_log entries, active_tasks. Single writer: `scripts/state/state_manager.py`.
- **Empire State** — Generic term for the operational status surface (heartbeats, queue depths, daemon health). Read via `state_manager.py status` or the `/system-health` page.
- **Event bus** — Postgres `agent_events` table with LISTEN/NOTIFY. Producers (state_manager, pulse_publish, send_gateway, etc.) emit `BRAVO_*` event types. Consumers claim via `claim_events()` with `FOR UPDATE SKIP LOCKED`.
- **Bridge lock** — Multi-machine arbitration for Telegram / Discord bridges. Lockfile at `~/.oasis/bridge_locks/<agent>.json`. Owner heartbeats every 15s.

## V6 architecture vocabulary

- **V6 mode** — `EMPIRE_V6_MODE` env var (off / shadow / on). Controls whether state DB is authoritative.
- **Pantry / Prep Table / Plate** — Data taxonomy (V6.7). Pantry = raw sources. Prep Table = deterministic Python pre-aggregations (e.g., `briefing_snapshot.py`). Plate = consumer views (CEO briefing, dashboard widgets). Snapshots run on cron; consumers prefer snapshots over live engines.
- **Guards** — Three chained PreToolUse hooks: `secret_guard.py` (blocks `.env*` reads), `exec_guard.py` (blocks dangerous Bash), `state_guard.py` (blocks edits to auto-generated mirror files).
- **Capability graph** — `brain/CAPABILITY_GRAPH.json`. Auto-built from every skill / script / agent / MCP / workflow frontmatter. Resolved at runtime by `capability_query.py`.
- **Memory retriever** — `scripts/core/memory_retriever.py`. FTS5 + LanceDB hybrid (Reciprocal Rank Fusion). Returns ≤1500-token snippet sets with file:line refs in <100ms. Replaces whole-file Read for context lookups.

## V6.9 CRM Substrate (Twenty pattern import, 2026-05-25)

Patterns imported from [twentyhq/twenty](https://github.com/twentyhq/twenty) (AGPLv3 — patterns only, no code). Replaces the JSONB-blob CRM internals with DB-backed metadata, view rows, and a typed workflow engine. Plan: `~/.claude/plans/i-m-dropping-you-a-magical-cat.md`.

- **Object Metadata** — `object_metadata` row defining a tenant's custom entity type (e.g. `lead`, `application`, `lender`). DB-backed registry that takes precedence over inline `manifest.data_model[]` via the schema-introspector. Migration 070. See `~/APPS/oasis-command-center/lib/schema-introspector.ts`.
- **Field Metadata** — `field_metadata` row defining one typed field under an Object Metadata. 16 types: `text / number / boolean / date / datetime / enum / json / currency / address / rich_text / link / multi_select / rating / phone / email / relation`. Superset of the legacy 7 inline types. Migration 070.
- **Saved View** — `views` row storing a named (kind + filter + sort + visible-fields) configuration per Object Metadata. Optionally workspace-shared (`owner_user_id IS NULL`) or per-user. Replaces ephemeral URL-param view state. Migration 071. See `~/APPS/oasis-command-center/lib/views/loader.ts`.
- **Workflow Step** — Typed handler in the workflow engine. Substrate set: `record-crud / http-request / if-else / delay / mail-sender / ai-agent`. Composable via `workflows.definition` JSONB. Adding a step type is one new file + one REGISTRY line (ADR-0003). See `~/APPS/oasis-command-center/lib/workflow-steps/`.
- **AI Agent Step** — Workflow step type that loads an agent persona (`getPersona`), substitutes `{{trigger.x}}` / `{{step_id.field}}` placeholders, fires single Anthropic call, returns text + token usage. Composes with `record-crud` step for writeback.
- **Field Permission** — `manifest.agents[].field_permissions` entry restricting an agent's read/write access to specific fields per entity_type. Three-state semantics: `undefined`=full / `[]`=zero / populated=scoped with default-deny on entities with any entry. Server-side enforced in `lib/role-gates.ts`. ADR-0004.

## V7.3 Typed Memory (OpenViking pattern import, 2026-07-18)

Patterns from [volcengine/OpenViking](https://github.com/volcengine/OpenViking) (AGPLv3 — patterns only, zero code). Governance: [docs/adr/0011-typed-memory-taxonomy.md](docs/adr/0011-typed-memory-taxonomy.md).

- **Typed memory** — every memory surface declares update semantics (MISTAKES=append-only, PATTERNS=mergeable with [P]→[V] promotion, DECISIONS=immutable, ACTIVE_TASKS=mutable-current, SESSION_LOG=immutable-generated). The registry lives in ADR-0011; writers obey it.
- **Memory diff audit** — `state/memory_diff/<stamp>.json`, written by every bravo_sleep run (even empty ones): each proposal's create/skip decision with duplicate evidence. Missing artifact after a scheduled run = the run crashed.
- **Abstract layer (L1)** — the `description:` frontmatter of every brain/memory file, indexed as a searchable `abstract` column in FTS5 + LanceDB (migration 003; backfilled by `scripts/core/abstract_backfill.py`). Files are findable by what they ARE. Freshness-aware ranking: stale files rank down (floor 0.7; `EMPIRE_FRESHNESS_RANK=0` to disable).

## V7.2 Persona Bench (agency-agents import, 2026-07-18)

Cherry-picked from [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) (MIT). Plan: `~/.claude/plans/i-m-dropping-you-a-elegant-truffle.md`.

- **Persona bench** — the full subagent roster across `.claude/agents/` (native spawnable, wins stem collisions) + `agents/` (recursive since V7.2.0, incl. `voltagent/` and the 10 agency imports). Count lives in `CAPABILITY_GRAPH.json` totals — never hand-counted.
- **Cherry-pick contract** — the ONLY way external personas enter the empire: hand-select against a confirmed gap, normalize to canonical frontmatter, add explicit `tools:`/`model:` scoping (auditors/coordinators read-only), strip personality fluff, keep Critical Rules + Success Metrics, ≤120 lines, source attribution. Bulk importers are never run — untyped personas would carry full Bash/Edit surface under the guard model.

## V7.1 Free-Tier Radar (six-repo audit import, 2026-07-17)

Patterns imported from [free-for-dev](https://github.com/ripienaar/free-for-dev), [public-apis](https://github.com/public-apis/public-apis), and [Made-With-ML](https://github.com/GokuMohandas/Made-With-ML) (links + patterns only — upstream lists are never mirrored). Plan: `~/.claude/plans/i-m-dropping-you-a-elegant-truffle.md`. Governance: [docs/adr/0010-external-resource-catalog.md](docs/adr/0010-external-resource-catalog.md).

- **Free-Tier Radar** — `brain/TOOL_SHED.md` § Section 9. The single curated catalog of free-tier services and free APIs mapped to real capability gaps, with per-row status (`candidate` / `adopted` / `rejected` / `policy`). Consult it BEFORE recommending or paying for any external service; fronted by `skills/resource-radar`.
- **Resource node** — `resource:` kind in `brain/CAPABILITY_GRAPH.json`, parsed from Radar table rows by `discover_resources()` in `build_capability_graph.py`. Makes external-service knowledge resolvable at runtime: `capability_query.py resolve "<need>" --kind resource`.
- **Slice-based eval** — `harness_eval.py` groups its checks into named slices (`lockstep / routing / boundary / guards / live-health / model-call`) and persists every run to `state/harness_eval_history.jsonl` (`run_id` + timestamp), so a regression inside one slice can't hide behind the aggregate score and score drift is trackable across sessions.

## Skill / agent vocabulary

- **Skill** — A reusable named capability at `skills/<name>/SKILL.md`. Frontmatter: `name`, `description`, `triggers`, `tier`, optionally `disable_model_invocation`, `argument_hint`.
- **Skill tiers** — `core` (foundational, used by many) / `specialized` (single-purpose) / `meta` (operates on other skills) / `safety` (guard rails).
- **Skill status lifecycle** — `[NEW]` → `[PROBATIONARY]` (3 successful uses) → `[VALIDATED]`. New patterns earn promotion; they don't get it by default.
- **Hard-dependency skill** — A skill that cannot function without a specific prerequisite (`EMPIRE_V6_MODE=on`, a specific `.env.agents` key, a running PM2 daemon). MUST declare its prerequisite check. See [docs/adr/0001-skill-dependency-classification.md](docs/adr/0001-skill-dependency-classification.md).
- **Soft-dependency skill** — A skill that degrades gracefully when its preferred backend is unavailable. MUST NOT include explicit prerequisite pointers (noise).
- **disable_model_invocation** — Frontmatter flag. When `true`, the skill never auto-loads via semantic match; only fires on explicit `/command` invocation. Used for demand-only skills (`hyperthink`, `retro`, `sparc-methodology`).
- **argument_hint** — Frontmatter key. Surfaces a one-line prompt at invocation ("What spec or requirements?"). Cleaner than embedding the question in the body.

## Browser / scraping

- **Research fetch** — Default URL-fetch entry: `scripts/research_fetch.py <url>`. Auto-escalates Firecrawl → CloakBrowser based on actual response. Per-domain reputation in `state/site_reputation.db`.
- **Browser ladder** — Mandatory 4-tier classification: Firecrawl → CloakBrowser (stealth tier-2) → Browser Harness (CC-authenticated) → Playwright (interactive unprotected). NEVER raw Playwright against bot-protected sites.
- **CloakBrowser** — `scripts/browser/cloak_browser_tool.py`. Drop-in Playwright replacement with C++ source-level fingerprint patches. Binary at `~/.cloakbrowser/`. Mandatory tier-2 for fresh-session scrapes against Cloudflare / DataDome / FingerprintJS.

## MCA / Lending (CredPort platform — repo `~/APPS/breeze-portal`, brand rebranded 2026-06-15)

Vocabulary for the merchant-funding domain. Captured 2026-06-08 with David's product spec. Use these terms verbatim across Breeze code, marketing, and any conversation with David's team.

- **Merchant** — In the MCA context, the funded business (NOT a generic e-commerce merchant). Schema: `merchants` row scoped by `tenant_id`. The merchant USER (the human who logs in) is `merchant_users.auth_user_id`.
- **Funder / Lender** — The MCA company providing capital. In Breeze, the funder is a `tenant`; their staff are `tenant_users`. David's company is the first tenant.
- **Advance** — The principal cash a funder gives a merchant against future receivables. Schema: `advances` row. NOT a loan in the traditional sense — interest is replaced by factor rate, term is approximate, and repayment is via receivables holdback rather than fixed installments.
- **Factor rate** — Multiplier on the advance that determines total repayment. `total_due = advance_amount * factor_rate`. Typical range 1.10× to 1.55× (10–55% premium). Stored as `numeric(4,3)`. NEVER confuse with interest rate.
- **Term** — Approximate days to payoff. Real payoff happens when total_due hits, which can be faster or slower than the stated term depending on the merchant's daily volume.
- **Daily holdback** — Pct of merchant's daily card receivables auto-pulled to repay the advance. Stored as `numeric(5,3)` (0.080 = 8%). Bounded 0–50%.
- **Draw / Draw request** — Merchant-initiated partial pull from an approved line. Schema: `draw_requests` (merchant submits) → `draws` (lender approves + funds). The headline self-serve action in the Breeze merchant portal.
- **Available to draw** — `principal - sum(funded_draws)`. Surfaced as the second of the six dashboard metrics.
- **Repayment** — One settled holdback pull (or manual wire / adjustment) credited against an advance. Schema: `repayments` ledger. Source enum: `ach | manual | adjustment | wire`.
- **RTR (Reserve-to-Receive)** — The relationship between what's been repaid and what's still due. Not yet a stored column, but the dashboard derives it from `paid_to_date_cents / total_repayment_due_cents`.
- **ISO** — Independent Sales Organization. Merchant-sourcing partner (broker) that introduces deals to funders. Out of scope for Breeze v1 (a future "broker portal" tab).
- **Syndication** — Splitting an advance across multiple funders. Out of scope for v1 — single-funder per advance.
- **Lender CRM** — David's existing back-office system (vendor unknown at v1). Breeze talks to it via HMAC-signed webhooks: outbound on `draw.approved`, inbound on `advance.funded` / `advance.closed` / `repayment.posted`. Stub mode by default until David shares the spec.
- **Stub mode** — Outbound webhook behavior when `tenants.crm_webhook_url` is empty: payload is written to `webhook_events` (visible in lender admin audit log) but no HTTP call is made. Lets the demo ship before the live integration spec arrives.
- **Breeze brand color** — Default `#1e40af`. Per-tenant override stored in `tenants.brand_primary_color`, injected as `--brand` CSS variable at layout level so the merchant sees the funder's brand, not Breeze's.

## Partner coordination & channel isolation (2026-08-03)

- **APEX / Knut** — **One agent, two names.** "Apex" is the persona; "Knut" is the bot (`@KnutRPEbot`). Both belong to **Adon's agent**. Never treat them as separate peers: `PEER_KEYS` in `scripts/integrations/agent_activity.py` and `coordination_agent.js` both default to `apex,knut`, because a row written under one key while only the other was watched is invisible — a Knut-authored file claim would not have stopped Bravo editing the same file.
- **OASIS partner group** — the shared Telegram group `OASIS 🏝️💸` (`COORD_GROUP_CHAT_ID`, id `-5165125484`): CC + Adon + Bravo + APEX/Knut, reached by `@BravoGCAdon_bot`. Adon is CC's equal partner in OASIS AI Solutions and PropFlow (per CC 2026-08-24), so the group's contents are partner-scoped by definition. It is the **human↔agent** channel; `agent_activity` is the **agent↔agent** channel.
- **Channel isolation** — internal operational traffic (blocked sending numbers, scraper logs, cron failures, tracebacks, daemon crashes) belongs in **CC's private DM** (`TELEGRAM_ALLOWED_USERS`), never the partner group. Enforced in two places by content, not just by lane: `_GROUP_BLOCKED_TERMS_RE` in `scripts/notify.py` (reroutes `group=True` to CC's DM) and in `scripts/integrations/agent_activity.py` (refuses the `--mirror` broadcast; the DB row is still written, so nothing is lost). `coordination_agent.js` applies the same denylist to **automated** posts only.
- **Reply exemption** — a message answering a human who spoke *in the group* is exempt from the isolation filter. Consent is the distinction: an unprompted broadcast is noise; an answer to a question asked in that room is not. Gagging it would break the bridge's purpose.

## V7.5 Guard & Continuity (davidondrej/skills import, 2026-08-03)

Terms from the [davidondrej/skills](https://github.com/davidondrej/skills) audit (MIT — patterns studied, no code copied). Plan: `~/.claude/plans/integrate-davidondrej-skills.md`.

- **Dangerous-command denylist** — The `HARD_BLOCKS` table in `scripts/state/exec_guard.py`: named regexes that block a command outright (exit 2) before it runs. Distinct from the **irreversible-op allowlist** in the same file, which logs and permits. "Blocked" and "logged" are different outcomes; say which one you mean. Contract locked by `scripts/tests/test_exec_guard.py` — every rule needs both a BLOCK case and the adjacent ALLOW case that proves it isn't over-broad.
- **Credential-exfil path** — A route that reveals a secret without reading a guarded *file*, so `secret_guard.py` (which is path-based) never sees it. `gh auth token` was the live example: it reads from gh's own keychain. When adding a tool that can print a credential, the guard that stops it is `exec_guard`, not `secret_guard`.
- **Handoff block** — A single paste-ready fenced block that lets an agent with zero session memory resume the work, emitted by `skills/handoff/`. The **carry**, as opposed to the **archive** (`state_sync.py` → `SESSION_LOG.md`). Both, not either — a handoff that contradicts the archive is worse than neither.
- **Atomic setup step** — One indivisible operator action (a single click, field, or paste-block) handed to CC by `skills/setup-help/`, always followed by the full remaining list. If it contains an "and", it is not atomic.
- **Low-confidence decision surface** — The output of `skills/decisions/`: choices the agent made but is genuinely unsure about, each with a named alternative and the check that would settle it. Covers what tests structurally cannot — tests verify what was written, not what was chosen.

## V7.6 Evidence-Gated Refinement (prime-agent import, 2026-08-07)

Terms from the [PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent) audit
(MIT — formats and mechanics studied, no code copied). Contract:
[[docs/adr/0015-evidence-gated-harness-refinement]]. Plan: `~/.claude/plans/i-m-dropping-you-a-luminous-lighthouse.md`.

- **Refinement** — A single proposed change to the agent's *own* instructions — a memory entry, a skill, a standing rule, or a subagent spec — recorded as a row in the `refinements` table and driven by `scripts/core/refine.py`. Not a code change: refinements edit what the agent is told, not what it runs. A refinement always names one file, one exact anchor, and one evidence command.
- **Evidence command** — The shell command whose **measured value** must change for a refinement to be kept. Supplied as `--evidence-cmd`, executed at propose time and re-executed at apply time; the comparison is on the value, never on a hash of the whole run, because folding in the exit code made an edit that *broke* the command look like a delta. A **keyed** command's exit code is a result, not a failure (`harness_eval --json` exits 1 whenever the harness is imperfect), so what proves a measurement happened is the key being present; an **unkeyed** command must exit 0 after the edit, since its output *is* the value. Exit 124/127 always reject. This is the canonical meaning of "evidence" in the refinement path: a paragraph of reasoning is **not** evidence and cannot be submitted as such. Contrast the upstream, where `evidence` is the proposing model's own rationale and the stored `expectedOutcome` is never run.
- **Volatile evidence** — An evidence command whose output differs between two identical back-to-back runs, usually because of a timestamp or run id (`harness_eval.py --json` is the live example — it stamps a fresh `timestamp` and `run_id` every run). Refused at propose time, because a command that always differs would make every refinement look effective. Fix by narrowing with `--evidence-key <dotted.json.path>`, e.g. `--evidence-key score`.
- **Inverse proposal** — The exact prior text of the edited region, stored **at apply time**, which `refine.py revert` replays to undo a refinement. Stored rather than reconstructed on demand: `.gitignore:44` untracks `memory/PATTERNS.md`, so git is not a rollback path for most refinement targets and the ledger is the only way back. `revert` refuses if the file's hash has moved since.
- **Refinement ledger** — The append-only history of every refinement and its terminal status, held in `state/empire_state.db` and mirrored for CC into `memory/PROPOSED_CHANGES.md`. `REJECTED` means the gate measured no effect and auto-reverted; `WITHDRAWN` means the operator withdrew it. The two are not interchangeable — one is a fact about the change, the other about the operator.
- **Self-edit kind** — Which of four destinations a lesson belongs in: `memory` (a fact to carry forward), `skill` (a routable procedure), `prompt_note` (a standing rule, always operator-gated), `subagent` (a delegation role, always operator-gated). A required argument, so the destination is a recorded decision rather than a default.
- **Auto-apply allowlist** — The only paths `refine.py` may write without CC: `memory/<file>.md` and `skills/<skill>/SKILL.md` at exactly those depths, minus `SESSION_LOG.md`, `PROPOSED_CHANGES.md` and `skills/_archive/*`. An **allowlist**, so a path matching nothing is held rather than applied — the six entry points, `PERSONAL.md`, `brain/**` and `scripts/state/**` can never auto-apply, and a new sensitive directory is protected the day it is created. Matched on the **resolved** path with segment-exact rules, never with a path glob: `fnmatch`'s `*` crosses `/`, so a glob allowlist classified `memory/../CLAUDE.md` as auto-appliable. Locked by `scripts/tests/test_refine.py`.

## Vibe-Security (20-point matrix, 2026-08-15)

Terms for the application-security layer. Contract:
[[docs/adr/0016-20-point-vibe-code-security-standard]]. The matrix itself:
[[skills/security-protocol/SKILL]]. The rule and its incident: [[brain/EXECUTION_RULES]] § 21.

- **20-Point Vibe-Security Matrix** — The twenty defects that recur in AI-generated and vibe-coded applications, each paired with a *mechanical* check (a grep, a query, a command) rather than a judgement call. Lives in exactly one file, `skills/security-protocol/SKILL.md`; every other surface points at it rather than restating the rows. Locked by `scripts/tests/test_20_point_security_contract.py`. Not to be confused with the two other matrices in this repo — see the next entry.
- **Build-time defense vs audit-time point** — The two are different jobs and the distinction is load-bearing. A **defense** is one of the seven in `prompts/_TEMPLATE_SYSTEM_PROMPT.md` § 3.1: what a change must satisfy *while you write it*. A **point** is one of the twenty: what you sweep for in code that *already exists*. Every point maps to at most one defense, but five points (rate limiting, injection, input validation, XSS, dependency hygiene) map to **none** — the defenses were written for building a feature and never covered untrusted input or dependency staleness. Saying "we satisfied the defenses" therefore does not mean "we passed the audit". The seven-row **Anti-Slop Matrix** (`PERSONAL.md` LOCKSTEP `anti_patterns`) is a third thing again: process defects, not security holes.
- **Two-layer public-route gate** — The pair of allowlists a new public-facing route must appear in: `oasis-command-center:middleware.ts` `PUBLIC_PATH_PREFIXES` (does an unauthenticated visitor get past the auth redirect?) and `app/layout.tsx` `FULL_BLEED_PREFIXES` (does the page render edge-to-edge or with the operator sidebar?). A prefix in one and not the other is the canonical asymmetric failure: missing middleware 401s the share link, missing layout leaks operator chrome over a prospect's view. The check is a diff of the two lists, and the proof is incognito against production — never a dev session. Rule: [[brain/EXECUTION_RULES]] § 13.
- **Server-side authorization boundary** — The place a permission decision is actually enforced: a route handler, middleware, an RLS policy, or a DB `CHECK`. Persona text, a hidden button, a disabled input, and a client-side redirect are **not** boundaries — they are documentation of an intent the server has to enforce independently. Distinct from the [[CONTEXT]] **Data bridge** entry, which names one specific implementation of this for browser-querying apps; this term is the general property. Rule: [[brain/EXECUTION_RULES]] § 14; single source in `oasis-command-center:lib/role-gates.ts`.
- **Pre-parse signature verification** — Verifying an inbound webhook's signature against the **raw** request body *before* the payload is parsed, logged, or acted on. The ordering is the whole term: verifying after parsing means untrusted attacker-controlled structure has already reached the application. `stripe.webhooks.constructEvent` for Stripe, a secret token for Telegram, HMAC for generic providers (as the Breeze **Lender CRM** integration already does). Pairs with tenant-scoped dedup on the provider event id (the *tenant-scoped dedup* pattern ([[memory/PATTERNS]])).
- **Decorative control** — A security control that exists in the code and defends nothing: a rate limiter keyed on a value the caller mints fresh each request, a role restriction expressed only in a prompt, a MIME allowlist that still contains SVG. Named because both HIGH findings in the 2026-05-18 public-forms audit were of this shape, and because a decorative control reads as coverage in every review that does not try to defeat it. The test for a control is not "does it exist" but "can I get past it".

---

## Versioning (unified 2026-08-08)

- **`architecture_version`** — The frontmatter field in each agent's `brain/STATE.md`, and the **only** version number the fleet uses. Currently `V9.2.0` in Bravo, Maven and Atlas alike. Before 2026-08-08 four lines ran in parallel — Bravo substrate `V7.6`, Bravo protocol `V9.1`, Maven `V7.16`, Atlas none — and because the higher number named the narrower layer, a bare "V9" read as superseding "V7.6" when it did not. `V8` was never used. If you find a second version number anywhere, it is drift: fix it to read from this field rather than restating a value. Past commit labels (`V7.6.x`, `V9.1`) stay as they are — they are real names in history.
- **Substrate vs protocol** — Two *layers*, one number. **Substrate** is the machinery: state DB, retrieval, guards, capability graph, vocabulary layer, refinement gate. **Protocol** is the instruction layer: agentic playbooks, the Phase-0 contract, the production defenses (`brain/INTENTS.md` still cites "V9.0 Defense #5" and that rule is live). Say which layer you mean; do not give either its own version.

---

## North Star

- **North Star (Bravo)** — Multiply CC's time and ship the systems that scale the empire. Bravo does **not** optimize for a dollar metric. All revenue targets, MRR, and deal economics are owned by **Atlas (CFO-Agent)** — route money questions there.

---

## How to update this file

1. New domain term enters the codebase → add the entry here in the same PR.
2. Existing term's meaning shifts → edit here; do NOT shadow with a new term.
3. Term retired → delete the entry; the search for its removal proves no skill still depends on it.
4. Skills that introduce ≥5 unique terms get their own `skills/<name>/LANGUAGE.md` (per ADR-0002); CONTEXT.md stays empire-wide.

If you're reading this in a fresh session and a term feels under-defined, that's a bug. Fix it.

## Related
- [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]] | [[docs/adr/0002-context-md-canonical-vocabulary]]
