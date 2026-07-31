---
description: "Canonical 5-layer reference for all CC agent design (Agents/UI, routing, hooks, skills, data); single source of logical truth for Bravo, Maven, Atlas, Hermes"
title: Agentic OS — Canonical Cross-Reference (V6.7 anchor)
source: YouTube video "Build your agentic OS better than 99% of people" (https://www.youtube.com/watch?v=-WCNwxz3uoM)
transcript: docs/references/agentic-os-99pct-transcript.txt
captured: 2026-05-14
version: V6.7 (slots into V6.0/Phase-2 → V6.5 → V6.6 → V6.7 lineage; see brain/V6_ARCHITECTURE.md "Agentic OS Orchestration (V6.7)")
mutability: GOVERNED
purpose: Single source of logical truth for how every CC agent (Bravo, Maven, Atlas, Hermes, future) should be structured. Practice may diverge — logic should not.
applies_to: Business-Empire-Agent (Bravo), CMO-Agent (Maven), CFO-Agent (Atlas), hermes (Hermes), all future client agents forged via skills/agent-forge
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
tags: [brain]
---
# Agentic OS Reference

This is the **logic spec**. Every CC agent — Bravo here, Maven at CMO-Agent, Atlas at trading-agent, Hermes at hermes, and every future client/empire agent — should be mappable to this. Implementation can differ per-agent; the mental model cannot.

The video's thesis in one line: **"Sparkly slop on top of a foundation of slop is compounded slop."** Most agentic-OS builds fail because the dashboards/agents/personalities are built on unprepared data and unstructured infrastructure. Fix the foundation first.

---

## 1. The Cross-Section (5 layers, top-to-bottom)

The video frames an agentic OS as a 5-layer stack. People obsess over the top and skip the bottom. The bottom is what makes it work.

| # | Layer | What lives there | Bravo equivalent | Status |
|---|-------|------------------|------------------|--------|
| 1 | **Agents / UI** | Personalities, dashboards, the pretty stuff | `agents/*.md` (17 agents), Command Center web app | ✓ overbuilt |
| 2 | **CLAUDE.md** | "Air traffic control" — routes the right info at the right time. Empire of CLAUDE.mds, not a diary. | `CLAUDE.md` + siblings `GEMINI.md` / `ANTIGRAVITY.md` / `AGENTS.md` / `OPENCODE.md` | ✓ canonical |
| 3 | **Hooks** | 18+ event injection points. Underutilized by 99% of users. | `.claude/settings.json` hooks: `file-guard`, `create-checkpoint`, `self-review` + V6 guards (`secret_guard`, `exec_guard`, `state_guard`) | ⚠ guards only — no `SessionStart`, no `PostCompact`, no `UserPromptSubmit` memory injection |
| 4 | **Skills** | Project-level + global. Reusable, composable. | `skills/` (50+) — local + plugin skills from `.claude/plugins/cache/` | ✓ rich |
| 5 | **Data / Integrations** | APIs, CLIs, MCPs, raw files. The foundation. | 47 CLI tools in `scripts/`, MCP servers, `.env.agents` credentials, Supabase, Turso, `memory/`, `state/empire_state.db` | ✓ but **no data-readiness audit** — see §5 |

**Where 99% of people stop:** layer 1. **Where leverage actually comes from:** layers 3, 4, 5.

---

## 2. The Four-Layer Maturity Ladder (reframe from the same video)

The video later re-frames the same stack as a build-order ladder. Use this for new agents.

1. **Identity** — CLAUDE.md, rules, compliance constraints (GDPR / SOC 2 / HIPAA / PIPEDA).
   - Bravo: `brain/SOUL.md` (IMMUTABLE), `brain/USER.md`, `CLAUDE.md` rules 0–10.
2. **Knowledge** — where data lives, how it's retrieved. Cloud, drive, skills, MCPs, RAG.
   - Bravo: `memory/`, `brain/CAPABILITIES.md`, `scripts/core/memory_retriever.py` (FTS5 + LanceDB hybrid).
3. **Workers** — materialized agents with explicit roles. Hire only when one agent is overburdened. **"Don't have agents for the sake of having agents."**
   - Bravo: `agents/*.md` (17 specialists), `brain/AGENTS.md` registry, chief-of-staff orchestrator.
4. **Automations** — hooks, cron, event bus, deterministic injections.
   - Bravo: V6 event bus (`scripts/core/event_router.py`), PM2 daemons, hooks (currently security-only).

**Rule:** Don't ascend to layer N+1 until layer N is solid. The video is blunt — "clean the skeletons before you ascend."

---

## 3. The Silver Platter Principle (THE central insight)

> "Put the core data on a silver platter so agents spend their session analyzing, not retrieving."

**The failure mode:** Agent uses 80% of its context window pulling raw JSON/metadata from APIs. The last 20% — the analysis you actually wanted — is where hallucinations, slowness, and weird behavior live.

**The fix:** Pre-aggregate deterministically (Python, not LLM) into **summary tables / summary files**. Agent reads the summary, spends 100% of its session on synthesis.

### Three-tier data taxonomy (Pantry / Prep Table / Plate)

| Tier | Meaning | Lives where |
|------|---------|-------------|
| **Pantry** | Raw sources, databases, integrations. Untouched. | Supabase, Turso, QuickBooks API, JotForm webhooks, Gmail, Drive, n8n, `.env.agents` credentials, MCP servers |
| **Prep Table** | Deterministic pre-aggregations. Python summary tables. KPIs distilled. **No LLM here.** | `state/empire_state.db` summary views, `memory/SOP_LIBRARY.md`, scheduled CRON jobs, `scripts/*_tool.py --json` outputs |
| **Plate** | What the agent actually consumes + acts on. The synthesis layer. | Agent briefs (`/briefing`, `ceo-briefing` skill), Telegram/Slack/email digests, dashboard views |

**Bravo's current state:** Pantry exists. Plate exists (briefings, dashboard). **Prep Table is partial** — most agents still pull raw data per-call instead of reading from pre-aggregated summary tables. This is the highest-leverage gap.

---

## 4. Critical Paths (SOPs for agents, not humans)

> "A skill is an infinite game. You don't finish a skill, you start one and keep improving it."

Every recurring task should have a **critical path** — an explicit step-by-step SOP the agent follows so it doesn't re-discover where data lives every time. Quote from video:

> "Based on all our conversation, I want you to map out the perfect critical path that would prevent us from going down the wrong avenues again."

**Bravo equivalent:**
- `memory/SOP_LIBRARY.md` — exists, growing
- `brain/INTENTS.md` — verb-by-verb playbooks (send-email, apply-migration, push-to-prod)
- `skills/outreach-send/`, `skills/ship/`, `skills/retro/` — crystallized critical paths

**Gap:** Most agents have 1–3 critical paths. Marco-style operations (recurring weekly reporting, content pipeline, lead enrichment) should each have one. Add as you discover the pattern, never preemptively.

---

## 5. The Silver Platter Audit (the skill itself)

The video's central deliverable is a slash command that produces:

1. **Data map** — every source, status (✓ / missing / quick-win), pros/cons
2. **Pantry / Prep Table / Plate breakdown** — visual HTML
3. **Data flow diagram** — relationships between sources
4. **Suggestions tab** — what can be built with current data
5. **30-day plan** — sequenced quick wins → automations → orchestration

**Bravo doesn't have this skill yet.** Closest analogs:
- `brain/CAPABILITIES.md` — registry of tools, not a data map
- `brain/CAPABILITY_GRAPH.json` — machine-readable registry, no data-readiness scoring
- `brain/TOOL_SHED.md` — catalog, not a flow diagram

**Recommended skill to build:** `skills/silver-platter/SKILL.md` — produces a per-agent data audit HTML report. Should run on:
- Bravo (Business-Empire-Agent)
- Maven (CMO-Agent)
- Atlas (trading-agent)
- Hermes (hermes)
- Every new client agent at provisioning time

The output becomes the agent's "Day 0 self-knowledge" doc.

---

## 6. Hooks — the under-the-radar leverage point

> "Hooks are this weird innocuous thing that no one touches, even though they're actually very straightforward, very reliable, and can come in very handy."

**18+ hook events in Claude Code.** Bravo currently uses ~5, all defensive (guards). The video specifically calls out:

| Hook event | Use case | Bravo status |
|------------|----------|--------------|
| **SessionStart** | Inject memory, current STATE.md, urgent inbox items, day-of-week reminder | ❌ not configured (staleness report is surfaced via boot, not via hook) |
| **PostCompact** | Re-inject identity + active task context after Claude auto-compresses | ❌ not configured |
| **UserPromptSubmit** | Triage classifier, route to right agent, inject relevant memory chunks | ❌ not configured |
| **PreToolUse** | Security guards | ✓ `file-guard`, `secret_guard`, `exec_guard`, `state_guard` |
| **PostToolUse / Stop** | Checkpoints, self-review | ✓ `create-checkpoint`, `self-review` |

**Recommended next:** `SessionStart` hook that runs `python scripts/core/agent_inbox.py list --to bravo` + `python scripts/state/state_manager.py status` + staleness report. Eliminates the "what's my state?" cold-start cost on every new session.

---

## 7. Orchestrator + Sub-Agent Pattern

> "Load one agent fully with the roles, responsibilities, and scopes of the sub-agents. This increases the likelihood you don't cold-start with mismatched/overlapping agent firing."

**Bravo: ✓ already canonical.** Chief-of-Staff (`agents/chief-of-staff.md`) is the orchestrator. 17 specialists. Routing via `brain/AGENT_ROUTER.md`. **One of the few places Bravo is ahead of the video.**

**Cross-agent consistency requirement:** Maven, Atlas, Hermes should each have:
1. A chief-of-staff equivalent
2. An `AGENT_ROUTER.md`
3. Explicit scopes per sub-agent (no overlap)

Maven appears to ✓ (separate CMO-Agent repo). Atlas ✓ (CFO role, 11 CFO skills). Hermes — verify.

---

## 8. End-Usage Decision (where the agent reaches the human)

The video's last fast-track question: **"Where do you actually want to read these briefs?"** Gmail, iPad, Slack, Telegram?

This determines the output adapter. Bravo currently delivers via:
- Telegram bridge (`telegram_agent.js`, `scripts/bridge_lock.py`)
- Command Center web (`oasis-command-center:`)
- Email (`scripts/integrations/send_gateway.py`)
- CLI (`bravo_cli/`)
- Discord/Slack — planned

**Cross-agent rule:** every agent must declare its primary delivery channel in its `brain/USER.md` or equivalent. Without this, you build dashboards no one reads.

---

## 9. The Three Personas (regression test for the framework)

The video stress-tests the framework against three avatars. Use these as a **regression test** when designing a new agent — does our framework handle all three? If yes, it generalizes.

| Persona | Domain | Stack | Critical constraint | What we'd build for them |
|---------|--------|-------|---------------------|--------------------------|
| **Marco** | E-commerce solopreneur, Slab House mystery boxes | Shopify, FB/TikTok ads, Twitch, QuickBooks, CSVs | Time-poor, 3h/Mon on P&L | Python summary tables from QuickBooks API → morning brief → `/pre-stream-prep` slash command → CFO bot + CMO bot orchestrated |
| **Sally** | M&A associate, boutique law firm | Outlook, Bill4Time, Bedrock (confidential), PDFs | Confidentiality — no Anthropic cloud | `/case-launch` slash command, PDF-intensive skills, Bedrock-only inference |
| **Dr. Sana Anwar** | Dermatologist | Athena Health (EHR), biopsies, intake forms | HIPAA — bifurcate clinical vs billing data, no PII to Anthropic | Hooks that scrub PII pre-inference, isolated CLAUDE.mds per domain, deterministic skills for biopsy summarization |

**Bravo's current personas:** CC (operator), Emmanuel (Hermes client), Sun Biz (demo). All three Marco/Sally/Sana patterns apply somewhere — see Hermes for Marco-shape, Sun Biz client for Sally-shape (regulated), future med-tech client for Sana-shape.

---

## 10. Cross-Reference Summary — What Bravo Already Has vs. What's Missing

| Concept from video | Bravo artifact | Status |
|--------------------|----------------|--------|
| CLAUDE.md as air-traffic-control | `CLAUDE.md` + 4 siblings | ✅ canonical |
| Empire of CLAUDE.mds | `CLAUDE.md`, `GEMINI.md`, `ANTIGRAVITY.md`, `AGENTS.md`, `OPENCODE.md` | ✅ |
| Project + global skills | `skills/` + `.claude/plugins/cache/` | ✅ |
| Orchestrator pattern | `agents/chief-of-staff.md` + `brain/AGENT_ROUTER.md` | ✅ |
| Critical paths / SOPs | `memory/SOP_LIBRARY.md`, `brain/INTENTS.md`, crystallized skills | ✅ partial |
| CLI-first over MCP-only | 47 CLI tools, CLAUDE.md Rule 2, `skills/cli-anything/` | ✅ ahead of video |
| Hooks (security) | `file-guard`, `secret_guard`, `exec_guard`, `state_guard` | ✅ |
| Identity / immutable rules | `brain/SOUL.md` (IMMUTABLE) | ✅ |
| Materialized agents | 17 `agents/*.md` files | ✅ |
| Compliance scaffolding | `brain/SECURITY_MODEL.md`, `EXECUTION_RULES.md`, `secret_guard` | ✅ |
| Cross-agent event bus | V6 Apex `scripts/core/event_router.py` + Supabase | ✅ ahead of video |
| Hybrid retrieval (FTS5 + vector) | `scripts/core/memory_retriever.py` (FTS5 + LanceDB RRF) | ✅ ahead of video |
| **Silver Platter audit skill** | — | ❌ **gap** |
| **Pantry/Prep Table/Plate taxonomy** | implicit in `memory/`, not explicit | ❌ **gap** |
| **Pre-aggregated summary tables (Prep Table layer)** | partial — `state_manager.py status`, not per-domain | ⚠ **partial** |
| **SessionStart memory-injection hook** | — | ❌ **gap** |
| **PostCompact identity-reinjection hook** | — | ❌ **gap** |
| **UserPromptSubmit triage hook** | — | ❌ **gap** |
| **Per-agent data-flow HTML report** | — | ❌ **gap** |
| **30-day implementation plan per new agent** | `brain/OKRs.md` (quarterly, not 30-day per-agent) | ⚠ **partial** |
| End-usage delivery channel declared | scattered — not enforced per-agent | ⚠ **partial** |

---

## 11. Cross-Agent Propagation Rule

When this doc is updated, the equivalent reference must exist (or be linked) in:

- `CMO-Agent/brain/AGENTIC_OS_REFERENCE.md` (Maven)
- `APPS/trading-agent/brain/AGENTIC_OS_REFERENCE.md` (Atlas)
- `APPS/hermes/brain/AGENTIC_OS_REFERENCE.md` (Hermes)
- Every future client-agent template under `brain/`

**Logic is shared. Implementation per-agent. Layers 1–5 of §1 are the contract. Pantry/Prep Table/Plate of §3 is the contract. Everything else is local.**

Per CLAUDE.md Rule 4 (cross-file sync) and Rule 10 (V6 Coherence Gate): propose changes in chat before unilaterally editing sibling agent repos.

---

## 12. References

- Full transcript: `docs/references/agentic-os-99pct-transcript.txt` (651 lines, 24.5KB, captured 2026-05-14)
- Source video: https://www.youtube.com/watch?v=-WCNwxz3uoM
- Related Bravo docs: `CLAUDE.md`, `brain/SOUL.md`, `brain/AGENTS.md`, `brain/CAPABILITIES.md`, `brain/INTERACTION_PROTOCOL.md`, `brain/AGENT_ROUTER.md`
