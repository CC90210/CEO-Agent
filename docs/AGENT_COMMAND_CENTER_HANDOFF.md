# Agent Command Center — Architecture & Capabilities Handoff

> 📜 **HISTORICAL HANDOFF (2026-05-25 state)** — MRR is Atlas-owned and CRM is inbound-first since 2026-07-09; see `brain/STATE.md` for current.
>
> **2026-05-28 relocation note:** All SunBiz-specific Python scripts (sequence_runner, lender_response_classifier, underwriting_orchestrator, shop_out_sender, renewal_reminder, text_torrent_tool, kixie_tool, migrate_leads_to_tenant_records, the underwriting/ submodules, etc.) and database migrations (042-070 SunBiz CRM lane, plus 045/046/049/055 sequence-state + reconstructor, plus 071-075 stage-model / merchant_summary / funder-catalog set) now live in `~/SunBiz-Agent`, not `~/CEO-Agent`. The bridge daemon scans both repos and dispatches via a `root` field in `_bridge_manifest.json`. Solara/Helios still invoke them via `run_script` with the manifest KEY (e.g. `sequence_runner_once`, `text_torrent_tool_blast`, `lender_response_classifier_loop`). References below to `scripts/<name>.py` for SunBiz tools mean "look in SunBiz-Agent/scripts/" — this doc was authored before the split.
>
> Briefing document for an external AI agent that's evaluating an open-source project and needs to cross-reference what the OASIS Agent Command Center already does. Written 2026-05-25 after a multi-session product expansion for our first real client tenant (Sun Biz Funding).
>
> Operator: CC (CC90210 on GitHub). 100% owner of OASIS AI Solutions. Maintains the Agent Command Center as the multi-tenant operating system for every business he runs and every client he onboards.

---

## TL;DR — What this is

A manifest-driven, multi-tenant operations dashboard with a per-machine local bridge that turns the operator's own machine into the execution layer for sensitive workflows. Built on Next.js 15 + Supabase + a Python daemon swarm running under PM2. AI agents (Bravo / Solara / Helios / Maven / Atlas / Aura / Hermes) are first-class — each tenant manifest declares which agents render in its shell, what tools they can call, and what data model they operate against.

The core insight: **one codebase, N tenants, each fully customized via a JSONB manifest** — brand, sidebar nav, data model, agent bindings, integrations, page primitives. No per-tenant forks. Adding a new client = inserting a row in `tenant_manifests`.

---

## The three repos

| Repo | GitHub remote | Local path | Purpose |
|---|---|---|---|
| **CEO-Agent** | `CC90210/CEO-Agent` | `~/Business-Empire-Agent` | Empire substrate. V6 state DB, retrieval engine, exec/state/secret guards, PM2 ecosystem, event bus, all empire-wide Python scripts. Bravo's home. |
| **oasis-command-center** | `CC90210/oasis-command-center` | `~/APPS/oasis-command-center` | The multi-tenant dashboard. Next.js 15 App Router. Manifest-driven shell, catch-all dispatcher at `/t/[slug]/[...path]`. Every tenant's UI lives here — no per-tenant dashboard repos. |
| **SunBiz-Agent** | `CC90210/SunBiz-Agent` | `~/SunBiz-Agent` | Authoritative storage for SunBiz-specific Python + migrations. Per the 2026-05-15 7d34f2e policy, SunBiz business logic lives canonically here; runtime copies live in CEO-Agent for PM2. Future cleanup will collapse this dual-storage via per-tenant `agent_roots`. |

Two more tenant-specific repos in the same family (not relevant to this handoff but worth knowing exist):
- `CC90210/CMO-Agent` (Maven — CMO agent, content/ads/funnels, multi-client)
- `CC90210/CFO-Agent` (Atlas — CFO agent, autonomous trading + finance)

---

## Tech stack

**Frontend:** Next.js 15 App Router, React 19, TypeScript, Tailwind, Lucide icons. No CSS-in-JS, no chart libraries (sparklines done in raw SVG). State: `useState` / `useEffect` / `useMemo` + URL search params for shareable views.

**Backend:** Supabase (PostgreSQL 15) for everything: auth, data, storage, RLS, edge functions. `getServiceSupabase()` for server-side service-role queries; `lib/supabase-server.ts` for session-aware queries. Per-tenant data isolation via `tenant_id` column on every shared table.

