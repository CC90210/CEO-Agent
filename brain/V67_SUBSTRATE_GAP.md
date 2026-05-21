---
title: V6.7 Substrate Gap — Maven & Atlas substrate-parity work pending
mutability: GOVERNED
purpose: Track the V6.0–V6.6 substrate scripts that Maven and Atlas are missing. The V6.7 logic propagation landed; the hooks + snapshot mechanics depend on this substrate being in place first.
created: 2026-05-14
related: brain/AGENTIC_OS_REFERENCE.md (the V6.7 spec), brain/CHANGELOG.md
---

# V6.7 Substrate Gap

When V6.7 (Agentic OS Orchestration) propagated across the empire on 2026-05-14, the **logic-tier essentials** landed in all four agents (Bravo, Maven, Atlas, Hermes):

- `brain/AGENTIC_OS_REFERENCE.md` — canonical logic spec
- `brain/DATA_TAXONOMY.md` — Pantry/Prep Table/Plate manifest
- `brain/INTENTS.md` — verb-by-verb playbook (new for Maven + Atlas; logic-only reference for Hermes)
- `skills/silver-platter/`, `skills/integrations-sync/`, `skills/memory-journaling/` (3 new skills, except Hermes which is logic-only)

But Bravo is the only agent with the **V6.0–V6.6 substrate** that the V6.7 hooks and snapshot scripts depend on. Maven and Atlas are missing it. This file is the gap audit + remediation path.

---

## What's missing in Maven (`~/CMO-Agent`)

Per audit 2026-05-14:

- ❌ `scripts/state/state_manager.py` — transactional state writer (V6.0 source-of-truth proxy)
- ❌ `scripts/core/memory_retriever.py` — FTS5 + LanceDB hybrid retrieval (V6 Ascension)
- ❌ `scripts/core/memory_aging.py` — staleness scanner
- ❌ `scripts/state/secret_guard.py` — credential leak prevention
- ❌ `scripts/state/exec_guard.py` — dangerous-command AST/regex gate
- ❌ `scripts/state/state_guard.py` — auto-generated-mirror edit protection
- ❌ `scripts/hooks/anti_pattern_hook.py` — regex anti-pattern enforcement
- ❌ `memory/ANTI_PATTERNS.json` — the pattern registry
- ❌ `state/empire_state.db` — SQLite/WAL transactional store
- ❌ `state/memory_index.db` — FTS5 retrieval index
- ❌ `scripts/core/cron_engine.py` — automation job registry
- ❌ `scripts/build_capability_graph.py` — capability auto-discovery

**Has:** `agent_inbox.py`, `brain/SOUL.md`, `brain/STATE.md`, `memory/ACTIVE_TASKS.md`, `memory/DECISIONS.md`, shared Supabase via `SHARED_DB.md`.

---

## What's missing in Atlas (`~/APPS/CFO-Agent`)

Per audit 2026-05-14:

- ❌ `scripts/state/state_manager.py`
- ❌ `scripts/core/memory_retriever.py`
- ❌ `scripts/core/memory_aging.py`
- ❌ `scripts/state/secret_guard.py` (with CFO-specific regex patterns for Kraken keys, SIN, business number, etc.)
- ❌ `scripts/state/exec_guard.py`
- ❌ `scripts/state/state_guard.py`
- ❌ `scripts/hooks/anti_pattern_hook.py`
- ❌ `memory/ANTI_PATTERNS.json`
- ❌ `state/empire_state.db`
- ❌ `state/memory_index.db`
- ❌ `scripts/core/cron_engine.py`
- ⚠ `scripts/audit_mcp_secrets.py` — referenced in Atlas's SessionStart hook but doesn't exist (silent fail)

**Has:** `agent_inbox.py`, `brain/CAPABILITY_GRAPH.json` (auto-discovered already), 21 finance-domain skills, finance/ knowledge modules.

**Critical:** Atlas's current `.claude/settings.local.json` (lines 26–36) calls `memory_aging.py` and `agent_inbox.py` on SessionStart, but `memory_aging.py` doesn't exist. **Silent failure on every Atlas session.** This pre-dates V6.7 — surfacing now because the substrate-parity sweep made it visible.

---

## Hermes is intentionally NOT propagated

Hermes is a single-user commerce-ops product, not a multi-agent orchestration engine. V6.7 hooks + snapshots don't fit. Logic-only mirrors landed at `~/APPS/hermes/brain/AGENTIC_OS_REFERENCE.md` + `brain/DATA_TAXONOMY.md`. No substrate work needed.

