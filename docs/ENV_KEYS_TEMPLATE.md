---
tags: [onboarding, deployment, credentials, template]
last_updated: 2026-05-03
freshness_threshold_days: 60
---

# Env Keys Template — Bravo Agent Fleet Onboarding

> **Purpose:** every environment variable Bravo's CLI tools and cron jobs read at runtime, in one searchable doc. Copy these key names into your real `.env.agents` (which is gitignored and lives at the repo root).
>
> **Why this is a doc, not `.env.agents.example`:** the `.env.*` deny rule blocks any `.env.*` file from being written by an agent. This file serves the same purpose without tripping that safety.

## How to use

1. Copy the variable names below into a new `.env.agents` at the repo root (CC must create this manually — the deny rule prevents Claude from writing it).
2. Fill in real values from each provider's dashboard.
3. Verify load with `python scripts/integrations/google_tool.py test` (any CLI tool will surface missing keys).

For client deployments (deploying Hermes / a sibling agent for someone else), copy the same keys into `.env.client-<id>` on the **client's** machine. NEVER copy CC's keys into a client deployment.

---

## Core LLM providers (at least one required)

| Variable | Provider | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | Anthropic | Primary — Claude Sonnet 4.6 / Opus 4.7 |
| `OPENAI_API_KEY` | OpenAI | Codex delegation, fallback |
| `OPENROUTER_API_KEY` | OpenRouter | Multi-model routing fallback |
| `DEEPSEEK_API_KEY` | DeepSeek | Optional, cheap-tier routing |
| `GROQ_API_KEY` | Groq | Optional, fast inference |
| `LOCAL_LLM_ENDPOINT` | Ollama | Optional, e.g. `http://localhost:11434` |

## Supabase (3 projects: bravo / atlas / maven)

| Variable | Notes |
|----------|-------|
| `SUPABASE_URL` | Primary project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role key (NOT anon) |
| `SUPABASE_ACCESS_TOKEN` | Management API token (`sbp_...`, rotates ~30d) |
| `SUPABASE_URL_BRAVO` | Bravo-specific project (multi-project setup) |
| `BRAVO_SUPABASE_URL` | Same as above (legacy alias) |
| `BRAVO_SUPABASE_SERVICE_ROLE_KEY` | Bravo project service_role |
| `SUPABASE_SERVICE_ROLE_KEY_BRAVO` | Same (legacy alias) |

## Payments — Stripe (3 brand accounts)

| Variable | Brand |
|----------|-------|
| `STRIPE_API_KEY` | OASIS AI primary (`sk_live_...`) |
| `STRIPE_API_KEY_KONA` | Conaugh McKenna brand |
| `STRIPE_API_KEY_NOSTALGIC` | Nostalgic Requests brand |

## Google Workspace

| Variable | Notes |
|----------|-------|
| `GMAIL_USER` | e.g. `conaugh@oasisai.work` |
| `GMAIL_ADDRESS` | Same (legacy alias) |
| `GMAIL_APP_PASSWORD` | 16-char app password from Google Account → Security |
| `GOOGLE_MEET_LINK` | Default Meet URL for booking confirmations |
| `BOOKING_LINK` | `https://calendar.app.google/tpfvJYBGircnGu8G8` (DO NOT use Calendly) |
| `WEBSITE_LINK` | `https://oasisai.work` |

## Automation — n8n + Late/Zernio

| Variable | Notes |
|----------|-------|
| `N8N_API_URL` | `https://n8n.srv993801.hstgr.cloud` |
| `N8N_API_KEY` | JWT, public-api audience, from n8n Settings → API |
| `LATE_API_KEY` | Zernio (formerly Late) social scheduling |

## Comms bridges

| Variable | Notes |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `DISCORD_TOKEN` | Optional, future bridge |
| `SLACK_BOT_TOKEN` | Optional, future bridge |

## Deployment / infra

| Variable | Notes |
|----------|-------|
| `VERCEL_TOKEN` | Vercel CLI / API |
| `VERCEL_API_TOKEN` | Same (legacy alias) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare ops |
| `CLOUDFLARE_TOKEN` | Same (legacy alias) |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | `ghp_...` for `gh` CLI |

## CRM / outreach

| Variable | Notes |
|----------|-------|
| `APOLLO_API_KEY` | Lead enrichment |
| `CLEARBIT_API_KEY` | Company data |
| `GHL_API_KEY` | GoHighLevel — OASIS client CRM |

## Content / media

| Variable | Notes |
|----------|-------|
| `ELEVENLABS_API_KEY` | Voiceover synthesis |
| `FIRECRAWL_API_KEY` | Structured web scraping |

## Agent behavior flags (operational toggles, not credentials)

| Variable | Effect |
|----------|--------|
| `BRAVO_FORCE_DRY_RUN` | Set to `1` to force all sends through dry-run path |
| `BRAVO_AGENT_LABEL` | Default `bravo` — identifier for cross-agent messages |
| `BRAVO_SETUP_CONFIG` | Optional override for setup wizard |
| `ATLAS_FORCE_DRY_RUN` | Atlas killswitch (set in `../APPS/CFO-Agent/.env.agents`) |

## Sibling agent pointers

| Variable | Path |
|----------|------|
| `ATLAS_REPO_PATH` | `C:\Users\User\APPS\CFO-Agent` |
| `MAVEN_REPO_PATH` | `C:\Users\User\CMO-Agent` |
| `AURA_REPO_PATH` | `C:\Users\User\AURA` |
| `HERMES_REPO_PATH` | `C:\Users\User\hermes` |

---

## Client deployment pattern

When OASIS deploys a sibling agent (e.g., Hermes) for a client:

1. Copy this template's key names into `.env.client-<id>` on the **client's** machine
2. Fill in **client-owned** keys (their Stripe, their Supabase, their email)
3. Set `CLIENT_ID=<id>` in the agent's wrapper script
4. NEVER copy CC's keys into a client deployment
5. Hermes already enforces this architecturally (local SQLite, no cloud)

Per-client isolation contract: `brain/AGENT_ORCHESTRATION.md` § "Per-client API key isolation".

---

## Related

- [[brain/AGENT_ORCHESTRATION]] · [[CLAUDE]] · [[brain/QUICK_REFERENCE]]
- `.env.agents` (gitignored, repo root) — actual credential file


## Related (graph)

- [[docs/INDEX]]
- [[docs/AGENT_REPO_CROSS_ANALYSIS_2026-04-22]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
