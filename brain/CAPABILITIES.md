---
tags: [capabilities, tools]
---

# CAPABILITIES — Tool & Integration Registry

> Complete inventory of what Bravo can do. Last reviewed: 2026-05-06 (V6.1 era).
>
> **Counts are live — read them, do not quote them.** Hardcoding counts in this header is a known regression vector. The MANIFEST block at the bottom of this file is auto-synced by `scripts/catalog_sync.py`. For absolute live truth: `python scripts/core/self_audit.py --json`.
>
> Marketing/social scripts (`late_tool.py`, `late_publisher.py`, `instagram_engine.py`, `codex_image_gen.py`) transferred to Maven on 2026-04-26 — they live at `../CMO-Agent/scripts/` now. Bravo subprocesses to Maven's `late_tool.py` only for read-only CEO-dashboard stats (see `ceo_dashboard.py:_content_this_week`).
>
> **V6.1 scaffolding mechanism** is live: the repo now ships as a true scaffold for new operators (`operator.profile.json` + `personalize.py` + `scaffold.py`). See the V6.0/V6.1 scripts table below.
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
- **Access:** Full read/write to all 148 active skills in `skills/`, all 114 top-level Python CLI tools in `scripts/` (215 total inc. subpackages), all brain/ and memory/ files, all subagent definitions.
- **Entry Point:** `AGENTS.md` (shared with Codex/Cursor/Windsurf). Identity routing at lines 13-15.
- **MCP Servers:** Same 9 servers as Claude Code (Playwright, Context7, Memory, Sequential Thinking, GitHub, Firecrawl, Obsidian, Filesystem, Knowledge Graph) when available via OpenCode.
- **Tool routing:** Same CLI-first rules — `scripts/integrations/send_gateway.py`, `scripts/integrations/supabase_tool.py`, `scripts/integrations/stripe_tool.py`, `scripts/integrations/google_tool.py`, `scripts/integrations/n8n_tool.py`.

### Anti-Gravity IDE (Native Local Agent — Multi-Model)

Models: Gemini 3.1 Pro High/Low, Gemini 3 Flash, Claude Sonnet/Opus 4.6, GPT-OSS 120B Medium
Entry Point: `ANTIGRAVITY.md` | Config: `.vscode/mcp.json`
Workflows: `.agents/workflows/` (35 active workflows: post, status, health, prime, content, commit, n8n, sync, research, debug, client-onboard, cli-anything, evolve, briefing, client-health-report, generate-proposal, strategic-review, competitive-report, qbr, onboard-team-member, meeting-prep, investor-update, knowledge-maintenance, review, ship, retro, create-prd, opencli, ingest, query-knowledge, lint-knowledge, browser-harness, close-review, e2e-testing, sop). Archived: skool-edit, skool-push (2026-05-18, see `.agents/workflows/_archive/`).

| Server | Purpose | Config |
|--------|---------|--------|
| **Playwright** | Browser automation, web research | npx @playwright/mcp --headless |
| **Context7** | Live library documentation | npx @upstash/context7-mcp |
| **Memory** | Persistent knowledge graph | npx @modelcontextprotocol/server-memory |
| **Sequential Thinking** | Multi-step reasoning | npx @modelcontextprotocol/server-sequential-thinking |
| **Knowledge Graph** | Vault graph — PageRank, communities, semantic search | npx tsx C:\Users\User\tools\knowledge-graph\src\mcp\index.ts |

**SDK INTEGRATIONS (Universal — replaces broken MCPs):**
| **Supabase** | Database CRUD, queries, RPC | `python scripts/integrations/supabase_tool.py select <table> --project bravo --limit 10` |
| **Stripe** | Balance, customers, products, invoices, subscriptions, payment links | `python scripts/integrations/stripe_tool.py balance` |

**Supabase tool commands:** `list-projects`, `list-tables`, `select`, `insert`, `update`, `delete`, `upsert`, `rpc`, `query`
**Stripe tool commands:** `balance`, `customers`, `products`, `prices`, `invoices`, `subscriptions`, `charges`, `payment-links`, `create-payment-link`, `create-customer`, `create-invoice`, `refund`, `events`
**Projects (Supabase):** `--project bravo` (default), `--project oasis`, `--project nostalgic`

### Gemini CLI (Diagnostic & Inference — 4th Tier)
- Tool: `@google/gemini-cli`
- Entry Point: `GEMINI.md`
- Purpose: Fast diagnostics, file system cleanup, automated audits, heartbeat monitoring, fallback execution
- Interface: `gemini` command (global npm)
- MCP Access (via `.gemini/settings.json`): Playwright, Context7, Memory, Sequential Thinking (4 active servers)
- CLI Tools: `python scripts/integrations/supabase_tool.py`, `python scripts/integrations/stripe_tool.py`, `python scripts/integrations/n8n_tool.py`, `python ../CMO-Agent/scripts/late_tool.py` (Maven)
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
| `memory_consolidation.py` | 3-layer memory: `WORKING.md` → `memories_episodic` / `memories_semantic`. Nightly cron. | `python scripts/core/memory_consolidation.py status --json` |
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
| `system_cleanup.py` | Find + delete redundant install clones, pip/npm caches, old `tmp/` files, `__pycache__` trees, scaffold backups. Active repo preserved by safety guard. **V6.1.1** | `python scripts/core/system_cleanup.py --apply` |
| `reap_orphan_mcps.py` | Kill duplicate/leaked MCP server processes (multi-editor host pattern leaves orphans). Keeps N most recent per signature. **V6.6** | `python scripts/reap_orphan_mcps.py --keep 4 --apply` |
| `system_health_check.py` | Self-sustaining maintenance pass: reap orphan MCPs, clean Temp >14d, run `self_audit.py` + `audit_mcp_secrets.py`, post inbox alerts on degradation. Scheduled via `BravoSystemHealth` task at login (5 min delay) + every 30 min. **V6.6** | `python scripts/core/system_health_check.py` |
| `build_bridge_manifest.py` | Generate the bridge manifest from `bridge_lock.py` arbitration data. | `python scripts/build_bridge_manifest.py` |
| `check_bridge_manifest.py` | Validate the bridge manifest is consistent with current PM2 + lockfile state. | `python scripts/check_bridge_manifest.py` |
| `update_readme_stats.py` | Walks disk, regenerates README.md count fields (skills/scripts/sub-agents/workflows/MCP servers) from real state. `--check` mode used by self_audit so the README never lies about itself. **V6.7** | `python scripts/update_readme_stats.py --apply` |

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

