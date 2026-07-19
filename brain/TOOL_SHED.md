---
name: TOOL_SHED
description: Master catalog of every GitHub repo wired into CC's empire — shareable with clients, prospects, and future self
type: reference
tags: [catalog, repos, tools, sharing, infrastructure]
created: 2026-04-21
updated: 2026-07-17
last_updated: 2026-07-17
freshness_threshold_days: 30
verified: 2026-07-17
---
# 🧰 TOOL SHED — CC's GitHub Repository Catalog

> A curated inventory of every repo that powers CC's empire, organized so it's useful as both an internal reference AND a shareable asset for clients, prospects, and Skool members.
>
> **Philosophy:** Every repo here has a clear use case. No slop, no bloat, no "I installed this once and forgot why."
>
> **Shareable?** Yes. Sections 1-7 can be shared publicly. Section 8 (install commands) assumes CC's environment.

---

## ⚡ Quick Use-Case Router

When someone asks you for a solution, send them here. **All repo names are clickable GitHub URLs.** If you're pasting this into a plain-text channel (email, SMS, Slack without markdown), use the **Plain-Text Export** at the bottom of this doc.

| Someone needs... | Send them this repo |
|------------------|---------------------|
| "How do I use AI to code faster?" | [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) + [Claude Code](https://claude.com/claude-code) |
| "I want AI agents that remember across sessions" | [wshobson/agents](https://github.com/wshobson/agents) (Pensyve memory) |
| "I need to run 20 AI agents in parallel on one codebase" | [Dicklesworthstone/claude_code_agent_farm](https://github.com/Dicklesworthstone/claude_code_agent_farm) |
| "I want drop-in AI personas for my workflow" | [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (131+ personas) |
| "I want to save my Claude sessions and search them later" | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) (already in CC's stack) |
| "I need to automate my DMs and capture leads" | [CC90210/ig-setter-pro](https://github.com/CC90210/ig-setter-pro) (PULSE) |
| "I need a real estate CRM" | [CC90210/real-estate-App](https://github.com/CC90210/real-estate-App) (PropFlow) |
| "I want live song requests at my gigs" | [CC90210/nostalgic-requests](https://github.com/CC90210/nostalgic-requests) |
| "I run a field service business (HVAC, landscaping, etc.)" | [CC90210/gritly](https://github.com/CC90210/gritly) |
| "I run a daycare and need attendance tracking" | [CC90210/tiktik](https://github.com/CC90210/tiktik) |
| "I need a lead capture funnel with payment" | Native Command Center funnel at `oasisai.work/f/` (cc-funnel repo RETIRED 2026-06-18) |
| "I sell Shopify products and want AI ad videos" | [CC90210/shopify-ad-engine](https://github.com/CC90210/shopify-ad-engine) |
| "I need a compliance/EDI/POS agent for wholesale" | [CC90210/hermes](https://github.com/CC90210/hermes) (Hermes — public, OASIS-built) |
| "I want an AI CFO watching my finances" | [CC90210/CFO-Agent](https://github.com/CC90210/CFO-Agent) (Atlas) |
| "I want an AI marketer writing & shipping my content" | [CC90210/CMO-Agent](https://github.com/CC90210/CMO-Agent) (Maven) |
| "I want an AI running my smart home" | [CC90210/Aura-Home-Agent](https://github.com/CC90210/Aura-Home-Agent) |
| "I need to scrape a website and structure the data" | [firecrawl/firecrawl-mcp-server](https://github.com/firecrawl/firecrawl-mcp-server) + [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) |
| "I need to scan my code for security issues before shipping" | [carlrannaberg/claudekit](https://github.com/carlrannaberg/claudekit) |
| "I want to query my Obsidian vault with AI" | [cyanheads/obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server) |
| "I need a Postgres performance-tuning MCP" | [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) |
| "I just inherited a codebase and need an instant architecture map" | [safishamsi/graphify](https://github.com/safishamsi/graphify) |

---

## 🏗️ Section 1: CC's Apps (CC90210 — What's Been Built)

All production repos owned by CC. These are the "source code" CC can point clients to.

| App | Repo | Stack | Use Case | Status |
|-----|------|-------|----------|--------|
| **OASIS AI Platform** | [CC90210/oasis-ai-platform](https://github.com/CC90210/oasis-ai-platform) | React 18, Vite, Supabase | Agency lead gen + client dashboard | Live |
| **PropFlow** | [CC90210/real-estate-App](https://github.com/CC90210/real-estate-App) | Next.js 14, Supabase, Stripe | Real estate CRM (50-50 w/ Adon) | Active build |
| **Nostalgic Requests** | [CC90210/nostalgic-requests](https://github.com/CC90210/nostalgic-requests) | Next.js, Supabase, Stripe Connect | Live-event song request + tipping | Live |
| **Gritly** | (pending) | Next.js 15, Drizzle, Better Auth, Stripe, Turso | Field service management (FSM) | Pre-launch |
| **TIKTIK** | [CC90210/tiktik](https://github.com/CC90210/tiktik) | Next.js 14, Supabase, Tailwind | Daycare attendance tracking | Live — tiktik-psi.vercel.app |
| **CC Funnel** | [CC90210/cc-funnel](https://github.com/CC90210/cc-funnel) | Next.js 14, Supabase | Lead capture funnel | **RETIRED 2026-06-18** — replaced by native funnel at oasisai.work/f/ (see APP_REGISTRY) |
| **IG Setter Pro** (PULSE) | [CC90210/ig-setter-pro](https://github.com/CC90210/ig-setter-pro) | Next.js 14, Turso, n8n, Claude API | Instagram DM automation + lead capture | Live |
| **Shopify Ad Engine** | [CC90210/shopify-ad-engine](https://github.com/CC90210/shopify-ad-engine) | Remotion, React 19, Three.js, Meta Ads API | Programmatic Shopify video ad generation | Client-ready |
| **Grape Vine Cottage** | [CC90210/grapevinecottage](https://github.com/CC90210/grapevinecottage) | Vite, React 18, Shadcn | Cottage booking site | Live |
| **On The Hill** | [CC90210/ON-THE-HILL](https://github.com/CC90210/ON-THE-HILL) | Vite, React 19 | Venue/restaurant site | Dev |
| **Mindset Companion** | [CC90210/MINDSET-COMPANION-LUCID](https://github.com/CC90210/MINDSET-COMPANION-LUCID) | Next.js 16, React 19 | Mindset/journaling app | Dev |
| **Lafreniere PM** | [CC90210/lafreniere-pm](https://github.com/CC90210/lafreniere-pm) | Next.js 16, Supabase, Stripe | Property management (Ty client) | Pre-launch |
| **Hermes** | [CC90210/hermes](https://github.com/CC90210/hermes) | Python 3.12, FastAPI, SQLite, Ollama OR Anthropic/OpenAI (DPA), pywinauto (A2000 desktop), Playwright (web ERPs), reportlab (GS1-128 labels) | EDI/POS compliance + A2000 takeover for wholesale (Emmanuel Lowinger) | v0.2.0 — demo public at [cc90210.github.io/hermes](https://cc90210.github.io/hermes/) |

### Agent Triad (CC's AI Operating System)

| Agent | Repo | Role | Key Tech |
|-------|------|------|----------|
| **Bravo** (CEO) | [CC90210/CEO-Agent](https://github.com/CC90210/CEO-Agent) | All-ops orchestrator, architecture, routing | Claude (fable-5 standard), Supabase, n8n — agent roster: CAPABILITY_GRAPH totals (32 nodes) |
| **Atlas** (CFO) | [CC90210/CFO-Agent](https://github.com/CC90210/CFO-Agent) | Financial advisory + tax compliance (pivoted from autonomous trading 2026-04-14) | Python, local Claude CLI, CRA + Revenu Quebec-aware tax calc |
| **Maven** (CMO) | [CC90210/CMO-Agent](https://github.com/CC90210/CMO-Agent) | Content, brand voice, ad campaigns | Meta + Google Ads SDKs, Remotion, Python |
| **Aura** (Home) | [CC90210/Aura-Home-Agent](https://github.com/CC90210/Aura-Home-Agent) | Smart home + life habits | Raspberry Pi 5, Home Assistant, ESP32, voice agent |

---

## 🤖 Section 2: Claude Code Extension Ecosystem

The curated lists, plugins, and toolkits that make Claude Code 10x more useful.

### The Canonical Awesome Lists
- **[hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)** — 40K ⭐ — THE hub. Skills, hooks, slash commands, CLAUDE.md examples. Sweep monthly.
- **[msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents)** — 132K ⭐ — ~263 personas, 17 divisions, MIT, very actively maintained. **Cherry-pick ONLY — never run its install.sh/convert.sh against a guard-based harness** (most files ship no `tools:`/`model:` → full default tool surface). V7.2.0 imported 10 hand-scoped (see `agents/INDEX.md` § Agency Imports) + 2→Atlas + 2→Maven.
- **[VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents)** — 17.8K ⭐ — 131+ drop-in subagent personas across 10 categories (dev, security, data/AI, infra).
- **[rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit)** — 1.4K ⭐ — Kitchen-sink aggregator. Lower signal-to-noise but useful for discovery.

### Top 10 Claude Code Extension Repos (Signal-Ranked)

| Rank | Repo | Stars | Why It Matters |
|------|------|-------|----------------|
| 1 | [wshobson/agents](https://github.com/wshobson/agents) | 34K | 184 specialized agents + **Pensyve** cross-session memory + 3-tier model routing (Opus/Sonnet/Haiku) |
| 2 | [carlrannaberg/claudekit](https://github.com/carlrannaberg/claudekit) | 663 | Git-stash auto-checkpointing, quality hooks, 6-agent parallel code review. Starred by Simon Willison. |
| 3 | [Dicklesworthstone/claude_code_agent_farm](https://github.com/Dicklesworthstone/claude_code_agent_farm) | 785 | Run 20-50 agents in parallel on one codebase with file-level locks + tmux dashboard |
| 4 | [steipete/claude-code-mcp](https://github.com/steipete/claude-code-mcp) | 1.2K | Wraps Claude Code as an MCP server — "agent in your agent" delegation pattern |
| 5 | [barkain/claude-code-workflow-orchestration](https://github.com/barkain/claude-code-workflow-orchestration) | — | Auto task decomposition + parallel agent execution |
| 6 | [ruvnet/ruflo](https://github.com/ruvnet/ruflo) | 32.6K | Multi-agent swarm platform with RAG. v3.5.80 active April 2026. |
| 7 | [VILA-Lab/Dive-into-Claude-Code](https://github.com/VILA-Lab/Dive-into-Claude-Code) | — | Academic architectural analysis. Research > toolkit. |
| 8 | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 162K* | 48 agents, 183 skills, 79 commands, AgentShield security. *Star count anomalous — audit before adopting wholesale. |

### Already in CC's Stack
- **[claude-mem](https://github.com/thedotmack/claude-mem)** — Session memory + search across conversations (installed as plugin)
- **[Codex Plugin](https://github.com/openai/codex)** (OpenAI Codex integration) — Dual-AI delegation for backend-heavy work

---

## 🔌 Section 3: MCP Servers

### Registered in `.claude/mcp.json` (9 — live source of truth; supabase/late/n8n below are CLI-replaced for agents, kept as dashboard/enabled extras)

| MCP | Purpose | Config |
|-----|---------|--------|
| **playwright** | Browser automation, E2E testing, scraping | `@playwright/mcp@latest` |
| **context7** | Real-time library/API docs — always current | `@upstash/context7-mcp@latest` |
| **memory** | Session-scoped memory | `@modelcontextprotocol/server-memory` |
| **sequential-thinking** | Extended reasoning chains | `@modelcontextprotocol/server-sequential-thinking` |
| **knowledge-graph** | Obsidian vault graph traversal | Custom TS MCP |
| **filesystem** | Sandboxed file access | Official MCP |
| **github** | GitHub ops (shim injects token) | `scripts/mcp_shims/github.js` |
| **firecrawl** | Structured web scraping | Firecrawl API wrapper |
| **obsidian** | Vault operations | Registered in mcp.json |
| **supabase** | DB queries, migrations, edge fns | Official Supabase MCP |
| **late/zernio** | Social media scheduling | Late API wrapper |
| **n8n-mcp** | Workflow automation | Community package |

### Recommended Adds (Priority Order)

| MCP | Repo | Why Add It | Effort |
|-----|------|-----------|--------|
| **Obsidian MCP** | [cyanheads/obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server) | 459 ⭐ — Closes the loop between Bravo's actions and CC's Obsidian vault. 8 tools: read/write notes, regex search, frontmatter/tag management. | Requires Obsidian Local REST API plugin + 1 MCP.json entry |
| **Postgres MCP Pro** | [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp) | 2.6K ⭐ — Index tuning, query plan explain, `pg_stat_statements` analysis. Read-only mode for prod. Huge for client DB work. | 1 MCP.json entry + connection string |
| **Graphify** | [safishamsi/graphify](https://github.com/safishamsi/graphify) | 41.9K ⭐ — Tree-sitter knowledge graph builder for codebases. Outputs Obsidian vault, Neo4j cypher, GraphML. Surfaces "god nodes" + cross-module connections. **NOT for Bravo** (CAPABILITY_GRAPH.json + smart_explore + Obsidian graph already cover this). **PILOT on next client app onboarding** (Hermes, OASIS Platform, PropFlow) — generates an instant architecture map for handoff. | 5 min `/graphify` per app |
| **Official GitHub MCP** | [github/github-mcp-server](https://github.com/github/github-mcp-server) | 29.1K ⭐ — Official GitHub MCP. 19 tool categories, OAuth scope filtering. Optional: `gh` CLI already covers this. | Optional — current `gh` setup works fine |

### Dead/Broken
- ~~Stripe MCP~~ — `v0.3.1` broke with proxy mode. Use `scripts/integrations/stripe_tool.py` instead.

---

## 💼 Section 4: Business Automation APIs

The third-party platforms CC's empire runs on. Each has a CLI wrapper in `scripts/` (CLI-first > MCP — more reliable).

| Service | CLI Wrapper | Use Case |
|---------|-------------|----------|
| **Stripe** | `scripts/integrations/stripe_tool.py` | Payments, subscriptions, Connect accounts |
| **Supabase** | `scripts/integrations/supabase_tool.py` | Postgres DB + auth + storage + edge functions |
| **n8n** | `scripts/integrations/n8n_tool.py` | Workflow automation, Telegram routing, DM flows |
| **Late/Zernio** | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | Multi-platform social scheduling |
| **Google Workspace** | `scripts/integrations/google_tool.py` | Gmail, Sheets, Drive, Calendar |
| **GitHub** | `gh` CLI (`/c/Program Files/GitHub CLI/gh.exe`) | Repos, PRs, issues, actions |
| **Firecrawl** | MCP wrapper | Structured web scraping |
| **Turso/libSQL** | Native client libs | Serverless SQLite (ig-setter-pro, Gritly) |

**Rule:** Never hardcode credentials. All secrets live in `.env.agents` (gitignored).

---

## 🎬 Section 5: Content & Media Pipeline

When CC says "make this a post," this stack runs end-to-end.

| Tool | Purpose | How It's Wired |
|------|---------|----------------|
| **[FFmpeg 8.0.1](https://ffmpeg.org)** | Video encoding, transcoding, compositing | `scripts/edit_content.py` wrapper |
| **[OpenAI Whisper](https://github.com/openai/whisper)** | Audio → SRT with word-level timestamps | Pip `openai-whisper` |
| **[ElevenLabs](https://elevenlabs.io)** | Voiceover synthesis | Pip `elevenlabs` + API key |
| **[Remotion 4.0.431](https://www.remotion.dev)** | React-based programmatic video | npm `remotion` + `@remotion/cli` + `@remotion/renderer` |
| **[Three.js](https://threejs.org)** | 3D graphics in video ads | Shopify Ad Engine dependency |

**Pipeline:** Raw iPhone video → Whisper transcription → FFmpeg trim/color → Remotion captions + B-roll → export → Late/Zernio multi-post.

---

## 🧠 Section 6: Research Inspirations (Patterns, Not Forks)

Papers and repos whose *ideas* CC adopted into his brain architecture. Credit where due.

| Pattern | Source | Where It Lives in CC's Stack |
|---------|--------|------------------------------|
| **Skill compositionality** | [Voyager (NVIDIA)](https://voyager.minedojo.org) | `brain/GROWTH.md` — skills built from simpler components |
| **Structured failure analysis** | [Reflexion paper](https://arxiv.org/abs/2303.11366) | `brain/BRAIN_LOOP.md` Step 7 |
| **Multi-hypothesis search** | [LATS paper](https://arxiv.org/abs/2310.04406) | `brain/BRAIN_LOOP.md` Step 4 (2-3 approaches, rank, backtrack) |
| **Heartbeat / merge window** | OpenClaw pattern | `brain/HEARTBEAT.md` |
| **NEPQ sales methodology** | [Jeremy Miner](https://www.7thlevelhq.com) | `../CMO-Agent/brain/CONTENT_BIBLE.md` (Maven canonical) — outreach scripts |
| **Plan/Execute/Prime/Commit workflow** | [Cole Medin (coleam00)](https://github.com/coleam00) | `.agents/commands/*.md` |
| **CLI-Anything methodology** | [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) | `skills/cli-anything/SKILL.md` + `scripts/cli_templates/` |
| **3-tier model routing** | [wshobson/agents](https://github.com/wshobson/agents) | Opus for critical, Sonnet for complex, Haiku for fast ops |

---

## 🚀 Section 7: Recommended Next Adds (Prioritized)

Not noise — these move the needle.

1. **[claudekit](https://github.com/carlrannaberg/claudekit)** — Drop in the git-stash checkpoint hook. Prevents the "I was 80% done and lost work" failure mode during risky refactors. **Effort: 10 min. Value: prevents losing work.**
2. **[cyanheads/obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server)** — Bravo writes to/queries the Obsidian vault directly. Massive leverage given CC's Obsidian graph is the second brain. **Effort: 30 min (requires Obsidian Local REST API plugin). Value: compounding.**
3. **[VoltAgent subagent personas](https://github.com/VoltAgent/awesome-claude-code-subagents)** — Cherry-pick `security-auditor`, `competitive-analyst`, `market-researcher` for drop-in delegation. **Effort: 5 min per persona. Value: immediate.**
4. **[Postgres MCP Pro](https://github.com/crystaldba/postgres-mcp)** — Add when taking on clients with their own Postgres (not Supabase). Index tuning + query plan analysis. **Effort: 1 hr per client. Value: billable expertise.**
5. **[Graphify](https://github.com/safishamsi/graphify)** — Run `/graphify` on a client app at onboarding to generate an instant codebase map (god nodes, cross-module connections, Obsidian export). Skip on Bravo itself — already covered by CAPABILITY_GRAPH + smart_explore. **Effort: 5 min per client app. Value: faster client codebase comprehension + visual deliverable.**

---

## 📦 Section 8: Install One-Liners (CC's Environment)

```bash
# Clone any of CC's apps into the standard location
cd /c/Users/User/APPS
gh repo clone CC90210/<repo-name>

# Add an MCP server to Claude Code config
# Edit: /c/Users/User/Business-Empire-Agent/.claude/mcp.json
# Edit: /c/Users/User/Business-Empire-Agent/.vscode/mcp.json  (Antigravity)
# Edit: ~/.gemini/settings.json  (Gemini CLI)
# All three must stay in sync — see CLAUDE.md Rule 4.

# Install claudekit
npm install -g @carlrannaberg/claudekit
# Then add hooks to .claude/settings.local.json per its README

# Install a VoltAgent subagent persona
# Download the .md from their repo → drop into agents/
# Bravo auto-registers personas in agents/INDEX.md
```

---

## 🛰️ Section 9: Free-Tier Radar

> Curated free-tier services + free public APIs mapped to REAL empire capability gaps and cost lines — sourced from the 2026-07-17 six-repo audit ([ripienaar/free-for-dev](https://github.com/ripienaar/free-for-dev), [public-apis/public-apis](https://github.com/public-apis/public-apis)). **Never mirror the upstream lists** (free-for-dev has NO license and churns daily; public-apis ships no data files and its query API api.publicapis.org is DEAD — DNS verified failing 2026-07-17). Fetch upstream on demand: `https://raw.githubusercontent.com/ripienaar/free-for-dev/master/README.md` (use TOC anchors, e.g. `#code-quality`) · `https://raw.githubusercontent.com/public-apis/public-apis/master/README.md`.
>
> **Row contract (machine-parsed):** this table is parsed by `scripts/build_capability_graph.py` `discover_resources()` into `resource:` nodes — keep the column order. `Slug` = kebab-case unique ID. `Status` ∈ `candidate` (needs CC signup/decision) | `adopted` (wired in) | `rejected` (evaluated, declined — reason in Conflicts) | `policy` (a rule, not a service). Keyed adoptions go: row here → `docs/ENV_KEYS_TEMPLATE.md` entry → CC signs up + hand-adds key to `.env.agents` → `scripts/integrations/<name>_tool.py` wrapper via `lib.secret_loader` → `integration_health.ping()` → SEED_JOBS health row.

| Slug | Capability | Service | Free Tier | Auth | Status | Conflicts / Replaces | Verified |
|------|-----------|---------|-----------|------|--------|----------------------|----------|
| healthchecks-deadman | cron dead-man-switch monitoring | [Healthchecks.io](https://healthchecks.io) | 20 checks, ping-by-URL | apiKey | candidate | none — closes the "crons report failure only from within; a dead host is invisible" blind spot. TOP PICK | 2026-07-17 |
| uptimerobot-uptime | external uptime probes | [UptimeRobot](https://uptimerobot.com) | 50 monitors @ 5-min | apiKey | candidate | none — all current monitoring runs ON the box it monitors; probe Hostinger n8n VPS + Vercel sites + Command Center | 2026-07-17 |
| betterstack-uptime | external uptime + status page | [BetterStack](https://betterstack.com) | 10 monitors | apiKey | candidate | overlaps uptimerobot-uptime — pick ONE external prober | 2026-07-17 |
| sentry-errors | error tracking for the agent runtime | [Sentry](https://sentry.io) | 5k errors/mo | apiKey (DSN) | candidate | none in Bravo (only local structured_log jsonl); Breeze app already uses Sentry — copy that pattern | 2026-07-17 |
| codecov-coverage | test-coverage reporting | [Codecov](https://codecov.io) | free for public repos | apiKey (token) | candidate | none — coverage is currently terminal-only; wire into .github/workflows/ | 2026-07-17 |
| sonarcloud-sast | hosted SAST / code quality | [SonarCloud](https://sonarcloud.io) | free for OSS | apiKey | candidate | overlaps codeql-sast — pick ONE; local ruff/mypy/security_audit.py stay regardless | 2026-07-17 |
| codeql-sast | SAST in GitHub Actions | [CodeQL](https://codeql.github.com) | free for public repos | none (GH-native) | candidate | overlaps sonarcloud-sast — pick ONE | 2026-07-17 |
| disify-email-validate | disposable/format email validation | [Disify](https://www.disify.com) | unlimited, no signup | none (browser UA header required — default python UA is 403-blocked) | adopted | none — standalone `scripts/integrations/email_validate_tool.py`; send_gateway wiring is a separate approved task | 2026-07-17 |
| caldays-holidays | public-holiday API | [caldays](https://caldays.com) | free, no signup | none | rejected | `is_quiet_day` already works OFFLINE — an external API inside cron scheduling adds a failure mode for zero gain | 2026-07-17 |
| exchangerate-fx | live FX rates | [Exchangerate.host](https://exchangerate.host) | free tier | none/apiKey | candidate | ATLAS-OWNED — Bravo never owns finance; pointer for CFO-Agent when cross-border deals need FX | 2026-07-17 |
| firecrawl-fallback | scraping cost reduction | Playwright + BeautifulSoup (already in-repo) | n/a | n/a | policy | prefer un-metered Playwright/bs4 before spending Firecrawl credits (research_fetch ladder already encodes this) | 2026-07-17 |
| elevenlabs-free-tier | TTS cost reduction | [ElevenLabs free tier](https://elevenlabs.io) | 10k chars/mo | apiKey | candidate | powwow cron is disabled on a dead metered key — free tier may cover the ~daily voice note after the claude_cli port | 2026-07-17 |
| enrichment-free-tiers | lead-enrichment cost check | [Apollo](https://apollo.io) / [Clearbit](https://clearbit.com) free tiers | limited credits/mo | apiKey | candidate | both ALREADY integrated (GHL/Apollo/Clearbit keys exist) — audit current plan usage before paying more, don't add a 3rd vendor | 2026-07-17 |
| vps-alternatives | n8n host cost question | [Oracle Cloud Always-Free](https://www.oracle.com/cloud/free/) / [Fly.io](https://fly.io) | always-free VM tiers | account | candidate | Hostinger VPS is the ONE fixed recurring host cost; migration is a real op with downtime risk — decision, not a quick win | 2026-07-17 |

**Closed slots (do not propose alternatives here):** DNS = Cloudflare (free, wired) · hosting = Vercel + Hostinger VPS · DB = Supabase (multi-project) · payments = Stripe · email = send_gateway → Gmail SMTP/OAuth ONLY (direct Resend/SendGrid/SES/Mailgun calls are architecturally banned) · SMS = TextTorrent + Twilio + Kixie (already triple-covered — consolidate, never add) · scraping = Firecrawl + Playwright + bs4 · TTS = ElevenLabs · vector = LanceDB + fastembed (local) · CI = GitHub Actions.

---

## 📚 Section 10: Learning & R&D References

> Education/reference repos from the 2026-07-17 six-repo audit. These are **reading material, not integrations** — nothing here installs, trains the model, or adds capability today. Fetch individual files on demand when the need arises.

| Repo | License | Honest one-liner | When to reach for it |
|------|---------|------------------|----------------------|
| [rasbt/LLMs-from-scratch](https://github.com/rasbt/LLMs-from-scratch) | Apache-2.0 | Build-a-GPT book code (tokenization → GPT-2-class pretrain → finetune). Pretraining is NOT laptop-viable; LoRA finetuning of small checkpoints is. | **When the own-LLM project greenlights**: Appendix E (LoRA on one GPU), ch06 (classification finetune), ch07 (instruction + DPO) are the recipes. Sequel: `rasbt/reasoning-from-scratch`. |
| [eriklindernoren/ML-From-Scratch](https://github.com/eriklindernoren/ML-From-Scratch) | MIT | NumPy-only reimplementations of ~30 classic ML/DL algorithms. **Stale since Oct 2019; `pip install` is broken** (dead `sklearn` shim, unpinned deps). | "Explain how algorithm X works internally" — read the single relevant `.py` on demand. Never install/run as-is; scikit-learn is the production answer. |
| [GokuMohandas/Made-With-ML](https://github.com/GokuMohandas/Made-With-ML) | MIT | MLOps course (design→data→model→serve→monitor). Classic supervised-ML ops, NOT agent-eval content despite the "llms" tag. | Two patterns already imported V7.1.0: slice-based eval + versioned eval-run records (both live in `harness_eval.py`). Revisit if an actual ML training workload ever lands. |
| [EbookFoundation/free-programming-books](https://github.com/EbookFoundation/free-programming-books) | CC-BY-4.0 | Link directory of free programming books. Explicitly low value for an agent (an LLM doesn't learn from having book links in-repo); kept at CC's request as a bookmark. | Literal "is there a good free book on X?" question — grep `books/free-programming-books-subjects.md` via raw fetch. Prefer Context7/live docs for actual technical reference. |

---

## 🔗 Obsidian Links
- [[brain/SOUL]] | [[brain/APP_REGISTRY]] | [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]]
- [[memory/MEMORY_INDEX]] | [[../CMO-Agent/brain/CONTENT_BIBLE]] (Maven canonical)

---

## Install Status Log

**2026-04-21:**
- ✅ `claudekit` v0.9.x installed globally. Hooks wired: `file-guard` (PreToolUse), `create-checkpoint` + `self-review` (Stop/SubagentStop). Config: `.claude/settings.json`.
- ✅ VoltAgent subagents (5): `security-auditor`, `code-reviewer`, `competitive-analyst`, `market-researcher`, `api-designer` → `agents/voltagent/`.
- ✅ VS Code extensions: Error Lens v3.28.0 + REST Client v0.25.0 installed in Antigravity.
- ⚠️ Obsidian MCP: wrapper + 3-file config synced. **PENDING:** CC must install "Local REST API" plugin in Obsidian, copy API key → add `OBSIDIAN_API_KEY=...` to `.env.agents`, then restart IDE.

## 📋 Plain-Text Export (copy-paste into email, SMS, Slack, WhatsApp)

> These are the same links above but in raw-URL format so they render in ANY channel — not just markdown viewers. Copy any block and paste directly.

### CC's Production Apps
```
OASIS AI Platform     https://github.com/CC90210/oasis-ai-platform
PropFlow (real estate) https://github.com/CC90210/real-estate-App
Nostalgic Requests     https://github.com/CC90210/nostalgic-requests
TIKTIK (daycare)       https://github.com/CC90210/tiktik
CC Funnel (RETIRED)    https://github.com/CC90210/cc-funnel  # replaced by native funnel oasisai.work/f/
IG Setter Pro (PULSE)  https://github.com/CC90210/ig-setter-pro
Shopify Ad Engine      https://github.com/CC90210/shopify-ad-engine
Grape Vine Cottage     https://github.com/CC90210/grapevinecottage
On The Hill            https://github.com/CC90210/ON-THE-HILL
Mindset Companion      https://github.com/CC90210/MINDSET-COMPANION-LUCID
Lafreniere PM          https://github.com/CC90210/lafreniere-pm
```

### CC's AI Agent Triad
```
Bravo (CEO/CTO Agent)  https://github.com/CC90210/CEO-Agent
Atlas (CFO Agent)      https://github.com/CC90210/CFO-Agent
Maven (CMO Agent)      https://github.com/CC90210/CMO-Agent
Aura (Home Agent)      https://github.com/CC90210/Aura-Home-Agent
```

### Top 10 Claude Code Extension Repos (2026)
```
1. wshobson/agents                    https://github.com/wshobson/agents
2. carlrannaberg/claudekit            https://github.com/carlrannaberg/claudekit
3. VoltAgent subagents                https://github.com/VoltAgent/awesome-claude-code-subagents
4. Dicklesworthstone/agent_farm       https://github.com/Dicklesworthstone/claude_code_agent_farm
5. steipete/claude-code-mcp           https://github.com/steipete/claude-code-mcp
6. ruvnet/ruflo                       https://github.com/ruvnet/ruflo
7. hesreallyhim/awesome-claude-code   https://github.com/hesreallyhim/awesome-claude-code
8. affaan-m/everything-claude-code    https://github.com/affaan-m/everything-claude-code
9. rohitg00/awesome-claude-code-toolkit https://github.com/rohitg00/awesome-claude-code-toolkit
10. VILA-Lab/Dive-into-Claude-Code    https://github.com/VILA-Lab/Dive-into-Claude-Code
```

### MCP Servers Worth Running
```
Playwright MCP          https://github.com/microsoft/playwright-mcp
Supabase MCP            https://github.com/supabase-community/supabase-mcp
Context7 MCP            https://github.com/upstash/context7
Firecrawl MCP           https://github.com/firecrawl/firecrawl-mcp-server
GitHub MCP (official)   https://github.com/github/github-mcp-server
Obsidian MCP (cyanheads) https://github.com/cyanheads/obsidian-mcp-server
Postgres MCP Pro        https://github.com/crystaldba/postgres-mcp
Graphify (codebase KG)  https://github.com/safishamsi/graphify
Memory MCP              https://github.com/modelcontextprotocol/servers
Sequential Thinking MCP https://github.com/modelcontextprotocol/servers
n8n MCP (community)     https://github.com/czlonkowski/n8n-mcp
Late/Zernio API         https://zernio.com
```

### Content & Media Pipeline
```
Remotion (programmatic video) https://github.com/remotion-dev/remotion
FFmpeg (encoding)             https://ffmpeg.org
OpenAI Whisper (transcription) https://github.com/openai/whisper
ElevenLabs (voice)            https://elevenlabs.io
```

### Research Inspirations (patterns, not forks)
```
Voyager (NVIDIA)          https://voyager.minedojo.org
Reflexion paper           https://arxiv.org/abs/2303.11366
LATS paper                https://arxiv.org/abs/2310.04406
CLI-Anything methodology  https://github.com/HKUDS/CLI-Anything
Cole Medin's repos        https://github.com/coleam00
Jeremy Miner NEPQ         https://www.7thlevelhq.com
```

---

## 🔒 Security Context (when sharing)

- **These are ALL public repos.** (Hermes was made public 2026-04-27 to host the Emmanuel demo at https://cc90210.github.io/hermes/ — it has no client secrets in tree.)
- **The Tool Shed doc itself is shareable** — no credentials, no business logic, no internal paths exposed.
- **What's NOT in this doc (intentionally):** `.env.agents`, client databases, API keys, MRR figures, the `memory/` journals.
- **When publishing as a Gist:** strip this "Security Context" section and the "Maintenance" section below — those are for CC, not external readers.

---

## Maintenance

- **Owner:** Bravo (CTO, on behalf of CC)
- **Update trigger:** Any new repo clone, MCP install, or major integration. Log the entry here BEFORE committing the install.
- **Publish protocol:** When CC is ready to share publicly — copy Sections 1-7 + Plain-Text Export into a GitHub Gist, strip internal commentary, link from oasisai.work, email signature, Skool.
- **Last full audit:** 2026-04-21
- **2026-05-03:** Added Graphify (Section 3 + Section 7 + Use-Case Router + Plain-Text Export). Pilot trigger: next client app onboarding (Hermes/OASIS Platform/PropFlow). Skipped Caveman (client-comm voice protection) and CodeBurn (subscription plans, premature until metered API client deploys).
- **2026-07-17 (V7.1):** Added Section 9 Free-Tier Radar (curated from free-for-dev + public-apis six-repo audit; machine-parsed into `resource:` capability-graph nodes) — 14 rows, 1 adopted (Disify), 1 rejected (caldays), 1 policy, 11 candidates awaiting CC picks. Upstream lists deliberately NOT mirrored (license/churn/schema).
- **Companion docs:** [[brain/CLIENT_PLAYBOOK]] (meeting + security material) · [[brain/BENCHMARK]] (sentience + capability score)

## Related

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
