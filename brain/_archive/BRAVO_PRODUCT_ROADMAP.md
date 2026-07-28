---
description: "Bravo V1.0 roadmap: six-phase product plan (CLI, browser harness, agent forge, runtime, installer, terminal); completion status per phase"
tags: [product, roadmap, vision]
created: 2026-04-22
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
status: archived
archived_on: 2026-07-19
archived_from: brain/BRAVO_PRODUCT_ROADMAP.md
archive_reason: "Superseded product roadmap with stale ownership and milestone assumptions."
superseded_by: brain/PRODUCT_ARCHITECTURE.md
---
# Bravo Product Roadmap

> Where Bravo is going — the path from "CC's internal command center" to **the best AI operating system on the market for solo founders and small teams**.

Anchor references: [[brain/SOUL]] · [[brain/AGENTS]] · [[brain/ORCHESTRATION]]

---

## Why This Exists

Two open-source projects reset the bar in early 2026:
1. **NousResearch/hermes-agent** v0.10.0 (95.6K stars) — productized the installable agent. Clean CLI, real install wizard, runtime home, session search, trajectory export, three-layer memory, profiles.
2. **browser-use/browser-harness** — productized browser control as procedural memory. Interaction skills + domain skills as separate compounding layers.

Bravo is not behind on business intelligence. Bravo's moat — multi-agent business orchestration, persistent state for three AI systems, revenue-tied governance — cannot be open-sourced. But Bravo was behind on *product surface*: no one-command install, fragmented CLI, no runtime home, no session FTS, no Agent Forge, no themed terminal.

The V1.0 push closes that gap and then leapfrogs with the moat.

---

## V1.0 Targets (Current Push)

### Phase 1 — Product CLI + Doctor ✅
- `bravo_cli/main.py` (v0.2.0)
- Branded banner, contextual launch, MRR/status in one glance
- 16 subcommands: doctor, status, setup, tools, skills, agent, browser, sessions, profile, logs, config, update, run, version
- `bin/bravo` + `bin/bravo.cmd` shell launchers

### Phase 2 — Browser Harness Pack ✅
- [[skills/browser-harness/SKILL]] + [[browser/SAFETY]] + `browser/interaction-skills` + `browser/domain-skills`
- Wired into `bravo browser setup | doctor | learn <site>`
- V5.6 outbound chokepoint preserved; writes gated on explicit approval

### Phase 3 — Agent Forge ✅
- [[skills/agent-forge/SKILL]] + `templates/agent-scaffold/` (12 files)
- `bravo agent create <name> --role <role>` → full brain/memory/scripts/skills/doctor in one command
- Forged agents inherit V5.6 chokepoint automatically
- Tested end-to-end: scaffold passes 100/100 self_audit

### Phase 4 — Runtime Layer ✅
- `runtime/session_store.py` — SQLite FTS5 session search (`bravo sessions search <q>`)
- `runtime/tool_manifest.py` — filesystem-truth tool registry (replaces hand-maintained counts)
- `runtime/profile_home.py` — `~/.bravo/` tree with 5 profiles (bravo/atlas/maven/aura/hermes)
- `scripts/catalog_sync.py` — regenerate counts in brain/CAPABILITIES.md + brain/STATE.md

### Phase 5 — Installer Layer ⏳ (Codex delivering)
- `install/install.ps1` — Windows one-command
- `install/install.sh` — POSIX one-command
- `install/bootstrap.py` — cross-platform shared helper
- Installers never touch secret values; the setup wizard writes local `.env.agents` only after git safety checks

### Phase 6 — Terminal Polish ✅
- BRAVO ASCII banner, cyan + magenta theme, ASCII fallback for cp1252 Windows
- Launch screen shows profile, system version, stance, MRR/target, suggested commands
- UTF-8 enforced on Windows with graceful fallback

---

## V1.1 Targets (Next 30 Days)

### Gateway Modularization
- `runtime/gateway/router.py` + `runtime/gateway/adapters/{telegram,email,n8n}.py`
- Modular adapter pattern without weakening `scripts/integrations/send_gateway.py`
- CLI: `bravo gateway status | start | stop`

### Trajectory Export (Hermes v0.8 pattern)
- ShareGPT-format session export for future RL training
- Opt-in per profile via `~/.bravo/config.toml`

