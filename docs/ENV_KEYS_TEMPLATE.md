---
tags: [onboarding, deployment, credentials, template]
last_updated: 2026-07-09
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
| `CLAUDE_CODE_OAUTH_TOKEN` | Anthropic | **Primary** — Claude Code subscription OAuth. Generate with `claude setup-token`; automations call the local `claude` CLI via `scripts/lib/claude_cli.py` |
| `ANTHROPIC_API_KEY` | Anthropic | **DEPRECATED for CC's deployment** (out of credits + CLI-only rule) — fork-only |
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

## Turso / libSQL (migration target — 5 databases, one per Supabase project)

**Two different credentials, and confusing them is the #1 setup failure.** A
*database* token connects to exactly one database; a *Platform API* token
creates and manages databases. Only `turso auth api-tokens mint` produces the
second kind. `TURSO_API_KEY` below is the first kind and 401s against the
Platform API.

| Variable | Notes |
|----------|-------|
| `TURSO_PLATFORM_TOKEN` | **Org-scoped.** Creates/deletes databases, mints db tokens. `turso auth login && turso auth api-tokens mint <name>` |
| `TURSO_ORG` | Organization slug — `turso org list` |
| `TURSO_DATABASE_URL` | **Canonical.** Bravo empire db, `libsql://<host>` |
| `TURSO_AUTH_TOKEN` | Database token for the above (full-access) |
| `TURSO_DB_PATH` | Local libSQL file — offline/test mode, no token needed |
| `BREEZE_TURSO_DATABASE_URL` / `BREEZE_TURSO_AUTH_TOKEN` | breeze-portal (separate trust boundary — merchant bank data) |
| `NOSTALGIC_TURSO_DATABASE_URL` / `NOSTALGIC_TURSO_AUTH_TOKEN` | nostalgic-requests |
| `PROPFLOW_TURSO_DATABASE_URL` / `PROPFLOW_TURSO_AUTH_TOKEN` | propflow |
| `OASIS_TURSO_DATABASE_URL` / `OASIS_TURSO_AUTH_TOKEN` | oasis-platform |
| `TURSO_DB_URL` | Legacy alias read by oasis-command-center `lib/turso.ts` |
| `TURSO_API_KEY` | **Pre-existing, unrelated.** Database token for ig-setter-pro. Deliberately NOT a fallback in `scripts/lib/db_turso.py` — using it would point the harness at another product's data. |
| `GRITLY_TURSO_DATABASE_URL` / `GRITLY_TURSO_AUTH_TOKEN` | Gritly's own database (pre-existing, not part of this migration) |

Provision with `python scripts/integrations/turso_admin.py create --all --write-env`
— it writes URLs and tokens straight into this file and never prints their values.

### Cutover flags — THREE, and each gates a DIFFERENT layer

Setting only the first is the trap: you get a deployment with the Turso data
plane, **Supabase auth**, and no browser bridge at all. It looks healthy until
someone logs in.

| Variable | What it actually switches |
|----------|---------------------------|
| `EMPIRE_DATA_BACKEND=turso_cloud` | Server data plane only (`.from()` / `.rpc()` routing) |
| `EMPIRE_AUTH_BACKEND=turso` | Auth **and** the `/api/data/bridge` + `/api/data/rpc` routes |
| `AUTH_SESSION_SECRET` | HMAC key for the session cookie. Required *alongside* the above — both routes **404** without it, which reads as "not deployed" rather than "misconfigured" |

Any of them unset → the app falls back to Supabase. That fallback IS the rollback
path, so it must keep working until the Supabase subscription is actually
cancelled. Push the per-app credential pair with
`python scripts/integrations/vercel_turso_sync.py --project <slug> --db <key>`;
if a Vercel project already carries a `TURSO_DATABASE_URL` that tool never wrote,
treat its target as unknown and re-push rather than assuming.

Before flipping an app that queries from the browser, prove the tenant boundary:
`realestate-App/scripts/verify_tenant_isolation.py`. See
`skills/turso-patterns/SKILL.md`.

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
| `TELEGRAM_BOT_TOKEN` | Bravo's DM bot (@Bravo_2003bot), from @BotFather |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated Telegram user IDs allowed to use the DM bot (CC's id). Also used as CC's id by the coordination bridge. |
| `DISCORD_TOKEN` | Optional, future bridge |
| `SLACK_BOT_TOKEN` | Optional, future bridge |

### OASIS coordination bridge (`coordination_agent.js` — agent↔agent + boardroom group)

| Variable | Notes |
|----------|-------|
| `CC_AGENT_BOT_TOKEN` | For **FULL two-way** mode (Bravo answers CC/Adon live in the group): a DEDICATED BotFather bot, Group Privacy **OFF**, MUST differ from `TELEGRAM_BOT_TOKEN` (two pollers on one token → 409). **Omit it** to run **table-only** mode (agent↔agent via the table, posting through the existing DM bot — zero new credential). |
| `COORD_ENABLE` | Set `true` to register `bravo-coord` in PM2 for **table-only** mode (no dedicated bot needed). Ignored when `CC_AGENT_BOT_TOKEN` is set (which auto-registers FULL mode). |
| `COORD_GROUP_CHAT_ID` | OASIS group chat id. Default `-5165125484`. |
| `CC_TELEGRAM_USER_ID` | **Required for the gate.** CC's Telegram user id. The bridge does NOT fall back to `TELEGRAM_ALLOWED_USERS` (that var auto-registers, so it can't be trusted for operator authority). Unset → gate fails closed: everyone is untrusted and CC's approvals are rejected. |
| `ADON_TELEGRAM_USER_ID` | Optional — labels Adon's messages (else learned passively as a non-CC human). |
| `COORD_AUTONOMY` | `converse_gate` (default) \| `full` \| `readonly`. Gate posture for non-CC-triggered mutations. |
| `COORD_REPLY_MODE` | `cc_directed` (default) \| `addressed` \| `cc_all` \| `all`. When Bravo replies in the group. |
| `COORD_TABLE_AUTORESPOND` | `true` (default) — spawn a coordinated response to actionable APEX `agent_activity` rows. |
| `COORD_AGENT_KEY` / `COORD_AGENT_LABEL` | Table identity `cc-agent` (APEX contract) / group label `BRAVO`. |
| `COORD_PEER_KEYS` | Other agents to read in the table. Default `apex`. |

> The agent↔agent channel is the `agent_activity` table on the **bravo** Supabase project (service-role only, RLS forced). APEX (Adon's agent) authenticates with the same `BRAVO_SUPABASE_SERVICE_ROLE_KEY`. See `database/102_agent_activity.sql` and `scripts/integrations/agent_activity.py`.

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

## Free-Tier Radar adoptions (V7.1)

When CC greenlights a `candidate` row from `brain/TOOL_SHED.md` § "Free-Tier Radar" (uptime probes, error tracking, dead-man pings, coverage, SAST, …), its key lands here FIRST as a documented row, then CC signs up for the service and hand-adds the key to `.env.agents` — agents never create, see, or paste keys (ADR-0010 rule 4). No keys are pre-registered for candidates; this section gains rows only per adoption. Currently adopted from the Radar: **Disify** (`email_validate_tool.py`) — no-auth, no key needed.

---

## Related

- [[brain/AGENT_ORCHESTRATION]] · [[CLAUDE]] · [[brain/QUICK_REFERENCE]]
- `.env.agents` (gitignored, repo root) — actual credential file


## Related (graph)

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