### Browser layers — Firecrawl, CloakBrowser, Playwright, Browser Harness (4 tools, complementary)

Common point of confusion. Each serves a **different job**; the right one depends on (a) public vs CC-authenticated and (b) bot-protected vs unprotected.

- **Firecrawl** — cloud-side scraper. Returns clean markdown, structured extraction, site mapping. Cheapest + fastest for unprotected public pages. `scripts/integrations/firecrawl_tool.py`.
- **CloakBrowser** *(added 2026-05-15, V6.7+)* — stealth Chromium 146 with C++ source-level fingerprint patches. Drop-in Playwright API. **Mandatory tier-1 for fresh-session work against bot-protected sites** (Cloudflare Turnstile, reCAPTCHA v3, DataDome, ShieldSquare, FingerprintJS, Akamai, Kasada, PerimeterX). Pre-fetched ~200MB binary at `C:\Users\User\.cloakbrowser\chromium-146.0.7680.177.4\chrome.exe`. CLI: `scripts/browser/cloak_browser_tool.py`. Skill: `skills/cloak-browser/SKILL.md`. Optional residential proxy via `CLOAK_PROXY_URL` for the hardest tier (Akamai/Kasada).
- **Playwright (MCP)** — stateless, ephemeral browser. Use for **unprotected** sites where you need interactive flow / visual snapshots beyond what Firecrawl gives. Raw Playwright fingerprints get blocked by Cloudflare within 1-3 requests, so default to CloakBrowser when the target has any bot defense.
- **Browser Harness** — attaches to your **actual logged-in Chrome** via CDP port 9222. Persistent cookies, real session, your real LinkedIn / Skool / community login. Best for: running tasks AS YOU (DM replies, community posts, member-list pulls). A real human's browser beats any stealth fork — use this when CC has the session.

**Decision ladder:**
1. Public unprotected page, just need text → **Firecrawl** (cheapest).
2. Firecrawl returns 403/429/empty OR target documented as bot-protected → **CloakBrowser** (mandatory stealth tier).
3. Need interactive flow / visual snapshot on an unprotected site → **Playwright MCP**.
4. Need to act as CC inside CC's logged-in account → **Browser Harness**.

The dispatcher in `computer_control.py browser` exposes `scrape` (Playwright) vs `do-as-me` (Browser Harness); CloakBrowser is invoked directly via its CLI when escalating from Firecrawl. Full matrix: [skills/web-scraping/SKILL.md](../skills/web-scraping/SKILL.md).

## Browser Harness (Direct Browser Control + Domain Skills)

Browser Harness is installed as Bravo's direct Chrome/Edge control layer. It complements Playwright MCP, Firecrawl, and OpenCLI by attaching to a real logged-in browser and turning site-specific discoveries into durable domain skills.

- **Stable checkout:** `C:\Users\User\APPS\browser-harness`
- **Executable:** `C:\Users\User\.local\bin\browser-harness.exe`
- **Global Codex skill:** `C:\Users\User\.codex\skills\browser-harness`
- **Bravo skill:** `skills/browser-harness/SKILL.md`
- **Runtime packaging skill:** `skills/agent-runtime-packaging/SKILL.md`
- **Diagnostics:** `python scripts/browser/browser_harness_doctor.py`
- **Direct attach helper:** `python scripts/browser/browser_connect.py` — connect to the running CDP browser (headless-aware)
- **Onboarding doctor:** `python scripts/onboarding_diagnostics.py`
- **Workflow:** `.agents/workflows/browser-harness.md`
- **Domain skills:** `browser/domain-skills/`
- **Interaction skills:** `browser/interaction-skills/`

**Current Windows note:** upstream Browser Harness assumed Unix sockets. The editable checkout has a local Windows compatibility patch that falls back to localhost TCP when `socket.AF_UNIX` is unavailable. Chrome/Edge still needs one-time remote-debugging profile approval before attach works.

**Safety:** Browser Harness may inspect and draft, but any real send/publish/delete/billing/finance/admin/production action requires explicit CC approval. Outbound communication still goes through `scripts/integrations/send_gateway.py`.

## MCP Replacement CLI Tools (5 — replaces broken credential MCPs)

