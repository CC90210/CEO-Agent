# Agent Repo Cross-Analysis: Hermes Agent + Browser Harness vs Bravo

Date: 2026-04-22
Prepared by: Codex, backend executor for Business-Empire-Agent
Scope: Diagnostic only. No production code, credentials, services, or database tables were changed.

## Sources Inspected

- Hermes Agent public repo: https://github.com/nousresearch/hermes-agent
- Browser Harness public repo: https://github.com/browser-use/browser-harness
- Local clone: `tmp/repo-research/hermes-agent` at commit `84449d9`
- Local clone: `tmp/repo-research/browser-harness` at commit `71f1b3b`
- Local Business-Empire-Agent repo at commit `8a966a8`, with pre-existing dirty worktree changes noted before inspection

Both external repos include MIT licenses. If we reuse code directly, keep attribution and license text. For this phase, the recommendation is to copy architecture patterns and product ideas first, not blindly paste their code.

## Executive Verdict

Bravo is already stronger than Hermes as a business-specific operating brain. It has real memory, real business context, the V5.6 outbound chokepoint, Supabase/Stripe/Google/n8n scripts, C-Suite routing, and a founder-specific mission. Hermes is stronger as a packaged agent product. Browser Harness is stronger as a focused browser automation primitive.

The honest gap is this:

Bravo feels like a powerful internal command center. Hermes feels like a product someone can install. Browser Harness feels like a small sharp tool agents can learn with. The leapfrog path is not to make Bravo a giant clone of Hermes. It is to give Bravo Hermes-grade onboarding, diagnostics, runtime packaging, skill lifecycle, and Browser Harness-grade compounding browser intelligence while preserving Bravo's business-specific judgment and safety rules.

If we execute this correctly, Bravo becomes the flagship agent factory: one command to install, one wizard to configure, one doctor to diagnose, one browser layer that learns, one scaffold to create Atlas/Maven/Aura/Hermes/client agents, and one memory system that gets better after every session.

## Scorecard

| Capability | Bravo Today | Hermes Agent | Browser Harness | Brutal Read |
|---|---:|---:|---:|---|
| Founder/business context | 10/10 | 2/10 | 1/10 | Bravo dominates. This is our moat. |
| One-command install | 3/10 | 9/10 | 8/10 | Bravo is behind. This is the biggest product gap. |
| Setup wizard | 3/10 | 9/10 | 7/10 | Bravo has scripts, not a guided onboarding flow. |
| Unified CLI | 4/10 | 9/10 | 8/10 | Bravo has many useful scripts but no single product command. |
| Terminal polish/branding | 4/10 | 9/10 | 6/10 | Hermes feels like a polished agent when launched. Bravo feels internal. |
| Runtime home/profile model | 4/10 | 9/10 | 7/10 | Hermes has `~/.hermes`; Bravo needs `~/.bravo` or `~/.oasis-agents`. |
| Skill system | 8/10 | 9/10 | 9/10 | Bravo has many skills. Hermes/Browser Harness manage and evolve them better. |
| Browser automation | 6/10 | 8/10 | 9/10 | Bravo has Playwright/Firecrawl coverage but lacks the durable browser-learning layer. |
| Messaging gateway | 7/10 | 10/10 | 1/10 | Bravo has Telegram/n8n/email paths. Hermes has a true multi-platform gateway architecture. |
| Memory/session recall | 8/10 | 9/10 | 6/10 | Bravo has brain/memory/Supabase. Hermes has stronger session search and profile isolation. |
| Agent creation/scaffolding | 6/10 | 8/10 | 4/10 | Bravo can become best-in-class here with a dedicated Agent Forge. |
| Security for business actions | 9/10 | 7/10 | 5/10 | Bravo's outbound chokepoint is better and should stay non-negotiable. |
| Windows-native fit | 7/10 | 4/10 | 5/10 | This is a leapfrog opportunity. Hermes is WSL/Linux-first. |

## What Hermes Has That We Need

Hermes is structured like an installable agent platform. Its strongest pieces are:

1. A real CLI front door.
   - `hermes_cli/main.py` exposes commands for chat, setup, model selection, gateway, auth, cron, skills, memory, tools, sessions, doctor, update, backup, import, profile, TUI, logs, and more.
   - Bravo has scripts, npm helpers, and workflows, but not one user-facing command like `bravo setup`, `bravo doctor`, or `bravo agent create`.

