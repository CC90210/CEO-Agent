---
name: currency-audit-2026-07-19
description: First system currency audit — 3-lens sweep for semantic staleness (prose contradicting live reality); 6 HIGH / 14 MED / 10 LOW findings, all fixed in V7.3.5
tags: [audit, hygiene, reference]
last_updated: 2026-07-19
freshness_threshold_days: 365
---

# System Currency Audit — 2026-07-19 (V7.3.5)

> The reference CC asked for: extensive research on diagnosis and fixes for everything "out of date with the motion." Repeatable via `skills/currency-audit/SKILL.md`. Trigger case: the README still sold "Solara + Suga" weeks after Suga retired — a rot class the time-based freshness gates (`memory_aging.py`) structurally cannot see, because the files weren't OLD, they were WRONG.

## Method

1. **Ground truth assembled from live sources** (never memory): `architecture_version: V7.3.3` (STATE.md frontmatter) · CAPABILITY_GRAPH totals 151 skills / 116 scripts / 32 agents / 35 workflows / 14 resources · 9 MCPs in mcp.json (+4 enabled = 13) · client personas Solara (ops) + Helios (sales), Suga retired · canonical domain oasisai.work · operator in Montreal QC since 2026-07 · `EMPIRE_V6_MODE=shadow` · model standard fable-5 (`model_registry.py`).
2. **Three parallel read-only Explore auditors** (~380K tokens): (a) brain/docs prose; (b) knowledge/registry cross-surface consistency; (c) config/automation claims vs live behavior.
3. **Every claim re-verified before fixing** (RULE 10). One auditor claim was REFUTED: the Plain-Text-Export URL `CC90210/CEO-Agent` is the real push remote — the actually-wrong link was §1's `CC90210/Business-Empire-Agent`.

## Findings → fixes (all shipped in the V7.3.5 commit)

### HIGH
| Finding | Fix |
|---|---|
| `brain/AGENTS.md` §20 documented retired **Suga** as active WITH a live routing rule; Solara/Helios defined nowhere in repo | §20 → retirement record; new §21 pointer to the V7.2 agency bench; Solara + Helios added to CONTEXT.md § People & agents and to §19 as the client-persona pair |
| `brain/STATE.md` body: "V6 Apex … architecture phase closed … updated 2026-06-06" + MANIFEST counts 127/150/21/34 | Header + Version row → V7.3.3 narrative; MANIFEST → graph-deferred table (151/116/32/35/14) |
| `skills/INDEX.md` "150 capabilities", missing 6 newest skills | (fixed in this sweep's commit — count graph-deferred, entries added) |
| `brain/TOOL_SHED.md` CC Funnel "Live" in 3 places (+ shareable export) | All 3 → RETIRED 2026-06-18, native funnel oasisai.work/f/; Bravo repo link corrected to CEO-Agent |
| `README.md` "stats check runs in pre-commit" was FALSE | Made TRUE: check appended to `.git/hooks/pre-commit` (blocks commits on drifted counts) |
| `~/APPS/CFO-Agent/brain/USER.md` "Tax Residency: Ontario — current" (5 lines) | Fixed in place (file is gitignored/per-operator — no commit exists, by design): Montreal QC 2026-07, transition-year + Revenu Québec framing; Atlas inbox'd |

### MED (summary — fixed)
Location drift "Collingwood ON" in AGENTS/GEMINI/ANTIGRAVITY entry headers + mirrors + `.rules/01-identity.md` + CONTEXT.md → Montreal QC (mirrors re-stamped via genome_sync) · model-routing tables citing "Opus 4.7 top tier / Haiku-Sonnet-Opus" → model_registry truth (fable-5 standard, opus-4-8 heavy code) in ORCHESTRATION.md + AGENTS.md · PLAYBOOK.md sent CC to Bravo for MRR → rerouted to Atlas; "8 MCPs" → 9/13 · INSTALL.md offered the retired Suga profile → Solara + Helios · vercel.app-as-canonical in AUTH_FINAL_SETUP / N8N_INBOUND_WEBHOOK / RUNBOOK_PM2_COLD_START / APP_REGISTRY / SECURITY_MODEL → oasisai.work (legacy alias noted where technical) · CLAUDE.md Inventory (150/105/23) → live values (151/115 top-level/25 seeded-23 active) · `knowledge/wiki/tech-stack.md` April snapshot ("4 MCPs", 180 skills, GPT-4o-era models, CC Funnel live, Atlas trading) → rewritten from live sources; `knowledge/log.md` backfilled; `knowledge/index.md` confidences decayed per SCHEMA · agent-forge scaffold gap CLOSED (CONTEXT.md template + ADR stub + in-progress lane now ship in `templates/agent-scaffold/`; V68 doc updated from aspirational to actual) · `memory/OPERATIONAL_STATE.md` 10d past its 7-day gate → re-verified live (PM2 10/10 online) + bumped · Maven CONTEXT.md relocation/model touch-ups (sibling commit).

### LOW (batch — fixed)
QUICK_REFERENCE MCP heading phrasing · CAPABILITIES review-date + counts → graph-deferred · PERSONAL.md G4 counts → graph-deferred (seed re-stamped) · `deploy-vps.yml` dead path trigger `scripts/core/scheduler.py` → `scripts/scheduler.py` · TOOL_SHED Agent Triad row (17 sub-agents / Sonnet 4.6 / Atlas trading) · knowledge/SCHEMA tree + frontier-models snapshot banner.

### Verified clean (no action)
Hook parity (template ≡ local, all 12 scripts exist) · package.json script targets · ENV_KEYS_TEMPLATE wrappers (no retired-service keys) · plugin.json 47-skill curation (deliberate subset) · `brain/V6_ARCHITECTURE.md` (correctly self-labeled historical) · EMPIRE_V6_MODE prose in CLAUDE/CONTEXT (tri-state described, no false "off") · auto-generated INDEX/WHEN_TO_USE docs (fresh, test-gated) · oasis-desktop.yml (still relevant) · Maven CONTEXT (no Suga claims).

## Root-cause pattern

Every HIGH finding is the same failure: **a fact materialized in N places, and the motion updated N-1 of them.** The durable cures applied: (1) counts become pointers to `CAPABILITY_GRAPH.json` totals instead of copies; (2) renames get a canonical glossary entry (CONTEXT.md) the moment they happen; (3) the sweep itself is now a registered skill (`currency-audit`) so it re-runs on every rename/retirement/version ship instead of waiting for CC to notice.

## Re-run recipe

`/currency-audit` — or follow `skills/currency-audit/SKILL.md` §How it works. Expected cost: 3 Explore agents + ~1-2h of fixes. Next scheduled sanity point: after the chore/montreal-turnkey-reset → main merge.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