### Credential Pool + Fallback Chains (Hermes v0.7 pattern)
- `runtime/credential_pool.py` — least-used distribution across same-provider keys
- Ordered provider fallback when Claude API is unavailable
- Health-check gate before swap

### ACP IDE Integration (Hermes v0.9 pattern)
- Native VS Code / Zed / JetBrains via JSON-RPC stdio
- Complements existing Claude Code IDE integration

### Tool Self-Registration
- Replace hand-maintained QUICK_REFERENCE.md routing table with `@register_tool` decorator + `tool_manifest` discovery
- End count drift permanently

---

## V2.0 Ambitions (Q3 2026)

### Self-Improvement (GEPA pattern)
- Analyze full execution traces after complex tasks
- Propose targeted prompt improvements in `brain/CHANGELOG.md`
- Agents with 20+ self-created skills complete domain-similar tasks measurably faster (Hermes benchmark: 40%)

### Task Brain DAG (OpenClaw 2026.3 pattern)
- Unified task management in the core loop, not bolted on
- `brain/BRAIN_LOOP.md` DAG section becomes the reference implementation
- Sibling agents (Atlas, Maven, Aura, Hermes) share the DAG substrate

### Tiered Sandbox Security (OpenClaw pattern)
- Main user session: full host access (current behavior)
- Group/channel/client messages: run in Docker sandbox by default
- Per-client permission profile under `~/.bravo/profiles/clients/`

### Voice + Canvas (OpenClaw pattern, deferred)
- Wake-word detection + continuous voice mode
- Canvas visual workspace for multi-step plans
- Lowest priority in V2.0 — only after core infrastructure compounds

### Nous Tool Gateway Equivalent (Hermes v0.10 pattern)
- Managed tool layer for client agents — one subscription for browser automation, web search, image gen, TTS
- Enables Hermes-client-agent deployments under OASIS AI umbrella
- Product surface for Bravo as a sellable platform, not just a repo

---

## What Bravo Does NOT Do (Intentional)

- **No monolithic `AIAgent` class** — Bravo preserves the 17-agent routing matrix with domain-specific personalities, safety gates, and decision autonomy. A single class across all entry points is elegant for Hermes; it would erase Bravo's moat.
- **No cookies/sessions/credentials in browser domain skills** — domain skills describe site mechanics only; auth state stays with the live browser profile.
- **No bypass of `send_gateway.py`** — outbound chokepoint is V5.6 canon and survives every refactor.
- **No unsafe `.env.agents` mutation** — installers generate templates only; the wizard refuses tracked env files and locally excludes `.env.agents` before writing credentials.
- **No aggressive compression of CLAUDE.md** — 120-line instruction-loss threshold is respected; skill-specific content moves to `skills/`, not removed.

---

## Success Criteria

| Metric | V1.0 | V1.1 | V2.0 |
|---|---|---|---|
| Install to first `bravo doctor` PASS | <5 min | <3 min | <90 s |
| Forge a new agent to first 100/100 audit | <60 s | <30 s | <10 s |
| Session FTS query latency @ 10K entries | <100 ms | <30 ms | <10 ms |
| Sibling agents sharing runtime | 1 (Bravo) | 3 (Bravo + Atlas + Maven) | 5 (full family) |
| Client agents deployed under OASIS umbrella | 0 | 1 (Hermes for Emmanuel) | 3+ |
| Net MRR driven by the product surface itself | $0 | retainer enablement | $1K+ MRR attributable |

---

## The Leapfrog Thesis

Hermes is a great framework. Browser Harness is a great primitive. OpenClaw is a great agent.

Bravo is the **business operating system**. Its advantages compound because it knows CC, the companies, the operating model, the revenue goal, the safety chokepoints, and the agent family. No open-source release can ship those things pre-wired to a founder's business.

V1.0 gives Bravo Hermes-grade infrastructure.
V1.1 adds Hermes-class resilience + IDE integration.
V2.0 makes Bravo the product surface under OASIS AI Solutions — one subscription, multiple agents, a proven chokepoint, and a moat the open-source world cannot ship.

## Related
- [[brain/SOUL]] · [[brain/AGENTS]] · [[brain/C_SUITE_ARCHITECTURE]]
- [[skills/browser-harness/SKILL]] · [[skills/agent-forge/SKILL]]
- [[runtime/README]] · [[runtime/SKILL_LIFECYCLE]]
- [[install/README]]