**Python daemons:** ~80 scripts under `scripts/` in CEO-Agent. PM2 ecosystem at `ecosystem.config.js` runs the long-lived ones. Each daemon uses `scripts/lib/secret_loader.py` for env (NEVER raw `os.environ`).

**Bridge layer:** `scripts/bravo_cli/bridge_chat_server.py` runs on the operator's machine at `localhost:9100`. Dashboard discovers it via pairing tokens (`~/.oasis/bridge_token`). Provides `/chat` (warm-pool Claude Code subprocess), `/exec-tool` (browser-mediated tool execution for cloud-mode), `/local-chat` (Ollama / LM Studio passthrough). The bridge is **per-machine** — each operator's machine runs its own. `scripts/bridge_lock.py` arbitrates Telegram routing so two machines never compete for the same bot token.

**AI providers:** Anthropic Claude (Opus 4.7, Sonnet 4.6, Haiku 4.5) as primary. Ollama / LM Studio for local fallback. Gemini 3 Flash for some lead-enrichment workloads. OpenAI Codex via plugin for dual-AI delegation (backend implementation + adversarial code review).

**External integrations live + wired:**
- Twilio (SMS) — multi-tenant via per-tenant credentials in `tenant_records.data`
- TextTorrent (SMS blast) — `scripts/text_torrent_tool.py`
- Gmail (IMAP + SMTP) — `scripts/integrations/google_tool.py` + send_gateway SMTP path
- Stripe — `scripts/stripe_tool.py`
- JotForm webhook receiver (legacy; being replaced by in-dashboard forms)
- Telegram (operator bridge to CC + per-tenant alerting)
- n8n MCP (workflow orchestration)
- Playwright MCP (browser automation)
- Cloak Browser (`~/.cloakbrowser/` C++ stealth Chromium) for bot-protected scrapes
- Firecrawl (multi-format URL → markdown)
- Late (social scheduling for Maven)

---

## Multi-tenant manifest model

This is the load-bearing architectural choice. Read this section twice.

**Source of truth:** `lib/manifest/seeds.ts` declares in-code defaults; `tenant_manifests` Supabase table overrides per tenant. The loader (`lib/manifest/loader.ts`) prefers DB → falls back to seed.

**A manifest is one JSONB document containing:**
```ts
{
  version: 1,
  tenant_slug: "sun",         // routing key for /t/<slug>/*
  brand: { name, logo, subtitle, footer_label, footer_tagline, primary_color },
  agents: [{ slug, display_name, enabled, primary, tool_palette, setup_answers }],
  nav: [{ href, label, icon, group, badge_key, expandable }],
  data_model: [{ name, label, fields: [{ name, type, required, enum_values, default }] }],
  pages: [{ path, label, kind, entity?, config? }],
  integrations: [{ kind, enabled, credential_env_key }],
  reasoning_prompts: [{ agent_slug, label, prompt }],
  settings: { /* per-tenant feature flags, thresholds, defaults */ }
}
```