| Tool | Script | Replaces MCP | Key Commands |
|------|--------|-------------|-------------|
| **Zernio (Late)** | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | Late MCP (env var broken) | `accounts`, `profiles`, `posts`, `create`, `cross-post`, `publish`, `failed` |
| **n8n (read/exec)** | `scripts/integrations/n8n_tool.py` | Always-works fallback | `list`, `search`, `get`, `execute`, `activate`, `deactivate`, `executions`, `stats` |
| **n8n (build/modify)** | n8n-mcp SDK flow | — | `get_sdk_reference`, `search_nodes`, `get_node_types`, `validate_workflow`, `create_workflow_from_code`, `update_workflow`, `archive_workflow`. Build canonical path — see `skills/n8n-mcp-integration` |
| **Supabase** | `scripts/integrations/supabase_tool.py` | Supabase MCP (token expired) | `list-projects`, `list-tables`, `select`, `insert`, `update`, `delete`, `query` |
| **Stripe** | `scripts/integrations/stripe_tool.py` | Stripe MCP (v0.3.1 proxy mode) | `balance`, `customers`, `products`, `invoices`, `subscriptions`, `charges` |
| **research_fetch** *(2026-05-16, DEFAULT)* | `scripts/research_fetch.py` | Single tier-aware URL fetcher. Auto-escalates Firecrawl → CloakBrowser based on actual response + SQLite per-domain reputation memory at `state/site_reputation.db`. Skill: `skills/research-fetch/SKILL.md`. | `fetch <url>` (bare URL also works), `reputation [domain]`, `reputation-clear <domain>`, `--force-tier {firecrawl,cloak}` |
| **Firecrawl** | `scripts/integrations/firecrawl_tool.py` | Firecrawl MCP (fallback). Use directly when you need crawl/extract/map/search; otherwise prefer `research_fetch`. | `scrape`, `crawl`, `search`, `extract`, `map` |
| **CloakBrowser** *(2026-05-15)* | `scripts/browser/cloak_browser_tool.py` | Stealth Chromium 146 — drop-in Playwright. Use directly for interactive `goto`/screenshot/check-stealth; otherwise `research_fetch` handles the escalation. | `scrape`, `goto`, `check-stealth`, `binary-info`, `download`, `clear-cache` |
| **Browser Harness Doctor** | `scripts/browser/browser_harness_doctor.py` | Browser Harness install/attach diagnostics | `[--json] [--strict]` |
| **Browser Connect** | `scripts/browser/browser_connect.py` | Attach to the running CDP browser and run scripted actions | `[--url URL] [--eval SNIPPET]` |
| **Onboarding Diagnostics** | `scripts/onboarding_diagnostics.py` | Productized setup readiness check | `[--json]` |

## V6.0 Architecture (2026-05-10 — transactional state + retrieval + guards)

> Live behind `EMPIRE_V6_MODE` (off/shadow/on). See [CLAUDE.md](../CLAUDE.md) "V6.0 Architecture" for the canonical spec.

| Component | Path | Purpose | CLI |
|-----------|------|---------|-----|
| **State Manager** | `scripts/state/state_manager.py` | Single-writer SQLite/WAL proxy for `state/empire_state.db` (heartbeats, session_log, active_task) — also mirrors heartbeat to Supabase | `heartbeat`, `log`, `task {add,close,list}`, `export [--check]`, `import-from-files`, `status` |
| **Memory Retriever** | `scripts/core/memory_retriever.py` | Hybrid lexical+semantic retrieval. FTS5 BM25 (`state/memory_index.db`) + LanceDB cosine (`state/memory_lance/`) with ONNX MiniLM-L6-v2 embeddings via fastembed. RRF merge (k=60). 226 sources / 2,857 chunks. Hybrid = default; `--lexical-only` / `--semantic-only` / `--explain` for introspection. ~9ms FTS5 + ~50ms semantic. | `build [--force] [--lexical-only]`, `update`, `query "..." [--lexical-only \| --semantic-only] [--explain] [--kind ...] [--limit N] [--json]`, `status` |
| **Exec Guard** | `scripts/state/exec_guard.py` | PreToolUse Bash hook. Hard blocks on DROP, DELETE-without-WHERE, ALTER DROP COLUMN, rm -rf / outside tmp, force-push to main, git reset --hard <ref>, fork bombs, dd-to-disk. AST-validates SQL via sqlglot. Read-only CLI verbs fast-path. | env: `EMPIRE_HOOK_EXEC_GUARD={enforce,report,off}` |
| **Secret Guard** | `scripts/state/secret_guard.py` | PreToolUse Read/Bash/Edit hook. Blocks Read on `.env*`/`*.pem`/`*.key`/`credentials.json`. Blocks `cat`/`grep`/`sed`/`awk` on those paths. | env: `EMPIRE_HOOK_SECRET_GUARD={enforce,report,off}` |
| **State Guard** | `scripts/state/state_guard.py` | PreToolUse Edit hook on auto-generated mirrors (`memory/SESSION_LOG.md` between markers). Pushes you to `state_manager.py` instead. | env: `EMPIRE_HOOK_STATE_GUARD={enforce,report,off}` |
| **Subprocess Guard** | `scripts/hooks/subprocess_guard.py` | PreToolUse Edit/Write/MultiEdit AST hook. Blocks new `subprocess.{Popen,run,...}` calls in `.py` files that omit `creationflags=` — the recurring "terminal window popped up" root cause. Compares against pre-existing file violations so cleanup edits aren't unfairly blocked. Bypass via `# noqa: SUBPROCESS`. Predicate shared with audit script via `scripts/lib/subprocess_ast.py`. | env: `EMPIRE_HOOK_SUBPROCESS_GUARD={enforce,report,off}` (default `report`) |
| **Subprocess Audit** | `scripts/audit_no_visible_subprocess.py` | Repo-wide scanner — exits 1 on any unflagged daemon-spawned subprocess call. Companion codemod: `scripts/migrate_subprocess_calls.py` (dry-run by default, `--apply` to bulk-patch). Canonical wrappers live in `scripts/_subprocess_helpers.py` + `bravo_cli/_subprocess_helpers.py` (`safe_run`, `safe_popen`, `safe_daemon_popen`). | `audit_no_visible_subprocess.py [--quiet \| --json] [path]` |
| **Retriever Post-Edit** | `scripts/retriever_postedit.py` | PostToolUse hook — fires `memory_retriever.py update` (detached) when an indexed file is written, keeping the FTS5 index warm. | auto |
| **Secret Loader** | `scripts/lib/secret_loader.py` | Canonical in-process loader for `.env.agents`. Refuses tmp/ callers + interactive shells. Audits every load to `state/secret_access.log`. | `from lib.secret_loader import load_env` |
| **Safe Error** _(archived 2026-05-21)_ | `scripts/_archive/safe_error.py` | Credential-pattern scrubber for tracebacks. No active callers; archived during 2026-05-21 cleanup. Revive if a future surface needs scrub-before-log. | — |
| **State DB** | `state/empire_state.db` | SQLite/WAL. Tables: `agent_state`, `session_log` (UNIQUE(session_id, note)), `active_task`, `state_transaction` (audit). | — |
| **Index DB** | `state/memory_index.db` | SQLite FTS5. Separate file so retrieval reads never block state writes. | — |
| **Migrations** | `state/migrations/{001_init,002_memory_index}.sql` | Idempotent; auto-applied on first connect. Tracked in git; everything else under `state/` is gitignored. (003_override_requests.sql deleted 2026-05-22 with the override-approval feature.) | — |
| **Audit logs (jsonl)** | `state/{exec_guard,secret_guard,state_guard,secret_access,state_manager}.log` | Local, gitignored. Reviewed weekly during 14-day soak before flipping `EMPIRE_HOOK_*=enforce`. | `tail -f state/exec_guard.log` |
| ~~Exec Override~~ | DELETED 2026-05-22 per CC | The exec_guard hook still blocks destructive commands; it just refuses them outright now rather than queuing for human approval. The block IS the protection. | — |
| **Event Bus** | `scripts/core/event_bus.py` + Supabase `agent_events` table | BUILD 3 cross-agent pub/sub. Raw psycopg `LISTEN/NOTIFY` with 5-second polling fallback; `claim_events()` RPC uses `FOR UPDATE SKIP LOCKED` for race-free dequeue. Migration 015 applied 2026-05-10. **All 4 producers wired** (state_manager.append_session_log → BRAVO_SESSION_LOG_APPENDED, pulse_publish.cmd_refresh → BRAVO_PULSE_REFRESHED, bridge_chat_server → BRAVO_CHAT_INTERACTION, send_gateway → BRAVO_OUTBOUND_SENT). | `publish --type X --payload '...'`, `tail --agent bravo`, `stats`, `reap`, `drain` |