---

## What's blocked until substrate lands

For Maven and Atlas, the following V6.7 pieces are deferred:

- **Hooks:** `.claude/settings.local.json` SessionStart / PreCompact / UserPromptSubmit hooks all depend on `state_manager.py`, `agent_inbox.py`, `memory_aging.py`, `memory_retriever.py` being present.
- **Snapshot scripts:** `scripts/snapshots/*_snapshot.py` need an in-place `state/` directory + the engine scripts they wrap (Maven has `meta_ads_engine.py` etc.; Atlas has `finance/wealth_tracker.py` etc., so the wrappers are buildable).
- **Cron job registration:** `cron_engine.py` SEED_JOBS need the engine itself to exist.
- **anti_pattern_hook wiring:** depends on `memory/ANTI_PATTERNS.json` + the hook script.

---

## Remediation Plan (next discrete plan, not this one)

### Phase 1 — Substrate parity (Maven + Atlas, ~3h each)

For each of Maven and Atlas:

1. Copy the 7 substrate scripts from `~/Business-Empire-Agent/scripts/` (state_manager, memory_retriever, memory_aging, secret_guard, exec_guard, state_guard, anti_pattern_hook). Adapt:
   - `PROJECT_ROOT` references (each script uses `Path(__file__).resolve().parent.parent` — already correct)
   - Atlas's `secret_guard.py`: extend regex patterns for CFO domain (Kraken keys, SIN, business number, account numbers, salary figures)
2. Copy `scripts/core/cron_engine.py`. Adapt SEED_JOBS:
   - Maven: content_calendar refresh, ad performance sync, weekly digest
   - Atlas: ACB recompute, tax position rebuild, quarterly FIRE update
3. Copy `scripts/build_capability_graph.py` (no adaptation needed). Run it to populate `brain/CAPABILITY_GRAPH.json` for Maven.
4. Copy `memory/ANTI_PATTERNS.json` (start with the 2 Bravo patterns; add agent-specific ones over time).
5. Bootstrap `state/empire_state.db` via `python scripts/state/state_manager.py import-from-files`.
6. Bootstrap `state/memory_index.db` via `python scripts/core/memory_retriever.py build`.

### Phase 2 — V6.7 hook + snapshot completion (Maven + Atlas, ~2h each)

For each:

1. Add the 4 hook scripts (session_start, pre_compact, user_prompt_submit, rotate_logs) — copy + minor adaptations.
2. Build the domain-adapted snapshot scripts:
   - Maven: `ad_performance_snapshot.py`, `content_velocity_snapshot.py`, `roas_snapshot.py`
   - Atlas: `portfolio_snapshot.py`, `acb_snapshot.py`, `tax_position_snapshot.py`, `fire_snapshot.py`
3. Register the cron entries.
4. Wire hooks in `.claude/settings.local.json`.
5. Smoke-test all hooks fire + emit valid JSON.
6. Run `silver-platter` audit to verify Pantry/Prep Table/Plate is complete.

### Phase 3 — Atlas SessionStart fix (urgent, ~10min)

Atlas's existing `.claude/settings.local.json` calls non-existent scripts. Either:
- (a) Remove the references until substrate lands (defensive — stops silent fail), or
- (b) Land substrate first then leave the references in place

Recommend (a) as a same-day defensive fix while (b) is the proper resolution.

---

## Tracking

When each phase lands, update this file with the date + commit hash. When both Maven and Atlas reach full V6.7 parity, mark this file as `RESOLVED` and archive to `memory/ARCHIVES/`.

| Agent | Substrate parity | V6.7 hooks | V6.7 snapshots | Status |
|-------|------------------|------------|----------------|--------|
| Bravo | ✅ V6.0–V6.6 | ✅ 2026-05-14 (`94740be`) | ✅ 2026-05-14 (`94740be`) | **Complete** |
| Maven | ⚠ partial (agent_inbox only) | ❌ blocked | ❌ blocked | **Substrate pending** |
| Atlas | ⚠ partial (agent_inbox + capability_graph only) | ❌ blocked + Atlas SessionStart silent-fail | ❌ blocked | **Substrate pending + urgent fix** |
| Hermes | N/A (intentionally skipped) | N/A | N/A | **Logic-only landed** |
