---
tags: [credentials, setup, cloning, security]
purpose: Documentation of every credential Bravo needs. Source-of-truth for `.env.agents` contents on any new machine or client clone. NEVER contains real values.
---

# CREDENTIALS SCAFFOLD

> This file documents every key Bravo needs to run production. Real values live ONLY in `.env.agents` (gitignored). Do NOT write secrets here — this file is committed.
>
> When cloning Bravo for a new machine or new client, use this as the master checklist of what `.env.agents` must contain.

## Priority Legend
- **[REQUIRED]** — Bravo cannot start without this
- **[CORE]** — Major capability lost if missing
- **[OPTIONAL]** — Feature-specific, nice to have
- **[CLONE ONLY]** — Only relevant when cloning for a client

---

## Core AI Layer
At minimum, Anthropic must be set. OpenAI is for the Codex delegation path only.

| Key | Priority | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | REQUIRED | Claude API — main reasoning engine. Get at console.anthropic.com |
| `OPENAI_API_KEY` | OPTIONAL | Codex/GPT paths only |
| `OPENAI_ORG_ID` | OPTIONAL | If multi-org OpenAI account |

## Database — Supabase
Agent state, CRM, revenue tracking, session logs, memory, self-modification audit.

| Key | Priority | Notes |
|---|---|---|
| `SUPABASE_URL` | REQUIRED | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | REQUIRED | Client-side reads (respects RLS) |
| `SUPABASE_SERVICE_ROLE_KEY` | REQUIRED | Server-side writes. Bypasses RLS — treat like a root password |
| `SUPABASE_MANAGEMENT_TOKEN` | CORE | `sbp_...` — expires every 30 days. Programmatic project management |
| `SUPABASE_PROJECT_ID` | CORE | Project ref id (same as subdomain) |

## Revenue — Stripe
MRR tracking, subscription ops, invoice generation, payment links.

| Key | Priority | Notes |
|---|---|---|
| `STRIPE_SECRET_KEY` | CORE | `sk_live_...` — use `sk_test_` during setup |
| `STRIPE_WEBHOOK_SECRET` | CORE | `whsec_...` only if Bravo listens for webhooks |
| `STRIPE_PUBLISHABLE_KEY` | OPTIONAL | Frontend embed only |

## Social Media — Zernio (formerly Late)
Post scheduling across X / LinkedIn / IG / TikTok / Threads / YouTube.

| Key | Priority | Notes |
|---|---|---|
| `LATE_API_KEY` | CORE | Variable name kept as LATE_API_KEY after Zernio rebrand |

## Email — Google Workspace
Outreach, nurture sequences, calendar, drive, docs, sheets.

| Key | Priority | Notes |
|---|---|---|
| `GOOGLE_WORKSPACE_EMAIL` | CORE | OAuth handled by gws CLI keyring. This is identity only |
| `GMAIL_APP_PASSWORD` | OPTIONAL | SMTP fallback if OAuth breaks |

Auth is via `gws auth login --scopes ...`. `.env.agents` does not contain OAuth refresh tokens — the GWS keyring does.

## Community Automation — Skool
No API key. Session-based via persistent Playwright Chromium profile.

| Key | Priority | Notes |
|---|---|---|
| `SKOOL_COMMUNITY_SLUG` | CORE | e.g., `agency-accelerants-6209` |

Setup: `python scripts/skool_engine.py login` once → auth persists in `tmp/skool-browser/` profile.

## Workflows — n8n
Visual workflow automation.

| Key | Priority | Notes |
|---|---|---|
| `N8N_API_URL` | CORE | `https://your-n8n.com/api/v1` |
| `N8N_API_KEY` | CORE | From n8n Settings → API |

## Scraping — Firecrawl
Web scraping, structured extraction, competitor research, OSINT.

| Key | Priority | Notes |
|---|---|---|
| `FIRECRAWL_API_KEY` | CORE | `fc-...` from firecrawl.dev |

## Notifications — Telegram Bot
Escalations, scan summaries, approval flows, heartbeats.

| Key | Priority | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | REQUIRED | Create bot via `@BotFather` |
| `TELEGRAM_CHAT_ID` | REQUIRED | Get from `@userinfobot` |

## Version Control — GitHub
PR/issue management, gh CLI, GitHub MCP server.

| Key | Priority | Notes |
|---|---|---|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | CORE | `ghp_...` — scopes: repo, workflow, read:org |

## Media Generation
Voice and image generation for content pipeline.

| Key | Priority | Notes |
|---|---|---|
| `ELEVENLABS_API_KEY` | OPTIONAL | Voice generation for video pipeline |

## CRM Enrichment (optional)
Lead enrichment and sales tooling. Bravo runs without these — CRM just starts empty.

| Key | Priority | Notes |
|---|---|---|
| `HUBSPOT_API_KEY` | OPTIONAL | If migrating from HubSpot |
| `APOLLO_API_KEY` | OPTIONAL | Lead enrichment |
| `LINKEDIN_SESSION_COOKIE` | OPTIONAL | Sales Navigator — never commit cookies |

## Client-Specific (clone mode only)
Populated when cloning Bravo for an OASIS AI client. Ignored on CC's primary instance.

| Key | Priority | Notes |
|---|---|---|
| `CLIENT_NAME` | CLONE ONLY | Display name across templates |
| `CLIENT_DOMAIN` | CLONE ONLY | Primary domain |
| `CLIENT_VERTICAL` | CLONE ONLY | HVAC / wellness / real-estate / etc. |
| `CLIENT_PRIMARY_COLOR` | CLONE ONLY | Brand color hex for content templates |
| `CLIENT_BRAND_VOICE_FILE` | CLONE ONLY | Path to markdown file with tone rules |

---

## Setting Up a New Machine

On a fresh machine (e.g., CC's MacBook):

1. **Clone the repo**
   ```bash
   cd ~/APPS  # or wherever you keep projects
   git clone https://github.com/CC90210/CEO-Agent.git
   cd business-empire-agent
   ```

2. **Create `.env.agents` from this scaffold**
   - Open this file (`brain/CREDENTIALS_SCAFFOLD.md`) as a reference
   - Create `.env.agents` at repo root (hooks will block commits automatically)
   - For each REQUIRED and CORE key above, add a `KEY=value` line
   - Source of truth for values: 1Password / Bitwarden / the Windows box's `.env.agents`

3. **Lock permissions**
   ```bash
   chmod 600 .env.agents
   grep -F '.env.agents' .gitignore   # must return a match
   ```

4. **Install Python deps**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python -m playwright install chromium
   ```

5. **Verify core integrations**
   ```bash
   python scripts/supabase_tool.py list projects
   python scripts/stripe_tool.py balance
   python scripts/firecrawl_tool.py scrape https://example.com
   ```

6. **One-time service logins**
   ```bash
   python scripts/skool_engine.py login    # manual Skool auth
   gws auth login                          # Google Workspace OAuth
   ```

7. **Start the daemon**
   ```bash
   python scripts/skool_engine.py daemon --interval 5 &
   ```

## Secret Rotation Protocol

When ANY key is suspected exposed:
1. Revoke it immediately in the provider's dashboard
2. Generate a new one
3. Update ONLY `.env.agents` (wrapper scripts read it at runtime — no config edits needed elsewhere)
4. Restart any long-running daemons so they pick up the new value
5. Log the rotation in `memory/MISTAKES.md` with date + root cause + prevention

## Obsidian Links
- [[skills/security-protocol/SKILL]]
- [[skills/ethical-hacking/SKILL]]
- [[brain/CLIENT_READY]]
- [[brain/CAPABILITIES]]
