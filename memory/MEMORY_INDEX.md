---
tags: [memory, index]
last_updated: 2026-05-21
freshness_threshold_days: 90
---
# MEMORY INDEX -- 3-Layer Architecture

> **Layer 1 (this file):** Pointers. Always loaded. ~150 chars each.
> **Layer 2:** Topic files. Read on-demand: `Read memory/<file>.md`
> **Layer 3:** Archives. Grep-only: `memory/ARCHIVES/*.md`

> Generated: 2026-05-10 | Files: 8 memory + 8 brain + 7 archives

## Memory Files (Layer 2 -- load when needed)

- **ACTIVE_TASKS.md** (171L) -- Current tasks, priorities, blocked items
  - ✅ V6 ASCENSION COMPLETE (2026-05-11)
  - 🔧 OPTIONAL FOLLOW-UPS (not blocking; do when convenient)
  - 🔥 BUSINESS PRIORITIES (carried over from 2026-05-06)
- **MISTAKES.md** (157L) -- Past errors, root causes, prevention strategies
  - Leaked Bash Background Tasks Spammed Console Popups Every 8s (2026-05-09)
  - Live Stripe Key in Antigravity User MCP Config — 2-Month Plaintext Leak (2026-05
  - Cold Call Primary Diffuse Failed on "We're Good" Double-Down (2026-05-06)
- **PATTERNS.md** (46L) -- Proven approaches, anti-patterns, validated workflows
  - [P] Cold Call Secondary Disarm — Agree, Validate, Isolate (2026-05-06)
  - [P] MCP Config Wrapper Pattern — Zero Plaintext Secrets (2026-05-06)
  - [V] MCP Config Audit Discipline (2026-05-06)
- **LONG_TERM.md** (77L) -- High-confidence persistent facts (architecture, business, technical)
  - Bravo uses 5-entry-point architecture: CLAUDE.md (Claude Code), AGENTS.md (Codex
  - All entry points share `brain/`, `memory/`, `.env.agents` — single source of tru
  - Identity is model-driven, not tool-driven. Claude/big-pickle = Bravo; GPT/Codex 
- **DECISIONS.md** (49L) -- Architectural and business decisions with rationale
  - 2026-02-27 — Multi-Agent Architecture (3-Tier)
  - 2026-02-27 — Playwright as Sole Web Research Tool
  - 2026-02-27 — .env.agents as Centralized Secret Store
- **SELF_REFLECTIONS.md** (57L) -- Failure analysis, lessons learned, reflexion entries
  - [Date] — [Trigger]
  - 2026-02-27 — First Live Social Media Posts
  - 2026-02-27 — Pydantic Monkey-Patching Failure
- **SOP_LIBRARY.md** (406L) -- Standard operating procedures with success rates
  - SOP-[ID]: [Name]
  - SOP-001: Social Media Content Creation & Publishing
  - SOP-002: Systematic Bug Investigation
- **SESSION_LOG.md** (382L) -- Recent session activity (last 10 sessions)
  - 2026-05-11 — Auto-sync
  - 2026-05-10 — Auto-sync
  - 2026-05-10 — BRAVO state_manager

## Brain Files (Layer 2 -- load for complex tasks)

- **STATE.md** (164L) -- Current operational state, confidence level, active systems
- **AGENTS.md** (308L) -- 17 subagents, routing matrix, permissions, Codex integration
- **CAPABILITIES.md** (796L) -- 180 skills, 30 workflows, 37 scripts, tool registry
- **BRAIN_LOOP.md** (199L) -- 10-step reasoning protocol, multi-hypothesis, reflexion
- **CEO_OPERATING_SYSTEM.md** (127L) -- 7 CEO domains, briefing protocol, revenue strategy
- **OKRs.md** (85L) -- Q2 2026 objectives and key results
- **RISK_REGISTER.md** (39L) -- Active business risks with mitigation plans
- **APP_REGISTRY.md** (66L) -- 12 apps with local paths, GitHub repos, stacks

## Archives (Layer 3 -- grep only)

- `ARCHIVES/2026-04-sprint-and-buildout.md`
- `ARCHIVES/PROPOSAL_FOR_BENNETT_V3.md`
- `ARCHIVES/README.md`
- `ARCHIVES/sessions-2026-02.md`
- `ARCHIVES/sessions-2026-03.md`
- `ARCHIVES/sessions-2026-04.md`
- `ARCHIVES/WHATSAPP_BRIDGE_SOP.md`

*Index built: 2026-05-10*

## Related

- [[memory/INDEX]]
- [[memory/ACTIVE_TASKS]]
- [[memory/ACTIVE_TASKS.template.md]]
