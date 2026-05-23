---
adr: 0003
title: Agent-first identity across all CLI entry files
status: accepted
date: 2026-05-23
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0003 — Agent-first identity across all CLI entry files

## Context

The five sibling entry files in each agent repo (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `ANTIGRAVITY.md`, `OPENCODE.md`) each open with an identity section that tells the AI runtime "who you are when CC opens this repo." Until 2026-05-23 these sections used a **model-driven** dispatch:

```
- Running on Claude → you are Bravo, full identity.
- Running on Gemini → you are Bravo's Inference Engine, read-only default.
- Running on GPT/OpenAI → you are Codex, backend executor.
- Running on local/Llama → identify by tool name, read-only.
```

The dispatch was load-bearing for one specific path — **Codex CLI invoked via `~/.claude/codex-plugin/scripts/codex-companion.mjs adversarial-review`** — where Claude Code wanted Codex to identify as Codex for backend review.

But it broke a much more common path: **OASIS Command Center chat selecting Codex CLI as the runtime for an agent.** The bridge's per-turn user prompt asserts "You are BRAVO" but Codex's auto-loaded `AGENTS.md` (loaded as system context before the bridge's user message arrives) anchored "You are Codex." System context won the conflict — operators saw "I'm Codex, backend executor" when they expected Bravo.

Atlas (`CFO-Agent`) never had this bug. Its identity section was already agent-first: "You are Atlas, regardless of which CLI runtime hosts you." Same Codex CLI invocation embodied Atlas correctly.

The Atlas pattern is the right one. Identity is the agent the operator opened (the repo / tenant / persona file). The CLI runtime is implementation plumbing — like which kernel the OS is running on.

## Decision

**Identity is agent-first across every entry file in every agent repo.** Replace model-driven dispatch with a single explicit assertion:

> You are `<Agent>`. The CLI runtime (Codex / Cursor / Gemini / OpenCode / Antigravity / etc) is implementation plumbing.

Per-runtime guidance that USED to live in the dispatch table is reframed as **safety advisories** that shape default risk posture but do NOT change identity:

- "If you're a Gemini-family model, lean read-only on `brain/SOUL.md` and `.env*` and ask before mutating state files" — still Bravo.
- "If you're an unproven local model, default to read-only" — still Bravo.

The Codex-as-adversarial-reviewer delegation lane is preserved via an **explicit override path**: when Claude Code (or any Bravo session) invokes `codex-companion.mjs` with the `adversarial-review` template, that template's prompt explicitly tells Codex to embody Codex for that single invocation. The explicit prompt overrides AGENTS.md. Without that explicit template, Codex defaults to the repo's agent identity.

## Consequences

**Positive:**
- Codex CLI / Gemini CLI / OpenCode invocations from OASIS Command Center now correctly embody the selected agent. CC's "I'm Codex" symptom is gone (verified live on 2026-05-23: Bravo via Codex CLI responds "I'm Bravo, CC's Lead Architect").
- Pattern is consistent across the empire. Atlas / Bravo / Maven all follow the same identity-section template, simplifying onboarding for new agent repos (Aura, Hermes, future clients).
- Safety advisories stay intact — the read-only-on-unproven-models guidance is still there, just no longer hidden inside an identity dispatch.

**Negative:**
- The `codex-companion.mjs adversarial-review` template is now load-bearing. If that template ever loses its explicit "you are Codex" wording, Codex will default to the repo's agent identity instead. This is a documented invariant — the template MUST keep an explicit identity assertion.
- Operators who memorized the old "GPT model → Codex" rule need to relearn. Trade-off accepted because the new rule is simpler.

## Files affected (2026-05-23)

- `/Users/conaugh/CEO-Agent/AGENTS.md` — Rule section rewritten (commit `1623b4d2`)
- `/Users/conaugh/CEO-Agent/GEMINI.md` — Same pattern (commit `f7bae62d`)
- `/Users/conaugh/CEO-Agent/ANTIGRAVITY.md` — Same pattern (commit `f7bae62d`)
- `/Users/conaugh/CEO-Agent/OPENCODE.md` — Same pattern (commit `f7bae62d`)
- `/Users/conaugh/CMO-Agent/AGENTS.md` — Same pattern (CMO-Agent commit `f5293e0`)
- `/Users/conaugh/CMO-Agent/OPENCODE.md` — Same pattern (CMO-Agent commit `0db1b3f`)
- `/Users/conaugh/CFO-Agent/AGENTS.md` — Already correct, no change needed (reference implementation)

## Open follow-ups

- **Maven's GEMINI.md / ANTIGRAVITY.md**: scanned clean for the model-driven dispatch pattern on 2026-05-23. If a future audit finds drift, apply the same fix.
- **Aura / Hermes**: not on the audit machine when this ADR was written. Same fix applies if those repos still have model-driven identity sections.
- **Rule numbering across entry files**: the 5 sibling files have significantly drifted in their rule schemes (CLAUDE.md has Rules 0-10, AGENTS.md has different Rules 0-10, GEMINI.md uses decimal subrules 2.5/2.5.1/2.6, etc). The "lockstep" claim in those files is currently fiction. Separate ADR / cleanup needed; this ADR is scoped to identity only.