2. A serious install path.
   - `scripts/install.sh` does OS detection, installs/locates `uv`, Python, Node, ripgrep, ffmpeg, creates `~/.hermes`, seeds config/env/SOUL, syncs bundled skills, and launches a setup wizard.
   - `setup-hermes.sh` handles developer bootstrap.
   - Bravo's README has setup instructions, but the product install does not exist yet as one command.

3. A runtime home directory.
   - Hermes stores config, auth, skills, memory, sessions, logs, cron, pairing, hooks, and caches under `~/.hermes`.
   - Bravo currently lives mostly inside the repo. That is fine for CC's machine, but it is weaker for productizing agents across client installs.

4. Config as a first-class product surface.
   - `cli-config.yaml.example` is broad and explicit: providers, model aliases, toolsets, browser, terminal backends, MCP servers, compression, privacy, shell hooks, TTS, and platform presets.
   - Bravo has `.env.agents`, docs, and local scripts. It needs a generated, validated config layer that can be edited with CLI commands.

5. Toolsets and execution backends.
   - Hermes has reusable toolset distributions and multiple terminal backends: local, Docker, SSH, Modal, Daytona, Singularity.
   - Bravo has many scripts, but the runtime does not yet expose them as clean tool bundles with environment/profile presets.

6. Gateway as a platform layer.
   - Hermes treats messaging as a daemonized gateway with adapters.
   - Bravo has Telegram and n8n strength, but gateway logic is not yet modular enough to become a reusable agent product surface.

7. Session search.
   - Hermes has SQLite/FTS-style session search and session lineage concepts.
   - Bravo has markdown state, mem0, Supabase, and session logs. That is powerful, but less convenient for agent-native search across past work.

8. Skills as procedural memory.
   - Hermes can browse, inspect, install, audit, reset, publish, snapshot, and patch skills.
   - Bravo can register skills, but the agent-managed skill lifecycle should become a first-class command set.

9. Terminal/TUI identity.
   - Hermes has skin/theme support and a distinct terminal feel.
   - Bravo needs a branded terminal launch experience: color, banner, health status, active agent, MRR target, current system status, and next command suggestions.

## Hermes Structure Worth Mirroring

Hermes top-level structure has useful separation:

| Hermes Area | Purpose | Bravo Equivalent Today | Recommended Bravo Path |
|---|---|---|---|
| `hermes_cli/` | Product CLI and setup commands | scattered scripts/npm commands | create `bravo_cli/` |
| `scripts/install.sh` | end-user install | manual README steps | create `install/install.ps1` and `install/install.sh` |
| `setup-hermes.sh` | dev bootstrap | partial npm/Python setup | create `scripts/bootstrap.py` |
| `gateway/` | messaging daemon/adapters | `telegram_agent.js`, n8n, scripts | create `runtime/gateway/` over time |
| `cron/` | scheduled jobs | n8n, scripts, cron docs | wrap into CLI-visible scheduler status |
| `tools/` | tool registry and backends | `scripts/` | create registry metadata for scripts |
| `skills/` and `optional-skills/` | bundled vs add-on skills | `skills/` only | add skill manifest, optional packs, sync/audit |
| `website/docs/` | public docs | README/docs/brain | generate docs from product commands and manifests |
| `ui-tui/` | full-screen terminal UI | no equivalent | later phase, after CLI/doctor |
| `plugins/` | extension surface | skills and MCP configs | add plugin packs only after core install works |

## What Browser Harness Has That We Need

Browser Harness is valuable because it is small and compounding. It is not trying to be a full agent. It is a focused browser control layer plus a skill-capture discipline.

Its strongest ideas:

1. Tiny direct-control runtime.
   - `run.py` reads Python from stdin, auto-starts a daemon, imports helpers, and executes browser commands.
   - `helpers.py` exposes the practical browser verbs: `new_tab`, `goto`, `click`, `type_text`, `press_key`, `scroll`, `screenshot`, `list_tabs`, `switch_tab`, `js`, `http_get`, and raw CDP access.
   - `daemon.py` handles the Chrome DevTools Protocol connection and socket lifecycle.

2. Interaction skills vs domain skills.
   - `interaction-skills/` are reusable mechanics: tabs, dialogs, scrolling, screenshots, file upload, keyboard, shadow DOM, iframes, etc.
   - `domain-skills/` are site-specific maps: stable selectors, private APIs, waits, traps, URL patterns, and known workflows.
   - Bravo has browser skills, but not this two-layer browser memory system.

3. "Learn while doing" discipline.
   - If an agent discovers a non-obvious site mechanic, it should turn that into a durable domain skill.
   - The skill should not store secrets, cookies, raw coordinates, or diary-style narration.

