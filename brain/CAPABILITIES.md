# CAPABILITIES — Tool & Integration Registry

> Complete inventory of what Bravo can do. Updated when new tools are added.

## MCP Servers (By Interface)

### Claude Code (Opus 4.6 — Lead Architect)
| Server | Purpose | Key Tools |
|--------|---------|-----------|
| **Playwright** | Browser automation, ALL web research, scraping, testing | navigate, snapshot, click, type, evaluate |
| **Context7** | Live library documentation lookup | resolve-library-id, query-docs |
| **Memory** | Persistent knowledge graph across sessions | create_entities, search_nodes, open_nodes |
| **n8n** | Workflow automation management (community n8n-mcp via REST API) | search_workflows, execute_workflow, get_workflow_details |
| **Late** | Social media posting (8+ platforms) | posts_create, posts_list, accounts_list, posts_cross_post |
| **Sequential Thinking** | Structured multi-step reasoning | sequentialthinking |

| **Supabase** | Database queries, migrations, schema management | execute_sql, list_tables, apply_migration |
| **Stripe** | Payments, subscriptions, invoices | Stripe MCP tools |

### Anti-Gravity IDE (Native Local Agent — Multi-Model)

Models: Gemini 3.1 Pro High/Low, Gemini 3 Flash, Claude Sonnet/Opus 4.6, GPT-OSS 120B Medium
Entry Point: `ANTIGRAVITY.md` | Config: `.vscode/mcp.json`
Workflows: `.agents/workflows/` (11 workflows: post, status, health, prime, content, commit, n8n, sync, research, debug, client-onboard)

**IMPORTANT — Windows env var pattern:** n8n and Late use `cmd /c wrapper.cmd` scripts (in `scripts/`) that `set` env vars before launching. Direct `env` blocks in JSON configs do NOT work on Windows. See `scripts/n8n-mcp-wrapper.cmd` and `scripts/late-mcp-wrapper.cmd`.

| Server | Purpose | Config |
|--------|---------|--------|
| **n8n-mcp** | Workflow automation (44 workflows, REST API) | `cmd /c scripts/n8n-mcp-wrapper.cmd` |
| **Late** | Social media posting (8+ platforms) | `cmd /c scripts/late-mcp-wrapper.cmd` |
| **Playwright** | Browser automation, web research | npx @playwright/mcp --headless |
| **Context7** | Live library documentation | npx @upstash/context7-mcp |
| **Memory** | Persistent knowledge graph | npx @modelcontextprotocol/server-memory |
| **Sequential Thinking** | Multi-step reasoning | npx @modelcontextprotocol/server-sequential-thinking |

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
- MCP Access (via `.gemini/settings.json`): n8n, Late, Playwright, Context7, Memory, Sequential Thinking (6 active servers)
- SDK Tools: `python scripts/supabase_tool.py`, `python scripts/stripe_tool.py` (replaces broken MCP servers)
- Note: Config synced with `.vscode/mcp.json`. n8n, Late, Supabase, and Stripe use `cmd /c wrapper.cmd` pattern for env vars.

## Supabase Projects

| Project | Region | Purpose |
|---------|--------|---------|
| **Bravo** | us-west-2 | Agent intelligence database (10 tables) |
| **nostalgic-requests** | us-west-2 | Nostalgic Requests platform |
| **oasis-ai-platform** | us-west-2 | OASIS AI platform |

**Organizations:** CC (oktipozhyojufxsytrse), oasis-ai-platform (sajanpiqysuwviucycjh)

## App Registry (6 External Repos)

Full routing table with local paths, GitHub URLs, tech stacks: `brain/APP_REGISTRY.md`

| App | Local Path | Stack |
|-----|-----------|-------|
| OASIS AI Platform | `APPS/oasis-ai-platform` | React 18, Supabase |
| PropFlow | `realestate-App` | Next.js 14, Supabase |
| Nostalgic Requests | (GitHub only) | Next.js, Supabase |
| Grape Vine Cottage | `APPS/Grape-Vine-Cottage` | Vite, React 18 |
| Mindset Companion | `APPS/MINDSET COMPANION APP/cc-mindset` | Next.js 16 |
| On The Hill | `APPS/ON-THE-HILL-WEBSITE` | Vite, React 19 |

## Sub-Agents (14)

See `brain/AGENTS.md` for the complete registry with orchestration decision matrix.

| Agent | Model | Specialty |
|-------|-------|-----------|
| architect | Opus | System design, DB schema, multi-service planning |
| content-creator | Sonnet | Copywriting, social content, CC's 5 pillars |
| debugger | Sonnet | Bug investigation, root cause analysis |
| documenter | Haiku | Documentation, memory updates |
| explorer | Haiku | Codebase navigation (read-only) |
| git-ops | Haiku | Git operations, PR management |
| researcher | Sonnet | Market research via Playwright |
| reviewer | Sonnet | Code quality & security audit |
| social-publisher | Haiku | Late API posting, platform char limits |
| video-editor | Sonnet | FFmpeg, Remotion, captions |
| workflow-builder | Sonnet | n8n automation creation |
| writer | Sonnet | Code writing, feature implementation |
| chief-of-staff | Sonnet | Communication, mission control, outreach |
| revenue-hunter | Sonnet | Sales strategy, lead nurturing |

