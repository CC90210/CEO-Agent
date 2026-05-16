
<img width="640" height="640" alt="image" src="https://github.com/user-attachments/assets/dc1786b4-f90c-49bf-b424-b8ad3ce459f1" />



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

One command. A few minutes. The wizard asks who you are, helps you connect your tools, and gives you your own personalized AI CEO or client digital employee.

---

## What you get

**Bravo** is the CEO. It works alongside its sibling C-Suite — together they run the empire:

| Agent | Role | What it owns |
|---|---|---|
| **Bravo** | CEO | Strategy, clients, outreach, revenue, daily ops |
| **[Atlas](https://github.com/CC90210/CFO-Agent)** | CFO | Tax, finance, treasury, FIRE planning, trading |
| **[Maven](https://github.com/CC90210/CMO-Agent)** | CMO | Content, brand, ads, social, video pipeline |

**V6.2 — Client products** (separate, paid offerings):

| Product | Industry | What it owns |
|---|---|---|
| **Solara** | Funding ops | Sun Biz Funding's lead → SMS → application → funded deal → renewal lifecycle |
| **Suga** | Brand ops | Suga Sean O'Malley's fan engagement, merch drops, social, sponsorship triage |

Each client product is a separate agent + dashboard profile. The Command Center renders an industry-specific sidebar (`SUN_NAV` / `SUGA_NAV`) based on the tenant's brand. New industries slot in by adding one profile + nav array — the underlying engine is the same.

---

## What it actually does

- **Autonomous reasoning loop** — 7-phase brain (orient → recall → assess → plan → verify → execute → reflect) running on a tick. Decides what to do next without being asked.
- **V6.0 Transactional State Engine** — Concurrent multi-agent safety via a SQLite/WAL engine, replacing legacy flat-file locks.
- **Semantic Memory Retrieval** — FTS5 full-text search indexing to load specific context chunks instead of entire files, drastically reducing token bloat.
- **Adversarial Security Hooks** — Deeply-tested AST and regex hooks (`exec_guard`, `secret_guard`, `state_guard`) that protect the host OS and environment variables against LLM hallucination and breakout attempts.
- **Sandboxed Docker Environments** — Turnkey `docker-compose` stacks for both `local` (read-only rootfs) and `cloud` (Nginx/Caddy + SSL) B2B client deployments.
- **Multi-provider routing** — Claude, OpenAI, OpenRouter, Groq, DeepSeek, local Ollama. Per-agent model config with fallbacks. Switch providers without touching code.
- **Self-learning skills** — successful patterns get extracted into reusable `SKILL.md` files. After 3 successful uses they promote into the main skill tree automatically.
- **Send chokepoint** — every outbound email passes 8 hardcoded gates: CASL compliance, cooldowns, daily/hourly caps, domain caps, DNS reputation, draft critic, bounce circuit breaker, reservation guard.
- **Multi-platform messaging** — one gateway, multiple adapters: Telegram (live), Discord, Slack. Single dispatcher routes inbound to the right C-Suite agent.
- **Forks for any operator** — clone the repo, run the setup wizard, and the codebase rewrites itself and fans out scoped secrets for your specific deployment.

---

## See it running

The reference deployment lives at **[agent-dashboard-cc90210.vercel.app](https://agent-dashboard-cc90210.vercel.app)** (auth-gated — that's the operator's working copy). After your install, your own dashboard runs at the same URL with your tenant data via Supabase RLS.

> **Add a screenshot:** drop `docs/screenshots/operations.png` into the repo and replace this block with `![operations](docs/screenshots/operations.png)`. The Operations page is the most legible single view (paired machines, warm process pool, live agent activity tape).

---

## How the install works

The one-liner does nine things:

1. Installs Python 3.10+, Node 18+, and Git if missing
2. Bootstraps the wizard into `~/.oasis/wizard/repo` and reuses that clone on future installs
3. Builds a Python venv at `~/.oasis/wizard/venv` and installs deps
4. Drops both `oasis` and `bravo` shims onto your PATH via `~/.oasis/bin`
5. Launches the **setup wizard** — asks who you are, what you sell, what you're optimizing for, and which APIs you have keys for. **Pick your profile** (CEO Bravo / CFO Atlas / CMO Maven / **client products Solara (SunBiz) · Suga**)
6. Renders your personal `brain/USER.md` from your answers (`scripts/personalize.py`)
7. **Data sovereignty prompt** — choose **Local libSQL** (PII never leaves the machine; recommended for client products like Solara/Suga) or **Cloud Supabase** (managed multi-tenant). Writes `EMPIRE_DATA_BACKEND` + `TURSO_DB_PATH`. The dashboard's [`lib/db.ts:getDbBackend()`](apps/command-center/lib/db.ts) reads this at request time and routes hot reads via [`lib/turso-queries.ts`](apps/command-center/lib/turso-queries.ts)
8. **Browser-driven dashboard pairing** — wizard opens your dashboard flow, waits for sign-in, and pairs the machine without making you juggle raw bearer tokens
9. **Rewrites the codebase to match you** — replaces the original operator's identity tokens across every reference in tracked files (`scripts/scaffold.py --apply --backup`), then runs `bravo doctor` to verify everything works

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
- **Supabase** (Postgres + RLS + pgvector) for state and shared empire data
- **Turso / libSQL** for tenant data sovereignty — client products store leads, deals, fan data on the operator's machine; OASIS reads pulse only
- **Multi-user team access** (V6.2) — `tenant_invites` + role-based gating (`owner`/`admin`/`loan_officer`/`processor`/`read_only`/`member`); owner machine pairings are trigger-protected from employee revocation. See [`database/037_team_roles_and_invites.sql`](database/037_team_roles_and_invites.sql) and the `/team` page
- **Stripe**, **n8n**, **Late/Zernio**, **Google Workspace** integrations via dedicated CLIs
- **Anthropic Claude** (Opus / Sonnet / Haiku) primary, with OpenAI / OpenRouter / Groq / DeepSeek / local Ollama as fallbacks
- <!-- STATS:mcp_servers-->**9 MCP servers**<!-- /STATS --> (Playwright, Context7, Memory, Sequential Thinking, Knowledge Graph, GitHub, Firecrawl, Obsidian, Filesystem)
- <!-- STATS:skills-->**154 skills**<!-- /STATS -->, <!-- STATS:scripts-->**127 scripts**<!-- /STATS -->, <!-- STATS:sub_agents-->**20 sub-agents**<!-- /STATS -->, <!-- STATS:workflows-->**36 workflows**<!-- /STATS --> (counts auto-regenerated by `scripts/update_readme_stats.py` — never go stale)
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

## Obsidian
- [[CONTRIBUTING]] · [[CLAUDE]] · [[brain/SOUL]] · [[brain/CAPABILITIES]] · [[docs/INDEX]] · [[docs/INSTALL]]

> "Only good things from now on."

## Related leaves
- [[prompts/RUN_OUTREACH]]
- [[scripts/windows_bootstrap]]
