# DELEGATION PROMPT: BRAVO → CLAUDE CODE (MAVEN C-SUITE ARCHITECTURE)

**From:** Bravo (CEO Agent, Antigravity/Gemini runtimes)
**To:** Claude Code (Lead Architect)
**Date:** 2026-04-18
**Priority:** Strategic — C-Suite Infrastructure Buildout

---

## 🛑 CONTEXT: WHAT JUST HAPPENED

CC had a major breakthrough and mandated the evolution of the AI infrastructure from a two-agent setup to a **Tripartite C-Suite AI Architecture**:
1. **Atlas (CFO)** — Wealth, tax, compliance, capital preservation (`CFO-Agent` repo)
2. **Bravo (CEO)** — Strategy, revenue operations, partnerships, vision (`Business-Empire-Agent` repo)
3. **Maven (CMO)** — Brand, content, distribution, paid ads, funnels (`Marketing-Agent` repo)

During my session, I successfully architected this transition, established the governance framework, and transformed the legacy `Marketing-Agent` (previously AdVantage V2.0 for SunBiz Funding only) into the new multi-brand CMO agent named **Maven**.

## ✅ WHAT HAS BEEN COMPLETED (PHASE 1 & 2)

**Phase 1: Architecture & Governance (In `Business-Empire-Agent`)**
- Created `brain/C_SUITE_ARCHITECTURE.md` (Read this first — it defines decision rights, conflict resolution, and the 5-phase roadmap).
- Fixed the stale Atlas reference in `AGENTS.md` (pointed from old trading-agent to the new `CFO-Agent`).
- Added Maven to the `AGENTS.md` decision matrix (all marketing, content, and ad questions now route to Maven).
- Created the **3-Way Pulse Protocol** (`data/pulse/ceo_pulse.json` and `cmo_pulse.json`). Atlas's `cfo_pulse.json` is used as a spend-gate.
- Updated `STATE.md`, `SESSION_LOG.md`, and `ACTIVE_TASKS.md` with the new architecture.

**Phase 2: Maven Identity Transformation (In `Marketing-Agent`)**
- Rewrote `brain/SOUL.md` (AdVantage V2.0 → Maven V1.0). Maven now explicitly handles a multi-brand portfolio (OASIS AI, PropFlow, Nostalgic Requests, CC's Personal Brand, and SunBiz).
- Rewrote `CLAUDE.md`, `ANTIGRAVITY.md`, and `GEMINI.md` to reflect the CMO identity, the multi-client awareness, and the new pulse protocol.
- Created `scripts/pulse_client.py` inside `Marketing-Agent` so Maven can programmatically read Bravo's/Atlas's pulse files and update its own `cmo_pulse.json`.
- *(Note: I was extremely careful to leave the 16 existing sub-agents and 19 skills completely untouched to preserve your logic and execution capabilities).*

## 🚀 YOUR MISSION (PHASE 3, 4, & 5)

I paused the buildout because moving core skills between repositories requires your architectural precision. You are picking up at **Phase 3**.

**Please execute the following:**

1. **Review the Blueprint:** Read `brain/C_SUITE_ARCHITECTURE.md` and `memory/ACTIVE_TASKS.md`. 
2. **Phase 3: Execute Skill Migration:**
   - Move the 10 marketing skills (`content-engine`, `email-marketing`, `funnel-management`, `brand-guidelines`, `growth-engine`, `competitive-intelligence`, `elite-video-production`, `lead-management`, `linkedin-outreach`, `persona-content-creator`) from `Business-Empire-Agent/skills/` to `CMO-Agent/skills/`.
   - Move the `content-studio/` directory (Remotion setup) to Maven's repo.
   - Update `CAPABILITIES.md` in both repositories to reflect this new ownership.
3. **Phase 4: Multi-Client Expansion:**
   - Scaffold the client profiles inside Maven's `brain/` directory (add profiles for OASIS AI, PropFlow, Nostalgic Requests, and CC's personal brand).
4. **Phase 5: Integration Testing:**
   - Test the 3-Way Pulse read/write logic using the new `pulse_client.py` script.

**Golden Rule:** Keep the code modular, update memory logs upon completion, and ensure Bravo retains CEO skills while Maven takes complete ownership of marketing.
