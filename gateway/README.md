---
tags: [gateway, telegram, discord, slack, messaging, agents]
---

# Multi-Platform Messaging Gateway

Routes messages from Telegram, Discord, and Slack to the correct AI agent
(Bravo / Atlas / Maven / Aura) based on keyword routing rules from `brain/AGENTS.md`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    gateway/index.js (entry)                     │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐           │
│  │  Telegram   │  │   Discord   │  │    Slack     │  adapters  │
│  │  Adapter    │  │   Adapter   │  │   Adapter    │           │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘           │
│         │                │                │                    │
│         └────────────────┼────────────────┘                    │
│                          ▼                                      │
│              ┌───────────────────────┐                         │
│              │   GatewayDispatcher   │  gateway/core/          │
│              │  route(msg, platform, │  dispatcher.js          │
│              │         sender)       │                         │
│              └───────────┬───────────┘                         │
│                          │                                      │
│          ┌───────────────┼──────────────────┐                  │
│          ▼               ▼                  ▼                  │
│       bravo           atlas / maven       aura                 │
│   (default/CEO)      (finance/CMO)    (smart home)             │
│                                                                 │
│  HTTP control: localhost:7773                                   │
│  Heartbeat: gateway/health.json (every 30s)                    │
└─────────────────────────────────────────────────────────────────┘
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | For Telegram | BotFather token |
| `DISCORD_TOKEN` | For Discord | Bot token from Discord Developer Portal |
| `SLACK_BOT_TOKEN` | For Slack | `xoxb-` token from Slack App config |
| `SLACK_APP_TOKEN` | For Slack Socket Mode | `xapp-` token |
| `SLACK_SIGNING_SECRET` | For Slack HTTP mode | Signing secret (alternative to app token) |
| `GATEWAY_CONTROL_PORT` | Optional | Admin HTTP port (default: 7773) |
| `TELEGRAM_ALLOWED_USERS` | Optional | Comma-separated Telegram user IDs |

All credentials must live in `.env.agents` — never hardcode.

## Starting the Gateway

```bash
# Direct (foreground — useful for testing)
node gateway/index.js

# Via gateway_admin.py
python scripts/gateway_admin.py start

# Via PM2 (recommended for production)
pm2 start gateway/index.js --name bravo-gateway
```

## Admin CLI

```bash
# Status
python scripts/gateway_admin.py status
python scripts/gateway_admin.py status --json

# List adapters
python scripts/gateway_admin.py list-adapters

# Send a test message
python scripts/gateway_admin.py send --platform telegram --to <chat_id> --message "hello"

# Test control server
python scripts/gateway_admin.py test-connection

# Stop
python scripts/gateway_admin.py stop
```

## How to Add a New Adapter

1. **Create** `gateway/adapters/<platform>.js` — copy `slack.js` as a template.
2. **Implement** the four interface methods: `start()`, `stop()`, `sendMessage(id, text)`, `onMessage(handler)`.
3. **Instantiate** the adapter in `gateway/index.js` and push it to `adapterRegistry`.
4. **Add** the `PLATFORM_TOKEN` env var to `.env.agents`.
5. **Register** the new env var in the table above.

## Telegram Backward Compatibility

`gateway/adapters/telegram.js` wraps the full `telegram_agent.js` V15.8 logic
as a class. Every command is preserved verbatim:
- All `/` slash commands (`/start`, `/help`, `/ship`, `/retro`, `/review`, `/plan`, `/costs`, `/memhealth`, `/compact`, `/stale`, `/clear`, `/whoami`)
- Model selection (`!opus`, `!sonnet`, `!haiku`)
- Gemini fallback (`!gemini`)
- Voice transcription
- File relay (screenshots, videos, documents)
- Approval gate (inline keyboard buttons)
- Outreach batch buttons
- Rate limiting and security firewall
- Conversation history persistence

`telegram_agent.js` is kept as a backup. The gateway is the active path.

## Environment overrides (gateway/adapters/telegram.js)

Auto-detected paths can be overridden when the local layout doesn't match
defaults (custom Python venv, alternate CLI install location, etc.). Add to
`.env.agents`:

| Env var | Default | When to set |
|---|---|---|
| `BRAVO_PYTHON` | `python3` on Mac, `.venv/Scripts/python.exe` on Windows | Custom virtualenv path or system Python |
| `BRAVO_MACHINE_NAME` | `MacBook` / `Windows Desktop` | Multi-machine fleets that need distinct labels |
| `BRAVO_TEMP_DIR` | `/tmp` on Mac, `%TEMP%` or `<repo>/tmp` on Windows | Sandboxes where the default `TEMP` isn't writable |
| `BRAVO_CLAUDE_EXE` | `claude` on Mac, `~/.local/bin/claude.exe` on Windows | Non-default Claude Code install path |
| `BRAVO_GEMINI_SCRIPT` | nvm/APPDATA-derived `index.js` path | Custom Gemini CLI install |

All five env vars are optional. The defaults work on CC's standard Windows + Mac layouts.

## OASIS Coordination Bridge (`coordination_agent.js`) — separate process

NOT part of this gateway. The OASIS coordination bridge is a **standalone**
top-level process (`coordination_agent.js`, PM2 name `bravo-coord`) that wires
Bravo into the shared **OASIS group** (`-5165125484`) with CC, Adon, and APEX
(Adon's agent, `@KnutRPEbot`). It is deliberately decoupled from the DM bridge.

Two channels (Telegram bots cannot see each other, so this split is mandatory):

| Channel | Direction | Mechanism |
|---|---|---|
| OASIS Telegram group | human ↔ agent | `coordination_agent.js` polls `CC_AGENT_BOT_TOKEN`; CC + Adon's messages drive Bravo; Bravo posts replies/status |
| `agent_activity` table | agent ↔ agent | `scripts/integrations/agent_activity.py` on the **bravo** Supabase (service-role, RLS forced). The ONLY APEX→Bravo path. |

Hard rules baked in:
- **Dedicated token.** `CC_AGENT_BOT_TOKEN` ≠ `TELEGRAM_BOT_TOKEN`; the process refuses to start otherwise (two pollers on one token → 409 / message loss).
- **Humans direct, agents coordinate.** A peer's `agent_activity` status row never auto-triggers a mutation.
- **Gated hands** (`COORD_AUTONOMY=converse_gate`, default): converse/read/analyse/draft/post-status freely; any mutation triggered by anyone other than CC spawns in plan mode and pauses for CC's one-tap approval in the group. CC-triggered work runs with `acceptEdits`.

Operate it:
```bash
# Post Bravo's status to the table + mirror to the group:
python scripts/integrations/agent_activity.py post --status start \
  --task "Batch 3" --files app/x.tsx --branch cc/batch-3 --mirror
# See what APEX is doing / has claimed before touching shared files:
python scripts/integrations/agent_activity.py peers --hours 6
python scripts/integrations/agent_activity.py claims --hours 6
# Start the bridge (after CC_AGENT_BOT_TOKEN is in .env.agents):
pm2 start ecosystem.config.js --only bravo-coord
```
Env keys: see `docs/ENV_KEYS_TEMPLATE.md` → "OASIS coordination bridge".
Schema: `database/102_agent_activity.sql`.

## Obsidian Links
- [[brain/AGENTS]] — routing rules source
- [[brain/CAPABILITIES]] — full tool inventory
- [[memory/SESSION_LOG]] — session history
