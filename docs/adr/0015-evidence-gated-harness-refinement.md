---
adr: 15
title: "Evidence-gated harness refinement: evidence is an executed command, not a rationale"
status: accepted
date: 2026-08-07
deciders: [bravo, cc]
supersedes: null
superseded_by: null
tags: [docs, adr, decision]
last_updated: 2026-08-07
---

# ADR-0015 — Evidence-gated harness refinement: evidence is an executed command, not a rationale

> Numbered 0015, not 0013: [[docs/adr/INDEX]] earmarks 0013 and 0014 for the pending
> 0003/0004 collision renumber, which needs CC's approval before anyone claims them.

## Context

CLAUDE.md Rule 9 promises continuous, automatic self-improvement. The 2026-08-07
prime-agent audit (plan: `~/.claude/plans/i-m-dropping-you-a-luminous-lighthouse.md`)
established that the promise was unimplemented prose. Every loop was open at one end:

- `scripts/harness_eval.py` had written **203 scored runs** to
  `state/harness_eval_history.jsonl`; the only file referencing that path was
  `harness_eval.py` itself. Measurement with no reader. The red 8/10 on 2026-08-05
  triggered nothing.
- `scripts/core/task_outcomes.py` held **46 verdicts**; its one non-dashboard consumer,
  `auto_heal.py:104`, shelled `task_outcomes.py stats` — a subcommand that has never
  existed. `telemetry_synced` was therefore permanently `False` while `auto_heal`
  reported "Synchronized neural routing telemetry and activation weights".
- `scripts/auto_dream.py` proposed `[P]`→`[V]` promotions and only printed them.
- `scripts/core/evolve.py` scaffolded skills from validated patterns and never checked
  that routing or mistake-recurrence changed.
- `memory/PROPOSED_CHANGES.md` had specified the correct schema since 2026-05-21 —
  File / Section / Current / Proposed / **Evidence** / Risk / **Rollback** / Status — and
  sat empty for 79 days because **no code ever wrote to it**.

The forcing function was that the design was already right and only the executor was
missing. PrimeIntellect-ai/prime-agent (MIT) ships that executor as its **Continual
Harness**: a typed self-edit store (`harness_state.json`), a `/refine` command, and an
append-only ledger recording each edit's `before`/`after`.

Its gate, however, fails in precisely the way this repo forbids. `refinement.ts:783-790`
sets `evidence: proposal.rationale` — the proposing model's own paragraph. A grep for
`runChildProcess|exec|spawn|confirm|approve|askUser` in that file returns zero hits; the
only check is `reviewAutoRefine()`, a second LLM call, and no approval flag exists. Every
proposal carries an `expectedOutcome` field that is stored and never executed. That is
Anti-Slop #6 — claim done without proof — wearing a ledger.

## Decision

Adopt the shape, invert the gate. **They store the expected outcome; we run it.**