4. Real-browser and remote-browser support.
   - Browser Harness can attach to a logged-in local browser or Browser Use Cloud.
   - This matters for agents that must operate in real web apps where APIs are not enough.

5. Doctor/setup/update baked in.
   - The skill itself teaches the agent to run `browser-harness --doctor`, `--setup`, and `--update`.
   - Bravo's browser stack needs this same operational hygiene.

## Browser Harness Structure Worth Mirroring

| Browser Harness Area | Purpose | Bravo Gap | Recommended Bravo Path |
|---|---|---|---|
| `SKILL.md` | global agent instruction for browser harness | browser instructions split across several skills | create a canonical Browser Harness skill pack |
| `helpers.py` | small editable browser API | Playwright/MCP usage is stronger but heavier | expose a thin helper API for routine browser work |
| `daemon.py` | long-lived browser connection | no canonical browser daemon | add browser profile/bootstrap doctor first |
| `admin.py` | setup/doctor/update/cloud | no browser-specific doctor | create `bravo browser doctor/setup/status` |
| `interaction-skills/` | browser mechanics | mechanics buried in docs/skills | add `browser/interaction-skills/` |
| `domain-skills/` | site knowledge | no durable web-app map layer | add `browser/domain-skills/` and enforce hygiene |

## What Bravo Already Does Better

This matters because the answer is not "Hermes is better." It is more precise:

1. Bravo has a real business operating model.
   - `brain/`, `memory/`, `agents/`, `.agents/workflows/`, `scripts/`, Supabase, n8n, Telegram, Stripe, Google Workspace, and the C-Suite pattern are already tied to CC's companies.

2. Bravo has stronger business safety.
   - The V5.6 `scripts/integrations/send_gateway.py` outbound chokepoint is better than a general-purpose agent's free-form messaging tools.
   - This should not be weakened. Every outbound email, DM, call log, and future browser-based send action should still route through the chokepoint or an explicit approval gate.

3. Bravo has real operating memory.
   - `brain/STATE.md`, `memory/ACTIVE_TASKS.md`, `memory/SESSION_LOG.md`, mem0, Supabase tables, and agent events provide a live operational view.

4. Bravo has a broader business script library.
   - The repo has many production scripts for Supabase, Stripe, Google, n8n, Telegram, health, context, and state sync.
   - The problem is packaging and discoverability, not lack of capability.

5. Bravo is Windows-relevant.
   - Hermes is much more Linux/WSL-oriented. CC's daily environment is Windows-heavy. A polished Windows-native installer would be a real differentiator.

## Brutal Gaps In Bravo Today

1. No real one-command installer.
   - The repo needs `install/install.ps1` for Windows and `install/install.sh` for macOS/Linux/WSL.
   - The install should check Python, Node, Git, ripgrep, Playwright, browser readiness, env template, config, skills, scripts, and services.

2. No unified product CLI.
   - `package.json` exposes helper commands, but there is no `bravo` or `empire` command.
   - Users should not need to know which script to call.

3. No guided setup wizard.
   - A user should be asked: which agent profile, which model/provider, which services, which browser mode, which gateway, which database project, which safety gates, and whether to run doctor now.

4. No product home directory.
   - Add `~/.bravo` or `~/.oasis-agents` with:
     - `config.toml`
     - `.env`
     - `profiles/`
     - `sessions/`
     - `logs/`
     - `skills/`
     - `browser/domain-skills/`
     - `browser/interaction-skills/`
     - `cache/`

5. Health checks are fragmented.
   - `self_audit.py`, `codex_health.py`, workstation scripts, and npm commands should be wrapped by one CLI: `bravo doctor`.

6. Script catalog is not manifest-driven.
   - Counts drift between README, STATE, CAPABILITIES, and actual filesystem.
   - Add `scripts/catalog_sync.py` or `scripts/regen_capabilities.py` to generate counts and command docs from filesystem truth.

7. Browser automation does not compound enough.
   - Existing Playwright and browser skills are useful.
   - Missing: domain-skill memory for specific sites, browser doctor, profile bootstrap, evidence bundle, and a standard "learn this site" flow.

8. Agent creation is not yet a product.
   - Bravo can create agents manually, but it needs a one-command Agent Forge:
     - `bravo agent create atlas --type cfo`
     - `bravo agent create client --template operations`
     - `bravo agent doctor hermes`

9. Gateway architecture is not modular enough.
   - Telegram is real, n8n is real, email is real, but they do not present as adapter plugins yet.
   - This is lower priority than CLI/install/browser, but it matters for long-term scale.

