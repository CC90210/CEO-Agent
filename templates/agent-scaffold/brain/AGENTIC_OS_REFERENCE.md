---
title: Agentic OS — Canonical Cross-Reference (V6.7 anchor for {{AGENT_NAME}})
source: YouTube video "Build your agentic OS better than 99% of people" (https://www.youtube.com/watch?v=-WCNwxz3uoM)
canonical_copy: ../../Business-Empire-Agent/brain/AGENTIC_OS_REFERENCE.md (Bravo holds the master; this is the {{AGENT_NAME}} mirror)
transcript: ../../Business-Empire-Agent/docs/references/agentic-os-99pct-transcript.txt
captured: 2026-05-14
version: V6.7
mutability: GOVERNED
purpose: Logic spec {{AGENT_NAME}} must be mappable to. Bravo holds the master; {{agent_name}} adapts implementation, never the logic.
applies_to: {{AGENT_NAME}} (the forged agent). Companion mirrors at ~/Business-Empire-Agent (Bravo), and any sibling agents in CC's empire.
---

# Agentic OS Reference — {{AGENT_NAME}} Mirror

This is the **logic spec for {{AGENT_NAME}}** — the same 5-layer cross-section and Pantry/Prep Table/Plate taxonomy that governs every CC agent. Implementation differs per agent; the mental model is invariant.

> **"Sparkly slop on top of a foundation of slop is compounded slop."** Most agentic-OS builds fail because the dashboards/agents/personalities are built on unprepared data. Fix the foundation first.

---

## 1. The Cross-Section (5 layers)

| # | Layer | {{AGENT_NAME}} equivalent | Status |
|---|-------|---------------------------|--------|
| 1 | **Agents / UI** | {{AGENT_NAME}} persona, terminal interface, any UI surface | TBD |
| 2 | **CLAUDE.md** | `CLAUDE.md` + sibling runtime files (`AGENTS.md`, `GEMINI.md` etc.) | ✓ scaffolded |
| 3 | **Hooks** | `.claude/settings.local.json` — V6.7 hooks pending substrate parity (state_manager.py, memory_retriever.py, guards) | ⚠ partial |
| 4 | **Skills** | `skills/` — includes silver-platter, integrations-sync, memory-journaling by default | ✓ scaffolded |
| 5 | **Data / Integrations** | Whatever {{AGENT_NAME}}'s domain requires — wrap each in `scripts/*_tool.py` with `--json` | TBD per agent |

**On forge:** the bootstrap wizard should ask the operator what {{AGENT_NAME}}'s domain is (e.g., real estate, lending, fitness, etc.) and personalize layer 5 + the snapshot list in `DATA_TAXONOMY.md` accordingly.

---

## 2. The Four-Layer Maturity Ladder

1. **Identity** — `brain/SOUL.md` ({{AGENT_NAME}} persona), `CLAUDE.md` rules.
2. **Knowledge** — `memory/`, domain-specific knowledge modules.
3. **Workers** — `agents/*.md` materialized specialists (if multi-domain).
4. **Automations** — V6.7 hooks once substrate lands; cron-scheduled snapshots.

Don't ascend until the layer below is solid.

---

## 3. The Silver Platter Principle (THE central insight)

> "Put the core data on a silver platter so agents spend their session analyzing, not retrieving."

**Failure mode:** {{AGENT_NAME}} pulls live API + database on every operator turn. 80% of context window goes to retrieval; 20% to actual synthesis. Fix: pre-aggregate deterministically into **Prep Table** snapshots.

### Three-tier data taxonomy

| Tier | Meaning | {{AGENT_NAME}} scope |
|------|---------|----------------------|
| **Pantry** | Raw integrations + on-disk raw data | See `brain/DATA_TAXONOMY.md` |
| **Prep Table** | Daily/weekly Python-aggregated summaries. No LLM. | TBD per domain |
| **Plate** | What agents consume — briefings, dashboards, digests | TBD per domain |

---

## 4. Critical Paths (SOPs for {{AGENT_NAME}})

Every recurring task gets an explicit SOP. List them in `brain/INTENTS.md` as verb-by-verb playbooks. Examples that apply to almost every agent:

- "Generate a status briefing"
- "Sync external data sources"
- "Log a decision or pattern"

Add domain-specific intents as they recur (every 3rd time you do the same thing manually, codify it).

---

## 5. Default Skill Set

Every forged agent receives these V6.7 canonical skills:

- `skills/silver-platter/` — data-readiness audit producing HTML report
- `skills/integrations-sync/` — idempotent refresh patterns
- `skills/memory-journaling/` — structured DECISIONS/PATTERNS/MISTAKES logging

Plus domain-specific skills the operator adds.

---

## 6. Cross-Agent Propagation

{{AGENT_NAME}} inherits V6.7 essentials at forge time. The master spec stays in Bravo (`~/Business-Empire-Agent/brain/AGENTIC_OS_REFERENCE.md`). When the master updates, this mirror should sync.

## References

- Bravo master: `~/Business-Empire-Agent/brain/AGENTIC_OS_REFERENCE.md`
- Bravo CLAUDE.md V6.7 anchor: "Agentic OS Orchestration (V6.7)"
- Source video: https://www.youtube.com/watch?v=-WCNwxz3uoM
- Transcript: `~/Business-Empire-Agent/docs/references/agentic-os-99pct-transcript.txt`
