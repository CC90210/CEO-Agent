---
tags: [knowledge, wiki, tech-stack, tools, infrastructure]
sources: [brain/CAPABILITIES.md, brain/STATE.md]
last_updated: 2026-07-19
confidence: 0.92
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
| Automation | n8n | — | self-hosted on Hostinger VPS (workflow count lives in n8n, not here) |

**Platform:** Windows 11 (primary desktop), bash shell

## AI Models in Use

| Model | Provider | Role |
|-------|---------|------|
| Claude Fable 5 (`claude-fable-5`) | Anthropic | Standard for top-tier reasoning + main agent loop (since 2026-06-12) |
| Claude Opus 4.8 / Sonnet 4.6 / Haiku 4.5 | Anthropic | Heavy code / general / cheap classification tiers — canonical map: `scripts/lib/model_registry.py` |
| Gemini 3.x | Google | Gemini CLI runtime — diagnostics, fast inference, fallback |
| GPT-5.x | OpenAI | Codex — dual-AI backend executor + adversarial review via codex-companion.mjs |

All model calls from automations route through the LOCAL `claude` CLI on subscription OAuth (`scripts/lib/claude_cli.py`, prompts via stdin) — never the metered API key.

## MCP Servers (9 registered in `.claude/mcp.json`; 13 across all configs)

Registered: Playwright, Context7, Memory, Sequential Thinking, Knowledge Graph, GitHub, Firecrawl, Obsidian, Filesystem. Four more (Supabase, n8n, Stripe, Late) ride via `enabledMcpjsonServers`. Authoritative config-path registry: `scripts/audit_mcp_secrets.py`.

**Note:** credentialed services (n8n, Late/Zernio, Supabase, Stripe, GWS) are used by agents via Python CLI wrappers — credential passing through MCP breaks frequently, so CLIs are the primary interface.

## CLI Tools (Primary Interface — More Reliable Than MCPs)

| Tool | Script | Replaces |
|------|--------|---------|
| Supabase | `scripts/integrations/supabase_tool.py` | Supabase MCP |
| Stripe | `scripts/integrations/stripe_tool.py` | Stripe MCP |
| n8n | `scripts/integrations/n8n_tool.py` | n8n MCP |
| Zernio (social) | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | Late/Zernio MCP |
| Google Workspace | `scripts/integrations/google_tool.py` | — |
| Lead CRM | `scripts/lead_engine.py` | — |
| Email | `scripts/integrations/email_engine.py` | — |
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
| Atlas (CFO) | Python, local Claude CLI (pivoted from trading/CCXT 2026-04-14) | `APPS/CFO-Agent` |
| TIKTIK | Next.js 14, Supabase, Tailwind | `APPS/tiktik` |
| CC Funnel (RETIRED 2026-06-18) | replaced by native funnel at oasisai.work/f/ | — |
| Shopify Ad Engine | Remotion 4, React 19, Three.js | `APPS/shopify-ad-engine` |
| Lafreniere PM | Next.js 16, Supabase, Stripe | `APPS/lafreniere-pm` |
| AURA | Claude Code agent, ESP32, Home Assistant | `AURA` |

## Key Automation Infrastructure

| System | Tool | Details |
|--------|------|---------|
| Community management | Skool engine | V2 research-enhanced, post-reply only, DMs disabled |
| Social scheduling | Zernio (formerly Late) | 8 connected accounts, `https://zernio.com/api/v1/` |
| Workflow automation | n8n | self-hosted, Hostinger VPS |
| Process scheduling | PM2 | Pinned to `.venv` Python, silent |
| Telegram bridge | telegram_agent.js | V11.0, 25 max turns, loads full brain context |
| Email | Google Workspace | `google_tool.py`, SMTP fallback, oasisaisolutions@gmail.com |
| Video production | FFmpeg 8.0.1 + Whisper + Remotion 4.0.436 | Word-level captions, 1080×1920 |
| AI image gen | Codex image gen | `../CMO-Agent/scripts/codex_image_gen.py` (owned by Maven) |

## Content Pipeline Stack

Raw iPhone video → `../CMO-Agent/scripts/content_pipeline.py` → Whisper word-level transcription →
karaoke captions → FFmpeg encode (1080×1920, CRF 18) → Codex image insertion →
thumbnail generation → Zernio schedule across 6 platforms.

## Skill and Workflow Counts (2026-07-19 — live source: `brain/CAPABILITY_GRAPH.json` totals; never trust a wiki snapshot over the graph)

- Skills: 151 · Script nodes: 116 · Agent nodes: 32 (incl. the V7.2 agency-import bench) · Workflows: 35 · Resource nodes (V7.1 Free-Tier Radar): 14
- MCP servers: 9 registered (13 across configs)
- Hooks: full PreToolUse guard chain (secret/exec/state/anti-pattern/subprocess) + SessionStart/UserPromptSubmit/PreCompact/PostToolUse/SubagentStop orchestration — see `.claude/settings.hooks.template.json`

## Sources
- `brain/CAPABILITIES.md` — complete tool and integration registry
- `brain/STATE.md` — operational status of each tool

## Obsidian Links
- [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/revenue-model]]
- [[brain/CAPABILITIES]] | [[brain/STATE]] | [[brain/APP_REGISTRY]]
- [[skills/mcp-operations/SKILL]] | [[skills/cli-anything/SKILL]]