**The catch-all renderer** at `app/t/[slug]/[...path]/page.tsx` dispatches based on `pages[].kind`. Page kinds shipped:
- `dashboard`, `table`, `kanban`, `form`, `markdown`, `reasoning` (generic)
- `import` (bulk lead import)
- `pipeline` (two-pipeline superview — Lead Pipeline above Opportunity Pipeline, Salesforce-style)
- `pipeline_entity` (single-entity Salesforce chevron rail + filtered table)
- `shopping_out` (SunBiz multi-lender outreach)
- `offers_v2` (deal-first offer intelligence — accordion + kanban toggle)
- `lenders_v2` (lender directory with expanded fields)
- `renewals_v2` (funded-deals-backed renewal urgency view)
- `settings` (tenant-scoped settings with preview-mode gating)
- `automations` (tenant-scoped cron + bridge status)
- `daily_plan` (new 2026-05-25 — today's priority queue)
- `cold_outreach` (new 2026-05-25 — cold-list blast composer)
- `underwriting` (new 2026-05-25 — bank statement upload + agent run)

**Preview mode:** every tenant-scoped surface honors a hard rule — if the signed-in operator doesn't own the requested tenant, `resolveDataTenant()` returns null, all components mount in "preview" (chrome visible, no fetches fire, empty scaffold). Prevents cross-tenant data leakage when the operator is browsing a client's view.

---

## Tenant: OASIS AI Solutions (CC's home)

**Slug:** `oasis`. CC's own business — an AI agency that sells custom AI agents to small/mid businesses. Manifest seed at `lib/manifest/seeds.ts` `OASIS_SEED`.

**Lead lifecycle stages** (11 stages, per migration 047 + 062): `new_contact → outreach → discovery → qualified → proposal → negotiation → onboarding → active_client → churned / lost / archived`.

**Agent bindings:** Bravo (lead architect, primary), Atlas (CFO), Maven (CMO), Aura (voice/sensory ops).

**Key surfaces:**
- Lead pipeline with AI scoring + AI next-action suggestions
- Proposal lifecycle (draft / sent / viewed / signed / declined / expired)
- Tasks board for the agent C-suite
- Reasoning tab — operator clicks an action → fires straight to Telegram → Bravo replies in chat

**North Star:** $10,000 USD Net MRR by 2026-09-30 ($5K achieved 2026-06-20 — BreezeAdvance deal). Tracked in `brain/STATE.md`.

---

## Tenant: Sun Biz Funding (first real client — MCA funding shop)

**Slug:** `sun` (manifest) / `submissions` (actual tenants.slug). Manifest seed at `lib/manifest/seeds.ts` `SUN_SEED`.

**Operator:** Ezra at Submissions@sunbizfunding.com. Team includes Jordan, Ethan, Emily.

**Industry:** Merchant Cash Advance funding — they intake leads, qualify, send to multiple lenders simultaneously ("shop out"), aggregate offers, present to the merchant, close funding deals, then re-engage at renewal windows.

**Agent bindings:** Solara (operational — admin ops), Helios (sales — cold outreach). Both are tenant-renamed instances of Bravo's persona pattern.

**Lead pipeline stages (per migration 064, fixed 066 + 067):** `imported → hot_lead → cold → outreach → contacted → viewed_application → signed_application → submitted → declined`.

**Application pipeline statuses (post-064):** `application_in → shopping → docs_out → login → follow_ups → funded → dead_file → declined`. Migration 067 fixed 10 stuck records that 064 silently failed to remap.

**Surfaces (current state after the 2026-05-25 second-meeting build):**

| Group | Tab | Status |
|---|---|---|
| Operations | Dashboard | ✅ Live |
| Operations | Agents (chat with Solara / Helios) | ✅ Live |
| Operations | Reasoning | ✅ Live |
| Operations | Playbook | ✅ Live |
| Operations | **Daily Plan** | 🆕 UI live, backing API routes shipping this session, daemon (`daily_plan_generator.py`) ready |
| Pipeline | Leads | ✅ Live |
| Pipeline | Shopping Out | ✅ Live with severity-tier warnings + Proceed Anyway override |
| Pipeline | Applications | ✅ Live |
| Pipeline | **Underwriting** | 🆕 UI live, backing API + daemon (`underwriting_orchestrator.py`) ready |
| Outreach | **Cold Outreach** | 🆕 UI live, backing API + daemon (`cold_outreach_runner.py`) ready |
| Deals | Offers Board | ✅ Live (accordion + kanban toggle) |
| Deals | Renewals | ✅ Live with progress bars + urgency sort |
| Deals | Commissions | ✅ Live |
| Deals | Lenders | ✅ Live with expanded field set |
| System | Import | ✅ Live with cold/warm split (new) |
| System | Forms | ✅ Live with 3-template grouping (new) |
| System | Sequences | ✅ Live (drip campaigns) |
| System | Team | ✅ Live |
| System | Automations | ✅ Live (Option A — tenant-scoped) |
| System | Settings | ✅ Live (Option A — tenant-scoped) |

**Shopping Out flow** (the funding-shop core workflow):
1. Operator picks application from list (filter by `SHOPPABLE_STATUSES`)
2. Lender recommender ranks all lenders by match score (`lib/lenders/match-fitness.ts`) + applies historical bias from `lender_feedback` table
3. Each lender gets a 1-3 sentence plain-English narrative ("Strong fit — revenue clears $30k floor, FICO 720, MCA match. 2d SLA.")
4. Severity-tier warnings flag mismatches (info / warning / high_risk). NOT hard blocks — operator can Proceed Anyway with a required override note. Override persists to `shop_out_warnings` audit table.
5. Operator selects lenders + attachments (bank statements from `lead_documents`)
6. Submit creates `application_lender_threads` rows at status='pending'
7. Bridge daemon `scripts/shop_out_sender.py` polls pending threads, fires SMTP via `send_gateway` (empire chokepoint with CASL + cooldown + daily-cap enforcement). Substitutes `{{owner_phone}}` placeholder from the rep's snapshot on the thread row.
8. `scripts/lender_response_classifier.py` polls Gmail labels every 5min, classifies inbound responses (approved / declined / info_requested / no_response), updates thread status, persists `lender_feedback` tuple for future recommender bias.

**Underwriting flow** (new, 2026-05-25):
1. Operator uploads bank statements (PDFs) via Underwriting tab → `lead_documents` with `doc_type='bank_statements_3mo'`
2. Operator clicks "Run underwriting" → creates `application_underwriting` row at status='pending'
3. Bridge daemon `scripts/underwriting_orchestrator.py` claims pending rows atomically (30s tick), runs:
   - `scripts/underwriting/statement_parser.py` — PDF → Anthropic vision → extracts deposits, NSF, loan payments, identifies known funding companies from a DB-backed registry
   - `scripts/underwriting/debt_detector.py` — cross-statement aggregation: monthly debt service, D/R ratio, lender count
   - `scripts/underwriting/sales_angle.py` — Claude-generated positioning copy for sales rep handoff
4. Computes metrics + risk flags + readiness score (0-100). Writes everything back to the row at status='complete'.
5. Dashboard surfaces metrics + risk flags + sales angle + "Push to Lender Recommender" button.

**Cold Outreach flow** (new, 2026-05-25):
1. Operator imports cold list via Import tab → `cold_lead_lists` + `cold_leads` (NOT warm pipeline)
2. Operator opens Cold Outreach tab → picks list, channel (Twilio SMS / TextTorrent SMS / email blast), composes template with `{{first_name}}` / `{{business_name}}` variables, sets daily cap
3. Submit creates `cold_outreach_campaigns` at status='queued' + `cold_outreach_recipients` rows
4. Daemon `scripts/cold_outreach_runner.py` (30s tick) drains pending recipients through `send_gateway` (same CASL + cooldown chokepoint)
5. Live tracker shows delivery counts, drill-down per recipient

**Daily Plan flow** (new, 2026-05-25):
1. Daemon `scripts/daily_plan_generator.py` runs daily 6am ET
2. Generates `daily_plan_items` rows across 6 categories: `priority_call`, `missing_info`, `stuck`, `new_offer`, `shop_today`, `renewal_eligible`
3. Operator opens Daily Plan tab → sees 6-pane today's queue + SOP checklist
4. Click row → drilldown via `?application=` or `?lead=` URL params → opens `LeadDetailDrawer` over the page
5. Dismiss / Done buttons update row status

---

## V6 substrate (CEO-Agent)

These are empire-wide primitives, not tenant-specific. The Agent Command Center inherits them.

**State DB** — SQLite/WAL at `state/empire_state.db`. Single source of truth for: heartbeats, session_log, active_task. Single-writer proxy: `scripts/state/state_manager.py`. Mode gated by `EMPIRE_V6_MODE` env (off/shadow/on). Markdown mirrors auto-regenerate.

**Retrieval engine** — `scripts/core/memory_retriever.py`. FTS5 lexical (BM25) + LanceDB cosine (fastembed ONNX MiniLM-L6-v2, 384-dim) fused via Reciprocal Rank Fusion. Indexes `memory/`, `skills/`, `brain/` files into 2700+ chunks. Queryable in <100ms with file:line citations. Used by the `UserPromptSubmit` hook to inject CONTEXT.md definitions automatically.

**Guards** (PreToolUse hooks in `.claude/settings.local.json`):
- `secret_guard.py` — blocks Read on `.env*`, `*.pem`, `*.key`, `credentials.json`. Blocks Bash that would `cat`/`grep` them.
- `exec_guard.py` — AST/regex policy gate on every Bash invocation. Blocks `DROP TABLE`, `TRUNCATE`, `DELETE FROM` without WHERE, `ALTER … DROP COLUMN`, `rm -rf /` outside tmp, `git push --force` to main, etc.
- `state_guard.py` — blocks edits on auto-generated state files between AUTO-GENERATED-BEGIN/END markers.

Each guard has three modes (report / enforce / off) controllable per-env. All audit-log to `state/<guard>.log`.

**Event bus** — Postgres `agent_events` with LISTEN/NOTIFY + `claim_events()` (FOR UPDATE SKIP LOCKED) for atomic dequeue. Producers: state_manager, send_gateway, bridge_chat_server. Consumers: `event_router.py` (cursor-based on-host tail → `state/event_router.log` → dashboard `/feed` page).

**Capability graph** — `brain/CAPABILITY_GRAPH.json`. Auto-discovered registry of every skill, script, agent, MCP server, workflow. Built by `scripts/build_capability_graph.py`. Resolved at runtime by `scripts/capability_query.py resolve "<intent>"`.

**CONTEXT.md** — empire vocabulary glossary (Pipeline, Tenant, Lead, Skill, etc.). Auto-injected into prompts that mention glossary terms. See `CONTEXT.md` in repo root.

**Agentic OS layer (V6.7+)** — five-layer architecture: Pantry (raw sources) → Prep Table (deterministic Python pre-aggregations in `scripts/snapshots/`) → Plate (consumer views like `skills/ceo-briefing`). Hooks become orchestration: `SessionStart` (state + inbox + staleness check), `PreCompact` (re-inject SOUL + ACTIVE_TASKS), `UserPromptSubmit` (tiered T1/T2/T3 retrieval).

---

## Schema highlights (Supabase)

Migrations live in `database/*.sql` (CEO-Agent + SunBiz-Agent mirror for SunBiz-specific). Numbered sequentially. Applied via `scripts/apply_migration.py`.

**Multi-tenancy primitives:**
- `tenants` — registry, slug + custom_fields JSONB
- `tenant_manifests` — per-tenant JSONB manifest (overrides in-code seed)
- `tenant_records` — wide-row JSONB store (`entity_type` discriminator: lead, application, lender, offer, funded_deal, etc.). One table for all tenant CRM data; queries filter by tenant_id + entity_type.
- `tenant_audit_log` — every CRUD action (before/after JSONB)
- `tenant_cron_jobs` — per-tenant scheduled jobs (executed by the bridge's cron poller)

**Forms + sequences:**
- `tenant_forms` — form definitions (slug, fields JSONB, multi-step)
- `form_submissions` — per-step submissions with file_attachments
- `form_views` — telemetry
- `drip_sequences` + `sequence_state` — drip campaign machine (cancel on form submission per the new hook)

**Lender shopout:**
- `application_lender_threads` — one thread per (application, lender) shop-out. Status: pending/sending/sent/replied/offer_received/declined/error. Carries body_template, attachments JSONB, send_interaction_id, owner_phone snapshot, warnings_acknowledged JSONB.

**SunBiz second-meeting expansion (migration 069, 14 new tables):**
- `application_underwriting` — automatic UW run output + metrics
- `follow_up_tasks` — Follow-Up Machine queue
- `daily_plan_items` — today's priority queue
- `cold_lead_lists` + `cold_leads` — cold-list storage (NOT warm pipeline)
- `cold_outreach_campaigns` + `cold_outreach_recipients` — multi-channel blast
- `shop_out_warnings` — severity + override-note audit log
- `known_funding_companies` — MCA registry (18 seeded — Forward Financing, OnDeck, Velocity, Kapitus, etc.)
- `offer_sources` — offer attribution (email_scan / portal_extract / manual)
- `email_thread_monitors` — email-scanner cursor state per tenant
- `lender_feedback` — intelligence learning tuples (lender, deal_profile, outcome)
- `personalized_form_links` — token-backed per-lead form links with view/submit telemetry
- `agent_memory_notes` — tenant/lead-scoped operator notes

**Key column on existing table (migration 069 ALTER):**
- `application_lender_threads.owner_phone` — assigned rep phone snapshot, substituted into `{{owner_phone}}` template placeholders
- `application_lender_threads.warnings_acknowledged` — per-thread snapshot of overrides

---

## Agent bindings

Agents are first-class manifest entries. Per the contract in `lib/manifest/schema.ts`:

```ts
type ManifestAgentBinding = {
  slug: string;               // "bravo" | "solara" | custom
  display_name: string;       // tenant-customizable rename
  enabled: boolean;
  primary?: boolean;          // drives sidebar "live" indicator
  model_override?: string;    // e.g. force Opus
  prompt_overlay?: string;    // tenant-specific system-prompt overlay
  tool_palette?: string[];    // allowlist of tools (subset of TOOL_DEFINITIONS)
  setup_answers?: object;     // operator's per-agent questionnaire answers
};
```

**Per-agent tool palette** is the security model: Solara (back-office) gets `list_records`, `update_record`, `send_email` — not `send_sms`. Helios (sales) gets `send_sms`, `send_email`, `score_lead`. Operator picks the palette in Settings → Agents.

**Per-agent setup answers** (Phase J of giggly-reef): operator answers a one-time questionnaire ("FICO floor?", "Quiet hours start?", "TCPA opt-in language?") that folds into the agent's system prompt as a "TENANT SETUP" overlay via `lib/agent-personas.ts`. Agent knows the operator's specifics from turn 1 without manual prompt-overlay editing.

**Tool execution paths:**
- Bridge mode (operator's machine online): agent calls bridge tools via `localhost:9100/exec-tool`. Used for: bash, browser automation, file ops, anything sensitive.
- Cloud mode (no bridge): cloud-only tools via `lib/cloud-tool-runner.ts`. Used for: Supabase reads/writes, send_gateway sends, lookup endpoints.

---

## Browser-tool ladder (mandatory routing for any URL fetch)

This is a hard rule: every URL-fetch decision goes through this ladder. `python scripts/research_fetch.py <url>` auto-escalates and remembers per-domain in `state/site_reputation.db`.

1. **Firecrawl** (`scripts/firecrawl_tool.py`) — default. Handles HTML, JS-rendered, search, batch.
2. **CloakBrowser** (`scripts/cloak_browser_tool.py`) — mandatory tier-2 stealth. C++ source-level fingerprint patches. Beats Cloudflare, DataDome, reCAPTCHA, FingerprintJS, Akamai, Kasada. Drop-in Playwright replacement.
3. **Browser Harness** (`scripts/browser/browser_harness_doctor.py`) — for CC-authenticated workflows (his real Chrome session against logged-in surfaces).
4. **Playwright MCP** — generic interactive flow for unprotected sites only.

NEVER use raw Playwright against bot-protected sites — gets blocked in 1-3 requests.

---

## Skills system

Pattern: `skills/<skill-name>/SKILL.md`. Frontmatter declares `name`, `description`, `triggers`, `tier`, optionally `disable_model_invocation`, `argument_hint`, `requires` (env vars / daemons / state files).

**148 active skills** registered in the capability graph. Examples:
- `outreach-send` — canonical cold/follow-up email path
- `hyperthink` — 7-phase deep reasoning protocol (disable_model_invocation: only fires on `/hyperthink`)
- `silver-platter` — per-agent data-readiness audit
- `integrations-sync` — idempotent refresh patterns
- `memory-journaling` — structured DECISIONS/PATTERNS/MISTAKES logging
- `codex-delegation` — dual-AI handoff
- `meeting-automation` — discovery call templates + structured note extraction
- `research-fetch` — the browser-ladder router

Skills are discoverable via `scripts/capability_query.py resolve "<intent>"` (returns top-N matching by trigger overlap).

---

## Distribution model

The Command Center is designed to be **forkable per client**. Two distribution mechanisms:

1. **Manifest seeding** — drop a row in `tenant_manifests`, the dashboard immediately renders that client's branded shell with their data model + nav + agents. No deploy.

2. **`skills/agent-runtime-packaging`** — packages the Bravo-shaped agent runtime for client self-hosting. Client gets a forked version of CEO-Agent with their tenant's secrets, their own Supabase project optionally, their own bridge daemon. Production example: SunBiz-Agent.

3. **`.claude-plugin/plugin.json`** — distribution manifest for the `npx skills@latest add` consumption path. 47 universally-useful skills listed; excludes Bravo-internal + staging + archived.

---

## Recent build — 2026-05-25 sessions

**Session 1 (Jordan/Oasis 2026-05-23 → 25):** SunBiz product meeting Phase 1-12 — sidebar IA, lead/app stage slimdown, Shopping Out page, Offers v2, Lenders v2, Renewals enhancement, migration 064.

**Session 2 (post-deploy fixes, 2026-05-25 morning):** Cross-tenant isolation hardening — AgentsModulesStatusBoard slug-gating, CronJobsManager agent-keys-driven (was hardcoded empire defaults), DescribeAutomationFlow `agent_key`-driven, layout brand+primaryAgent resolution gates, Sidebar/SidebarShell defaults, FormPublicClient footer, ComingSoon component move + 9 imports, 8 shared route bullets, reasoning EmptyState, Option A pattern for Settings + Automations, Codex P2 owned-vs-preview distinction, Shopping Out drawer auto-pop, Underwriting + Renewal Reminder Planned modules added to AgentsModulesStatusBoard.

**Session 3 (this handoff's session — 2026-05-25 evening):** SunBiz second product meeting expansion. Massive scope:
- 3 new dashboard tabs: Daily Plan, Cold Outreach, Underwriting
- 5 new bridge daemons: `renewal_reminder.py`, `follow_up_generator.py`, `cold_outreach_runner.py`, `daily_plan_generator.py`, `underwriting_orchestrator.py`
- 4 surgical edits to existing daemons: `shop_out_sender.py` (owner_phone substitution), `sequence_runner.py` (form-submission hook cancels drips), `lender_response_classifier.py` (lender_feedback persistence), `statement_parser.py` (DB-backed funding company registry)
- Migration 069: 14 new tables + 18 seed rows
- Shopping Out severity-tier warnings (info / warning / high_risk) replacing the prior hard-block model. Proceed Anyway override with required note → `shop_out_warnings` audit table
- Lender narrative generation (`lib/lenders/match-narrative.ts`) — 1-3 sentence plain-English ranking explanation per lender
- Lender feedback bias (`lib/lenders/feedback-bias.ts`) — adjusts scores based on historical (lender × industry × revenue) outcomes
- 3 forms re-templated: Initial Lead Capture, Full Application, Bank Statement Upload
- Import page split: cold/warm distinction (cold leads stored in `cold_lead_lists` + `cold_leads`, NOT warm pipeline); promote-to-warm is explicit operator action
- BankTab enhanced with underwriting status badge + sparklines + re-run button + link to full Underwriting tab
- Three-repo synchronization: all SunBiz scripts now mirrored to SunBiz-Agent per the 7d34f2e (2026-05-15) authoritative-storage policy
- Playbook 08 § Section 10 codifies the "what lives where" matrix + 4-step mirror ritual + verification command

---

## Known gaps (honest punch list as of 2026-05-25 evening)

Things shipped this session but not yet operationally complete:

1. **Migration 069 NOT yet applied to Supabase** — awaiting CC's go-ahead. Idempotent; will run in <30s. Until applied, new tabs render empty / API routes return 500 on the new tables.

2. **10 new API routes** — Daily Plan (2), Cold Outreach (4), Underwriting (3), plus already-shipped cold-lists routes from the Import split. Shipping THIS SESSION via parallel writer agents (3 agents in flight as this document was written).

3. **Cron seeds for the 4 new daemons** — `renewal_reminder_once`, `follow_up_generator_once`, `cold_outreach_runner_loop`, `daily_plan_generator_once` registered in `_bridge_manifest.json` (the bridge's discoverable script registry), but the `tenant_cron_jobs` rows aren't yet seeded for SunBiz. Each needs a daily cron expression + the tenant operator's blessing on the schedule before going live (don't want a 9am Telegram blast nobody approved).

4. **Codex independent audit** — rate-limited (`6:53 PM` cutoff). Rule 8 requires Codex review on big tasks. Re-run after cutoff: `node ~/.claude/codex-plugin/scripts/codex-companion.mjs review --wait`.

5. **VPS deployment** — runbook exists at `SunBiz-Agent/docs/VPS_BRINGUP.md`. NOT yet executed against a real VPS. Playbook 08 § Section 9 has the daemon inventory + migration order + smoke-test steps.

6. **Doctor coverage gap** — `SunBiz-Agent/scripts/doctor.py` checks SunBiz-Agent env keys but not the CEO-Agent daemon keys (`BRAVO_SUPABASE_URL`, `BRAVO_FIELD_ENCRYPTION_KEY`). Documented in VPS_BRINGUP.md.

7. **Tenant CSS theming** — `manifest.brand.primary_color` exists in the schema but isn't wired into a CSS-variable swap in the layout. Per-tenant accent colors render the same gold across all tenants today.

8. **AI editor for manifests (Phase 2)** — the dashboard reads manifests but doesn't let operators EDIT them via AI chat yet. The schema (`MANIFEST_SCHEMA_VERSION = 1`) is ready; the function-calling tool surface needs wiring.

---

## Open-source projects worth cross-referencing

If you're evaluating an open-source project that's already done some of this, the most useful comparison axes:

1. **Multi-tenant manifest model** — Does it have a per-tenant JSONB customization layer that controls brand + nav + data model + agents + integrations? Or does it require per-tenant forks? Ours is single-codebase, manifest-driven.

2. **Bridge-side execution** — Does it have a per-operator local daemon for sensitive workflows (bank statements, customer data, real Chrome sessions)? Or is everything cloud-side? Ours is hybrid: dashboard reads/writes via Supabase, daemons run on operator's machine via PM2 with pairing tokens.

3. **Severity-tier vs hard-block recommenders** — How does it handle "this option is risky but the operator can override"? Ours: severity tiers + Proceed Anyway with override note + persistent audit log.

4. **Cold/warm pipeline separation** — Does it conflate import-to-pipeline with imported-cold-leads? Ours: cold lists are intentionally separate from warm pipeline; promotion is explicit.

5. **Drip cancellation on conversion** — When a lead does the thing the drip was nagging them to do (submits the form), does the drip stop? Ours: form-submission event → `sequence_runner.py` cancels in-flight steps + logs the transition.

6. **Per-agent tool palette** — Can the operator restrict what tools each AI agent has access to per-tenant? Ours: yes, declared in manifest.agents[].tool_palette.

7. **CASL + cooldown + daily-cap chokepoint** — Is every outbound (SMS, email, blast) routed through a single chokepoint that enforces compliance + rate limits? Ours: `scripts/integrations/send_gateway.py` is the canonical chokepoint; daemons call into it, never bypass.

8. **Idempotent migration pattern** — Are schema migrations re-runnable on prod? Ours: all wrapped in `DO $$ ... END $$` or use `IF NOT EXISTS` / `DROP CONSTRAINT IF EXISTS THEN ADD CONSTRAINT`. Documented per-file in playbook 08 § Section 9.

9. **Manifest preview-mode gating** — When an operator browses a client's tenant view, does any client data leak? Ours: `resolveDataTenant()` returns null for non-owners; every tenant component bails to empty scaffold; no fetches fire.

10. **Schema for the funding-shop vertical specifically** — Migration 069's 14 tables cover the MCA / funding-shop business model end-to-end. If the open-source project is also funding-vertical, that's the most direct comparison surface.

---

## Key files for the cross-referencing AI to read first

If you have limited context budget, read these in this order:

1. `lib/manifest/schema.ts` — the manifest type system
2. `lib/manifest/seeds.ts` — OASIS_SEED + SUN_SEED examples (declarative tenant definitions)
3. `app/t/[slug]/[...path]/page.tsx` — the catch-all dispatcher (one file, ~900 lines, dispatches all 17 page kinds)
4. `lib/lenders/match-fitness.ts` + `lib/lenders/match-narrative.ts` + `lib/lenders/feedback-bias.ts` + `lib/lenders/shop-out.ts` — the lender recommendation engine
5. `components/shopping-out/ShoppingOutClient.tsx` — the funding-shop core workflow UI
6. `database/069_sunbiz_meeting2_expansion.sql` — the most recent schema, shows the MCA-funding data model
7. `scripts/shop_out_sender.py` + `scripts/underwriting_orchestrator.py` + `scripts/lender_response_classifier.py` — the funding-shop daemon trio
8. `scripts/integrations/send_gateway.py` — the universal outbound chokepoint
9. `ecosystem.config.js` (CEO-Agent) — PM2 daemon inventory
10. `content/playbooks/08-sunbiz-production-pre-flight.md` — production operations runbook including the three-repo matrix

---

## Repo health snapshot (2026-05-25)

| Metric | CEO-Agent | oasis-command-center | SunBiz-Agent |
|---|---|---|---|
| Lines of code | ~120k (Python heavy) | ~85k (TS) | ~25k (mirror) |
| Active scripts | 80 | — | 13 (mirror subset) |
| Active skills | 148 | — | — |
| Active migrations | 69 | — | 12 (mirror subset) |
| Active page kinds | — | 17 | — |
| Active components | — | ~240 | — |
| Active API routes | — | ~120 | — |
| PM2 daemons | 8 (Windows-default) | — | — |
| Latest commit | `5f...3` (state sync) | `bb8b60e` (playbook §10) | `7862e36` (mirror) |

---

## Contact + decision authority

**Operator:** CC (CC90210). Sole decision-maker. North star: $10K USD Net MRR by 2026-09-30 ($5K achieved 2026-06-20). Communication is Telegram + in-dashboard chat.

**External AI working on the new repo:** This handoff document is for you. If you need to reach the human operator with a question, surface it as text — the agent reading this doc will route it to CC. Don't assume you can make architecture decisions independently — propose, get a yes, then build.

**Update cadence for this document:** Re-write at the end of any session that changes the manifest schema, adds a tenant, adds a page kind, or ships a substrate migration (V6.x bump). Last updated: 2026-05-25 evening.