1. **Evidence is an executed command.** `scripts/core/refine.py propose` requires
   `--evidence-cmd` and *executes* it, storing the result. A refinement survives `apply`
   only if re-running that same command produces a **different** recorded value. No
   delta ⇒ the change did nothing measurable ⇒ the file is auto-reverted and the row
   marked `REJECTED (no measured effect)`. Prose is not evidence and cannot be supplied
   as such. This is CLAUDE.md Rule 2 ("Proof: the verification command + its actual
   output") made mechanical.
2. **Volatile commands are refused at propose time.** `propose` runs the evidence command
   **twice** and rejects it if two back-to-back runs already differ, pointing the caller
   at `--evidence-key <dotted.json.path>`. Without this, `harness_eval --json`'s per-run
   `timestamp`/`run_id` would make every refinement appear to have an effect and the gate
   would pass everything. A gate that cannot fail is not a gate.
3. **The inverse is stored, not synthesized.** The exact prior text is persisted at apply
   time; `revert` is a data operation that refuses to run if the file's hash has moved
   since. prime-agent's `rollbackProposal()` reconstructs the inverse from reversed edits
   at rollback time, which drifts if the file changed underneath. This matters more here
   than there: `.gitignore:44` untracks `memory/PATTERNS.md`, so **git is not a rollback
   path** for most refinement targets — the ledger is the only way back.
4. **Auto-apply is a fail-closed allowlist.** Only `memory/*.md` and `skills/*/SKILL.md`
   may be written autonomously, minus carve-outs (`SESSION_LOG.md` is machine-generated,
   `PROPOSED_CHANGES.md` is this tool's own mirror, `skills/_archive/*` is frozen). Any
   path matching no glob is `HELD` for CC. The six entry points, `PERSONAL.md`, `brain/**`
   and `scripts/state/**` therefore can never auto-apply — Rule 4 (lockstep) and Rule 10
   (never silently rewrite shared substrate) — and a new sensitive directory is protected
   the day it is created, with nobody remembering to add it.
5. **Four self-edit kinds, chosen explicitly.** `prompt_note | memory | skill | subagent`,
   a required `--kind`. prime-agent carries the same taxonomy as prose in
   `REFINEMENT_SYSTEM_PROMPT:146-147` with no classifier in code; here it is an argparse
   choice, so the destination is a recorded decision rather than a hope.
6. **The mutating path is not reachable from the chat bridge.** `propose`/`apply`/
   `revert`/`cancel` take a free-text shell command; inbound Telegram content is untrusted
   data. Only `list`/`show`/`ledger` are `visible: true` in `CAPABILITY_META`, enforced
   independently by `scripts/_bridge_manifest.json`.

## Consequences

**Positive:**
- `harness_eval`'s history and `task_outcomes`' verdicts stop being write-only telemetry:
  they are the standard evidence commands, so a measurement now decides something.
- A refinement that sounded good but changed nothing leaves a `REJECTED` row with the
  measured before/after attached, so the same idea is not re-proposed blind.
- `PROPOSED_CHANGES.md` has a writer, and its Status field — which prime-agent's ledger
  lacks entirely — distinguishes `REJECTED` (the gate measured no effect) from
  `WITHDRAWN` (the operator withdrew it).

**Negative:**
- Evidence quality is now the bottleneck. A lazily chosen command (one that changes for
  unrelated reasons) launders a bad refinement through the gate. The volatility
  pre-check catches *noisy* commands, not *irrelevant* ones — that judgment stays human.
- Every `propose` pays two evidence runs and every `apply` a third. With
  `harness_eval --json` at roughly a minute, a proposal is not free.
- The allowlist means the highest-value targets (the entry points, `brain/`) are exactly
  the ones that still require CC. This is deliberate, but it caps how much the loop can
  close without an operator.

**Neutral:**
- One additive table (`refinements`) in `state/empire_state.db`, created with
  `CREATE TABLE IF NOT EXISTS` on the `task_outcomes.py` pattern. No guard, hook, daemon
  or cron changed.
- Sibling propagation to Maven and Atlas is deliberately deferred until the gate has
  rejected at least one real proposal here — see [[brain/V68_AGENT_OS_PATTERNS]].

## Enforcement

- `python scripts/core/refine.py propose …` refuses prose-only evidence structurally:
  `--evidence-cmd` is a required argument and its output is executed, not read.
- `python scripts/core/refine.py list` / `ledger` — every proposal, its measured delta,
  and its terminal status. `memory/PROPOSED_CHANGES.md` mirrors it for CC.
- `python scripts/build_capability_graph.py --check` — `script:refine` must stay
  registered with valid `CAPABILITY_META` (validated by
  `scripts/lib/capability_metadata.py validate_capability_meta`).
- Review-time: a refinement whose evidence command cannot plausibly respond to the change
  is a bad proposal even when the gate passes it. Say so in review.

## References

- Source: <https://github.com/PrimeIntellect-ai/prime-agent> (MIT — formats and mechanics
  studied, no code copied). Counter-example cited: `refinement.ts:783-790`.
- Related: [[docs/adr/0001-skill-dependency-classification]] (harness-refinement declares
  its state dep hard) · [[docs/adr/0011-typed-memory-taxonomy]] (the `memory` kind writes
  into that taxonomy) · [[docs/adr/0002-context-md-canonical-vocabulary]]
- Code: `scripts/core/refine.py` · `scripts/core/auto_heal.py read_outcome_telemetry()` ·
  `skills/harness-refinement/SKILL.md` · `memory/PROPOSED_CHANGES.md`

## Obsidian Links
- [[docs/adr/INDEX]]
- [[CONTEXT]]