**Hook chain:** Bash → secret_guard → exec_guard. Read → secret_guard. Edit/Write → secret_guard → state_guard → subprocess_guard. Each guard exits 0/2 and writes to its own JSONL audit log. Default modes are safe (`report`/`off`) — flip to `enforce` after soak.

**Drift check:** `python scripts/state/state_manager.py export --check` exits 1 if mirror markdown is out of sync with the DB. Run before commits in `EMPIRE_V6_MODE=on`.

### V6.0 Phase 2 — Productized Deployment (2026-05-10)

Turnkey deployment for B2B clients. Two compose targets, scoped secrets, dashboard health module, operator-facing playbooks.

| Component | Path | Purpose |
|-----------|------|---------|
| **Local compose** | `infra/docker-compose.local.yml` | Single-developer / client laptop. Read-only rootfs, `cap_drop:[ALL]`, `no-new-privileges`, 127.0.0.1-only ports. memory/brain/skills mounted read-only. Only `state/`, `tmp/`, `logs/` are writable. |
| **Cloud compose** | `infra/docker-compose.cloud.yml` | Always-on VPS. `include:`s the prod stack (5 daemons + pgbouncer + Caddy) and adds `command-center` (Next.js) + `state-api` (read-only FastAPI). Requires Compose ≥ 2.20. |
| **Command Center image** | `infra/Dockerfile.commandcenter` | Next.js 15 multi-stage build. Non-root UID 10001, `output: 'standalone'`, healthcheck via `/api/health`. |
| **Caddy dashboard route** | `infra/Caddyfile` | TLS-terminated dashboard endpoint with basic auth. `/api/health` carved out for probes. |
| **State API** | `scripts/state/state_api.py` | Read-only FastAPI service. Wraps `state_manager.status()` + tails guard logs. Mounted with `state/` read-only — physically cannot write to the DB. Endpoints: `/health`, `/status`, `/guards`, `/retrieval`. |
| **System Health page** | `oasis-command-center:app/system-health/page.tsx` | Server component → `/api/state-health` → state-api. Shows DB stats, agent ticks, all three guard modes + 24h block counts. Header carries a `via state-api` / `via supabase-mirror` tag so operators see which read path served the payload. |
| **State-health read path** | `oasis-command-center:app/api/state-health/route.ts` | Two-tier: tries `state-api:8500/status` first (canonical, available in local + Cloud Compose). On Vercel where that hostname isn't routable, falls back to a Supabase mirror that synthesizes the same shape from `agent_state_snapshot` + `agent_events` + `session_logs` via `getServiceSupabase()`. Envelope carries `source` field; FTS5/guard-tail sections render empty (local-only). |
| **Operator Playbook page** | `oasis-command-center:app/playbook/onboarding/page.tsx` | `react-markdown` renders `docs/playbooks/*.md`. Updated by editing markdown, not code. |
| ~~Override Approvals page~~ ~~Override API~~ ~~Override mirror table~~ ~~Override consumer daemon~~ | ALL DELETED 2026-05-22 per CC | The entire Apex Phase 2 dashboard-approval surface (dashboard page, API route, Supabase table + RPCs, consumer daemon, related migrations 035 + 048) was removed. exec_guard still blocks destructive commands; it just refuses outright. The block IS the protection. |
| **Event router daemon (Apex Phase 3)** | `scripts/core/event_router.py` | Polls `agent_events` with a cursor (`state/event_router.cursor`), projects each row to a uniform shape, appends to `state/event_router.log` jsonl. Cursor-based — sees every event exactly once on the host. Run-modes: `once`, `loop`, `tail`. |
| **Event Feed page (Apex Phase 3)** | `oasis-command-center:app/feed/page.tsx` | Live cross-agent activity tape. Server-renders the last hour of `agent_events`; `refresher.tsx` client island calls `router.refresh()` every 5s so the operator sees sibling activity land without websockets. |
| **Event feed API** | `oasis-command-center:app/api/event-feed/route.ts` | GET `/api/event-feed?since_minutes=60&limit=100&source=&event_type=`. Service-role read with bounded windows + filters; used by the page on initial render and any future client poller. |
| **Playbook docs** | `docs/playbooks/{01-getting-started,02-safe-interaction,03-when-to-call-cc,04-pause-and-rollback}.md` | Four operator SOPs. Plain-English contract for non-technical clients. |
| **Wizard V6.0 steps** | `bravo_cli/wizard.py:step_environment`, `step_v6_init` | `step_environment` detects local vs cloud. `step_v6_init` writes EMPIRE_V6_MODE + EMPIRE_HOOK_* defaults, bootstraps `state/empire_state.db`, builds the FTS5 index, fans out scoped env files, optionally runs `docker compose build`. |
| **Scoped env files** | `.env.agents.{core,webhook,dashboard}` | Generated by `_fan_out_scoped_env_files()`. Each container gets only the keys it needs — defense in depth against single-service RCE exfiltrating the full credential set. `core` gets everything; `webhook` only Stripe webhook + Supabase + Telegram; `dashboard` only public Supabase + state-api URL. |
| **Install Docker probe** | `install.sh` / `install.ps1` | Friendly probe — heads-up if Docker isn't installed/running, never aborts the install. Wizard + CLI tools work without Docker; only the sandbox needs it. |

