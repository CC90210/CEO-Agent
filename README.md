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
- **Multi-machine pairing** — same dashboard, multiple bridges. Desktop runs production daemons; laptop adds a chat-server. Pair endpoint is fingerprint-idempotent so re-installs don't duplicate rows.
- **Forks for any operator** — clone the repo, run the wizard, and the codebase rewrites itself for you. Your name, your brand, your north star, your voice.

---

## See it running

The reference deployment lives at **[agent-dashboard-cc90210.vercel.app](https://agent-dashboard-cc90210.vercel.app)** (auth-gated — that's the operator's working copy). After your install, your own dashboard runs at the same URL with your tenant data via Supabase RLS.

> **Add a screenshot:** drop `docs/screenshots/operations.png` into the repo and replace this block with `![operations](docs/screenshots/operations.png)`. The Operations page is the most legible single view (paired machines, warm process pool, live agent activity tape).

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

## After install — your first 10 minutes

```bash
bravo status              # Live operational summary
bravo doctor              # Health check across credentials, scripts, MCPs
bravo agent list          # See all C-Suite agents
```

Then open your dashboard, head to **`/playbook/client-deploy`**, and follow the 6-phase runbook (it's the same playbook the original operator uses to onboard their own machine — you're effectively your own first client). Phase 06 hands you the override syntax and the `bravo bridge restart` move so you can run yourself for week 1 without needing help.

If something breaks: `python scripts/self_audit.py` — verdict `HEALTHY` means ship-grade. Anything else, the script tells you exactly what to fix.

Or talk to it through Telegram from anywhere.

---

## Why fork this vs build from scratch

- **You skip the 6 months of plumbing** — multi-tenant Supabase + RLS + AES-256-GCM encryption + bridge auth + warm-process pool + popup-suppression + cross-machine pairing are all done. This stuff isn't fun to build and isn't your differentiation.
- **You get the operator's actual playbook** — not just code. The `/playbook` surface in the dashboard is the working playbook the original operator uses daily, not aspirational documentation.
- **You don't pay rent on it** — MIT-licensed, fork-friendly. No SaaS lock-in. Your data lives on your Supabase or the shared one (your call).
- **It's been used in production** — the reference deployment ships with 149+ Vercel deploys, daily MRR tracking, daily Skool community automation, and a paired Mac + Windows setup. The bugs you'd hit on a greenfield build have already been hit and fixed.

If you'd rather build from scratch: respect, but you're paying yourself ~$50K of engineering time at market rates to get to where this repo starts.

---

## Under the hood

- **Python 3.12** + **Node 20** runtime
- **Supabase** (Postgres + RLS + pgvector) for state
- **Stripe**, **n8n**, **Late/Zernio**, **Google Workspace** integrations via dedicated CLIs
- **Anthropic Claude** (Opus / Sonnet / Haiku) primary, with OpenAI / OpenRouter / Groq / DeepSeek / local Ollama as fallbacks
- <!-- STATS:mcp_servers-->**9 MCP servers**<!-- /STATS --> (Playwright, Context7, Memory, Sequential Thinking, Knowledge Graph, GitHub, Firecrawl, Obsidian, Filesystem)
- <!-- STATS:skills-->**153 skills**<!-- /STATS -->, <!-- STATS:scripts-->**115 scripts**<!-- /STATS -->, <!-- STATS:sub_agents-->**20 sub-agents**<!-- /STATS -->, <!-- STATS:workflows-->**36 workflows**<!-- /STATS --> (counts auto-regenerated by `scripts/update_readme_stats.py` — never go stale)
- **Self-audit gate** — `python scripts/self_audit.py` enforces graph health, orphan detection, and config drift on every commit. Verdict must be `HEALTHY` to ship.

See [`brain/CAPABILITIES.md`](brain/CAPABILITIES.md) for the full inventory and [`brain/SECURITY_MODEL.md`](brain/SECURITY_MODEL.md) for the canonical security architecture (multi-tenant RLS, encryption at rest, bridge token lifecycle, HMAC self-pair, threat model).

---

## Pricing

**Free.** MIT-licensed. Fork it, scaffold it for your operator identity, run it on your infrastructure. There is no SaaS tier and no plan to add one. The reference deployment is the original operator's own working copy — it is not a hosted product you sign up for.

If you want help installing or customizing it for your business: [open an issue](https://github.com/CC90210/CEO-Agent/issues) or reach out to the original operator below.

---

## Built by

[Conaugh McKenna](https://oasisai.work) (CC) — founder, [OASIS AI Solutions](https://oasisai.work). Solo build. One operator's working copy, designed from the start to fork for anyone else.

[MIT licensed](LICENSE) · [Issues](https://github.com/CC90210/CEO-Agent/issues) · [Install help](.github/ISSUE_TEMPLATE/install_help.md) · [Security model](brain/SECURITY_MODEL.md) · [Contributing](CONTRIBUTING.md)

> "Only good things from now on."
