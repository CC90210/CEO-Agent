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

   **The comparison is on the measured value, never on a digest of the whole run.**
   Folding the exit code into the compared hash made two distinct failures look like
   success, both found by the Codex adversarial audit on 2026-08-08: an edit that
   *breaks* the evidence command (exit 0 → 1) registered as a delta, and an edit that
   moved only the exit code while the measured number sat still also registered as a
   delta. "It changed" is not "it improved". Exit codes are therefore judged by whether
   the command carries a result channel:
   - **keyed** (`--evidence-key`): the exit code is a *result*, not a failure.
     `harness_eval --json` exits 1 whenever the harness is imperfect — it is 9/10 today —
     so requiring exit 0 would reject the evidence command this ADR recommends. The key
     being present in the parsed output is the proof a measurement happened.
   - **unkeyed**: the output *is* the value, so a crash changes it and mimics a delta.
     Exit 0 after the edit is required.
   - Exit 124 (timeout) and 127 (could not execute) always reject: no measurement happened.

   A consequence worth stating: red → green *is* a legitimate refinement (a failing check
   that the edit fixes), so a clean baseline is deliberately **not** required at propose time.
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
4. **Auto-apply is a fail-closed allowlist, enforced on the RESOLVED path.** Only
   `memory/<file>.md` and `skills/<skill>/SKILL.md` may be written autonomously, minus
   carve-outs (`SESSION_LOG.md` is machine-generated, `PROPOSED_CHANGES.md` is this
   tool's own mirror, `skills/_archive/*` is frozen). Any path matching no rule is `HELD`
   for CC. The six entry points, `PERSONAL.md`, `brain/**` and `scripts/state/**`
   therefore can never auto-apply — Rule 4 (lockstep) and Rule 10 (never silently rewrite
   shared substrate) — and a new sensitive directory is protected the day it is created,
   with nobody remembering to add it.

   **This must not be a path glob.** The first implementation used
   `fnmatch(rel, "memory/*.md")`, and `fnmatch`'s `*` matches `/` — so
   `memory/../CLAUDE.md` and `memory/sub/deep.md` both classified as auto-appliable.
   Verified live 2026-08-08 and independently flagged by Codex the same day; four
   characters defeated the entire fail-closed claim. Classification now runs on the
   output of `_resolve()` (which collapses `..` and follows symlinks) using
   segment-exact rules with an explicit component count. Allow rules match
   case-sensitively and deny rules case-insensitively, so both directions err toward
   holding. Locked by `scripts/tests/test_refine.py`, which carries every traversal
   spelling as a regression case — a boundary with no test is one edit from reopening,
   and this one reopened inside a single session.
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
- ~~Sibling propagation to Maven and Atlas is deliberately deferred until the gate has
  rejected at least one real proposal here~~ — see the amendment below.

## Amendment — 2026-08-08: propagated, same day

The deferral above was **overruled by CC on the day this ADR was accepted**, so it is struck
rather than left to mislead. The decision itself is unchanged; only its rollout is.
(This ADR is otherwise immutable per [[docs/adr/INDEX]] — amend with a dated note, never
rewrite the reasoning.)

`scripts/core/refine.py` now runs in **Bravo, Maven and Atlas**, deployed verbatim with only
`CAPABILITY_META["owner"]` differing, alongside a single `architecture_version: V9.2.0`
across all three. Lex-Agent takes the vocabulary only — 4 skills and no capability graph
means the gate would have nothing real to gate on.

Three things the original deferral got right, wrong, and didn't foresee:

1. **Right:** the risk it named is still live. An evidence command that changes for
   unrelated reasons will launder a bad refinement through, and there is *still* no field
   evidence about how often that happens — now across three repos instead of one. Read the
   recorded rejection reasons; do not trust a bare `APPLIED`.
2. **Wrong:** waiting was framed as risk reduction. It was risk *concentration*. Deploying
   to a second repo immediately surfaced a corruption bug Bravo alone could not:
   `Path.write_text()` translates `\n` to `os.linesep`, so reverting an LF-stored file
   rewrote every line ending. Bravo's memory files are CRLF and round-tripped by luck, so
   every byte-hash check I ran had passed. Maven's are LF. Atlas's are **mixed**. One repo
   cannot test a portability claim.
3. **Didn't foresee:** the per-agent surface is the evidence command, not the code. Bravo's
   `harness_eval.py` / `task_outcomes.py` do not exist in either sibling and Atlas also
   lacks `build_capability_graph.py`, so each agent's SKILL.md documents its own commands
   with `capability_query.py resolve` as the shared floor. Atlas additionally forbids
   financial figures as evidence — a changed MRR proves the market moved, not that the edit
   helped, and it would pass any refinement on the next tick.

Enforced by `scripts/tests/test_fleet_parity.py` (drift, owner, one version line, and that
no sibling cites an evidence command it does not have) and redeployed by
`python scripts/deploy_refinement.py --apply`. **Fix bugs in Bravo and redeploy; never
patch a sibling copy.**

## Enforcement

- `python scripts/core/refine.py propose …` refuses prose-only evidence structurally:
  `--evidence-cmd` is a required argument and its output is executed, not read.
- `python scripts/core/refine.py list` / `ledger` — every proposal, its measured delta,
  and its terminal status. `memory/PROPOSED_CHANGES.md` mirrors it for CC.
- `python scripts/build_capability_graph.py --check` — `script:refine` must stay
  registered with valid `CAPABILITY_META` (validated by
  `scripts/lib/capability_metadata.py validate_capability_meta`).
- `python -m pytest scripts/tests/test_refine.py` — 44 cases locking the two boundaries:
  every traversal/depth/case spelling that must stay `HELD`, and the evidence-runner
  contract (bounded output, explicit `<key-missing>`, stable digest for a sane command,
  and the live assertion that `harness_eval --json` is volatile unkeyed but stable when
  keyed to `score`). **New allow rules require a new test in the `HELD`/`AUTO` tables.**
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
