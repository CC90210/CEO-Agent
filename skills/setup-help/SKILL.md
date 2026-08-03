---
name: setup-help
description: Walk CC through an operator-blocked setup ONE atomic step at a time, always listing what remains. Use when CC must do something the agent cannot — a dashboard signup, a DNS record, a bank or Plaid approval, an OAuth consent, a VPS action, an entity or counsel step. Triggers on "help me set up", "walk me through", "how do I", "setup-help", "/setup-help", or any handoff where the next action is CC's to take.
triggers: [help me set up, walk me through, how do I set up, setup help, configure this, get this working, what do I do next]
tier: standard
dependencies: []
disable-model-invocation: true
tags: [skill, setup-help, operator, onboarding]
last_updated: 2026-08-03
---

# Setup Help

Guide CC through a setup one atomic step at a time, in plain English.

Manual-only. This fires when CC asks, or when a plan hits an action only CC can take.

## Why this exists

CC's blocked items are almost never engineering — they are dashboard clicks, DNS records, bank
approvals, and consent screens the agent has no hands for. Handing CC a twelve-item checklist
converts one blocker into twelve, because CC has to hold the state. This skill holds the state
instead: CC does one thing, comes back, gets the next one.

## Response format — every single response, no exceptions

**1. Current step.** ONE atomic action. A single click, a single field, a single command.
1–2 lines. Plain English. If it needs sub-steps it is too big — split it and push the rest down.

**2. A `----` divider.**

**3. Still remaining.** Every remaining step, numbered, one short line each. Always. Even when
only one is left ("Still remaining: nothing after this"). This is the part CC is actually
buying — it is what lets them stop holding the map.

## Rules

- **Anything the agent can do, the agent does.** Before writing a step for CC, check whether a
  CLI wrapper already covers it: `python scripts/capability_probe.py check <service>`. A service
  marked OK means you are authorized — run it yourself and collapse that step out of CC's list.
  Handing CC a step the agent was wired to do is the failure this skill must not commit.
- **A command CC must run is a paste-block, never instructions.** One fenced block, complete,
  no placeholders CC has to reason about. If it must run somewhere else (a VPS, another
  machine), say where in one clause and give the block ready to paste. Never narrate SSH.
- **Never ask CC for a secret.** Ask them to put it where the loader reads it, then continue.
  Never ask them to paste a token into chat.
- **One step means one.** "Go to Settings, then Billing, then click Upgrade" is three steps
  wearing a trenchcoat. Send the first one.
- **Wait.** After a step, stop. Do not pre-answer the next one — CC's result may change it.
- **When CC reports a failure, fix the step, do not repeat it.** Re-sending the same instruction
  louder is the thing CC has explicitly pushed back on. Diagnose, then send a different step.
- **Track completion honestly.** If CC skips a step, it stays in "Still remaining" flagged as
  skipped. Silently dropping it produces a setup everyone believes is finished and isn't.

## Ending

When the last step lands, verify it rather than declare it. Run the real check — hit the live
endpoint, query the row, re-run the probe — and show the output. Then state in one line what is
now working that wasn't. If verification is impossible from here, say exactly that and name
what would prove it.

## Obsidian Links
- [[brain/EXECUTION_RULES]]
- [[skills/verification-before-completion/SKILL]]
