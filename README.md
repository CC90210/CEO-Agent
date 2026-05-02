# Bravo — Autonomous AI CEO

> The agent that runs a real business. Strategy, clients, revenue, content, outreach — all automated.

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash
```

```powershell
# Windows
irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex
```

One command. Five minutes. The wizard asks who you are, you paste a few API keys, and you have your own personalized AI CEO.

---

## What you get

**Bravo** is the CEO. It works alongside three siblings — together they run the empire:

| Agent | Role | What it owns |
|---|---|---|
| **Bravo** | CEO | Strategy, clients, outreach, revenue, daily ops |
| **[Atlas](https://github.com/CC90210/CFO-Agent)** | CFO | Tax, finance, treasury, FIRE planning, trading |
| **[Maven](https://github.com/CC90210/CMO-Agent)** | CMO | Content, brand, ads, social, video pipeline |
| **[Aura](https://github.com/CC90210/Aura-Home-Agent)** | Lifestyle | Home, habits, smart-home, voice |

---

## What it actually does

- **Autonomous reasoning loop** — 7-phase brain (orient → recall → assess → plan → verify → execute → reflect) running on a tick. Decides what to do next without being asked.
- **Multi-provider routing** — Claude, OpenAI, OpenRouter, Groq, DeepSeek, local Ollama. Per-agent model config with fallbacks. Switch providers without touching code.
- **Self-learning skills** — successful patterns get extracted into reusable `SKILL.md` files. After 3 successful uses they promote into the main skill tree automatically.
- **Three-layer memory** — working scratchpad → episodic events → semantic facts, with nightly importance-scored consolidation backed by pgvector + mem0.
- **Send chokepoint** — every outbound email passes 8 hardcoded gates: CASL compliance, cooldowns, daily/hourly caps, domain caps, DNS reputation, draft critic, bounce circuit breaker, reservation guard.
- **Multi-platform messaging** — one gateway, multiple adapters: Telegram (live), Discord, Slack. Single dispatcher routes inbound to the right C-Suite agent.
- **Forks for any operator** — clone the repo, run the wizard, and the codebase rewrites itself for you. Your name, your brand, your north star, your voice.

---

## How the install works

The one-liner does eight things:

1. Installs Python 3.10+, Node 18+, and Git if missing
2. Clones into `~/.bravo`
3. Builds a Python venv and installs deps
4. Drops a `bravo` shim onto your PATH
5. Launches the **setup wizard** — asks who you are, what you sell, what you're optimizing for, and which APIs you have keys for
6. Renders your personal `brain/USER.md` from your answers (`scripts/personalize.py`)
7. **Rewrites the codebase to match you** — replaces the original operator's identity tokens across 165+ files (`scripts/scaffold.py --apply --backup`)
8. Runs `bravo doctor` to verify everything works

After it finishes, your machine has your own personalized CEO agent. Not a fork of someone else's working copy — yours.

Full install reference: [`docs/INSTALL.md`](docs/INSTALL.md)

---

## After install

```bash
bravo status              # Live operational summary
bravo agent list          # See all C-Suite agents
bravo doctor              # Health check across credentials, scripts, MCPs
bravo run telegram_agent  # Start the Telegram bridge
```

Or talk to it through Telegram from anywhere.

---

## Under the hood

- **Python 3.12** + **Node 20** runtime
- **Supabase** (Postgres + RLS + pgvector) for state
- **Stripe**, **n8n**, **Late/Zernio**, **Google Workspace** integrations via dedicated CLIs
- **Anthropic Claude** (Opus / Sonnet / Haiku) primary, with OpenAI / OpenRouter / Groq / DeepSeek / local Ollama as fallbacks
- **9 MCP servers** (Playwright, Context7, Memory, Sequential Thinking, Knowledge Graph, GitHub, Firecrawl, Obsidian, Filesystem)
- **152 skills**, **93 scripts**, **21 sub-agents**, **36 workflows**
- **100/100 self-audit health** (run `python scripts/self_audit.py` any time)

See [`brain/CAPABILITIES.md`](brain/CAPABILITIES.md) for the full inventory.

---

## Built by

[Conaugh McKenna](https://oasisai.work) (CC) — founder, [OASIS AI Solutions](https://oasisai.work). Solo build. One operator's working copy, designed from the start to fork for anyone else.

[MIT licensed](LICENSE) · [Issues](https://github.com/CC90210/CEO-Agent/issues) · [Install help](.github/ISSUE_TEMPLATE/install_help.md)

> "Only good things from now on."
