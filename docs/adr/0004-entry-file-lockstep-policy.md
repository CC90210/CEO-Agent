---
adr: 0004
title: Entry-file lockstep policy — what must match across CLAUDE.md / AGENTS.md / GEMINI.md / ANTIGRAVITY.md / OPENCODE.md
status: accepted
date: 2026-05-23
deciders: [bravo, cc]
supersedes: null
superseded_by: null
tags: [docs, adr, decision]
last_updated: 2026-05-23
---

# ADR-0004 — Entry-file lockstep policy

## Context

Each agent repo has five sibling entry files — one per CLI runtime that auto-loads a markdown system context on session boot:

- `CLAUDE.md` (Claude Code)
- `AGENTS.md` (Codex / Cursor / Windsurf / Aider — any AGENTS.md-convention CLI)
- `GEMINI.md` (Gemini CLI)
- `ANTIGRAVITY.md` (Antigravity IDE)
- `OPENCODE.md` (OpenCode terminal)

All five reference the same `brain/` and `memory/` directories. CLAUDE.md `RULE 4` mandates that editing one file requires syncing the rest "in lockstep."

A 2026-05-23 audit found the lockstep claim is **fiction**:

| File | Rule scheme |
|---|---|
| `CLAUDE.md` | Clean Rules 0-10 (state sync · answer first · tool routing · creds · cross-file sync · verification · obsidian · app registry · codex delegation · self-improvement · v6 coherence) |
| `AGENTS.md` | DIFFERENT Rules 0-10 (state sync · answer · tool routing · creds · cross-file sync · **outbound chokepoint** · verification · **surgical changes** · **no destructive ops** · **fail closed** · plain english) |
| `GEMINI.md` | Decimal subrules (2.5 / 2.5.1 / 2.6 / 4.5 / 4.6 / 4.7 …) and different headings |
| `ANTIGRAVITY.md` | Another scheme (3 / 3.1 / 3.5 / 5 / 5.1 / 5.2 / 5.3 / 5.5) |
| `OPENCODE.md` | No `RULE N:` section headers; uses prose paragraphs |

Three reasons the drift happened and is partially legitimate:

1. **Runtime-specific safety advice belongs in each file.** Gemini's "default read-only on `brain/SOUL.md`" rule is meaningless in CLAUDE.md because Claude isn't a Gemini-family model. Antigravity's IDE-cursor-positioning rules are irrelevant to Claude Code.
2. **The runtimes were added across many months.** Each addition (OPENCODE 2026-05-03, ANTIGRAVITY before that, GEMINI earlier) carried over the rule set THEN current, and no one circled back to harmonize when later rules were added to CLAUDE.md.
3. **Hard harmonization would be 2-3 hours of risky edits.** Forcing all five files to identical rule numbering means re-renumbering 50+ rule citations across the empire's skills + brain files. High blast radius.

## Decision

Three rule classes, explicit in this ADR:

### Class A — **MUST match exactly across all 5 files** (identity + safety invariants)

These are non-negotiable. If they drift, an AI runtime can violate the operator's expectations. Editing one requires editing the other 4 in the same commit:

- **Identity** (the "You are <Agent>" assertion + runtime-as-plumbing framing) — codified in [ADR-0003](0003-agent-first-identity-pattern.md). 2026-05-23 sweep confirmed parity.
- **Continuous state sync** (the `python scripts/state_sync.py --note "..."` discipline + staleness gate)
- **Credentials & security** (`.env.agents` is not LLM-readable; secret_guard hook enforces)
- **No destructive operations without confirmation** (the `git push --force`, `rm -rf`, `DROP TABLE` policy)
- **Cross-file sync awareness** (the meta-rule that points BACK to this ADR + lists what must match)

Editing any Class A rule in CLAUDE.md MUST be followed by editing the other 4 files in the SAME commit. The state_sync hook flags single-file edits to Class A rules as a warning in `state/state_guard.log`.

### Class B — **SHOULD match in spirit, allowed to drift in wording** (operational guidance)

- Tool routing preferences (CLI-first, MCP-secondary)
- Verification (run tests, check Supabase, use `git status`)
- Codex delegation pattern
- Self-improvement / continuous learning
- Answer-first principle

Each runtime's flavor of these rules can phrase the same idea slightly differently. The principle stays the same. No SAME-commit obligation; periodic harmonization passes (quarterly) reconcile drift.

### Class C — **Runtime-specific, MAY differ entirely** (per-runtime safety + UX)

- Gemini's read-only-on-unproven-models advisory (lives in GEMINI.md only)
- Antigravity's IDE-cursor + native-Hook behavior
- OpenCode's terminal-aware ergonomics
- CLI-specific argument quirks

These are EXPECTED to live in only one file. Cross-referencing the others is wrong — would create false equivalences.

## Consequences

**Positive:**
- Lockstep promise becomes honest: we ARE in lockstep on Class A (identity, security, destructive-ops) — the parts that matter.
- Future edits to operational rules don't require a 5-file dance.
- Class A invariants are tightly defined → easier to audit drift.

**Negative:**
- The audit found Class A is ALREADY in mostly-good shape (identity sweep happened 2026-05-23), but Class B/C drift is real and won't be auto-fixed by this ADR.
- Operators reading multiple files might be confused when rule numbers don't match. Mitigated by removing rule numbers from cross-references (cite by section name instead).

**Rejected alternatives:**

1. **Force-harmonize all 5 files.** Rejected: 2-3 hours of edits, risk of breaking runtime-specific behavior, no clear payoff once Class A is sound.
2. **Drop the lockstep claim entirely.** Rejected: Class A genuinely IS in lockstep and that's load-bearing for security + identity. Throwing out the claim because some of it drifted is overcorrection.

## Action items (small, optional)

- [ ] Update `CLAUDE.md` Rule 4's wording to reference this ADR and Class A/B/C taxonomy instead of "edit all 5 in lockstep."
- [ ] Mirror the wording update in `AGENTS.md`, `GEMINI.md`, `ANTIGRAVITY.md`, `OPENCODE.md` so each file points to the same policy.
- [ ] One follow-up audit pass: confirm every Class A rule is actually present + worded compatibly in all 5 files. Run via `scripts/audit_entry_file_class_a.py` (to be written).

These are nice-to-have, not load-bearing. The ADR itself is the policy artifact.

## Obsidian Links
- [[docs/adr/INDEX]]
- [[CONTEXT]]
