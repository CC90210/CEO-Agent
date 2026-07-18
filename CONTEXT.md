---
name: CONTEXT
description: Canonical vocabulary for the Business-Empire-Agent / Bravo OS. Every skill, agent, and entry-point must use these terms with these meanings. If a new domain term needs to enter the codebase, add it here first.
tags: [vocabulary, canonical, context]
last_updated: 2026-07-17
---

# CONTEXT — Canonical Vocabulary

> Single source of truth for OASIS / PropFlow / empire terminology.
> If you find yourself re-deriving what a term means mid-session, the term either belongs here or its existing entry needs tightening. Update this file; don't re-derive.

Pattern adapted from [mattpocock/skills CONTEXT.md](https://github.com/mattpocock/skills) — but our scope is empire-wide, not skill-local.

---

## People & agents

- **CC** — The operator. Owner of Business-Empire-Agent, OASIS AI Solutions, and 100% of the empire. Adon is a 50/50 partner on PropFlow only.
- **Bravo** — This agent. CC's right hand and second brain — **CEO, COO, and CTO in one** (Maven owns CMO; Atlas owns CFO). "Lead Architect" is the CTO facet, not the whole role. Spans five runtimes (Claude / Gemini / Antigravity / OpenCode / IDE-agnostic); identity is shared, routing differs per-runtime entry point.
- **Maven** — CMO agent at `~/CMO-Agent`. Owns all content, brand voice, ads, social posting. Bravo NEVER writes content; routes to Maven.
- **Atlas** — CFO agent at `~/APPS/CFO-Agent`. Owns tax/compliance, financial advisory, equity research. Pivoted from autonomous trading 2026-04-14; trading code archived under `archive/trading-automation/`.
- **Hermes** — Messaging/inbox agent at `~/APPS/hermes`.
- **Aura** — Branding/design agent.
- **Lex** — Legal/contracts agent at `~/APPS/Lex-Agent` (`CC90210/Lex-Agent`). In-house counsel: drafts/reviews contracts, ranks legal risk in plain English. Product-first + multi-tenant. **Not a licensed attorney — never gives legal advice** (UPL gate in its `brain/COMPLIANCE.md`). Added 2026-06-18.
- **Codex** — OpenAI's executor, integrated as Bravo's dual-AI backend specialist. Delegated to via `codex-companion.mjs` for backend implementation, deep debugging, adversarial review.

## Brands

- **OASIS AI Solutions** — CC's primary B2B brand. AI automation consulting + custom agents for local businesses. Collingwood, ON.
- **PropFlow** — Tenant-screening + landlord-automation product. CC + Adon 50/50. Has its own Supabase project (separate from empire DB). Bucket-list feature: real-estate portal embed.
- **CredPort** — The multi-tenant MCA / business-funding software platform (named 2026-06-15; was working-named "Fundrail"): a merchant-facing portal + funder back-office that many funders run on, each under their own branding. A **separate jointly-owned company** — **60% OASIS AI / 40% David** (equity split). Commercial terms — the monthly engagement fee and the platform-fee split — are owned by **Atlas / CFO**, not tracked here. Has its own Supabase project (trust boundary on merchant financial data). Repo: [CC90210/breeze-portal](https://github.com/CC90210/breeze-portal) (repo name still `breeze-portal`; product brand is CredPort). Platform brand (CredPort) shows on public/landing surfaces; tenant brand (BreezeAdvance etc.) shows inside each funder's portal. MCA domain vocabulary in the "MCA / Lending" section below.
- **BreezeAdvance** — David's **existing MCA funding company** (breezeadvance.com), NOT the platform. It is the **first funder / first tenant** on CredPort. Do not conflate: "BreezeAdvance" = the funder (keeps its own navy/cyan brand inside its portal); "CredPort" = the separate software platform company. Other funders onboard later as additional tenants with their own logos + brand.
- **Nostalgic Requests** — Personal/legacy brand. Lower priority than OASIS and PropFlow.

## Multi-tenancy

- **Tenant** — A customer-facing namespace inside the empire DB. Tenant-scoped data is filtered by `tenant_id`. Examples: OASIS, PropFlow, CC-Funnel.
- **Tenant manifest** — Config object describing a tenant's nav, theme, feature flags. Lives in code under `oasis-command-center:config/tenants/`.
- **Tenant-scoped feature** — A feature that should appear in ONE tenant's nav only (e.g., `/forms` lives in CC-Funnel, NOT in OASIS). Infrastructure features extrapolate across tenants; product features do not. See `feedback_tenant_scoped_nav.md`.
- **Empire DB** — CC's Supabase project. Single source for all empire + client data; tenant_id-scoped. (Turso-per-tenant was deferred 2026-05-15.)

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

## MCA / Lending (Breeze — `~/APPS/breeze-portal`)

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