## CLI-Anything (Universal CLI Generation)

Generate agent-native CLI wrappers for any software, API, or service. When MCPs break, CLIs still work.

- **Skill:** `skills/cli-anything/SKILL.md` — 7-phase pipeline (analyze → design → implement → test → package → integrate)
- **Workflow:** `.agents/workflows/cli-anything.md` — `/cli-anything <target>` trigger
- **Templates:** `scripts/cli_templates/` — reusable Python components (ReplSkin, Backend, setup.py)
- **Existing CLIs:** `supabase_tool.py`, `stripe_tool.py`, `edit_content.py` (already follow this pattern)
- **Based on:** [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology

## Workflows (12 active — `.agents/workflows/`)

| Command | Purpose |
|---------|---------|
| /client-onboard | New OASIS client setup |
| /commit | Smart commit — conventional format, staged analysis |
| /content | Create platform content |
| /debug | Systematic bug fixing |
| /health | Full workspace diagnostic |
| /n8n | Search, inspect, manage n8n workflows |
| /post | Publish via Late API |
| /prime | Load full project context |
| /research | Competitive intelligence |
| /status | Project status report |
| /sync | End-of-session sync |
| /cli-anything | Generate CLI wrapper for any software/API/service |

## Skills (53)

> **Note:** All skills use the Claude Agent Skills 2.0 structure. They are stored in `skills/[skill-name]/SKILL.md` format. The descriptions inside the frontmatter define their activation triggers.

| Category | Skills |
|----------|--------|
| **Agent Intelligence** | heartbeat, self-healing, memory-management, growth-engine, sop-breakdown, sequential-reasoning |
| **Development** | systematic-debugging, TDD, verification, executing-plans, writing-plans, finishing-branch, git-worktrees |
| **Browser & Testing** | **browser-automation** (Playwright MCP reference), **e2e-testing** (parallel sub-agent E2E), webapp-testing |
| **Content** | writing-skills, doc-coauthoring, internal-comms, brand-guidelines, brainstorming |
| **Code** | mcp-builder, skill-creator, subagent-development, parallel-agents, code-review (2), **code-review** (pre-landing, Fix-First), **ship** (full deploy pipeline), **retro** (weekly retrospective) |
| **Automation** | n8n-mcp-integration, n8n-patterns, supabase-patterns, ai-integration |
| **Creative** | frontend-design, canvas-design, algorithmic-art, theme-factory, web-artifacts |
| **Files** | pdf, docx, pptx, xlsx |
| **Security** | security-protocol, using-superpowers |
| **CLI & Integration** | **cli-anything** (universal CLI generation from any software/API) |
| **Meta** | slack-gif-creator |

## External Services (No MCP)

| Service | Access Method | Purpose |
|---------|---------------|---------|
| n8n | n8n-mcp / API | Workflow automation (Full CRUD via Bravo) |
| Gmail | API / SMTP | Email drafting, research, and approval-based sending |
| Notion | API | Task tracking, project management, and knowledge base |
| ElevenLabs | Python SDK | Voice & audio generation (elevenlabs pip package) |
| Vercel | Git push auto-deploy | Hosting & previews |
| GoHighLevel | n8n webhooks | CRM for OASIS clients |
| Twilio | API/n8n | SMS & voice (Nostalgic Requests) |
| Shopify | Admin UI | FromOasis e-commerce |
| Telegram | telegram_agent.js (V6.0) | CLI bridge for remote execution — routes to Gemini/Claude. Prefers global gemini install. Start: `npm run telegram` |

## Video Production Pipeline

| Tool | Version | Purpose |
|------|---------|---------|
| FFmpeg | 8.0.1 (full build) | Video encoding, overlays, captions, audio normalization |
| Python | 3.12.10 | Script runtime for edit_content.py |
| Whisper | openai-whisper | Auto-transcription → SRT captions |
| ElevenLabs | elevenlabs SDK | Text-to-speech voiceover generation |
| Remotion | 4.0.431 | Programmatic video/animation generation |

Pipeline script: `scripts/edit_content.py` — probe, transcribe, voiceover, edit
Agent: `agents/video-editor.md` | Command: `/edit-video`

## Tech Stack

- **OS:** Windows 11 (Desktop), macOS (MacBook)
- **Languages:** TypeScript (primary), Python (video pipeline, MCP servers)
- **Frameworks:** Next.js 14 (App Router), Tailwind CSS
- **Database:** Supabase (PostgreSQL) — 3 projects, 10-table agent schema
- **Hosting:** Vercel (auto-deploy from git)
- **Payments:** Stripe (3 brand accounts)
- **Automation:** n8n (Hostinger VPS: https://n8n.srv993801.hstgr.cloud)
- **AI Models:** Claude Opus/Sonnet, Gemini 1.5 Pro/Flash, GPT-4o, Gemini CLI (v0.32.1)
