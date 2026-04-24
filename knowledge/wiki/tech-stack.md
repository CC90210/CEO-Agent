---
tags: [knowledge, wiki, tech-stack, tools, infrastructure]
sources: [brain/CAPABILITIES.md, brain/STATE.md]
last_updated: 2026-04-06
confidence: 0.90
---

# Tech Stack — Full Technology Inventory

> Every tool, language, framework, and integration in use across the Business-Empire-Agent system.
> [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/client-playbook]]

## Core Languages and Frameworks

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Language | TypeScript | Primary | All app development |
| Language | Python | 3.12.10 | CLI scripts, automation engines, ML pipeline |
| Web framework | Next.js | 14 (App Router) | All web apps |
| Styling | Tailwind CSS | — | All UI |
| Database | Supabase (PostgreSQL) | — | 3 projects, 28 tables |
| Hosting | Vercel | — | Auto-deploy from git |
| Payments | Stripe | — | 3 brand accounts |
| Automation | n8n | — | 47 workflows on Hostinger VPS |

**Platform:** Windows 11 (primary desktop), bash shell

## AI Models in Use

| Model | Provider | Role |
|-------|---------|------|
| Claude Opus/Sonnet 4.6 | Anthropic | Bravo (Lead Architect), Skool engine, content pipeline |
| Gemini 1.5 Pro/Flash | Google | Gemini CLI — diagnostics, fast inference, fallback |
| GPT-4o / GPT-OSS 120B | OpenAI | Codex (backend executor, code review) |
| Codex (external AI) | OpenAI | Dual-AI backend executor via codex-companion.mjs |

## MCP Servers (4 Working)

These are stateless — they don't need credentials and never break.

| Server | Purpose | Key Tools |
|--------|---------|-----------|
| Playwright | Browser automation, web research, Skool | navigate, snapshot, click, type |
| Context7 | Live library documentation | resolve-library-id, query-docs |
| Memory | Persistent knowledge graph | create_entities, search_nodes |
| Sequential Thinking | Multi-step structured reasoning | sequentialthinking |

**Note:** 4 credential MCPs (n8n, Late/Zernio, Supabase, Stripe) were replaced with Python CLI
tools because credential passing through MCP breaks frequently.

## CLI Tools (Primary Interface — More Reliable Than MCPs)

| Tool | Script | Replaces |
|------|--------|---------|
| Supabase | `scripts/supabase_tool.py` | Supabase MCP |
| Stripe | `scripts/stripe_tool.py` | Stripe MCP |
| n8n | `scripts/n8n_tool.py` | n8n MCP |
| Zernio (social) | `scripts/late_tool.py` | Late/Zernio MCP |
| Google Workspace | `scripts/google_tool.py` | — |
| Lead CRM | `scripts/lead_engine.py` | — |
| Email | `scripts/email_engine.py` | — |
| Booking | `scripts/booking_engine.py` | — |
| Content calendar | `../CMO-Agent/scripts/content_engine.py` | — |
| Revenue tracking | `scripts/revenue_engine.py` | — |
| Competitive intel | `scripts/competitive_intel.py` | — |
| Financial model | `scripts/financial_model.py` | — |
| Client health | `scripts/client_health.py` | — |
| CEO dashboard | `scripts/ceo_dashboard.py` | — |

All scripts: support `--json` flag, read credentials from `.env.agents`, Supabase-backed.

## Supabase Projects (3)

| Project | Region | Purpose | Tables |
|---------|--------|---------|--------|
| Bravo | us-west-2 | Agent intelligence + business ops | 28 (14+14) |
| oasis-ai-platform | us-west-2 | OASIS AI platform | — |
| nostalgic-requests | us-west-2 | Nostalgic Requests platform | — |

## App Portfolio (12 external repos)

| App | Stack | Local Path |
|-----|-------|-----------|
| OASIS AI Platform | React 18, Vite, Supabase | `APPS/oasis-ai-platform` |
| PropFlow | Next.js 14, Supabase, Stripe | `realestate-App` |
| Nostalgic Requests | Next.js 16, Supabase, Stripe Connect | `APPS/nostalgic-requests` |
| Grape Vine Cottage | Vite, React 18 | `APPS/Grape-Vine-Cottage` |
| Mindset Companion | Next.js 16, React 19 | `APPS/MINDSET COMPANION APP/cc-mindset` |
| On The Hill | Vite, React 19 | `APPS/ON-THE-HILL-WEBSITE` |
| Atlas (CFO) | Python 3.11+, CCXT, Claude API | `APPS/CFO-Agent` |
| TIKTIK | Next.js 14, Supabase, Tailwind | `APPS/tiktik` |
| CC Funnel | Next.js 14, Supabase, Tailwind | `APPS/cc-funnel` |
| Shopify Ad Engine | Remotion 4, React 19, Three.js | `APPS/shopify-ad-engine` |
| Lafreniere PM | Next.js 16, Supabase, Stripe | `APPS/lafreniere-pm` |
| AURA | Claude Code agent, ESP32, Home Assistant | `AURA` |

## Key Automation Infrastructure

| System | Tool | Details |
|--------|------|---------|
| Community management | Skool engine | V2 research-enhanced, post-reply only, DMs disabled |
| Social scheduling | Zernio (formerly Late) | 8 connected accounts, `https://zernio.com/api/v1/` |
| Workflow automation | n8n | 47 workflows, Hostinger VPS |
| Process scheduling | PM2 | Pinned to `.venv` Python, silent |
| Telegram bridge | telegram_agent.js | V11.0, 25 max turns, loads full brain context |
| Email | Google Workspace | `google_tool.py`, SMTP fallback, oasisaisolutions@gmail.com |
| Video production | FFmpeg 8.0.1 + Whisper + Remotion 4.0.436 | Word-level captions, 1080×1920 |
| AI image gen | Codex image gen | `scripts/codex_image_gen.py` |

## Content Pipeline Stack

Raw iPhone video → `../CMO-Agent/scripts/content_pipeline.py` → Whisper word-level transcription →
karaoke captions → FFmpeg encode (1080×1920, CRF 18) → Codex image insertion →
thumbnail generation → Zernio schedule across 6 platforms.

## Skill and Workflow Counts (2026-03-31)

- Skills: 180 (81 core + 42 GWS + 41 recipes + 10 personas + 6 context-optimization)
- Workflows: 30 active (`.agents/workflows/`)
- Scripts: 37 CLI engines and system tools
- Agents: 17 including Codex as external executor
- MCP servers: 4 working + 4 replaced by CLI
- Hooks: 4 active (2 PreToolUse safety, 1 PostToolUse audit, 1 Notification)

## Sources
- `brain/CAPABILITIES.md` — complete tool and integration registry
- `brain/STATE.md` — operational status of each tool

## Obsidian Links
- [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/revenue-model]]
- [[brain/CAPABILITIES]] | [[brain/STATE]] | [[brain/APP_REGISTRY]]
- [[skills/mcp-operations/SKILL]] | [[skills/cli-anything/SKILL]]