10. Public README is not conversion-grade.
   - Hermes tells a new user exactly how to install and what happens next.
   - Bravo's README explains the system, but does not yet create the "I can run this in two minutes" feeling.

11. Terminal UX is under-branded.
   - We can add a clean banner, colors, status blocks, and command suggestions without wasting time on decorative fluff.
   - This matters because terminal feel changes perceived power.

12. Missing files are referenced by docs.
   - The local audit found references to files like `scripts/setup_shared_db.py`, `onboard-client.sh`, `sanitize-for-client.sh`, and `.env.agents.template` that are not present.
   - That creates trust gaps for productization.

## What Not To Copy

Do not copy Hermes' size for its own sake. Some Hermes files are extremely large, and that can become hard to maintain. Bravo should copy the product surfaces and architecture boundaries, not the monolith shape.

Do not weaken Bravo's safety by adding broad browser or messaging power without gates. Browser Harness is intentionally direct and high-trust. For CC's business agents, any real account action, outbound communication, finance action, admin setting, or irreversible browser click needs explicit approval rules.

Do not make all agents identical. Atlas, Maven, Aura, Bravo, and Hermes should share the core runtime, install/doctor/browser/session substrate, but each should keep its own domain brain and permissions.

Do not make the browser layer the only automation layer. APIs, Supabase tools, Stripe tools, Google tools, n8n tools, and send_gateway should remain primary when available. Browser automation is the fallback and UI-only layer.

## Target Architecture: Bravo As Agent Factory

The next version should add a product shell around the existing intelligence.

Recommended top-level additions:

```text
bravo_cli/
  __init__.py
  main.py
  commands/
    setup.py
    doctor.py
    status.py
    config.py
    skills.py
    tools.py
    browser.py
    agents.py
    sessions.py
    gateway.py

install/
  install.ps1
  install.sh

config/
  bravo-config.example.toml
  profiles/
    bravo.toml
    atlas.toml
    maven.toml
    aura.toml
    hermes.toml

runtime/
  script_registry.py
  session_store.py
  tool_manifest.py
  gateway/
    adapters/
    router.py

browser/
  README.md
  interaction-skills/
  domain-skills/
  evidence/

templates/
  agent-scaffold/
    AGENTS.md
    CLAUDE.md
    GEMINI.md
    ANTIGRAVITY.md
    brain/
    memory/
    skills/
    scripts/

skills/
  agent-forge/
    SKILL.md
  browser-harness/
    SKILL.md
```

Recommended first CLI commands:

```text
bravo setup
bravo doctor
bravo status
bravo config show
bravo config set <key> <value>
bravo skills list
bravo skills audit
bravo tools list
bravo browser setup
bravo browser doctor
bravo browser learn <site>
bravo sessions search <query>
bravo agent create <name> --template <template>
bravo agent doctor <name>
bravo gateway status
```

## Browser Harness Rollout Across Agents

The browser layer should be shared, but permissions should be agent-specific.

| Agent | Browser Harness Use | Guardrails |
|---|---|---|
| Bravo | GitHub, Supabase, Vercel, Stripe dashboard read-only checks, n8n, Google Workspace, client portals | Send actions through `send_gateway`; approval before admin/finance/destructive browser actions |
| Atlas | Banking portals, accounting dashboards, Stripe, tax sites, budget tools | Explicit approval before money movement, tax filings, bank transfers, subscription changes |
| Maven | LinkedIn, X/Twitter, Meta Ads, Google Ads, Canva, content schedulers, analytics dashboards | Approval before publishing, paid ad changes, budget changes, mass DMs |
| Aura | Home Assistant, router UI, device dashboards, local services | Approval before locks, cameras, network resets, privacy-sensitive views |
| Hermes/client agents | Supplier portals, order systems, inventory dashboards, client CRMs, browser-only workflows | Per-client permission profile and audit log required |

The domain-skill library should start with:

```text
browser/domain-skills/
  github.md
  supabase.md
  vercel.md
  stripe-dashboard.md
  n8n.md
  google-workspace.md
  browser-use-cloud.md
  linkedin.md
  meta-ads.md
  x-twitter.md
  canva.md
  home-assistant.md
  shopify.md
  client-portal-template.md
```

Each domain skill must include:

- URL patterns
- login/profile assumptions
- stable selectors or robust discovery methods
- private API endpoints if safely observable
- wait/load traps
- common failure modes
- evidence to capture
- actions requiring approval
- explicit "do not store secrets/cookies/session state" rule

## Execution Roadmap

