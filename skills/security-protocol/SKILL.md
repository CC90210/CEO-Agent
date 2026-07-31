---
name: security-protocol
description: Secrets and authentication management. Ensures API keys, tokens, and credentials are NEVER exposed in plain text. Use when handling any credential, API key, or sensitive configuration.
triggers: [secret, credential, API key, exposed, rotation, security, token, password, leak, gitguardian]
tier: core
dependencies: []
tags: [skill, security-protocol]
last_updated: 2026-06-21
---

# SECRETS AND AUTHENTICATION MANAGEMENT

> **Purpose:** Ensures API keys, tokens, and database credentials are NEVER exposed in plain text files when different AI platforms interact with this workspace.

## Core Rules

1. **Never hardcode secrets.** No credentials of any kind belong in entry points (`CLAUDE.md`, `ANTIGRAVITY.md`, `GEMINI.md`) or any script. No `api_key = "sk-..."` lines anywhere.
2. **Single source of truth.** All agents must read tokens exclusively from the repo's `.env.agents` file. Never put them in code, never in commit messages.
3. **No new file types that hold raw secrets.** Files like `.long_lived_token.txt`, `credentials.json`, `service_account.json` should never exist inside a repo. If a tool needs such a file, put it outside the repo and reference it by path in `.env.agents`.
4. **MCP configs absorb from env.** When generating configuration files for new MCP servers, the server init process must read keys from `.env.agents` or local shell env vars — never paste tokens into JSON configs.
5. **`.env.agents` is gitignored everywhere.** The repo root `.gitignore` in every agent must include `.env` + `.env.*` with only `.env.agents.template` whitelisted.
6. **Untrusted spawns are text-only.** Any bridge/daemon that spawns a model in response to NON-operator input (a group peer, an inbound webhook, scraped content) MUST run that spawn with **no filesystem/exec/network tools** (`--disallowedTools` for Read/Grep/Glob/Bash/Edit/Write/WebFetch/…), a **secret-stripped env**, and a **sandboxed cwd** — not merely a read-only allowlist. A `Read`/`Grep` allowlist still reaches `.env.agents` by absolute path and exfiltrates it. Only operator-gated spawns (CC's Telegram id / an identity-gated `/chat`) get file tools. Reference: `coordination_agent.js` `UNTRUSTED_DENY_TOOLS`.

## Detection — Run Before Every Push

Every agent ships with `scripts/scan_secrets.py`. Run it before shipping anything sensitive:

```bash
# Fast: scan the working tree (skips gitignored files)
python scripts/scan_secrets.py

# Thorough: scan every commit in every branch (catches leaked-once-then-deleted)
python scripts/scan_secrets.py --history

# Scan a sibling agent's repo
python scripts/scan_secrets.py --path ~/CMO-Agent
```

The scanner catches (non-exhaustive):
- Anthropic, OpenAI, Google AI keys (`sk-ant-`, `sk-`, `AIza`)
- GitHub PATs (`ghp_`, `gho_`, `github_pat_`)
- Supabase service role (`sbp_`)
- Stripe live/test secrets (`sk_live_`, `sk_test_`)
- AWS access keys (`AKIA`, `ASIA`)
- Slack, Discord, Telegram bot tokens
- Twilio SIDs
- **Facebook/Meta long-lived access tokens (`EAA...`)** ← the 2026-04-24 CMO-Agent leak pattern
- PGP / SSH / JWT material
- Suspicious filenames (`*_token.txt`, `credentials.json`, `id_rsa`, etc.)

## Incident Response — When A Leak Is Discovered

### 1. Rotate the credential at its provider BEFORE anything else
The leaked value is already public. Scrubbing git history on its own is insufficient — attackers may have already cloned. Revoke first.

- Anthropic: https://console.anthropic.com/settings/keys → Revoke
- OpenAI: https://platform.openai.com/api-keys → Delete
- Stripe: dashboard → Developers → API keys → Reveal & Roll
- GitHub: https://github.com/settings/tokens → Delete
- Facebook/Meta: https://developers.facebook.com/apps → Settings → Basic → **Reset App Secret** (this invalidates every token ever issued to the app)
- Supabase: project → Settings → API → generate new service_role
- Telegram bots: @BotFather → `/revoke`

### 2. Scrub git history
```bash
pip install git-filter-repo
git branch emergency-backup-before-scrub
git filter-repo --path <leaked-file> --invert-paths --force
git push origin --force --all
git push origin --force --tags
```

### 3. Prevent recurrence
Add the leaked file's pattern to `.gitignore`, then commit + push.

### 4. Notify
If the leak affected anything client-facing (Stripe, client tokens, client data), notify CC immediately. Write a Reflexion entry in `memory/MISTAKES.md` documenting the root cause.

## Known Leak Patterns (add to `.gitignore` of every new repo)

```gitignore
# Secrets
.env
.env.*
!.env.agents.template
!.env.example

# Token/credential files
*.token
*_token.txt
*_token.json
*token*.txt
.long_lived_token*
credentials.json
service_account.json

# SSH / TLS
id_rsa
id_ed25519
*.pem
*.key
*.p12
*.pfx

# MCP configs (often carry API keys)
.claude/mcp.json
.vscode/mcp.json
```

`templates/agent-scaffold/.gitignore` ships with all of this — every forged agent inherits it.

## Incidents Log

**2026-04-24 — CMO-Agent Facebook token leak**
- Root cause: `.long_lived_token.txt` (183-char Facebook long-lived User Access Token) was committed in Maven's initial commit `3e6e83e` on 2026-04-18. When CMO-Agent was flipped public later (to enable the cross-agent OASIS AI setup wizard clone flow), the token became world-readable. GitGuardian flagged it.
- Detection gap: `.env*` was gitignored but not `*.token` / `*token*.txt`. The filename didn't trip the narrow gitignore.
- Fix applied: `scripts/scan_secrets.py` + hardened `.gitignore` patterns + scanner in `bravo setup` workflow + this skill updated.
- Prevention: every forged agent now inherits the hardened `.gitignore` via `templates/agent-scaffold/`. Pre-push scans recommended before any public flip.

## Safe Handling in Subagents

When spawning subagents that need API access, pass secrets via environment variables or a shared `.env.agents` path reference — never paste the raw string into the prompt structure.


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]] | [[memory/MISTAKES]]
- `scripts/scan_secrets.py` (the detection tool)
- `templates/agent-scaffold/.gitignore` (the baseline)
