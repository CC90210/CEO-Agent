---
name: harness-refinement
description: Propose, measure, apply and roll back changes to Bravo's own prompts, memory, skills and subagent specs — with an executed command as the evidence gate. A refinement that cannot show a before/after delta on a real command is auto-reverted, never merged. Use when a lesson should become a durable change to the harness rather than another line of prose, or when CC asks to change an agent rule and wants the change measured and reversible.
tags: [skill, self-improvement, governance, refinement, v7.6, evidence]
triggers: ["refine the harness", "propose a change to my own rules", "change an agent rule", "queue a proposed change for CC", "roll back a harness refinement", "apply a refinement", "show the refinement ledger", "make this lesson permanent", "prove this change helped"]
owner: bravo
tier: T2
status: NEW
risk: medium
argument_hint: "What should change, and what command would prove it worked?"
requires: [state:state/empire_state.db]
last_updated: 2026-08-07
---

# harness-refinement — evidence-gated self-edits (V7.6.1)

## Overview

The executable half of [[skills/self-improvement-protocol]] Protocol 4. That skill says
*learn from outcomes*; this one is how a lesson actually becomes a durable change without
anyone taking the agent's word for it.

**The rule: evidence is a command, not a paragraph.** You name a command whose output must
change for the refinement to be worth keeping. `apply` runs it again afterwards. If the
output is identical, the edit did nothing measurable and is **auto-reverted**.

Decision record: [[docs/adr/0015-evidence-gated-harness-refinement]]. Imported from
prime-agent's Continual Harness with its gate inverted — it stores an `expectedOutcome` and
never runs it; we run it.

## When to use this instead of just editing the file

| Situation | Use |
|---|---|
| A lesson worth making permanent in memory or a skill | **this skill** |
| A change to CLAUDE.md / an entry point / `brain/` | **this skill** — it queues for CC and can never auto-apply |
| Recording something that happened (no behaviour change intended) | `memory/PATTERNS.md` directly, or `state_sync.py` |
| A code fix | just fix it; this is for the harness's own instructions |

If you cannot name a command that would move, you do not yet know what the change is for.
That is the useful part of the friction — don't route around it.

## The four kinds

`--kind` is required, and it forces the destination to be a decision rather than a default:

| Kind | Means | Typical target |
|---|---|---|
| `memory` | a fact or pattern the agent should carry forward | `memory/PATTERNS.md`, `memory/MISTAKES.md` |
| `skill` | a procedure that should be routable | `skills/<name>/SKILL.md` |
| `prompt_note` | a standing policy or rule | an entry point — always operator-gated |
| `subagent` | a delegation role | `.claude/agents/*.md` — always operator-gated |

## Workflow

```bash
# 1. Propose. --current must appear EXACTLY ONCE in the file.
python scripts/core/refine.py propose \
  --kind memory --file memory/PATTERNS.md \
  --current "<exact existing text>" --proposed "<replacement>" \
  --evidence-cmd "python scripts/harness_eval.py --json" --evidence-key score \
  --reason "why this helps"

# 2. Review the queue (mirrored into memory/PROPOSED_CHANGES.md for CC).
python scripts/core/refine.py list
python scripts/core/refine.py show <id>

# 3. Apply. Re-runs the evidence command and auto-reverts if nothing moved.
python scripts/core/refine.py apply <id>
python scripts/core/refine.py apply <id> --approve   # only CC, for HELD targets

# 4. Undo, or withdraw a proposal that shouldn't proceed.
python scripts/core/refine.py revert <id>
python scripts/core/refine.py cancel <id> --reason "..."
```

## Choosing an evidence command

Good evidence responds to *this* change and nothing else. Standard options:

| Command | Proves |
|---|---|
| `python scripts/harness_eval.py --json` + `--evidence-key score` | a harness check flipped |
| `python scripts/core/task_outcomes.py rate --json` + `--evidence-key first_pass_success_pct` | first-pass success moved |
| `python scripts/capability_query.py resolve "<intent>"` | routing changed for a real intent |
| `python scripts/build_capability_graph.py --check` | graph shape/drift changed |

