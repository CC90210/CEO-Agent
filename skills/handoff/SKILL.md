---
name: handoff
description: Compact the current session into one paste-ready block a fresh agent can resume from — what happened, why, what is left, and what NOT to redo. Use when hitting context limits, ending a work session, switching runtimes (Claude to Gemini/Codex/OpenCode), or partitioning a task across fresh contexts. Triggers on "handoff", "hand this off", "write a handoff", "/handoff", "pass this to a fresh session".
triggers: [handoff, hand off, fresh session, context limit, switch runtime, resume elsewhere, pass this on]
tier: standard
dependencies: [memory-management, verification-before-completion]
disable-model-invocation: true
tags: [skill, handoff, session, continuity]
last_updated: 2026-08-03
---

# Handoff

Write a handoff that lets an agent with **zero memory of this session** continue without
re-asking CC, re-discovering the codebase, or repeating a mistake this session already paid for.

Manual-only (`disable-model-invocation`). This never fires mid-task — a handoff written while
work is still moving is a snapshot of a moving target.

## Why this is separate from `state_sync`

`state_sync.py` writes the durable, agent-facing record (state DB → `SESSION_LOG.md`,
`ACTIVE_TASKS.md`). That is the **archive**. A handoff is the **carry** — a single block CC can
paste into a different runtime right now. Run both: `state_sync` for the record, handoff for
the transfer. They are not substitutes.

This matters here specifically because CC runs six entry points (Claude, Gemini, Antigravity,
OpenCode, ZCode, Codex). A handoff crossing runtimes cannot assume the receiver can read our
state DB or has our hooks loaded — so it must be self-contained prose, not a pointer.

## Output

Emit the whole handoff as **one fenced code block** in chat so CC copies it in a single click.
Then save a copy to `memory/handoffs/YYYY-MM-DD-<slug>.md` and tell CC the path in one line.

## Required sections

**1. One-paragraph orientation.** What we were doing and why, for someone who has never seen
this project. Name the repo and branch. No jargon without a one-clause gloss.

**2. What actually changed.** File paths with a one-line reason each. Commits by hash + subject.
If nothing was committed, say so plainly.

**3. Verification state — the honest one.** What was proven, with the command and its real
output. What was NOT verified, named explicitly. Per the Definition of Done in CLAUDE.md, a
step without proof is "in progress," and the handoff must say so rather than let the next agent
inherit a false green.

**4. Dead ends — the highest-value section.** What was tried that did not work, and why. This is
the part that pays for the handoff: without it the next agent re-runs the same failed approach
and spends the same tokens discovering the same wall. Include tool failures and their fallbacks.

**5. Open decisions.** Anything CC has not ruled on, phrased as a question with a recommendation.

**6. Next concrete action.** ONE action, specific enough to start immediately — a command, a
file, a question for CC. Not "continue the integration."

**7. Landmines.** Anything that will bite the next agent: a guard that blocks an obvious command,
a flaky tool, a file that must not be hand-edited, a stale claim in a memory file.

## Rules

- **Assume zero shared context.** No "as discussed", no "the usual place", no unexplained
  pronouns. Every reference resolves inside the block.
- **Inherited claims are claims, not state.** Anything this session took on faith from a prior
  handoff must be labelled as such, so the next agent re-verifies rather than compounds it
  (Rule 10 — the V6 coherence gate exists because a stale inherited claim nearly rewrote a
  working email template).
- **Never quote a credential.** Name the wrapper to call, never the value. If a secret would
  make the handoff clearer, that is a sign the next agent should run
  `python scripts/capability_probe.py check <service>` instead.
- **Length follows the work.** A one-file fix gets a short block. Do not pad to look thorough.

## After writing

Run `python scripts/state/state_sync.py --note "<one-line summary>"` so the durable record and
the carry agree. A handoff that contradicts `SESSION_LOG.md` is worse than neither.

## Obsidian Links
- [[skills/memory-management/SKILL]]
- [[skills/verification-before-completion/SKILL]]
- [[brain/EXECUTION_RULES]]
