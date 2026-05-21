---
adr: 0002
title: CONTEXT.md as canonical empire vocabulary
status: accepted
date: 2026-05-16
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0002 — CONTEXT.md as canonical empire vocabulary

## Context

Multiple sessions have observed agents re-deriving the meaning of recurring terms ("interaction", "drip sequence", "OASIS Outbound", "Pulse", "tenant-scoped feature") from scratch every session. Token cost is small per occurrence but compounds — and more critically, agents drift toward subtly different definitions in different sessions, which then leak into commits and skills.

Pattern adapted from [mattpocock/skills CONTEXT.md](https://github.com/mattpocock/skills/blob/main/CONTEXT.md): a single project-root glossary that every skill and entry point references. Terms in the glossary are mandatory vocabulary; deviations are bugs.

We have `brain/SOUL.md` (identity / values), `brain/USER.md` (CC profile), and `memory/PERSONAS.md` (target audience archetypes) — but no general empire glossary. The closest analog is scattered definitions inside `brain/CAPABILITIES.md` and `brain/AGENT_ROUTER.md`, which mix vocabulary with operational instructions.

## Decision

Create `/CONTEXT.md` at repo root as the canonical empire glossary. Scope:

1. **People & agents** (CC, Bravo, Maven, Atlas, Hermes, Aura, Codex)
2. **Brands** (OASIS AI Solutions, PropFlow, Nostalgic Requests)
3. **Multi-tenancy** (Tenant, Tenant manifest, Tenant-scoped feature, Empire DB)
4. **Sales / CRM** (Lead, Interaction, Pipeline, Drip sequence, Outreach Send, OASIS Outbound, Lead score, Pulse)
5. **State / substrate** (State DB, Empire State, Event bus, Override, Bridge lock)
6. **V6 architecture** (V6 mode, Pantry/Prep/Plate, Guards, Capability graph, Memory retriever)
7. **Skill / agent vocabulary** (Skill, tiers, status lifecycle, hard/soft dependencies, disable_model_invocation, argument_hint)
8. **Browser / scraping** (Research fetch, Browser ladder, CloakBrowser)
9. **North Star** ($5K Net MRR by June 18, 2026 — extended 2026-05-18 from May 30)

Entries are **≤2 lines each**. CONTEXT.md is a glossary, not a manual. Operational detail belongs in the skill / brain / memory file linked from the entry.

### Sibling entry points must reference CONTEXT.md

All five runtime entry points ([CLAUDE.md](../../CLAUDE.md), [GEMINI.md](../../GEMINI.md), [ANTIGRAVITY.md](../../ANTIGRAVITY.md), [AGENTS.md](../../AGENTS.md), [OPENCODE.md](../../OPENCODE.md)) reference CONTEXT.md as a lazy-load on the first operational turn (per the Triage matrix in CLAUDE.md). The reference is a bare string, not an `@`-import (per CLAUDE.md "HARD RULE — no @-imports").

### Skill-local glossaries

A skill that introduces ≥5 unique terms beyond CONTEXT.md gets its own `skills/<name>/LANGUAGE.md`. The skill body references it; CONTEXT.md does not absorb it. This keeps CONTEXT.md empire-wide and prevents skill-jargon bloat.

### Update protocol

- New term enters codebase → add CONTEXT.md entry in same PR.
- Term meaning shifts → edit CONTEXT.md; do NOT shadow with new term.
- Term retired → delete the entry; the absence proves no skill depends on it.
- CONTEXT.md `last_updated:` frontmatter date stays current.

## Consequences

**Positive:**
- Eliminates re-derivation cost per session.
- Forces a single canonical definition for terms that span tenants / brands / runtimes.
- Onboarding cost for sibling agents (Maven, Atlas, Hermes) drops — they reference CONTEXT.md instead of re-explaining empire vocabulary in their own CLAUDE.md.
- Memory retriever indexes CONTEXT.md alongside the rest of `memory/` and `brain/`, so cold sessions can pull glossary snippets via `python scripts/core/memory_retriever.py query "what is OASIS Outbound"`.

**Negative:**
- One more file to keep current. Mitigated by `last_updated:` field surfacing staleness in the SessionStart hook.
- Risk of CONTEXT.md becoming a dumping ground. Mitigated by the ≤2-lines-per-entry rule and the skill-local LANGUAGE.md escape hatch.

**Neutral:**
- Sibling agents (Maven, Atlas, Hermes) maintain their own CONTEXT.md files in their own repos. Cross-empire vocabulary (Bravo, CC, North Star) is duplicated by convention — the structural update rule (CLAUDE.md propagation) keeps them in sync.

## Enforcement

- This ADR creates `CONTEXT.md`. Future sessions reference it; new terms go there first.
- `skills/skill-creator/SKILL.md` is updated to require new skills consult CONTEXT.md before introducing domain terms.
- The Triage matrix in CLAUDE.md (and siblings) loads CONTEXT.md on the first operational turn that requires domain interpretation.

## References

- Source pattern: https://github.com/mattpocock/skills/blob/main/CONTEXT.md
- Related: [ADR-0001 — Skill dependency classification](0001-skill-dependency-classification.md)
- Memory retriever: [scripts/core/memory_retriever.py](../../scripts/core/memory_retriever.py)