### Phase 1: Product CLI + Doctor

Goal: make Bravo launch like a serious agent product.

Build:

- `bravo_cli/main.py`
- `bravo setup`
- `bravo doctor`
- `bravo status`
- `bravo tools list`
- `bravo skills list`
- Windows-first `install/install.ps1`
- POSIX `install/install.sh`
- `config/bravo-config.example.toml`

Keep it conservative:

- Wrap existing scripts.
- Do not rewrite business logic.
- Do not touch credentials.
- Do not change production services.

### Phase 2: Browser Harness Pack

Goal: make browser automation compounding and reusable.

Build:

- `skills/browser-harness/SKILL.md`
- `browser/interaction-skills/`
- `browser/domain-skills/`
- `bravo browser setup`
- `bravo browser doctor`
- `bravo browser learn <site>`
- Evidence bundle conventions

This should adapt Browser Harness' discipline, while preserving Bravo's Playwright/Firecrawl/MCP strengths.

### Phase 3: Agent Forge

Goal: make Bravo the master creator of new agents.

Build:

- `skills/agent-forge/SKILL.md`
- `templates/agent-scaffold/`
- `bravo agent create`
- `bravo agent doctor`
- profile templates for Bravo, Atlas, Maven, Aura, Hermes

Agent Forge should create the brain/memory/skills/scripts/docs skeleton and ask the setup questions needed for a real deployable agent.

### Phase 4: Session Store + Search

Goal: give agents durable recall beyond markdown logs.

Build:

- `runtime/session_store.py`
- SQLite database under `~/.bravo/sessions/`
- FTS5 search
- `bravo sessions search`
- `bravo sessions recent`
- optional summary generation

This complements, not replaces, `brain/STATE.md`, `memory/SESSION_LOG.md`, mem0, and Supabase.

### Phase 5: Gateway Modularization

Goal: turn Telegram/n8n/email paths into an adapter architecture.

Build later:

- `runtime/gateway/router.py`
- `runtime/gateway/adapters/telegram.py`
- `runtime/gateway/adapters/email.py`
- `runtime/gateway/adapters/n8n.py`
- `bravo gateway status/start/stop`

Keep V5.6 outbound chokepoint intact.

### Phase 6: Terminal Polish + Docs

Goal: make the system feel premium on launch.

Build:

- branded terminal banner
- theme config
- quick status block
- command suggestions
- README quick install section
- generated command reference
- docs index for agent creation

This should come after the CLI works. Polish should sit on top of reliable commands, not hide missing infrastructure.

## Immediate Build Queue For Next Turn

If execution starts next, the best first slice is:

1. Create `bravo_cli/main.py` with `setup`, `doctor`, `status`, `tools list`, and `skills list`.
2. Add `install/install.ps1` and `install/install.sh` that perform safe checks and point to setup.
3. Add `config/bravo-config.example.toml`.
4. Add `scripts/catalog_sync.py` or a lightweight manifest generator to end count drift.
5. Add `skills/browser-harness/SKILL.md` plus starter `browser/domain-skills/` and `browser/interaction-skills/` directories.
6. Update README with a quick install section.
7. Run `python scripts/core/self_audit.py` and `git status --short`.
8. Sync `brain/STATE.md` and `memory/SESSION_LOG.md`.

This gives CC an immediate visible improvement without risking database, email, Stripe, or production automation.

## Critical Safety Rules For The Build

- Do not weaken `scripts/integrations/send_gateway.py`.
- Do not let browser automation send messages, publish content, move money, change billing, delete data, or alter production services without explicit approval.
- Do not put secrets in browser domain skills.
- Do not store cookies or session state in skills.
- Do not add direct `smtplib.SMTP_SSL()` or bypass outbound logging.
- Do not make installer scripts mutate `.env.agents`; generate templates and ask.
- Do not make destructive shell/database/git operations part of setup.

## Final Take

Hermes proves that the market now expects agents to be installable products, not just repos full of good scripts. Browser Harness proves that browser automation should become procedural memory, not one-off clicking.

Bravo's advantage is deeper: it already knows CC, the companies, the operating model, the revenue goal, the safety chokepoints, and the agent family. The move is to wrap that intelligence in a product-grade runtime:

- one command to install
- one wizard to configure
- one doctor to debug
- one CLI to operate
- one browser layer that learns
- one scaffold to create new agents
- one memory/search layer that compounds

That is the path to making Bravo, Atlas, Maven, Aura, and Hermes feel less like separate builds and more like an AI operating system CC can keep expanding.

## Related

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