**Volatile commands are refused at propose time.** `propose` runs the command twice; if two
back-to-back runs already differ, it stops and tells you to narrow it with
`--evidence-key`. `harness_eval --json` alone is volatile — it stamps a fresh `timestamp`
and `run_id` every run — so it must be keyed. Without that check, everything would look
like it had an effect and the gate would pass everything.

The pre-check catches *noisy* commands. It cannot catch *irrelevant* ones: a command that
changes for unrelated reasons will launder a bad refinement through the gate. That judgment
is yours.

**Exit codes.** A keyed command's exit code is treated as a *result*, not a failure —
`harness_eval --json` exits 1 whenever the harness is imperfect, and requiring exit 0 would
reject it outright. What proves a measurement happened is the key being present. An
**unkeyed** command must exit 0 after the edit, because its output *is* the value, so a
crash would otherwise mimic a delta. Exit 124 (timeout) and 127 (could not execute) always
reject. Red → green is a valid refinement, so a clean baseline is not required up front.

## What can auto-apply

A fail-closed **allowlist** — `memory/<file>.md` and `skills/<skill>/SKILL.md`, exactly
those depths. Everything else is `HELD` for CC, including all six entry points,
`PERSONAL.md`, `brain/**` and `scripts/state/**`. Carve-outs inside the allowlist:
`memory/SESSION_LOG.md` (machine-generated between markers),
`memory/PROPOSED_CHANGES.md` (this tool's own mirror), `skills/_archive/*`.

Unmatched paths are held, not applied. A new sensitive directory is therefore safe on the
day it is created, without anyone remembering to add it.

Classification runs on the **resolved** path, so `memory/../CLAUDE.md` is judged as
`CLAUDE.md` and a symlink is judged as its target — don't bother trying to spell your way
around it, and don't "simplify" this back into a path glob: `fnmatch`'s `*` matches `/`, so
a glob allowlist let `memory/../CLAUDE.md` through. `scripts/tests/test_refine.py` carries
every spelling as a regression case. **A new allow rule needs a new test row.**

## Rollback

The exact prior text is stored **at apply time**, so `revert` is a data operation. It
refuses if the file's hash has moved since — it will not undo over someone else's edit.

This matters more than it looks: `.gitignore:44` untracks `memory/PATTERNS.md`, so **git
is not a rollback path** for most refinement targets. The ledger is the only way back.

## Statuses

| Status | Meaning |
|---|---|
| `PENDING` | queued, auto-appliable |
| `HELD` | queued, needs CC's `--approve` |
| `APPLIED` | applied and the evidence moved |
| `REJECTED` | the gate measured no effect (or a no-op edit) — auto-reverted |
| `REVERTED` | was applied, then rolled back |
| `WITHDRAWN` | the operator withdrew it — distinct from the gate rejecting it |

## Bridge exposure

Only `list`, `show` and `ledger` are visible to the chat bridge. `propose`/`apply`/
`revert`/`cancel` take a free-text shell command, and inbound Telegram content is
untrusted data — exposing them would be a remote-execution path. Enforced in
`CAPABILITY_META` and independently in `scripts/_bridge_manifest.json`.

## Anti-patterns

- **Prose as evidence.** Structurally impossible here, and don't reintroduce it by picking
  a command you know will change for unrelated reasons.
- **Proposing against text you haven't read.** `--current` must match exactly once; guessing
  fails at propose time, which is the cheap place to fail.
- **Treating `REJECTED` as a bug.** A rejection is the gate working. Read the recorded
  before/after and either pick better evidence or accept the change wasn't load-bearing.
- **Batching unrelated edits into one proposal.** One refinement, one measurable claim.

## Obsidian Links
- [[skills/self-improvement-protocol]] | [[skills/self-evolution]] | [[skills/retro]]
- [[docs/adr/0015-evidence-gated-harness-refinement]] | [[docs/adr/0001-skill-dependency-classification]]
- [[memory/PROPOSED_CHANGES]] | [[memory/PATTERNS]] | [[CONTEXT]]
