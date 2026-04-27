---
tags: [memory, index]
---
# MEMORY INDEX -- 3-Layer Architecture

> **Layer 1 (this file):** Pointers. Always loaded. ~150 chars each.
> **Layer 2:** Topic files. Read on-demand: `Read memory/<file>.md`
> **Layer 3:** Archives. Grep-only: `memory/ARCHIVES/*.md`

> Generated: 2026-04-03 | Files: 8 memory + 8 brain + 6 archives
> Archives: [[memory/ARCHIVES/README]] | Lead System: [[memory/ARCHIVES/lead_system/README]]

## Memory Files (Layer 2 -- load when needed)

- **ACTIVE_TASKS.md** (31L) -- Current tasks, priorities, blocked items
- **MISTAKES.md** (27L) -- Past errors, root causes, prevention strategies
  - Zombie Python Daemon (2026-04-02)
  - Vercel Shared Module Crash (2026-03-23)
  - Windows Watchdog Zombies (2026-03-23)
- **PATTERNS.md** (27L) -- Proven approaches, anti-patterns, validated workflows
  - [P] Daemon Redeploy (2026-04-02)
  - [V] Zernio Posting
  - [V] Query-First MCP — Question → tool → call → return real data. Never describe.
- **LONG_TERM.md** (61L) -- High-confidence persistent facts (architecture, business, technical)
  - Bravo uses 3-tier agent architecture: Claude Code (Opus), Gemini CLI, Antigravit
  - All agents share entry points, brain/, memory/, .env.agents
  - Late MCP profileId returns dict not str — requires Pydantic patch in uv cache
- **DECISIONS.md** (38L) -- Architectural and business decisions with rationale
  - 2026-02-27 — Multi-Agent Architecture (3-Tier)
  - 2026-02-27 — Playwright as Sole Web Research Tool
  - 2026-02-27 — .env.agents as Centralized Secret Store
- **SELF_REFLECTIONS.md** (55L) -- Failure analysis, lessons learned, reflexion entries
  - [Date] — [Trigger]
  - 2026-02-27 — First Live Social Media Posts
  - 2026-02-27 — Pydantic Monkey-Patching Failure
- **SOP_LIBRARY.md** (404L) -- Standard operating procedures with success rates
  - SOP-[ID]: [Name]
  - SOP-001: Social Media Content Creation & Publishing
  - SOP-002: Systematic Bug Investigation
- **SESSION_LOG.md** (153L) -- Recent session activity (last 10 sessions)
  - 2026-03-28 — CEO Risk Management + Crisis Response + Sales Methodology Skills
  - 2026-03-28 — SOP Library: CEO-Level SOPs Added (SOP-010 through SOP-017)
  - 2026-03-28 — CEO Operating System: Brain-Level Architecture

## Brain Files (Layer 2 -- load for complex tasks)

- **STATE.md** (134L) -- Current operational state, confidence level, active systems
- **AGENTS.md** (219L) -- 17 subagents, routing matrix, permissions, Codex integration
- **CAPABILITIES.md** (392L) -- 180 skills, 30 workflows, 37 scripts, tool registry
- **BRAIN_LOOP.md** (198L) -- 10-step reasoning protocol, multi-hypothesis, reflexion
- **CEO_OPERATING_SYSTEM.md** (127L) -- 7 CEO domains, briefing protocol, revenue strategy
- **OKRs.md** (85L) -- Q2 2026 objectives and key results
- **RISK_REGISTER.md** (39L) -- Active business risks with mitigation plans
- **APP_REGISTRY.md** (59L) -- 12 apps with local paths, GitHub repos, stacks

## Archives (Layer 3 -- grep only)

- `ARCHIVES/PROPOSAL_FOR_BENNETT_V3.md`
- `ARCHIVES/README.md`
- `ARCHIVES/sessions-2026-02.md`
- `ARCHIVES/sessions-2026-03.md`
- `ARCHIVES/sessions-2026-04.md`
- `ARCHIVES/WHATSAPP_BRIDGE_SOP.md`

*Index built: 2026-04-03*

## Obsidian Links
- [[brain/STATE]] | [[brain/DASHBOARD]] | [[brain/CAPABILITIES]]
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/LONG_TERM]]
- [[memory/MISTAKES]] | [[memory/PATTERNS]] | [[memory/SOP_LIBRARY]]