**Bring-up (local):**
```
git clone https://github.com/CC90210/CEO-Agent.git && cd CEO-Agent
bash install.sh                # installs deps, probes Docker
oasis setup                    # wizard adds EMPIRE_V6_MODE=shadow + scoped env files
docker compose -f infra/docker-compose.local.yml up -d --build
open http://127.0.0.1:3100/system-health
```

**Bring-up (cloud, on the VPS):**
```
git clone … && cd CEO-Agent && bash install.sh
EMPIRE_DEPLOY_TARGET=cloud oasis setup    # wizard sets EMPIRE_V6_MODE=on + enforce
docker compose -f infra/docker-compose.cloud.yml up -d --build
# Caddy auto-provisions Let's Encrypt for $DASHBOARD_DOMAIN + $OPS_DOMAIN
```

## V6.0 Scaffolds (2026-04-22 — not yet active; migrations 014/015 not applied)

> V6.0 is scaffolded but NOT activated. `docs/V6_ARCHITECTURE.md` is the design doc. Activation gated on CC sign-off on the 4 open questions.

| Component | Path | Purpose | CLI |
|-----------|------|---------|-----|
| **Event Bus** | `scripts/core/event_bus.py` | Postgres LISTEN/NOTIFY pub/sub replacing pulse JSON | `publish`, `stats`, `reap`, `drain`, `tail` |
| **Memory Chunker** | `scripts/core/memory_chunker.py` | Markdown → RAG chunks with wiki-link provenance | `<path> [--stats] [--json]` |
| **Memory Ingest** | `scripts/core/memory_ingest.py` | Chunk + embed + upsert to `memory_chunks` | `[--dry-run] [--only FILE] [--force-reembed]` |
| **Memory Query** | `scripts/core/memory_query.py` | Hybrid RAG retrieval (vector + trigram + freshness) | `--task "..." [--k N] [--format markdown\|json]` |
| **PII Scrubber** | `scripts/pii_scrubber.py` | Regex + optional Presidio PII redaction with reversible table | `scrub`, `unscrub`, `audit` |
| **DNS Reputation Doctor** | `scripts/dns_reputation.py` | Check SPF/DKIM/DMARC presence for a sender domain (invoked by `send_gateway.py doctor`) | `--domain oasisai.work` |
| **Webhook Listener** | `scripts/hooks/webhook_listener.py` | FastAPI endpoint for Stripe (sig-verified) / N8N (token) / Telegram updates → event bus | `uvicorn webhook_listener:app` |
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
| **Email** | `scripts/integrations/email_engine.py` | Free Gmail SMTP sending, templates, nurture sequences. Cold outreach uses `send-template` (Gate 1b refuses raw text-only OASIS commercial sends). | `send`, `send-template`, `templates list/create`, `sequence list/create/run`, `log`, `stats` |
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
| **Cron** | `scripts/core/cron_engine.py` + `scripts/core/cron_dispatcher.py` | Automated job registry plus allowlisted script-backed execution for Atlas/Maven jobs | `cron_engine.py list/add/toggle/due/seed`; `cron_dispatcher.py due --execute`, `run <job_id>` |

All engines: `--json` flag for agent consumption, credentials from `.env.agents`, Supabase backend.

## Semantic Memory (1 CLI tool — added 2026-04-06)

Auto-deduplicating semantic memory layer backed by local Qdrant (pgvector upgrade path available).
Complements markdown memory: markdown handles structured state, mem0 handles fuzzy fact retrieval.

