---
name: decisions
description: Surface the choices made during the current work that the agent is genuinely NOT confident about, with the alternatives that were not considered. Use before shipping, before a review, or when CC asks "what did you decide", "what are you unsure about", "/decisions". Retrospective — for drilling still-open choices forward one at a time, that is a different move.
triggers: [decisions, what did you decide, what are you unsure about, low confidence choices, second guess this]
tier: standard
dependencies: []
disable-model-invocation: true
tags: [skill, decisions, review, self-audit]
last_updated: 2026-08-03
---

# Decisions

List the choices made during this work that you are **genuinely unsure about** — and for each,
the alternative that might be better.

Manual-only. This is a deliberate audit CC invokes, not something that fires on its own.

## Why this exists

An agent's self-review is biased toward its own completeness (this is why Rule 8 requires an
independent Codex audit on big tasks). But the bias has a specific shape worth attacking
directly: the low-confidence calls made *quietly* — the column type picked in five seconds, the
regex boundary guessed, the error swallowed because the happy path worked — never surface,
because nothing in the workflow asks about them. Tests cover what was written, not what was
chosen. This skill asks.

## The question

> While working on this, which important decisions did I make that I am not confident about?
> For each, is there a genuinely better alternative we did not consider?

Reason about it properly before answering. Re-read the actual diff — do not answer from memory
of the session, which is exactly where the confident-sounding reconstruction comes from.

## Hard rules

- **Only genuine uncertainty.** If the choice was obviously right, leave it out. A list padded
  with settled decisions dilutes the two that matter and trains CC to skim it.
- **Name the alternative.** "I'm unsure about the caching approach" is not usable. "I cached on
  mtime; if two writes land in the same second the cache serves stale — hashing the content
  costs ~2ms and removes the class of bug" is.
- **Include the ones nobody asked about.** Silent defaults, error handling picked without
  thought, a boundary condition assumed rather than checked, a name that will be wrong in a
  month. These are the point of the exercise.
- **Say what would settle it.** For each: the command, the test, or the one question to CC that
  turns the uncertainty into a fact. An unresolvable "hmm" is not a finding.
- **Rank by blast radius, not by how unsure you feel.** A 60%-confident call inside a hook that
  every agent runs outranks a 20%-confident call in a one-off script.
- **Empty is a valid answer** — but only after actually looking. If every call really was clear,
  say "nothing I'm genuinely unsure about" and name the two closest calls anyway so CC can
  disagree.

## Output

Short. One block per decision:

- **What I chose** — one line.
- **Why I'm unsure** — the specific failure mode, not "it could be better."
- **The alternative** — concrete.
- **What would settle it** — a command, a test, or a question for CC.

Then stop. Do not fix anything. This skill surfaces; CC decides what gets acted on.

## Obsidian Links
- [[skills/code-review/SKILL]]
- [[skills/verification-before-completion/SKILL]]
