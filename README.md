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
| **[Atlas](https://github.com/CC90210/CFO-Agent)** | CFO | Tax, treasury, research, FIRE planning, financial advisory |
| **[Maven](https://github.com/CC90210/CMO-Agent)** | CMO | Content, brand, ads, social, video pipeline |

All three siblings share the same V6.8 substrate (state DB, retrieval, exec_guard, vocabulary layer) and coordinate via the cross-agent event bus and pulse protocol. Atlas can veto Maven's ad spend; Bravo reads both pulses before scheduling client work.

**V6.2 — Client products** (separate, paid offerings):

| Product | Industry | What it owns |
|---|---|---|
| **Solara** | Funding ops | Sun Biz Funding's lead → SMS → application → funded deal → renewal lifecycle |
| **Suga** | Brand ops | Suga Sean O'Malley's fan engagement, merch drops, social, sponsorship triage |

Each client product is a separate agent + dashboard profile. The Command Center renders an industry-specific sidebar (`SUN_NAV` / `SUGA_NAV`) based on the tenant's brand. New industries slot in by adding one profile + nav array — the underlying engine is the same.

---

## What it actually does

- **Autonomous reasoning loop** — 7-phase brain (orient → recall → assess → plan → verify → execute → reflect) running on a tick. Decides what to do next without being asked.
- **Transactional state engine (V6.0)** — `state/empire_state.db` (SQLite/WAL) is the source of truth for heartbeats, session_log, and active_task. Single writer proxy ([`scripts/state/state_manager.py`](scripts/state/state_manager.py)) replaces flat-file race conditions. Markdown mirrors auto-regenerate.
- **Hybrid semantic memory** — FTS5 lexical + LanceDB cosine (fastembed MiniLM-L6-v2, no PyTorch dep) fused via Reciprocal Rank Fusion through one entry point: [`scripts/core/memory_retriever.py`](scripts/core/memory_retriever.py). Replaces whole-file context loads with <100ms targeted snippet sets.
- **Adversarial security hooks** — AST + regex policy gates on every tool call: [`exec_guard.py`](scripts/state/exec_guard.py), [`secret_guard.py`](scripts/state/secret_guard.py), [`state_guard.py`](scripts/state/state_guard.py). Three modes per guard (off/report/enforce), JSONL audit logs in `state/`. Destructive commands (`DROP TABLE`, `rm -rf /`, `git push --force`) are refused outright — no approval queue, no human-in-the-loop friction. The block IS the protection.
- **Multi-machine bridge arbitration (V6.5)** — [`scripts/bridge_lock.py`](scripts/bridge_lock.py) is the lockfile arbiter for Telegram (and future Discord/Slack) bridges across paired machines. Acquire / heartbeat (15s) / release. Replaced the silent-409-dormancy failure mode that left bridges broken for days.
- **Capability graph (V6.6)** — [`brain/CAPABILITY_GRAPH.json`](brain/CAPABILITY_GRAPH.json) is the canonical machine-readable registry of every skill, script, agent, MCP server, and workflow. Auto-discovered from frontmatter + docstrings + MCP configs. Resolve intents at decision time: `python scripts/capability_query.py resolve "send outreach email"`. Add new capabilities with `python scripts/register.py skill <name>`.
- **Hooks-as-orchestration (V6.7)** — `.claude/settings.local.json` wires `SessionStart` (state + inbox + 7-day staleness, ~380ms), `PreCompact` (SOUL + ACTIVE_TASKS re-injected before compression, ~7KB), and `UserPromptSubmit` (tiered T1/T2/T3 retrieval snippet injection, ~200ms) plus the anti-pattern hook on `PreToolUse Bash`. Hooks are no longer just guards — they're the orchestration layer.
- **Pantry / Prep Table / Plate data tier (V6.7)** — [`brain/DATA_TAXONOMY.md`](brain/DATA_TAXONOMY.md) is the manifest. Three snapshot pipelines (`briefing_snapshot.py`, `leads_snapshot.py`, `client_alerts_snapshot.py`) pre-aggregate via cron so consumers (CEO briefing, leads dashboard, client alerts) read a deterministic JSON instead of burning context on live retrieval.
- **Research-fetch ladder + CloakBrowser (V6.7)** — [`scripts/research_fetch.py`](scripts/research_fetch.py) is the default URL entry point: auto-escalates Firecrawl → CloakBrowser → Browser Harness → Playwright with per-domain reputation memory in `state/site_reputation.db`. CloakBrowser is a drop-in Playwright replacement with C++ source-level fingerprint patches — mandatory tier-2 stealth for Cloudflare / DataDome / reCAPTCHA / FingerprintJS / Akamai / Kasada protected sites.
- **Agent-OS vocabulary layer (V6.8)** — Root [`CONTEXT.md`](CONTEXT.md) is the canonical empire glossary (people, brands, multi-tenancy, sales/CRM, state/substrate, V6 arch, browser ladder, North Star). Auto-injected on UserPromptSubmit when a glossary term appears in the prompt. Architectural decisions live in [`docs/adr/`](docs/adr/) — separate from tactical business decisions.
- **Skill governance (V6.8)** — Frontmatter conventions enforced by the resolver: `disable_model_invocation` (slash-command-only skills), `argument_hint` (runtime prompts), and `requires: [env:KEY, daemon:NAME, state:PATH]` (hard deps per ADR-0001, verified by `capability_query.py check-deps`). Lifecycle dirs: `skills/_archive/` and `skills/in-progress/`.
- **External distribution** — [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) packages 47 universally-useful skills for `npx skills@latest add` consumption. Operators who don't want to fork the whole agent can grab just the skills.
- **Multi-provider routing** — Claude, OpenAI, OpenRouter, Groq, DeepSeek, local Ollama. Per-agent model config with fallbacks. Switch providers without touching code.
- **Self-learning skills** — successful patterns extracted into reusable `SKILL.md` files. After 3 successful uses they promote into the main skill tree automatically.
- **Send chokepoint** — every outbound email passes 8 hardcoded gates: CASL compliance, cooldowns, daily/hourly caps, domain caps, DNS reputation, draft critic, bounce circuit breaker, reservation guard.
- **Multi-platform messaging** — one gateway, multiple adapters: Telegram (live), Discord, Slack. Single dispatcher routes inbound to the right C-Suite agent.
- **Sandboxed Docker** — Turnkey `docker-compose` stacks for both `local` (read-only rootfs) and `cloud` (Nginx/Caddy + SSL) B2B client deployments.
- **Forks for any operator** — clone the repo, run the setup wizard, and the codebase rewrites itself and fans out scoped secrets for your specific deployment.

---

<details>
<summary><strong>V6 architecture timeline</strong></summary>

| Version | Date | Primary deliverable | Critical files |
|---|---|---|---|
| **V6.0** | 2026-05-10 | Four pillars: state DB (SQLite/WAL), FTS5 retrieval, exec/secret/state guards, scoped secret loader | `state/empire_state.db`, `scripts/{state_manager,memory_retriever,exec_guard,secret_guard,state_guard}.py` |
| **V6.0 Phase 2** | 2026-05-10 | Productized deployment: setup wizard `step_v6_init`, `infra/docker-compose.{local,cloud}.yml`, `state-api` FastAPI, `/system-health` + `/playbook/onboarding` Command Center pages, scoped env fan-out (`.env.agents.{core,webhook,dashboard}`) | `infra/docker-compose.*.yml`, [`app/(internal)/system-health/page.tsx`](https://github.com/CC90210/oasis-command-center/blob/main/app/system-health/page.tsx) |
| **V6 Apex** | 2026-05-10 | Cross-agent event bus (Postgres `agent_events` with LISTEN/NOTIFY + `claim_events` SKIP LOCKED), hybrid semantic memory (FTS5 + LanceDB RRF), `/feed` view. ~~Dashboard override approvals~~ deleted 2026-05-22 per CC — exec_guard still blocks destructive commands; the block IS the protection. | `brain/EVENT_BUS_CONTRACT.md`, `scripts/core/event_router.py`, [`app/(internal)/feed/page.tsx`](https://github.com/CC90210/oasis-command-center/blob/main/app/feed/page.tsx) |
| **Command Center split** | 2026-05-18 | `apps/command-center/` extracted to its own GitHub repo + Vercel project (preserves 366 commits); parent repo refocused on Python/agent intelligence | [oasis-command-center](https://github.com/CC90210/oasis-command-center), `~/APPS/oasis-command-center` |
| **V6.5** | 2026-04-20 | Multi-machine bridge arbitration replacing silent-409 dormancy | `scripts/bridge_lock.py` |
| **V6.6** | 2026-04-26 | Capability graph + auto-discovery + runtime resolver + add-a-skill wizard | `brain/CAPABILITY_GRAPH.json`, `scripts/{build_capability_graph,capability_query,register}.py` |
| **V6.7** | 2026-05-14 | Hooks-as-orchestration, Pantry/Prep Table/Plate data tier, research_fetch ladder, CloakBrowser, three canonical skills (silver-platter / integrations-sync / memory-journaling), six new INTENTS playbooks | `scripts/hooks/{session_start,pre_compact,user_prompt_submit,rotate_logs}.py`, `scripts/snapshots/*.py`, `brain/DATA_TAXONOMY.md`, `scripts/{research_fetch,cloak_browser_tool}.py` |
| **V6.8** | 2026-05-16 | Vocabulary layer (CONTEXT.md auto-injection), ADRs (`docs/adr/`), skill frontmatter conventions, lifecycle dirs, distribution manifest | `CONTEXT.md`, `docs/adr/0001-skill-dependency-classification.md`, `.claude-plugin/plugin.json` |
| **V6.8.1** | 2026-05-16 | Load-bearing substrate: glossary auto-injection on UserPromptSubmit, ADR `check-deps` enforcement, register.py wizard emits V6.8 frontmatter by default | `scripts/hooks/user_prompt_submit.py`, `scripts/capability_query.py check-deps` |

Source of truth: [`CLAUDE.md`](CLAUDE.md) and [`brain/CAPABILITIES.md`](brain/CAPABILITIES.md). The README is the curated surface; the graph is the inventory.

</details>

---

## Capability graph

The README lists what's worth highlighting. The full inventory lives in a machine-readable graph: [`brain/CAPABILITY_GRAPH.json`](brain/CAPABILITY_GRAPH.json). It's auto-discovered from frontmatter and MCP configs; never hand-maintained.

```bash
# Resolve an intent to its best-fit skill
python scripts/capability_query.py resolve "send outreach email"

# Verify a node's hard dependencies (env vars, daemons, state files)
python scripts/capability_query.py check-deps outreach-send

# Add a new skill end-to-end (frontmatter + graph rebuild + self-audit)
python scripts/register.py skill my-new-skill --description "..." --triggers "..."
```

`register.py` ends the 6-step add-a-skill ritual. `capability_query.py resolve` is what the agent itself calls at decision time instead of grepping markdown.

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
7. **Data sovereignty prompt** — choose **Local libSQL** (PII never leaves the machine; recommended for client products like Solara/Suga) or **Cloud Supabase** (managed multi-tenant). Writes `EMPIRE_DATA_BACKEND` + `TURSO_DB_PATH`. The dashboard's [`lib/db.ts:getDbBackend()`](https://github.com/CC90210/oasis-command-center/blob/main/lib/db.ts) reads this at request time and routes hot reads via [`lib/turso-queries.ts`](https://github.com/CC90210/oasis-command-center/blob/main/lib/turso-queries.ts)
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

If something breaks: `python scripts/core/self_audit.py` — verdict `HEALTHY` means ship-grade. Anything else, the script tells you exactly what to fix.

Or talk to it through Telegram from anywhere.

---

## Don't want to fork the whole agent? Grab the skills

If you have Claude Code and just want the reusable parts: [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) lists 47 universally-useful skills (debugging, testing, code review, browser automation, MCP operations, content optimization, etc.) packaged for `npx skills@latest add` consumption. Excludes Bravo-internal (`outreach-send`, `gws-*`), staging, archived.

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
- <!-- STATS:skills-->**149 skills**<!-- /STATS -->, <!-- STATS:scripts-->**97 scripts**<!-- /STATS -->, <!-- STATS:sub_agents-->**21 sub-agents**<!-- /STATS -->, <!-- STATS:workflows-->**35 workflows**<!-- /STATS --> (counts auto-regenerated by [`scripts/update_readme_stats.py`](scripts/update_readme_stats.py) — `--check` exits 1 on drift, runs in pre-commit)
- **Self-audit gate** — `python scripts/core/self_audit.py` enforces graph health, orphan detection, and config drift on every commit. Verdict must be `HEALTHY` to ship.
- **Security model** — Three guards (exec/secret/state) gate every Bash, Read, and Edit. Three modes per guard (off/report/enforce) via env var; cloud target enforces all three by default, local target runs `secret_guard=enforce, exec_guard=report, state_guard=off`. Audit logs in `state/{guard}.log`. Dashboard-driven override workflow (HMAC-signed) when an action is legitimately blocked.

See [`brain/CAPABILITIES.md`](brain/CAPABILITIES.md) for the full inventory, [`brain/SECURITY_MODEL.md`](brain/SECURITY_MODEL.md) for the canonical security architecture (multi-tenant RLS, encryption at rest, bridge token lifecycle, HMAC self-pair, threat model), and [`CONTEXT.md`](CONTEXT.md) for the canonical vocabulary every sibling agent shares.

---

## Pricing

**Free.** MIT-licensed. Fork it, scaffold it for your operator identity, run it on your infrastructure. There is no SaaS tier and no plan to add one. The reference deployment is the original operator's own working copy — it is not a hosted product you sign up for.

If you want help installing or customizing it for your business: [open an issue](https://github.com/CC90210/CEO-Agent/issues) or reach out to the original operator below.

---

## Built by

[Conaugh McKenna](https://oasisai.work) (CC) — founder, [OASIS AI Solutions](https://oasisai.work). Solo build. One operator's working copy, designed from the start to fork for anyone else.

[MIT licensed](LICENSE) · [Issues](https://github.com/CC90210/CEO-Agent/issues) · [Install help](.github/ISSUE_TEMPLATE/install_help.md) · [Security model](brain/SECURITY_MODEL.md) · [Contributing](CONTRIBUTING.md)

## Obsidian
- [[CONTRIBUTING]] · [[CLAUDE]] · [[CONTEXT]] · [[brain/SOUL]] · [[brain/CAPABILITIES]] · [[docs/INDEX]] · [[docs/INSTALL]]

> "Only good things from now on."

## Related leaves
- [[prompts/RUN_OUTREACH]]
- [[scripts/windows_bootstrap]]