| Tool | Script | Purpose | Key Commands |
|------|--------|---------|-------------|
| **Semantic Memory** | `scripts/integrations/mem0_tool.py` | Semantic search, auto-dedup, cross-session context injection | `add`, `search`, `list`, `get`, `delete`, `history`, `stats` |

**Stack:** mem0ai 1.0.10, fastembed (thenlper/gte-large, 1024-dim, local ONNX), Claude Haiku (extraction), Qdrant (embedded, local)
**Storage:** `data/mem0_qdrant/` (persisted, no server required)
**Skill:** `skills/semantic-memory/SKILL.md` — when to use vs markdown memory, upgrade path to Supabase pgvector

## System Maintenance Tools (3 CLI tools — added 2026-03-31, inspired by Claude Code internals)

Patterns extracted from Claude Code's internal harness architecture (1,902 TS files, 35 subsystems). These implement the same context management, cost tracking, and memory aging patterns that Claude Code uses internally.

| Tool | Script | Purpose | Key Commands |
|------|--------|---------|-------------|
| **Context Manager** | `scripts/core/context_manager.py` | Tiered loading, transcript compaction, deferred init health | `tier "<query>"`, `compact [--dry-run]`, `status`, `health` |
| **Cost Tracker** | `scripts/cost_tracker.py` | Per-operation cost tracking (label:units), budget alerts | `log --label X --units N`, `summary [--period today]`, `budget --check`, `session` |
| **Memory Aging** | `scripts/core/memory_aging.py` | Confidence decay, stale fact detection, memory health grading | `scan`, `stale [--days 30]`, `health`, `archive [--dry-run]` |

**Config:** `.agents/config.toml` sections `[context]`, `[cost_tracking]`, `[memory_aging]`
**Skill:** `skills/context-optimization/SKILL.md` — full reference for all 5 patterns

## Google Workspace (1 CLI tool — 7 services, 30+ commands)

Full Google ecosystem via `scripts/integrations/google_tool.py`. Auth: GWS CLI keyring (auto-refreshes). All commands support `--json`.

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
| **NotebookLM** | `scripts/integrations/notebooklm_tool.py` | `list`, `create --title "..."`, `use <id>`, `ask "..."`, `summary` |
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
| **Memory Index** | `scripts/core/memory_index.py` | 3-layer memory architecture (index → topics → archives) | `build`, `search "<query>"`, `stats` |
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
| ~~Skool Community~~ | _(archived 2026-05-18)_ | Skool community comment/reply daemon — paused when CC stepped away from the primary retainer. Code preserved at `scripts/_archive/skool/` for revival when CC launches their own community. | n/a |
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
| `scripts/browser/browse_and_capture.py` | Browser screenshot + capture |
| `../CMO-Agent/scripts/content_generator.py` | Claude API content generation |
| `scripts/generate_covers.py` | Cover art / image generation |
| `scripts/macos_control.py` | macOS system automation |
| `scripts/music_control.py` | Audio/music control |
| `scripts/outreach_engine.py` | Outreach campaign automation |
| `../CMO-Agent/scripts/render_video.py` | Remotion video rendering |
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

**All autonomous sends route through `scripts/integrations/send_gateway.py`.** Direct `smtplib` calls from business engines are a regression and must be reverted in review.

| Layer | File | Role |
|---|---|---|
| Gateway | `scripts/integrations/send_gateway.py` | Single chokepoint. CASL + cooldown + daily cap + multi-brand + logging. 17 tests green. |
| Context | `scripts/core/context_builder.py` | `get_entity_context()` — relationship stage, sentiment, prior interactions. Input for persona-aware LLM drafts. |
| Migrations | `scripts/apply_migration.py` | Applies `database/*.sql` via Supabase Management API. |
| Supabase Mgmt API | `scripts/integrations/supabase_admin.py` | Shared client for Supabase Management API (auth provider config, etc.). Handles Cloudflare-friendly UA. CLI: `python scripts/integrations/supabase_admin.py get /v1/projects/<ref>/config/auth` · `enable-google-oauth --project-ref X --client-id Y --client-secret Z`. |
| Cloudflare DNS | `scripts/integrations/cloudflare_admin.py` | Shared client for Cloudflare DNS. CLI: `list-zone --domain X` · `upsert-txt --domain X --name _vercel --value Y` · `sync-vercel-txt --domain X --vercel-project Y` (recovers a Vercel domain that needs new TXT verification). Built after the 2026-04-30 oasisai.work outage. |
| Ledger | `lead_interactions` table (+ migration 003: `cooldown_until`, `agent_source`, `metadata`) | Unified cross-engine action log. |
| CASL | `scripts/casl_compliance.py` | Suppression + footer + RFC 2369/8058 headers. Composed by the gateway. |
| Templates | `scripts/wire_all_templates.py` | Keeps OASIS Welcome / Value Add / CTA congruent across sessions. Verifies `https://oasisai.work` + `https://calendar.app.google/tpfvJYBGircnGu8G8`. |

Rewired engines (all route through gateway): `outreach_engine`, `email_engine`, `funnel_nurture`, `booking_engine`. `outreach_batch` was retired 2026-05-16 along with the cold-outreach Telegram-approval cron. See [[skills/send-gateway/SKILL]] for complete contract.

## Agent Governance Scripts (V5.6+)

Scripts that enforce Bravo's coherence, autonomy, and self-correction. Run in-process or on cron. All accept `--json` for agent-readable output.

