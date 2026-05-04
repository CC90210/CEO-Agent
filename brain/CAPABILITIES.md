---
tags: [capabilities, tools]
---

# CAPABILITIES — Tool & Integration Registry

> Complete inventory of what Bravo can do. Last updated: 2026-05-01 (V6.1).
> **Totals (live disk truth, 2026-05-01 V6.1): 153 skills · 36 workflows · 93 scripts · 21 agents (14 file-based in `agents/` + 7 native Claude Code in `.claude/agents/`) · 9 MCP servers + Codex (external). V6.1 adds the scaffolding mechanism (operator.profile.json + personalize.py + scaffold.py) — repo now ships as a true scaffold for new operators.**
>
> Marketing/social scripts (`late_tool.py`, `late_publisher.py`, `instagram_engine.py`, `codex_image_gen.py`) transferred to Maven on 2026-04-26 — they live at `../CMO-Agent/scripts/` now. Bravo subprocesses to Maven's `late_tool.py` only for read-only CEO-dashboard stats (see `ceo_dashboard.py:_content_this_week`).
>
> These counts are reported live by `python scripts/self_audit.py`. If
> they drift, the audit will flag it. Trust the live numbers, not any
> integer hardcoded in a satellite doc.
>
> **📦 For the shareable GitHub repo catalog (CC's "tool shed" for clients/prospects): see [[brain/TOOL_SHED]]**

## MCP Servers (By Interface)

### Claude Code (Opus 4.6 — Lead Architect)
| Server | Purpose | Key Tools |
|--------|---------|-----------|
| **Playwright** | Browser automation, ALL web research, scraping, testing | navigate, snapshot, click, type, evaluate |
| **Context7** | Live library documentation lookup | resolve-library-id, query-docs |
| **Memory** | Persistent knowledge graph across sessions | create_entities, search_nodes, open_nodes |
| **Sequential Thinking** | Structured multi-step reasoning | sequentialthinking |
| **Knowledge Graph** | Obsidian vault as graph — PageRank, communities, semantic search, path-finding | kg_search, kg_node, kg_central, kg_bridges, kg_paths, kg_communities, kg_index |

### OpenCode (big-pickle — Bravo, same identity)
- **Identity:** Full **Bravo** — CC's Lead Architect. Same persona, voice, capabilities as Claude-powered Bravo.
- **Access:** Full read/write to all 151 skills in `skills/`, all 68 Python CLI tools in `scripts/`, all brain/ and memory/ files, all subagent definitions.
- **Entry Point:** `AGENTS.md` (shared with Codex/Cursor/Windsurf). Identity routing at lines 13-15.
- **MCP Servers:** Same 9 servers as Claude Code (Playwright, Context7, Memory, Sequential Thinking, GitHub, Firecrawl, Obsidian, Filesystem, Knowledge Graph) when available via OpenCode.
- **Tool routing:** Same CLI-first rules — `scripts/send_gateway.py`, `scripts/supabase_tool.py`, `scripts/stripe_tool.py`, `scripts/google_tool.py`, `scripts/n8n_tool.py`.

### Anti-Gravity IDE (Native Local Agent — Multi-Model)

Models: Gemini 3.1 Pro High/Low, Gemini 3 Flash, Claude Sonnet/Opus 4.6, GPT-OSS 120B Medium
Entry Point: `ANTIGRAVITY.md` | Config: `.vscode/mcp.json`
Workflows: `.agents/workflows/` (33 workflows: post, status, health, prime, content, commit, n8n, sync, research, debug, client-onboard, cli-anything, skool-edit, skool-push, evolve, briefing, client-health-report, generate-proposal, strategic-review, competitive-report, qbr, onboard-team-member, meeting-prep, investor-update, knowledge-maintenance, review, ship, retro, create-prd, opencli, ingest, query-knowledge, lint-knowledge)

| Server | Purpose | Config |
|--------|---------|--------|
| **Playwright** | Browser automation, web research | npx @playwright/mcp --headless |
| **Context7** | Live library documentation | npx @upstash/context7-mcp |
| **Memory** | Persistent knowledge graph | npx @modelcontextprotocol/server-memory |
| **Sequential Thinking** | Multi-step reasoning | npx @modelcontextprotocol/server-sequential-thinking |
| **Knowledge Graph** | Vault graph — PageRank, communities, semantic search | npx tsx C:\Users\User\tools\knowledge-graph\src\mcp\index.ts |

**SDK INTEGRATIONS (Universal — replaces broken MCPs):**
| **Supabase** | Database CRUD, queries, RPC | `python scripts/supabase_tool.py select <table> --project bravo --limit 10` |
| **Stripe** | Balance, customers, products, invoices, subscriptions, payment links | `python scripts/stripe_tool.py balance` |

**Supabase tool commands:** `list-projects`, `list-tables`, `select`, `insert`, `update`, `delete`, `upsert`, `rpc`, `query`
**Stripe tool commands:** `balance`, `customers`, `products`, `prices`, `invoices`, `subscriptions`, `charges`, `payment-links`, `create-payment-link`, `create-customer`, `create-invoice`, `refund`, `events`
**Projects (Supabase):** `--project bravo` (default), `--project oasis`, `--project nostalgic`

### Gemini CLI (Diagnostic & Inference — 4th Tier)
- Tool: `@google/gemini-cli`
- Entry Point: `GEMINI.md`
- Purpose: Fast diagnostics, file system cleanup, automated audits, heartbeat monitoring, fallback execution
- Interface: `gemini` command (global npm)
- MCP Access (via `.gemini/settings.json`): Playwright, Context7, Memory, Sequential Thinking (4 active servers)
- CLI Tools: `python scripts/supabase_tool.py`, `python scripts/stripe_tool.py`, `python scripts/n8n_tool.py`, `python ../CMO-Agent/scripts/late_tool.py` (Maven)
- Note: Config synced with `.vscode/mcp.json`. Credential-dependent services use CLI tools — not MCP.

## Supabase Projects

| Project | Region | Purpose |
|---------|--------|---------|
| **Bravo** | us-west-2 | Agent intelligence (14 tables) + business ops (14 tables) = 28 tables |
| **nostalgic-requests** | us-west-2 | Nostalgic Requests platform |
| **oasis-ai-platform** | us-west-2 | OASIS AI platform |

**Organizations:** CC (oktipozhyojufxsytrse), oasis-ai-platform (sajanpiqysuwviucycjh)

## App Registry (12 External Repos)

Full routing table with local paths, GitHub URLs, tech stacks: `brain/APP_REGISTRY.md`

| App | Local Path | Stack | CLAUDE.md |
|-----|-----------|-------|-----------|
| OASIS AI Platform | `APPS/oasis-ai-platform` | React 18, Vite, Supabase | Yes |
| PropFlow | `realestate-App` | Next.js 14, Supabase, Stripe | Yes |
| Nostalgic Requests | `APPS/nostalgic-requests` | Next.js 16, Supabase, Stripe Connect | Yes |
| Grape Vine Cottage | `APPS/Grape-Vine-Cottage` | Vite, React 18 | No |
| Mindset Companion | `APPS/MINDSET COMPANION APP/cc-mindset` | Next.js 16, React 19 | No |
| On The Hill | `APPS/ON-THE-HILL-WEBSITE` | Vite, React 19 | No |
| Atlas (CFO) | `APPS/CFO-Agent` | Python 3.11+, CCXT, Claude API | Yes |
| TIKTIK | `APPS/tiktik` | Next.js 14, Supabase, Tailwind | Yes |
| CC Funnel | `APPS/cc-funnel` | Next.js 14, Supabase, Tailwind | Yes |
| Shopify Ad Engine | `APPS/shopify-ad-engine` | Remotion 4, React 19, Three.js | Yes |
| Lafreniere PM | `APPS/lafreniere-pm` | Next.js 16, Supabase, Stripe | Yes |
| AURA | `AURA` | Claude Code agent, ESP32, Home Assistant | No |

## Sub-Agents (17 incl. Codex)

See `brain/AGENTS.md` for the complete registry with orchestration decision matrix, permission levels, and scope restrictions. Codex (Agent #17) runs as an external AI executor for backend-heavy tasks — see `skills/codex-delegation/SKILL.md`.

## Agent Teams (Experimental — enabled 2026-04-06)

Claude Code native parallel subagents. Enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `~/.claude/settings.json`. Windows uses `teammateMode: "in-process"`.

**Subagent definitions** live in `.claude/agents/` — read by Claude Code natively at spawn time:

| Agent | Model | Purpose |
|-------|-------|---------|
| `security-reviewer` | sonnet | Auth flaws, RLS gaps, credential exposure, OWASP top 10 |
| `researcher` | sonnet | Multi-source research, docs, competitive analysis |
| `code-reviewer` | sonnet | Two-pass structural + adversarial code review |
| `content-writer` | opus | Platform content in CC's authentic voice |
| `debugger` | sonnet | Root-cause debugging, 5 Whys, bisect regressions |
| `architect` | opus | System design, DB schema, API contracts |

**Spawn via natural language** — no slash command needed:
> "Spawn a teammate using the security-reviewer agent to audit the auth flow while I implement the new endpoint."

**Skill:** `skills/agent-teams/SKILL.md` — when to use, communication patterns, Windows limitations, anti-patterns.

## V6.0 Multi-Provider Routing & DL Stack (2026-05-01)

V6.0 ships the multi-provider model router, autonomous skill synthesis, 3-layer memory consolidation, multi-platform messaging gateway, and a deep-learning skeleton stack. Every script below is `--help` clean and `--json` capable.

| Script | Purpose | Example |
|--------|---------|---------|
| `model_router.py` | Multi-provider LLM routing (Claude, OpenAI, OpenRouter, Groq, DeepSeek, local). Reads `brain/MODEL_CONFIG.md`. | `python scripts/model_router.py list-providers --json` |
| `skill_synthesizer.py` | Extracts successful patterns from `agent_decisions`, generates SKILL.md, validates, registers. | `python scripts/skill_synthesizer.py synthesize --decision-id <id>` |
| `skill_metrics.py` | Tracks per-skill `metrics.json`. Promotes `[NEW]` → `[VALIDATED]` after 3 successful uses. | `python scripts/skill_metrics.py report --json` |
| `memory_consolidation.py` | 3-layer memory: `WORKING.md` → `memories_episodic` / `memories_semantic`. Nightly cron. | `python scripts/memory_consolidation.py status --json` |
| `gnn_skill_router.py` | Graph neural net over Obsidian vault. Predicts next-skill-to-load from task embedding. | `python scripts/gnn_skill_router.py predict --task "draft outreach"` |
| `rlhf_outreach.py` | RLHF/DPO skeleton trained on `lead_interactions` approve/reject signals. | `python scripts/rlhf_outreach.py build-dataset` |
| `neural_memory.py` | Neural Turing Machine with content + location addressing. Differentiable memory layer. | `python scripts/neural_memory.py read --query "..."` |
| `maml_onboard.py` | Model-agnostic meta-learning for rapid client onboarding (<10 examples → adapted policy). | `python scripts/maml_onboard.py adapt --client-id X` |
| `tft_forecast.py` | Temporal Fusion Transformer over Stripe + n8n + sentiment for MRR forecast P10/P50/P90. | `python scripts/tft_forecast.py forecast --horizon 30` |
| `neuro_symbolic_gate.py` | Datalog-style compliance rules (CASL, cooldown, caps, DNS) layered over draft critic. | `python scripts/neuro_symbolic_gate.py rules --json` |
| `gateway_admin.py` | Admin CLI for the multi-platform gateway (Telegram + Discord + Slack adapters). | `python scripts/gateway_admin.py status --json` |
| `setup_wizard.py` | Interactive client onboarding — collects credentials, validates, writes env, smoke-tests. | `python scripts/setup_wizard.py` |
| `personalize.py` | Renders `brain/USER.md` + memory templates from `brain/operator.profile.json`. Idempotent. **V6.1** | `python scripts/personalize.py apply --json` |
| `scaffold.py` | Token-replaces operator identifiers across the codebase at fork-time. Refuses to run on the original operator's repo by design. **V6.1** | `python scripts/scaffold.py --apply --backup` |
| `system_cleanup.py` | Find + delete redundant install clones, pip/npm caches, old `tmp/` files, `__pycache__` trees, scaffold backups. Active repo preserved by safety guard. **V6.1.1** | `python scripts/system_cleanup.py --apply` |

**Config:** `brain/MODEL_CONFIG.md` (per-agent provider/model + fallbacks).
**Operator profile:** `brain/operator.profile.json` (gitignored — schema in `operator.profile.example.json`). Single source of truth for identity/brand/voice.
**Container skill:** `skills/auto-generated/SKILL.md` (parent for runtime-synthesized skills).
**Working memory:** `memory/WORKING.md` (cleared nightly by consolidation).
**Gateway entry:** `gateway/index.js` (HTTP control on `localhost:7773`).
**Public install:** `install.sh` / `install.ps1` (one-line install for non-technical clients).
**Fork mechanism (V6.1):** wizard → `personalize.py apply --force` → (if new operator) `scaffold.py --apply --backup` → `bravo doctor`. Turns a fresh clone into the new operator's personal agent.

## CLI-Anything (Universal CLI Generation)

Generate agent-native CLI wrappers for any software, API, or service. When MCPs break, CLIs still work.

- **Skill:** `skills/cli-anything/SKILL.md` — 7-phase pipeline (analyze → design → implement → test → package → integrate)
- **Workflow:** `.agents/workflows/cli-anything.md` — `/cli-anything <target>` trigger
- **Templates:** `scripts/cli_templates/` — reusable Python components (ReplSkin, Backend, setup.py)
- **Existing CLIs:** `supabase_tool.py`, `stripe_tool.py` (already follow this pattern)
- **Based on:** [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology

## OpenCLI (Website-to-CLI Automation)

Transform any website into structured CLI commands via browser automation. Complements cli-anything (local software) by wrapping **websites** using browser sessions.

- **Install:** `npm install -g @jackwener/opencli` (v1.1.1 installed globally)
- **Skill:** `skills/opencli/SKILL.md` — exploration, synthesis, adapter creation
- **Workflow:** `.agents/workflows/opencli.md` — `/opencli <url-or-command>` trigger
- **Based on:** [jackwener/opencli](https://github.com/jackwener/opencli)
- **50+ prebuilt adapters:** Twitter, YouTube, Discord, LinkedIn, Reddit, HackerNews, Medium, GitHub, and more
- **Key commands:** `opencli list` (discover), `opencli explore <url>` (API discovery), `opencli synthesize` (generate adapters)
- **Auth:** Cookie-based (reuse browser login), header-based (tokens), public API
- **Plugin system:** `opencli plugin install github:user/repo` — extend without code changes
- **Relationship:** cli-anything wraps local software → OpenCLI wraps websites. Use Playwright MCP for one-off browsing, OpenCLI for repeatable web commands.

## Computer Control — Unified Dispatcher (V6.2)

`scripts/computer_control.py` is the single entry point for full-machine automation. It picks the right backend based on platform + intent, so agents don't need to know whether to call macos_control, windows_control, Playwright, Browser Harness, Hermes A2000, or Anthropic Computer Use.

**Backends it routes to (no replacement, just dispatch):**

| Intent | Backend | Why |
|---|---|---|
| `cc.open("Chrome")` / `cc.click(x,y)` / `cc.type(...)` | `scripts/macos_control.py` (mac) or `scripts/windows_control.py` (windows) | Native desktop primitives — 60+ commands each |
| `cc.click_text("Submit")` (vision-driven, no coordinates) | Anthropic Computer Use Tool API | LLM sees screen, picks coordinates |
| `cc.browser.scrape(url)` | Playwright MCP | Stateless, ephemeral, no login |
| `cc.browser.do_as_me(intent)` | Browser Harness via CDP :9222 | YOUR logged-in Chrome with persistent session |
| `cc.desktop_erp.run_recipe(...)` | Hermes `adapters/a2000_desktop.py` | pywinauto + JSON recipe for legacy Windows ERPs (A2000) |

**CLI:** `python scripts/computer_control.py info` — shows which backends are available on this machine. Then `open / click / click-text / type / keystroke / screenshot / scroll / window {list,focus,frontmost} / browser {scrape,do-as-me}`.

### Playwright vs Browser Harness — they are complementary, not duplicates

This is a common point of confusion. They serve **different jobs**:

- **Playwright (MCP)** — stateless, ephemeral browser. New context per call, no login persistence. Best for: scraping public pages, signup-flow testing as anonymous user, headless CI checks. Spins up fresh Chromium/Firefox/WebKit on demand.
- **Browser Harness** — attaches to your **actual logged-in Chrome** via CDP port 9222. Persistent cookies, real session, your real LinkedIn/Skool/primary retainer-platform login. Best for: running tasks AS YOU while you sleep (DM replies, community posts, member-list pulls). Houses `browser/domain-skills/` — recorded recipes for sites you actually use.

**Rule of thumb:** if the task could be done by anyone (scrape, test, fetch) → Playwright. If the task has to be done as you (logged in, your account, your reputation) → Browser Harness. The dispatcher in `computer_control.py browser` exposes this choice via `scrape` vs `do-as-me`.

## Browser Harness (Direct Browser Control + Domain Skills)

Browser Harness is installed as Bravo's direct Chrome/Edge control layer. It complements Playwright MCP, Firecrawl, and OpenCLI by attaching to a real logged-in browser and turning site-specific discoveries into durable domain skills.

- **Stable checkout:** `C:\Users\User\APPS\browser-harness`
- **Executable:** `C:\Users\User\.local\bin\browser-harness.exe`
- **Global Codex skill:** `C:\Users\User\.codex\skills\browser-harness`
- **Bravo skill:** `skills/browser-harness/SKILL.md`
- **Runtime packaging skill:** `skills/agent-runtime-packaging/SKILL.md`
- **Diagnostics:** `python scripts/browser_harness_doctor.py`
- **Direct attach helper:** `python scripts/browser_connect.py` — connect to the running CDP browser (headless-aware)
- **Onboarding doctor:** `python scripts/onboarding_diagnostics.py`
- **Workflow:** `.agents/workflows/browser-harness.md`
- **Domain skills:** `browser/domain-skills/`
- **Interaction skills:** `browser/interaction-skills/`

**Current Windows note:** upstream Browser Harness assumed Unix sockets. The editable checkout has a local Windows compatibility patch that falls back to localhost TCP when `socket.AF_UNIX` is unavailable. Chrome/Edge still needs one-time remote-debugging profile approval before attach works.

**Safety:** Browser Harness may inspect and draft, but any real send/publish/delete/billing/finance/admin/production action requires explicit CC approval. Outbound communication still goes through `scripts/send_gateway.py`.

## MCP Replacement CLI Tools (5 — replaces broken credential MCPs)

| Tool | Script | Replaces MCP | Key Commands |
|------|--------|-------------|-------------|
| **Zernio (Late)** | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | Late MCP (env var broken) | `accounts`, `profiles`, `posts`, `create`, `cross-post`, `publish`, `failed` |
| **n8n (read/exec)** | `scripts/n8n_tool.py` | Always-works fallback | `list`, `search`, `get`, `execute`, `activate`, `deactivate`, `executions`, `stats` |
| **n8n (build/modify)** | n8n-mcp SDK flow | — | `get_sdk_reference`, `search_nodes`, `get_node_types`, `validate_workflow`, `create_workflow_from_code`, `update_workflow`, `archive_workflow`. Build canonical path — see `skills/n8n-mcp-integration` |
| **Supabase** | `scripts/supabase_tool.py` | Supabase MCP (token expired) | `list-projects`, `list-tables`, `select`, `insert`, `update`, `delete`, `query` |
| **Stripe** | `scripts/stripe_tool.py` | Stripe MCP (v0.3.1 proxy mode) | `balance`, `customers`, `products`, `invoices`, `subscriptions`, `charges` |
| **Firecrawl** | `scripts/firecrawl_tool.py` | Firecrawl MCP (fallback) | `scrape`, `crawl`, `search`, `extract`, `map` |
| **Browser Harness Doctor** | `scripts/browser_harness_doctor.py` | Browser Harness install/attach diagnostics | `[--json] [--strict]` |
| **Browser Connect** | `scripts/browser_connect.py` | Attach to the running CDP browser and run scripted actions | `[--url URL] [--eval SNIPPET]` |
| **Onboarding Diagnostics** | `scripts/onboarding_diagnostics.py` | Productized setup readiness check | `[--json]` |

## V6.0 Scaffolds (2026-04-22 — not yet active; migrations 014/015 not applied)

> V6.0 is scaffolded but NOT activated. `docs/V6_ARCHITECTURE.md` is the design doc. Activation gated on CC sign-off on the 4 open questions.

| Component | Path | Purpose | CLI |
|-----------|------|---------|-----|
| **Event Bus** | `scripts/event_bus.py` | Postgres LISTEN/NOTIFY pub/sub replacing pulse JSON | `publish`, `stats`, `reap`, `drain`, `tail` |
| **Memory Chunker** | `scripts/memory_chunker.py` | Markdown → RAG chunks with wiki-link provenance | `<path> [--stats] [--json]` |
| **Memory Ingest** | `scripts/memory_ingest.py` | Chunk + embed + upsert to `memory_chunks` | `[--dry-run] [--only FILE] [--force-reembed]` |
| **Memory Query** | `scripts/memory_query.py` | Hybrid RAG retrieval (vector + trigram + freshness) | `--task "..." [--k N] [--format markdown\|json]` |
| **PII Scrubber** | `scripts/pii_scrubber.py` | Regex + optional Presidio PII redaction with reversible table | `scrub`, `unscrub`, `audit` |
| **DNS Reputation Doctor** | `scripts/dns_reputation.py` | Check SPF/DKIM/DMARC presence for a sender domain (invoked by `send_gateway.py doctor`) | `--domain oasisai.work` |
| **Webhook Listener** | `scripts/webhook_listener.py` | FastAPI endpoint for Stripe (sig-verified) / N8N (token) / Telegram updates → event bus | `uvicorn webhook_listener:app` |
| **V6 Migration 014** | `database/014_v6_pgvector_memory.sql` | pgvector + `memory_chunks` + `search_memory_chunks` RPC | `python scripts/apply_migration.py database/014_v6_pgvector_memory.sql` |
| **V6 Migration 015** | `database/015_v6_event_bus_extensions.sql` | LISTEN/NOTIFY trigger + `claim_events`/`ack_event`/`fail_event` RPCs | `python scripts/apply_migration.py database/015_v6_event_bus_extensions.sql` |
| **Docker stack** | `infra/Dockerfile` + `infra/docker-compose.yml` | 5-service containerized daemon set for headless VPS | `docker compose -f infra/docker-compose.yml up -d` |
| **Caddy reverse proxy** | `infra/Caddyfile` | TLS + webhook routing | loaded by Caddy container |
| **VPS deploy workflow** | `.github/workflows/deploy-vps.yml` | CD on push to main | auto |
| **Infra runbook** | `infra/README.md` | VPS hardening + deploy + rollback playbook | — |

**Pattern:** Stateless MCPs (Playwright, Context7, Memory, Sequential Thinking) work fine. Credential MCPs break. CLI tools read `.env.agents` directly — never break.

**Note:** Most CLI tools accept `--json` as a global flag BEFORE the subcommand: `python scripts/tool.py --json subcommand`. Exceptions that accept it AFTER: stripe_tool.py, n8n_tool.py, firecrawl_tool.py, revenue_engine.py, ceo_dashboard.py.

**Firecrawl vs Playwright:** Use Firecrawl for data extraction (markdown, structured schemas, site maps, search). Use Playwright for interactive automation (login, forms, clicks). See `skills/web-scraping/SKILL.md` for the full decision guide.

## Business Operations Engines (8 CLI tools — zero paid services)

| Engine | Script | Purpose | Key Commands |
|--------|--------|---------|-------------|
| **Lead CRM** | `scripts/lead_engine.py` | Full pipeline management, scoring, interactions | `list`, `add`, `view`, `update`, `score`, `interact`, `followups`, `pipeline`, `search`, `funnel` |
| **Email** | `scripts/email_engine.py` | Free Gmail SMTP sending, templates, nurture sequences. Cold outreach uses `send-template` (Gate 1b refuses raw text-only OASIS commercial sends). | `send`, `send-template`, `templates list/create`, `sequence list/create/run`, `log`, `stats` |
| **Region Inference** | `scripts/region_inference.py` | Lead → regional phrase ("the Toronto area" / "the Collingwood area" / "Central Ontario"). Auto-injected into outreach templates as `{{region}}` for geo-rapport. | `python scripts/region_inference.py '{"company":"X","phone":"..."}'` |
| **Template Wiring** | `scripts/wire_all_templates.py` | Canonical OASIS template sync + verification. Enforces website link + Google Calendar CTA in `email_templates`. | `--verify-only --json` / `--dry-run` |
| **Outreach send (canonical SOP)** | [skills/outreach-send/SKILL.md](../skills/outreach-send/SKILL.md) | One-command cold/follow-up email path for all AIs (Claude Code, OpenCode, Codex, Gemini, Antigravity). Auto geo-rapport. | See skill doc. |
| **Outreach eligibility filter** | `scripts/outreach_eligible.py` | Picks leads ready to email. Encodes 3-day → 1-week → 2-week cadence + auto-dormant after 3 unanswered touches. | `--limit 20`, `--mark-dormant`, `--json` |
| **Lead scrape (preferred)** | `scripts/scrape_firecrawl_leads.py` | Firecrawl-based search + structured extract. Pulls owner first name + email + phone from business websites. Inserts to Supabase. | `--target 50 --cities "X,Y" --niches "A,B"` |
| **Booking** | `scripts/booking_engine.py` | Self-hosted Cal.com replacement, slot management | `slots open/open-week/list/close`, `book`, `cancel`, `available`, `remind`, `complete` |
| **Content** | `../CMO-Agent/scripts/content_engine.py` | Content calendar, templates, multi-platform posting | `calendar`, `create`, `create-multi`, `templates list/create/render`, `due`, `week-plan`, `stats` |
| **Revenue** | `scripts/revenue_engine.py` | MRR tracking, Stripe sync, forecasting | `mrr`, `dashboard`, `sync-stripe`, `log-revenue`, `history`, `forecast`, `clients`, `goal` |
| **Competitive Intel** | `scripts/competitive_intel.py` | Competitor profiles, battlecards, landscape reports | `add`, `list`, `view`, `update`, `battlecard`, `report`, `matrix`, `delete` |
| **Financial Model** | `scripts/financial_model.py` | Unit economics, scenario modeling, concentration risk | `unit-economics`, `forecast`, `scenario`, `concentration`, `runway` |
| **Cron** | `scripts/cron_engine.py` + `scripts/cron_dispatcher.py` | Automated job registry plus allowlisted script-backed execution for Atlas/Maven jobs | `cron_engine.py list/add/toggle/due/seed`; `cron_dispatcher.py due --execute`, `run <job_id>` |

All engines: `--json` flag for agent consumption, credentials from `.env.agents`, Supabase backend.

## Semantic Memory (1 CLI tool — added 2026-04-06)

Auto-deduplicating semantic memory layer backed by local Qdrant (pgvector upgrade path available).
Complements markdown memory: markdown handles structured state, mem0 handles fuzzy fact retrieval.

| Tool | Script | Purpose | Key Commands |
|------|--------|---------|-------------|
| **Semantic Memory** | `scripts/mem0_tool.py` | Semantic search, auto-dedup, cross-session context injection | `add`, `search`, `list`, `get`, `delete`, `history`, `stats` |

**Stack:** mem0ai 1.0.10, fastembed (thenlper/gte-large, 1024-dim, local ONNX), Claude Haiku (extraction), Qdrant (embedded, local)
**Storage:** `data/mem0_qdrant/` (persisted, no server required)
**Skill:** `skills/semantic-memory/SKILL.md` — when to use vs markdown memory, upgrade path to Supabase pgvector

## System Maintenance Tools (3 CLI tools — added 2026-03-31, inspired by Claude Code internals)

Patterns extracted from Claude Code's internal harness architecture (1,902 TS files, 35 subsystems). These implement the same context management, cost tracking, and memory aging patterns that Claude Code uses internally.

| Tool | Script | Purpose | Key Commands |
|------|--------|---------|-------------|
| **Context Manager** | `scripts/context_manager.py` | Tiered loading, transcript compaction, deferred init health | `tier "<query>"`, `compact [--dry-run]`, `status`, `health` |
| **Cost Tracker** | `scripts/cost_tracker.py` | Per-operation cost tracking (label:units), budget alerts | `log --label X --units N`, `summary [--period today]`, `budget --check`, `session` |
| **Memory Aging** | `scripts/memory_aging.py` | Confidence decay, stale fact detection, memory health grading | `scan`, `stale [--days 30]`, `health`, `archive [--dry-run]` |

**Config:** `.agents/config.toml` sections `[context]`, `[cost_tracking]`, `[memory_aging]`
**Skill:** `skills/context-optimization/SKILL.md` — full reference for all 5 patterns

## Google Workspace (1 CLI tool — 7 services, 30+ commands)

Full Google ecosystem via `scripts/google_tool.py`. Auth: GWS CLI keyring (auto-refreshes). All commands support `--json`.

| Service | Commands | Scope |
|---------|----------|-------|
| **Calendar** | `calendar list`, `calendar create`, `calendar delete` | Read/write events, Meet links, attendees |
| **Gmail** | `gmail send`, `gmail list`, `gmail read` | Send/read/manage email (SMTP fallback) |
| **Drive** | `drive list`, `drive upload`, `drive download`, `drive delete`, `drive info`, `drive share` | Files, folders, permissions |
| **Docs** | `docs create [--html file]`, `docs read`, `docs append`, `docs export [--format pdf/docx/txt/html]` | Create from HTML, read, export |
| **Sheets** | `sheets create`, `sheets read`, `sheets write`, `sheets append`, `sheets info` | Spreadsheets, ranges, row ops |
| **Slides** | `slides create`, `slides read`, `slides export [--format pdf/pptx]` | Presentations, export |
| **Tasks** | `tasks list`, `tasks add`, `tasks complete` | Task lists, create/complete tasks |

**Not yet authorized (need `gws auth login --scopes ...`):** Meet API (meeting management), YouTube Data API, People/Contacts, Forms, Chat, Keep, Classroom.

### Markdown → Google Doc Export

`scripts/md_to_gdoc.py` — thin wrapper that converts any `brain/*.md` (or any markdown file) to a styled Google Doc. Strips YAML frontmatter, renders tables/code/blockquotes with inline CSS, calls `google_tool.py docs create`.

| Command | Effect |
|---------|--------|
| `python scripts/md_to_gdoc.py brain/TOOL_SHED.md` | Creates Doc titled from first H1 |
| `python scripts/md_to_gdoc.py brain/X.md --title "Custom Title"` | Custom title |
| `python scripts/md_to_gdoc.py brain/X.md --folder <drive-id>` | Place in specific Drive folder |
| `python scripts/md_to_gdoc.py brain/X.md --json` | Agent-readable `{id, name, url}` |

Use when CC asks for a shareable version of any brain/ or memory/ doc. Docs are private by default — use `google_tool.py drive share` to share with specific emails.

## NotebookLM (1 CLI tool — deep research RAG)

On-site RAG for source-grounded chat, podcast generation, and multi-format content. Auth: browser session (`~/.notebooklm/storage_state.json`).

| Tool | Script | Key Commands |
|------|--------|-------------|
| **NotebookLM** | `scripts/notebooklm_tool.py` | `list`, `create --title "..."`, `use <id>`, `ask "..."`, `summary` |
| | | `source add <url/file>`, `source add-research <query>`, `source list` |
| | | `generate audio/video/report/quiz/flashcards/slide-deck [--wait]` |
| | | `download audio/video/report <path>` |

**Auth status:** Session expired — CC needs to run `notebooklm login` once in terminal.
**Skill:** `skills/notebooklm/SKILL.md` — workflows, pipelines, strategic patterns.

## Bravo Memory + Intelligence Tools (added 2026-04-04)

| Tool | Script | Purpose | Key Commands |
|------|--------|---------|-------------|
| **Codex Image Gen** | `../CMO-Agent/scripts/codex_image_gen.py` (owned by Maven) | AI image generation via Codex (no extra API keys) | `generate "<prompt>" --style branded`, `styles` |
| **autoDream** | `scripts/auto_dream.py` | Memory consolidation: Orient → Gather → Consolidate → Prune | `run [--dry-run]`, `status` |
| **Memory Index** | `scripts/memory_index.py` | 3-layer memory architecture (index → topics → archives) | `build`, `search "<query>"`, `stats` |
| **Codex Health** | `scripts/codex_health.py` | Full Codex integration health check (grade A-F) | `[--json]` |

**Content pipeline moved to Maven** — see section above. When CC says "make this a post," route to `C:\Users\User\CMO-Agent`.

## CEO Operating System (5 CLI tools — added 2026-03-28)

These scripts power the CEO dashboard, client health tracking, proposals, and business intelligence layer. All support `--json` and read from `.env.agents`.

| Tool | Script | Purpose | Key Commands |
|------|--------|---------|-------------|
| **Client Health** | `scripts/client_health.py` | Health scoring (0-100), churn prediction, NPS tracking | `report`, `score <client>`, `alerts`, `trends` |
| **Proposal Generator** | `scripts/proposal_generator.py` | Proposal/SOW/NDA generation from templates | `generate`, `list-templates`, `preview`, `export` |
| **CEO Dashboard** | `scripts/ceo_dashboard.py` | Unified KPI aggregator across all business data | `briefing`, `revenue`, `pipeline`, `full` |

The following were added to the Business Operations Engines table above (already present):

- `scripts/competitive_intel.py` — Competitor CRUD + battlecard generation + landscape matrix
- `scripts/financial_model.py` — CAC/LTV/payback, SaaS metrics, cohort analysis, cash flow scenarios

**Data infrastructure (added 2026-03-28):**
- `data/competitors.json` — Persistent competitor intelligence store
- `data/market_research/` — Market research archive
- `data/templates/` — Reusable proposal/SOW/NDA template library
- `proposals/` — Generated proposals output directory

**Skills backing this system (12 new — `skills/*/SKILL.md`):**

| Skill | Purpose |
|-------|---------|
| `client-success` | Health scoring (0-100), churn prediction, retention playbooks, NPS, expansion |
| `proposal-generation` | Proposal/SOW/NDA generation, pricing matrices, follow-up cadence |
| `strategic-planning` | OKR framework, scenario planning (bull/base/bear), QBR template, weekly CEO review |
| `competitive-intelligence` | Competitor tracking, battlecards, monitoring cadence, response playbooks |
| `financial-modeling` | Unit economics (CAC/LTV/payback), SaaS metrics, cohort analysis, cash flow forecasting |
| `team-management` | Hiring framework, contractor onboarding, 1:1s, performance reviews, RACI delegation |
| `meeting-automation` | Pre-meeting briefs, post-meeting protocol, follow-up cadence, calendar intelligence |
| `project-management` | Project definition, phase gates, milestone tracking, scope management, multi-project dashboard |
| `ceo-dashboard` | 5 North Star metrics, revenue/pipeline/ops/content/health dashboards, weekly digest |
| `investor-communications` | Monthly updates, pitch deck structure, advisory board, valuation, partnerships |
| `knowledge-management` | PARA framework, capture protocols, progressive summarization, template library |
| `scaling-playbook` | Revenue-based scaling triggers, first hire framework, service productization, pricing evolution |

## Platform Automation Engines (Browser-Based)

| Engine | Script | Purpose | Key Commands |
|--------|--------|---------|-------------|
| **Skool Community** | `scripts/skool_engine.py` | Autonomous Skool community manager — post replies, DM welcome, member engagement | `daemon`, `run-cycle`, `scan-posts`, `scan-dms`, `engage-members` |
| **Instagram** | `../CMO-Agent/scripts/instagram_engine.py` (owned by Maven) | Instagram DM auto-reply, content scheduling, engagement | `daemon`, `check-dms`, `auto-reply`, `post` |
| ~~LinkedIn~~ | _(removed 2026-04-25)_ | LinkedIn outreach automation was removed by design. CC drafts LinkedIn messages by hand. For LinkedIn profile **research only**, use Browser Harness under CC's logged-in session. | n/a |

## Lead Generation & Outreach Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `../CMO-Agent/scripts/content_repurposer.py` | Transform content across platforms via Claude API | Active |
| `scripts/funnel_sync.py` | Sync funnels to GoHighLevel | Active |
| `scripts/funnel_nurture.py` | Nurture sequence automation | Active |

## Utility Scripts

| Script | Purpose |
|--------|---------|
| `scripts/browse_and_capture.py` | Browser screenshot + capture |
| `../CMO-Agent/scripts/content_generator.py` | Claude API content generation |
| `scripts/generate_covers.py` | Cover art / image generation |
| `scripts/macos_control.py` | macOS system automation |
| `scripts/music_control.py` | Audio/music control |
| `scripts/outreach_engine.py` | Outreach campaign automation |
| `../CMO-Agent/scripts/render_video.py` | Remotion video rendering |
| `scripts/skool_watchdog.py` | Skool community monitoring daemon |
| `scripts/transcribe.py` | Whisper audio transcription |

## Notification & Scheduling

| Script | Purpose |
|--------|---------|
| `scripts/notify.py` | Cross-platform notifications (Telegram) with category filtering |
| `scripts/scheduler.py` | Task scheduling system |
| `../CMO-Agent/scripts/late_publisher.py` (owned by Maven) | Late API publishing wrapper |

## Agent Entry Points (V5.6 — 2026-04-20)

Four entry files at the repo root — one per AI tooling surface. Every agent that opens this repo wakes up with the same identity via the shared `brain/` and `memory/` directories. Edit one, sync the others (Rule 4).

| File | Read by | Role of the agent |
|---|---|---|
| [CLAUDE.md](../CLAUDE.md) | Claude Code CLI | Bravo — Lead Architect, business ops, memory writes |
| [GEMINI.md](../GEMINI.md) | Gemini CLI | Fast diagnostics, heartbeat, fallback execution |
| [ANTIGRAVITY.md](../ANTIGRAVITY.md) | Antigravity IDE (VS Code native) | Infantry / Architect hybrid, primary IDE agent |
| [AGENTS.md](../AGENTS.md) | **Codex CLI + Codex IDE extension, Cursor, Windsurf** | **Backend executor in the dual-AI pattern** |

## Outbound Communication Architecture (V5.6 — 2026-04-20)

**All autonomous sends route through `scripts/send_gateway.py`.** Direct `smtplib` calls from business engines are a regression and must be reverted in review.

| Layer | File | Role |
|---|---|---|
| Gateway | `scripts/send_gateway.py` | Single chokepoint. CASL + cooldown + daily cap + multi-brand + logging. 17 tests green. |
| Context | `scripts/context_builder.py` | `get_entity_context()` — relationship stage, sentiment, prior interactions. Input for persona-aware LLM drafts. |
| Migrations | `scripts/apply_migration.py` | Applies `database/*.sql` via Supabase Management API. |
| Supabase Mgmt API | `scripts/supabase_admin.py` | Shared client for Supabase Management API (auth provider config, etc.). Handles Cloudflare-friendly UA. CLI: `python scripts/supabase_admin.py get /v1/projects/<ref>/config/auth` · `enable-google-oauth --project-ref X --client-id Y --client-secret Z`. |
| Cloudflare DNS | `scripts/cloudflare_admin.py` | Shared client for Cloudflare DNS. CLI: `list-zone --domain X` · `upsert-txt --domain X --name _vercel --value Y` · `sync-vercel-txt --domain X --vercel-project Y` (recovers a Vercel domain that needs new TXT verification). Built after the 2026-04-30 oasisai.work outage. |
| Ledger | `lead_interactions` table (+ migration 003: `cooldown_until`, `agent_source`, `metadata`) | Unified cross-engine action log. |
| CASL | `scripts/casl_compliance.py` | Suppression + footer + RFC 2369/8058 headers. Composed by the gateway. |
| Templates | `scripts/wire_all_templates.py` | Keeps OASIS Welcome / Value Add / CTA congruent across sessions. Verifies `https://oasisai.work` + `https://calendar.app.google/tpfvJYBGircnGu8G8`. |

Rewired engines (all route through gateway): `outreach_engine`, `outreach_batch`, `email_engine`, `funnel_nurture`, `booking_engine`. See [[skills/send-gateway/SKILL]] for complete contract.

## Agent Governance Scripts (V5.6+)

Scripts that enforce Bravo's coherence, autonomy, and self-correction. Run in-process or on cron. All accept `--json` for agent-readable output.

| Script | Purpose | Usage |
|---|---|---|
| `scripts/self_audit.py` | **Self-diagnostic health check.** Scans brain/, memory/, skills/, agents/, scripts/ for orphans, broken wiring, undocumented scripts, MCP config drift. Emits 0-100 health score. | `python scripts/self_audit.py` (human) or `--json` |
| `scripts/draft_critic.py` | Adversarial second-opinion reviewer. Runs on every Claude-drafted outbound before `send_gateway`. Answers the 2026-04-19 "dumb outreach" complaint. | Called by gateway hook, also `--review <draft>` |
| `scripts/inbound_classifier.py` | The inbound chokepoint companion to `send_gateway`. Classifies every inbound email/DM into unified `lead_interactions` ledger so no engine re-contacts a replied lead. | Called by engines; `--classify <payload>` |
| `scripts/autonomous_agent.py` | The always-on reasoning loop. Wakes on schedule or Telegram poke, consults pulse files, picks highest-leverage action, executes, logs. | `python scripts/autonomous_agent.py --once` or daemon mode |
| `scripts/state_sync.py` | Canonicalizes session state at end of every session. **NON-NEGOTIABLE** per Rule 4. | `python scripts/state_sync.py --note "<1-sentence summary>"` |
| `scripts/register_skill.py` | Runtime skill catalog: create/register/sync-all all `SKILL.md` folders into Supabase `skills_registry`, synthesize triggers/tier/owner/risk/source hashes, route a plain-English task to the right skills, and audit drift. | `python scripts/register_skill.py sync-all --deactivate-missing --json` · `python scripts/register_skill.py route "<task>" --json` · `python scripts/register_skill.py audit --json` |
| `scripts/build_maven_env.py` | One-time setup: seeds Maven's `.env.agents` from Bravo's shared infra credentials. | Run once per Maven bootstrap |
| `scripts/agent_heartbeat.py` | Write heartbeat to `agent_state_snapshot` so Command Center detects live agents within 15 min. | `python scripts/agent_heartbeat.py --agent bravo` |
| `scripts/crm_reset.py` | Archive cold/dead leads from bravo Supabase CRM. CC directive: remove noise, keep warm leads only. | `python scripts/crm_reset.py --dry-run` |
| `scripts/deploy_command_center.py` | One-shot production deploy for OASIS AI Agent Command Center. Sets real User-Agent for Supabase Management API. | `python scripts/deploy_command_center.py` |
| `scripts/integration_health.py` | Bump `integrations_health` row from any background worker. Supports Command Center Settings → Integrations page. | `python scripts/integration_health.py --integration stripe --status ok` |
| `scripts/fleet_health.py` | Cross-agent health rollup: pulse freshness (Bravo/Atlas/Maven), inbox unread per agent, cron job state, bridge lock status, memory staleness summary. | `python scripts/fleet_health.py`, `--json`, `--agent <name>` |
| `scripts/cron_dispatcher.py` | Executes allowlisted script-backed cron jobs from the shared registry (Atlas pulse publish, Maven token check, Maven backlog audit) and writes run status back to Supabase. | `python scripts/cron_dispatcher.py due --execute`, `run <job_id>`, `--dry-run` |
| `scripts/pulse_publish.py` | Atomic, schema-validated writer for Bravo's ceo_pulse.json. Only blessed path to update the file (direct edits forbidden per AGENT_ORCHESTRATION.md). | `python scripts/pulse_publish.py refresh --net-mrr <X> --priority "<...>"`, `validate`, `status` |
| `scripts/n8n_webhook_secret.py` | Manage shared secrets for OASIS Command Center inbound webhook (n8n workflow 1cGIN32alM8sf8OV). Issue/list/revoke. | `python scripts/n8n_webhook_secret.py issue`, `--list`, `--revoke <id>` |
| `scripts/seed_plan_template.py` | Seed (or update) weekday/weekend plan templates for an operator in the Command Center. | `python scripts/seed_plan_template.py --operator cc --type weekday` |
| `scripts/seed_profile.py` | Seed (or update) OASIS Command Center operator profile. Idempotent, defaults to CC's profile. | `python scripts/seed_profile.py`, `--email <email>` |
| `scripts/sync_slash_commands.py` | Drift-detect dashboard slash-command catalog against actual `.agents/workflows/` on disk. Detect-only, not auto-fix. | `python scripts/sync_slash_commands.py` |
| `scripts/agent_inbox.py` | **Async agent-to-agent messaging** (mcp_agent_mail pattern). Bravo/Atlas/Maven/Aura/Codex post structured messages to `tmp/agent_inbox/`, orchestrator picks up at checkpoints. Closes the synchronous-delegation gap. | `post --from <agent> --to <agent> --subject ... --body ...`, `list --to bravo`, `read <msg_id>`, `reply --in-reply-to <msg_id>` |
| `scripts/md_to_gdoc.py` | Markdown → styled Google Doc export. Wraps `google_tool.py docs create` with inline CSS for tables, code, blockquotes. | `python scripts/md_to_gdoc.py brain/TOOL_SHED.md [--title "..."] [--folder <drive-id>] [--json]` |
| `scripts/name_utils.py` | **Render-path name sanitizer.** Single source of truth for blocking placeholder lead names ("Contact", "Owner", "info", empty, etc.) before they reach a real recipient. Imported by `email_engine`, `outreach_engine`, `funnel_nurture`, `autonomous_agent`. Tests: `scripts/test_name_utils.py` (21 cases). Motivated by the 2026-04-25 "Hi Contact," incident. | `from name_utils import safe_first_name, safe_full_name, sanitize_template_vars` |
| `scripts/sibling_repos.py` | **Cross-repo path resolver.** Single source of truth for sibling-agent locations (Bravo/Maven/Atlas/Aura). Used by `agent_inbox.py` (cross-repo posting) and `ceo_dashboard.py` (subprocess to Maven's late_tool for content stats). Per-machine override via `BRAVO_REPO`/`MAVEN_REPO`/`ATLAS_REPO`/`AURA_REPO` env vars. | `from sibling_repos import repo_for, script_in` |

## Business Ops Database Schema (14 tables — Supabase Bravo)

| Domain | Tables | Purpose |
|--------|--------|---------|
| **CRM** | `leads`, `lead_interactions` (extended 2026-04-20 with cooldown_until + agent_source + metadata for unified ledger) | Lead tracking, interaction history, scoring, cross-engine cooldown enforcement |
| **Funnels** | `funnels`, `funnel_entries` | Conversion funnel tracking |
| **Email** | `email_templates`, `nurture_sequences`, `email_log` | Email marketing, sequences, delivery tracking |
| **Bookings** | `booking_slots`, `bookings` | Self-hosted scheduling system |
| **Revenue** | `revenue_events`, `monthly_metrics` | Payment tracking, MRR history |
| **Content** | `content_calendar`, `content_templates` | Content planning and scheduling |
| **Automation** | `cron_jobs` | 12 automated business workflows |

## Cron Jobs (12 automated workflows)

| Job | Schedule | Type |
|-----|----------|------|
| Morning Content Post | Daily 9am | content_post |
| Afternoon Content Post | Daily 1pm | content_post |
| Evening Content Post | Daily 7pm | content_post |
| Lead Follow-up Check | Weekdays 8am | lead_followup |
| Booking Reminders | Daily 6pm | booking_reminder |
| Stripe Revenue Sync | Daily 6am | stripe_sync |
| Weekly MRR Report | Monday 9am | revenue_report |
| Weekly Pipeline Review | Monday 10am | pipeline_review |
| Nurture Sequence Check | Weekdays 10am | nurture_check |
| Monthly Metrics Snapshot | 1st of month 9am | monthly_snapshot |
| Content Week Plan | Sunday 8pm | content_planning |
| Instagram Research | Mon/Wed/Fri 11am | ig_research |

## Knowledge Compilation System (Karpathy-style — added 2026-04-06)

Bypasses RAG entirely. Raw source documents are compiled by an LLM into structured, cross-linked
markdown wiki pages. Deterministic retrieval via `knowledge/index.md` — no embeddings, no vector stores.

| File | Purpose |
|------|---------|
| `knowledge/SCHEMA.md` | Navigation guide for LLMs — read this before any operation |
| `knowledge/index.md` | Catalog of all wiki pages — start here for queries |
| `knowledge/log.md` | Chronological ingest history |
| `knowledge/raw/` | Immutable source documents (never modify) |
| `knowledge/wiki/` | LLM-compiled structured pages |

**Three operations:**
- `/ingest` — compile a raw document into the wiki (workflow: `.agents/workflows/ingest.md`)
- `/query-knowledge` — retrieve sourced answers (workflow: `.agents/workflows/query-knowledge.md`)
- `/lint-knowledge` — check for broken links, stale facts, missing cross-refs

**Skill:** `skills/knowledge-compilation/SKILL.md`

**Seeded wiki pages (2026-04-06):**
- `knowledge/wiki/ai-automation-agency.md` — OASIS AI positioning, ICP, services, pitch
- `knowledge/wiki/revenue-model.md` — MRR breakdown, primary retainer deal, $5K gap analysis
- `knowledge/wiki/tech-stack.md` — Full technology inventory, all tools and integrations
- `knowledge/wiki/client-playbook.md` — Client lifecycle, NEPQ, health scoring, retention

## Workflows (33 active — `.agents/workflows/`)

| Command | Cadence | Purpose |
|---------|---------|---------|
| /briefing | Daily | CEO morning briefing — MRR, pipeline, client health, #1 priority |
| /cli-anything | On-demand | Generate CLI wrapper for any software/API/service |
| /client-health | Weekly (Fri) | Client health scoring, churn risk alerts, retention actions |
| /client-onboard | On-demand | New OASIS client setup |
| /commit | On-demand | Smart commit — conventional format, staged analysis |
| /competitive-report | Monthly | Competitor scan — pricing, features, reviews, battlecard updates |
| /content | On-demand | Create platform content (with OpenCLI trend check) |
| /create-prd | On-demand | Generate 15-section PRD for client projects |
| /debug | On-demand | Systematic bug fixing |
| /evolve | On-demand | Extract session patterns → promote to skills, SOPs, or CLAUDE.md rules |
| /health | On-demand | Full workspace diagnostic |
| /investor-update | Monthly | Investor/advisor monthly update — metrics, milestones, risks |
| /knowledge-maintenance | Weekly (Sun) | PARA capture review, inbox zero, template library update |
| /meeting-prep | On-demand | Pre-meeting brief, agenda, context, post-meeting follow-up |
| /n8n | On-demand | Search, inspect, manage n8n workflows |
| /onboard-team-member | On-demand | Contractor/hire onboarding — docs, access, 30-day plan |
| /opencli | On-demand | Explore websites, run prebuilt adapters, create website CLI adapters |
| /post | On-demand | Publish via Zernio (with OpenCLI verification) |
| /prime | On-demand | Load full project context |
| /proposal | On-demand | Generate proposal/SOW/NDA from client brief |
| /qbr | Quarterly | Quarterly business review — grade OKRs, compile QBR, next quarter targets |
| /research | On-demand | Competitive intelligence (OpenCLI-first for platforms) |
| /retro | Weekly (Sun/Mon) | Retrospective — commits, scores, patterns, improvement actions |
| /review | On-demand | Pre-landing code review with Fix-First methodology |
| /ship | On-demand | Full shipping pipeline — test, review, changelog, PR, deploy |
| /skool-edit | On-demand | Edit Skool lessons or About page via Playwright |
| /skool-push | On-demand | Bulk-push course content to Skool |
| /status | On-demand | Project status report |
| /strategic-review | Quarterly | Strategic review — revenue, pipeline, competitive, OKR progress |
| /sync | On-demand | End-of-session sync |
| /ingest | On-demand | Compile raw document into knowledge wiki |
| /query-knowledge | On-demand | Sourced answer from compiled knowledge wiki |

## Skills (151 active — Supabase-routed runtime catalog)

> **Note:** All skills use the Claude Agent Skills 2.0 structure. They are stored in `skills/[skill-name]/SKILL.md` format. Supabase `skills_registry` is the runtime cache: `register_skill.py sync-all` syncs trigger/tier/owner/risk/source-hash metadata, and `register_skill.py route "<task>"` picks the right skills to load.

### Runtime Shape

| Dimension | Current distribution |
|----------|----------------------|
| **Tier** | 14 core · 45 standard · 92 specialized |
| **Owner agent** | Bravo 125 · Codex 15 · Maven 8 · Aura 2 · Atlas 1 |
| **Largest categories** | Google 44 · Development 12 · Memory 11 · Operations 11 · Orchestration 10 · Persona 9 · Browser 7 · Revenue 7 |
| **Risk metadata** | 118 normal · 22 sensitive · 11 approval-gated |

Full human index: [[skills/INDEX]]. Runtime selection: `python scripts/register_skill.py route "<task>" --json`.

## External Services (No MCP)

| Service | Access Method | Purpose |
|---------|---------------|---------|
| n8n | n8n-mcp / API | Workflow automation (Full CRUD via Bravo) |
| Gmail | API / SMTP | Email drafting, research, and approval-based sending |
| Notion | API | Task tracking, project management, and knowledge base |
| Vercel | Git push auto-deploy | Hosting & previews |
| GoHighLevel | n8n webhooks | CRM for OASIS clients |
| Twilio | API/n8n | SMS & voice (Nostalgic Requests) |
| Shopify | Admin UI | FromOasis e-commerce |
| Telegram | telegram_agent.js (V11.0) | CLI bridge for remote execution — full-context parity, loads CLAUDE.md + brain files. 25 max turns. Start: `npm run telegram` |

## Video Production Pipeline — OWNED BY MAVEN

The full video stack (FFmpeg + Whisper + Remotion + ElevenLabs + content-studio + 37 Remotion skills) lives in the CMO-Agent repo. When CC says "make this a post" with a video, route the task there. Bravo does not own any video production scripts, skills, or agents.

- Repo: `C:\Users\User\CMO-Agent`
- Pipeline: `../CMO-Agent/scripts/edit_content_v2.py`
- Studio: `../CMO-Agent/content-studio/`
- Remotion skills: `../CMO-Agent/content-studio/.claude/rules/remotion/`

## Orchestration Config (`.agents/config.toml`)

Centralized configuration for agent behavior, routing, security, and performance. All AI interfaces reference this file.

| Section | Purpose |
|---------|---------|
| `[routing]` | Complexity-based task routing — thresholds, agent assignments, domain overrides |
| `[anti_drift]` | Drift prevention — checkpoint intervals, scope creep limits, error cascade detection |
| `[permissions]` | Claims-based agent access control — per-agent levels, file scope restrictions |
| `[sparc]` | SPARC methodology phases — required outputs, approval gates |
| `[performance]` | Resource limits — max agents, timeouts, memory budgets, caching |
| `[workers]` | Background workers — audit, memory, sync, optimize (intervals + tasks) |
| `[hooks]` | Enhanced hook lifecycle — pre/post operation automation + learning triggers |
| `[security]` | Input validation, secret scanning, blocked patterns |
| `[logging]` | 3-tier logging config (Supabase traces, session files, diagnostics) |

## Safety & Automation Hooks (`.claude/settings.local.json`)

| Hook Event | Matcher | Action |
|------------|---------|--------|
| **PreToolUse** | Edit/Write | Blocks editing `.env`, `.env.*`, `.env.agents` — credentials must be updated manually |
| **PreToolUse** | Bash | Blocks `rm -rf /~/.git`, `git push --force main/master`, `DROP TABLE`, `TRUNCATE TABLE` |
| **PostToolUse** | Bash | Audit-logs git push, git commit, npm build, vercel deploy to `tmp/hook_audit.log` |
| **Notification** | (all) | Windows desktop alert when Claude Code needs input |

**Permission deny rules:** `.env*` files, `.obsidian/**`, destructive git ops, `rm -rf` on root/home/git.

## Native Claude Code Skills (16 — `.claude/skills/`)

These are registered in Claude Code's native skill system with proper frontmatter (model override, effort level, auto-discovery). They complement the 154 skills in `skills/` which use the Agent Skills 2.0 format.

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/prime` | Session start, status check | Load context + health report |
| `/commit` | After code changes | Smart conventional commit |
| `/review` | Before shipping | Pre-landing code review |
| `/ship` | Ready to deploy | Full 9-phase shipping pipeline |
| `/retro` | Weekly (Sunday/Monday) | Retrospective with scores + actions |
| `/content` | Content creation | Brand voice content with trend check |
| `/post` | After content approval | Publish via Zernio (formerly Late) |
| `/plan-feature` | New feature request | Deep analysis → implementation plan |
| `/execute` | Plan approved | Step-by-step plan execution |
| `/debug` | Bug encountered | Root-cause-first debugging |
| `/opencli` | Web automation | Website-to-CLI commands |
| `/create-prd` | Client project | 15-section PRD generation |
| `/research` | Need information | Multi-source research |
| `/evolve` | Pattern detected | Self-improvement pipeline |
| `/health` | System check | Full diagnostic |
| `/status` | Quick update | Status from memory files |

## Tech Stack

- **OS:** Windows 11 (Desktop), macOS (MacBook)
- **Languages:** TypeScript (primary), Python (video pipeline, MCP servers)
- **Frameworks:** Next.js 14 (App Router), Tailwind CSS
- **Database:** Supabase (PostgreSQL) — 3 projects, 28-table schema (14 agent + 14 business ops)
- **Hosting:** Vercel (auto-deploy from git)
- **Payments:** Stripe (3 brand accounts)
- **Automation:** n8n (Hostinger VPS: https://n8n.srv993801.hstgr.cloud)
- **AI Models:** Claude Opus/Sonnet, Gemini 1.5 Pro/Flash, GPT-4o, Gemini CLI (v0.32.1)

## Setup & Bootstrap
- [[scripts/windows_bootstrap]] — Windows environment bootstrap guide (Python, FFmpeg, Node, dependencies)

## Obsidian Links
- [[brain/AGENTS]] | [[brain/STATE]] | [[brain/APP_REGISTRY]]
- [[brain/MODEL_CONFIG]] — V6.0 per-agent provider/model routing config
- [[brain/USER.template]] — public-clone operator profile template
- [[memory/WORKING]] — V6.0 ephemeral working memory (consolidated nightly)
- [[memory/ACTIVE_TASKS.template]] | [[memory/SESSION_LOG.template]]
- [[skills/mcp-operations/SKILL]] | [[skills/browser-automation/SKILL]]
- [[skills/auto-generated/SKILL]] — V6.0 runtime-synthesized skill container

## Manifest

<!-- MANIFEST:BEGIN -->
_Auto-generated by `scripts/catalog_sync.py` — do not edit this block manually._
_Last synced: 2026-04-28T03:54:27.303057+00:00_

| Type | Count |
|---|---:|
| Python scripts | 69 |
| PowerShell scripts | 9 |
| Shell scripts | 4 |
| **Total scripts** | **82** |
| Skills | 151 (7 destructive) |
| Agents | 20 |
| Workflows | 35 |

**Scripts by category:**

- Other: 29
- Data & Memory: 16
- System: 9
- Communication: 9
- Governance: 5
- Content: 5
- Browser & Web: 4
- Finance: 4
- Google: 1

<!-- MANIFEST:END -->
