# Turso Migration and Harness Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the Supabase-to-Turso migration at the documentation, routing, reporting, memory, scheduling, and cross-agent layers so every green health signal represents the same live truth.

**Architecture:** Treat live source and executable checks as canonical, then make generated artifacts, memory, entry points, health reports, and peer handovers derive from that truth. Preserve intentional legacy Supabase surfaces only when they are explicitly annotated with their remaining purpose; fail gates on unclassified stale context.

**Tech Stack:** Python 3.12, pytest, Turso/libSQL compatibility layer, Markdown capability graph, local cron engine, Claude/Codex lifecycle hooks.

---

### Task 1: Freeze and classify migration residue

**Files:**
- Inspect: `brain/`, `memory/`, `skills/`, `scripts/`, registered OASIS app roots
- Modify: active stale files identified by `scripts/core/doc_sweep.py`
- Test: `scripts/tests/test_doc_sweep.py` or nearest existing doc-sweep coverage

1. Run the live doc sweep and repository-wide `rg` inventory.
2. Classify each reference as stale, transitional, historical, or intentional compatibility naming.
3. Replace stale primary-backend claims with Turso truth.
4. Annotate legitimate legacy references with a reason.
5. Run the sweep again and require zero unclassified Tier 1/2 findings.

### Task 2: Correct reporting and degraded-brief detection

**Files:**
- Modify: `scripts/harness_eval.py`
- Modify: `scripts/daily_brief.py`
- Test: the matching harness/daily-brief tests under `scripts/tests/`

1. Add failing tests for timeout/degraded markers.
2. Make `check_brief_renders` reject degraded output.
3. Increase the dashboard child timeout while remaining below the wrapper budget.
4. Prove normal output remains green and timeout output goes red.

### Task 3: Add weekly full-truth reporting

**Files:**
- Create: `scripts/weekly_truth_digest.py`
- Modify: `scripts/core/cron_engine.py`
- Test: new focused tests under `scripts/tests/`

1. Write tests for deterministic summaries, hard timeouts, failure propagation, and always-notify behavior.
2. Implement the digest over self-audit, fleet health, and pytest.
3. Add the approved active Sunday 07:00 seed job.
4. Rebuild capability metadata and safely seed production cron state.
5. Verify the job is listed and dry-run the digest without sending a duplicate real notification.

### Task 4: Repair state, memory, and pulse contracts

**Files:**
- Modify: `scripts/state/state_sync.py`
- Modify: relevant lifecycle hook scripts/settings
- Repair: `memory/SESSION_LOG.md`
- Test: state-sync regression tests

1. Reproduce duplicated frontmatter and stale judgment behavior.
2. Add tests requiring one frontmatter block and a fresh session-end pulse.
3. Repair the writer and normalize the existing log without losing session entries.
4. Wire session-end state sync/heartbeat through approved hooks.
5. Verify `fleet_health.py` reports Bravo fresh.

### Task 5: Restore hook and entry-point parity

**Files:**
- Modify: `C:/Users/User/.claude/settings.json`
- Modify: `.claude/settings.local.json`
- Modify: lockstep entry points and mirrors when canonical source proves drift
- Test: `scripts/codex_health.py`, `scripts/agent_genome.py`, lockstep tests

1. Preserve existing hook arrays and merge missing lifecycle hooks.
2. Regenerate or synchronize lockstep blocks from the canonical seed.
3. Verify Codex health 13/13 and genome 10/10.

### Task 6: Add durable migration and inventory gates

**Files:**
- Modify: `scripts/core/self_audit.py` and/or `scripts/harness_eval.py`
- Modify: `scripts/core/doc_sweep.py`
- Modify: `skills/architecture-migration-gate/SKILL.md`, `skills/turso-patterns/SKILL.md`
- Test: focused self-audit, harness, router, and migration-gate tests

1. Add failing tests for stale component-as-primary claims and unregistered new capabilities.
2. Make migration completion depend on a stored impact manifest and classified sweep.
3. Detect malformed memory frontmatter and disagreement among flagship health checks.
4. Ensure new scripts/skills/workflows have one canonical registration path and overlap check.
5. Rebuild generated graph/docs and prove resolver behavior.

### Task 7: Review, verify, and hand over

**Files:**
- Create: `docs/handovers/2026-08-20-oasis-turso-agent-alignment-handover.md`
- Update: `memory/SESSION_LOG.md`, `brain/STATE.md`

1. Run focused tests after each change.
2. Run the full suite twice, self-audit, harness with model, genome, Codex health, fleet health, and doc sweep.
3. Run pre-landing review plus an independent cold audit.
4. Write a self-contained Adon/APEX handover with architecture truth, required peer changes, commands, and acceptance gates.
5. Sync state and report exact remaining external dependencies, if any.
