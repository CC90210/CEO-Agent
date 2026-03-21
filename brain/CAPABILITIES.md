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
Workflows: `.agents/workflows/` (15 workflows: post, status, health, prime, content, commit, n8n, sync, research, debug, client-onboard, cli-anything, skool-edit, skool-push, evolve)

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
| **Bravo** | us-west-2 | Agent intelligence (14 tables) + business ops (14 tables) = 28 tables |
| **nostalgic-requests** | us-west-2 | Nostalgic Requests platform |
| **oasis-ai-platform** | us-west-2 | OASIS AI platform |

**Organizations:** CC (oktipozhyojufxsytrse), oasis-ai-platform (sajanpiqysuwviucycjh)

## App Registry (8 External Repos)

Full routing table with local paths, GitHub URLs, tech stacks: `brain/APP_REGISTRY.md`

| App | Local Path | Stack |
|-----|-----------|-------|
| OASIS AI Platform | `APPS/oasis-ai-platform` | React 18, Supabase |
| PropFlow | `realestate-App` | Next.js 14, Supabase |
| Nostalgic Requests | (GitHub only) | Next.js, Supabase |
| Grape Vine Cottage | `APPS/Grape-Vine-Cottage` | Vite, React 18 |
| Mindset Companion | `APPS/MINDSET COMPANION APP/cc-mindset` | Next.js 16 |
| On The Hill | `APPS/ON-THE-HILL-WEBSITE` | Vite, React 19 |
| Atlas Trading Agent | `APPS/trading-agent` | Python 3.11+, CCXT, Claude API |
| TIKTIK | `APPS/tiktik` | Next.js 14, Supabase, Tailwind |

## Sub-Agents (16)

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
| explorer | Haiku | Codebase navigation, file search (read-only) |
| meta-agent | Sonnet | Generate new subagent definitions from descriptions [PROBATIONARY] |

## CLI-Anything (Universal CLI Generation)

Generate agent-native CLI wrappers for any software, API, or service. When MCPs break, CLIs still work.

- **Skill:** `skills/cli-anything/SKILL.md` — 7-phase pipeline (analyze → design → implement → test → package → integrate)
- **Workflow:** `.agents/workflows/cli-anything.md` — `/cli-anything <target>` trigger
- **Templates:** `scripts/cli_templates/` — reusable Python components (ReplSkin, Backend, setup.py)
- **Existing CLIs:** `supabase_tool.py`, `stripe_tool.py`, `edit_content.py` (already follow this pattern)
- **Based on:** [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology

## Business Operations Engines (6 CLI tools — zero paid services)

| Engine | Script | Purpose | Key Commands |
|--------|--------|---------|-------------|
| **Lead CRM** | `scripts/lead_engine.py` | Full pipeline management, scoring, interactions | `list`, `add`, `view`, `update`, `score`, `interact`, `followups`, `pipeline`, `search`, `funnel` |
| **Email** | `scripts/email_engine.py` | Free Gmail SMTP sending, templates, nurture sequences | `send`, `send-template`, `templates list/create`, `sequence list/create/run`, `log`, `stats` |
| **Booking** | `scripts/booking_engine.py` | Self-hosted Cal.com replacement, slot management | `slots open/open-week/list/close`, `book`, `cancel`, `available`, `remind`, `complete` |
| **Content** | `scripts/content_engine.py` | Content calendar, templates, multi-platform posting | `calendar`, `create`, `create-multi`, `templates list/create/render`, `due`, `week-plan`, `stats` |
| **Revenue** | `scripts/revenue_engine.py` | MRR tracking, Stripe sync, forecasting | `mrr`, `dashboard`, `sync-stripe`, `log-revenue`, `history`, `forecast`, `clients`, `goal` |
| **Cron** | `scripts/cron_engine.py` | Automated job scheduling, 12 seeded business workflows | `list`, `add`, `toggle`, `run`, `due`, `seed` |

All engines: `--json` flag for agent consumption, credentials from `.env.agents`, Supabase backend.

## Business Ops Database Schema (14 tables — Supabase Bravo)

| Domain | Tables | Purpose |
|--------|--------|---------|
| **CRM** | `leads`, `lead_interactions` | Lead tracking, interaction history, scoring |
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

## Workflows (15 active — `.agents/workflows/`)

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
| /skool-edit | Edit Skool lessons or About page via Playwright |
| /skool-push | Bulk-push course content to Skool |
| /evolve | Extract session patterns → promote to skills, SOPs, or CLAUDE.md rules |

## Skills (60)

> **Note:** All skills use the Claude Agent Skills 2.0 structure. They are stored in `skills/[skill-name]/SKILL.md` format. The descriptions inside the frontmatter define their activation triggers.

| Category | Skills |
|----------|--------|
| **Agent Intelligence** | heartbeat, self-healing, memory-management, growth-engine, sop-breakdown, sequential-reasoning, mcp-operations |
| **Development** | systematic-debugging, test-driven-development, verification-before-completion, executing-plans, writing-plans, finishing-a-development-branch, using-git-worktrees, code-review, receiving-code-review, requesting-code-review, ship, subagent-driven-development, dispatching-parallel-agents |
| **Browser & Testing** | browser-automation, e2e-testing, webapp-testing |
| **Content & Outreach** | content-engine, writing-skills, doc-coauthoring, internal-comms, brand-guidelines, brainstorming, linkedin-outreach, market-research, investor-materials, strategic-compact, retro, notebooklm |
| **Automation** | n8n-mcp-integration, n8n-patterns, supabase-patterns, ai-integration, skool-automation |
| **Creative** | frontend-design, canvas-design, algorithmic-art, theme-factory, web-artifacts-builder, slack-gif-creator |
| **Files** | pdf, docx, pptx, xlsx |
| **Security** | security-protocol, using-superpowers |
| **CLI & Integration** | cli-anything |
| **Meta** | skill-creator, mcp-builder, using-superpowers |
| **Revenue & Sales** | lead-management, email-marketing, funnel-management, revenue-operations, booking-management |

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
| Remotion | 4.0.436 | Programmatic video/animation generation (37 Claude skills) |

Pipeline script: `scripts/edit_content.py` — probe, transcribe, voiceover, edit
Remotion Studio: `content-studio/` — React-based video compositions (OasisPromo, QuoteDrop, CeoLog, SobrietyLog)
Remotion Skills: `content-studio/.claude/rules/remotion/` — 37 rule files for AI-assisted video generation
Agent: `agents/video-editor.md` (no dedicated workflow — invoke via content pipeline)

## Tech Stack

- **OS:** Windows 11 (Desktop), macOS (MacBook)
- **Languages:** TypeScript (primary), Python (video pipeline, MCP servers)
- **Frameworks:** Next.js 14 (App Router), Tailwind CSS
- **Database:** Supabase (PostgreSQL) — 3 projects, 28-table schema (14 agent + 14 business ops)
- **Hosting:** Vercel (auto-deploy from git)
- **Payments:** Stripe (3 brand accounts)
- **Automation:** n8n (Hostinger VPS: https://n8n.srv993801.hstgr.cloud)
- **AI Models:** Claude Opus/Sonnet, Gemini 1.5 Pro/Flash, GPT-4o, Gemini CLI (v0.32.1)

## Obsidian Links
- [[brain/AGENTS]] | [[brain/STATE]] | [[brain/APP_REGISTRY]]
- [[skills/mcp-operations/SKILL]] | [[skills/browser-automation/SKILL]]