| Script | Purpose | Usage |
|---|---|---|
| `scripts/core/self_audit.py` | **Self-diagnostic health check.** Scans brain/, memory/, skills/, agents/, scripts/ for orphans, broken wiring, undocumented scripts, MCP config drift. Emits 0-100 health score. | `python scripts/core/self_audit.py` (human) or `--json` |
| `scripts/audit_rls_coverage.py` | Supabase RLS coverage check for every tenant-scoped table. Fails if a `tenant_id` table lacks RLS or policies. | `python scripts/audit_rls_coverage.py --json` |
| `scripts/draft_critic.py` | Adversarial second-opinion reviewer. Runs on every Claude-drafted outbound before `send_gateway`. Answers the 2026-04-19 "dumb outreach" complaint. | Called by gateway hook, also `--review <draft>` |
| `scripts/inbound_classifier.py` | The inbound chokepoint companion to `send_gateway`. Classifies every inbound email/DM into unified `lead_interactions` ledger so no engine re-contacts a replied lead. | Called by engines; `--classify <payload>` |
| `scripts/autonomous_agent.py` | The always-on reasoning loop. Wakes on schedule or Telegram poke, consults pulse files, picks highest-leverage action, executes, logs. | `python scripts/autonomous_agent.py --once` or daemon mode |
| `scripts/state/state_sync.py` | Canonicalizes session state at end of every session. **NON-NEGOTIABLE** per Rule 4. | `python scripts/state/state_sync.py --note "<1-sentence summary>"` |
| `scripts/register_skill.py` | Runtime skill catalog: create/register/sync-all all `SKILL.md` folders into Supabase `skills_registry`, synthesize triggers/tier/owner/risk/source hashes, route a plain-English task to the right skills, and audit drift. | `python scripts/register_skill.py sync-all --deactivate-missing --json` · `python scripts/register_skill.py route "<task>" --json` · `python scripts/register_skill.py audit --json` |
| `scripts/build_maven_env.py` | One-time setup: seeds Maven's `.env.agents` from Bravo's shared infra credentials. | Run once per Maven bootstrap |
| `scripts/core/agent_heartbeat.py` | Write heartbeat to `agent_state_snapshot` so Command Center detects live agents within 15 min. | `python scripts/core/agent_heartbeat.py --agent bravo` |
| `scripts/crm_reset.py` | Archive cold/dead leads from bravo Supabase CRM. CC directive: remove noise, keep warm leads only. | `python scripts/crm_reset.py --dry-run` |
| `scripts/deploy_command_center.py` _(moved 2026-05-18)_ | One-shot production deploy for OASIS AI Agent Command Center. Migrated to the standalone `oasis-command-center` repo when the dashboard was extracted; deploys now run there via `vercel deploy --prod`. | `cd ~/APPS/oasis-command-center && vercel deploy --prod` |
| `scripts/integration_health.py` | Bump `integrations_health` row from any background worker. Supports Command Center Settings → Integrations page. | `python scripts/integration_health.py --integration stripe --status ok` |
| `scripts/fleet_health.py` | Cross-agent health rollup: pulse freshness (Bravo/Atlas/Maven), inbox unread per agent, cron job state, bridge lock status, memory staleness summary. | `python scripts/fleet_health.py`, `--json`, `--agent <name>` |
| `scripts/core/cron_dispatcher.py` | Executes allowlisted script-backed cron jobs from the shared registry (Atlas pulse publish, Maven token check, Maven backlog audit) and writes run status back to Supabase. | `python scripts/core/cron_dispatcher.py due --execute`, `run <job_id>`, `--dry-run` |
| `scripts/pulse_publish.py` | Atomic, schema-validated writer for Bravo's ceo_pulse.json. Only blessed path to update the file (direct edits forbidden per AGENT_ORCHESTRATION.md). | `python scripts/pulse_publish.py refresh --net-mrr <X> --priority "<...>"`, `validate`, `status` |
| `scripts/integrations/n8n_webhook_secret.py` | Manage shared secrets for OASIS Command Center inbound webhook (n8n workflow 1cGIN32alM8sf8OV). Issue/list/revoke. | `python scripts/integrations/n8n_webhook_secret.py issue`, `--list`, `--revoke <id>` |
| `scripts/seed_plan_template.py` | Seed (or update) weekday/weekend plan templates for an operator in the Command Center. | `python scripts/seed_plan_template.py --operator cc --type weekday` |
| `scripts/seed_profile.py` | Seed (or update) OASIS Command Center operator profile. Idempotent, defaults to CC's profile. | `python scripts/seed_profile.py`, `--email <email>` |
| `scripts/core/sync_slash_commands.py` | Drift-detect dashboard slash-command catalog against actual `.agents/workflows/` on disk. Detect-only, not auto-fix. | `python scripts/core/sync_slash_commands.py` |
| `scripts/core/agent_inbox.py` | **Async agent-to-agent messaging** (mcp_agent_mail pattern). Bravo/Atlas/Maven/Aura/Codex post structured messages to `tmp/agent_inbox/`, orchestrator picks up at checkpoints. Closes the synchronous-delegation gap. | `post --from <agent> --to <agent> --subject ... --body ...`, `list --to bravo`, `read <msg_id>`, `reply --in-reply-to <msg_id>` |
| `scripts/md_to_gdoc.py` | Markdown → styled Google Doc export. Wraps `google_tool.py docs create` with inline CSS for tables, code, blockquotes. | `python scripts/md_to_gdoc.py brain/TOOL_SHED.md [--title "..."] [--folder <drive-id>] [--json]` |
| `scripts/name_utils.py` | **Render-path name sanitizer.** Single source of truth for blocking placeholder lead names ("Contact", "Owner", "info", empty, etc.) before they reach a real recipient. Imported by `email_engine`, `outreach_engine`, `funnel_nurture`, `autonomous_agent`. Tests: `scripts/test_name_utils.py` (21 cases). Motivated by the 2026-04-25 "Hi Contact," incident. | `from name_utils import safe_first_name, safe_full_name, sanitize_template_vars` |
| `scripts/sibling_repos.py` | **Cross-repo path resolver.** Single source of truth for sibling-agent locations (Bravo/Maven/Atlas/Aura). Used by `agent_inbox.py` (cross-repo posting) and `ceo_dashboard.py` (subprocess to Maven's late_tool for content stats). Per-machine override via `BRAVO_REPO`/`MAVEN_REPO`/`ATLAS_REPO`/`AURA_REPO` env vars. | `from sibling_repos import repo_for, script_in` |
| `scripts/critic_template_check.py` | **Regression test for OASIS templates vs `draft_critic`.** Renders every OASIS email template against a synthetic lead and runs the critic at the live gateway threshold (6.5). Exits 1 if any template fails. Run before merging any template OR critic config change. Originated from the 2026-05-04 template-drift mistake. | `python scripts/critic_template_check.py [--json]` |
| `scripts/integrations/n8n_inbound_doctor.py` | **Diagnostic for the OASIS Inbound Qualifier (Bravo Aware) n8n workflow.** Verifies workflow `1cGIN32alM8sf8OV` is active, the Supabase `record_inbound_from_n8n` RPC exists and accepts payloads, and the email_engine IMAP poll path can write to `lead_interactions`. Use when inbound classification appears broken. | `python scripts/integrations/n8n_inbound_doctor.py [--json]` |

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
- `knowledge/wiki/revenue-model.md` — [ARCHIVED 2026-05-18] MRR breakdown pre-2026-05-18; preserved as historical context. Current MRR lives in brain/STATE.md.
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
- [[brain/USER.template.md]] — public-clone operator profile template
- [[memory/WORKING]] — V6.0 ephemeral working memory (consolidated nightly)
- [[memory/ACTIVE_TASKS.template.md]] | [[memory/SESSION_LOG.template.md]]
- [[skills/mcp-operations/SKILL]] | [[skills/browser-automation/SKILL]]
- [[skills/auto-generated/SKILL]] — V6.0 runtime-synthesized skill container

## VPS Operator Helpers

Paste-into-Claude-Code prompts for operating the SunBiz Funding VPS (`ssh root@srv1723601`). Idempotent, config-only — safe to re-run.

- [[docs/deploy/VPS_BYPASS_PERMISSIONS_SETUP]] — Configure Claude Code / Codex / Gemini CLI for auto-approve defaults so VPS sessions can do extensive work without permission prompts.
- [[docs/deploy/VPS_DIAGNOSTIC_PROMPT]] — Full SunBiz portal health check — layered diagnostic that fixes what it can safely and reports what needs CC's attention.

## Operational & Maintenance Scripts

Top-level `scripts/` entries that aren't surfaced under a major capability above. Most are CLI tools, cron handlers, or PM2 daemons; some are codemods used during maintenance passes. Listed here so they're discoverable + `self_audit.py` doesn't flag them as undocumented.

| Script | One-liner | Invocation type |
|---|---|---|
| `scripts/add_future_annotations.py` | Add `from __future__ import annotations` to Python files that use PEP 604 syntax | codemod (manual) |
| `scripts/auto_score_leads.py` | Auto-score OASIS leads — daily cron handler | cron (`auto_score_leads`) |
| `scripts/bravo_sleep.py` | Nightly memory consolidation by an LLM judge | cron (Bravo Sleep Agent) |
| `scripts/conftest.py` | pytest conftest — adds scripts/ to sys.path so bare imports resolve in tests | pytest infrastructure |
| `scripts/daily_brief.py` | AI-narrated morning summary to CC's Telegram | cron (`daily_brief`) |
| `scripts/dashboard_email_consumer.py` | Dashboard outbound-email consumer daemon | PM2 (`dashboard-email-consumer`) |
| `scripts/email_template.py` | Single canonical OASIS AI branded HTML email template | library (imported by send/funnel scripts) |
| `scripts/enrich_oasis_leads.py` | Fill missing phone + first name on OASIS leads | CLI (manual) |
| `scripts/ensure_cockpit.py` | Ensure the Bravo Console cockpit terminal is alive | SessionStart hook |
| `scripts/generate_changelog.py` | Generate a conventional-commits → CHANGELOG.md draft from `git log` | CLI (manual) |
| `scripts/oasis_embed_server.py` | OASIS Town V6 Apex Phase 3 — embedding + retrieval bridge for the agent sim | server (on-demand) |
| `scripts/provision_client_tenant.py` | Provision a client tenant in Supabase (auth user, role, manifest seed) | CLI (onboarding) |
| `scripts/provision_secrets.py` | Materialize a tenant's integration secrets onto this host | CLI (onboarding) |
| `scripts/quest_publisher.py` | Publish memory/ACTIVE_TASKS.md tasks to Supabase `oasis_quests` table | CLI (`publish` / `loop`) |
| `scripts/run_sql_via_mgmt_api.py` | One-shot — run a SQL file against oasis via the Supabase Management API | CLI (DBA) |
| `scripts/schedule_helpers.py` | Local-time cron parsing + quiet-day awareness | library (cron_engine + scheduler) |
| `scripts/security_audit.py` | Empire-wide security audit — seven independent scans, one report | CLI (manual / deploy gate) |
| `scripts/set_secret.py` | Safely set keys in `.env.agents` without an editor | CLI (manual) |
| `scripts/smoke_n8n_inbound_rpc.py` | End-to-end smoke test for the n8n inbound bridge | CLI (manual) |
| `scripts/wiki_link_auditor.py` | Audit broken Obsidian `[[wikilinks]]` in brain/ and memory/ | CLI (manual) |

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
