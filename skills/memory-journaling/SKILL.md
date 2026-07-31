---
name: memory-journaling
description: Structured decision and pattern logging. Guides the agent through writing high-quality entries to memory/DECISIONS.md, memory/PATTERNS.md, or memory/MISTAKES.md with proper frontmatter, cross-links, and version tags.
tags: [skill, memory, journaling, decisions, patterns]
triggers: ["log a decision", "journal this", "memory journal", "log this pattern", "record this", "save this learning", "memory-journaling"]
owner: documenter
tier: T1
risk: low
last_updated: 2026-05-21
---

# Memory Journaling — Structured Decision + Pattern Logging

## Overview

Memory drifts when entries are written ad-hoc — bullet here, paragraph there, no cross-links, no `last_updated` field, dates omitted. This skill enforces structure: every journal entry has a category, a date, a body shape per category, wiki-links to related files, and a freshness tag.

**When to invoke:**
- CC says "log this" / "journal that" / "save this learning"
- After a non-obvious decision is made (architectural, business, commitment)
- After a pattern proves itself (used successfully)
- After a mistake (use the "Diagnose why you made a mistake" intent in INTENTS.md, which routes here for the actual write)

**Trigger:** `/journal <category>`, "log a decision", "save this pattern"

## Category Routing

Pick the right file. If unsure, ask CC.

| Category | File | Use for |
|----------|------|---------|
| **Decision** | `memory/DECISIONS.md` | Architectural choices, business commitments, technology bets, scope cuts |
| **Pattern** | `memory/PATTERNS.md` | Validated approaches that worked — repeat-worthy |
| **Mistake** | `memory/MISTAKES.md` | Failure modes — what went wrong, why, prevention |
| **Reflection** | `memory/SELF_REFLECTIONS.md` | Personal/agent introspection, growth observations |
| **Anti-pattern** | `memory/ANTI_PATTERNS.json` | Regex-detectable bad patterns the `anti_pattern_hook` should flag |

## Entry Shapes

### Decision entry

```markdown
## YYYY-MM-DD — <one-line title>

**Context:** What was the situation? Constraints?

**Decision:** What we chose. Be specific — names, paths, numbers.

**Why:** The reasoning. Tradeoffs accepted.

**Alternatives rejected:** What else was on the table + why we passed.

**Related:** [[brain/X]] | [[skills/Y/SKILL.md]] | (commit hash if applicable)
```

### Pattern entry

```markdown
## [P] / [V] — <pattern name>

**Pattern:** One sentence — what the pattern is.

**When:** The trigger condition.

**How:** The step-by-step.

**Why it works:** The mechanism.

**Uses:** N (increment per re-use; promote [P] → [V] at 3)

**First seen:** YYYY-MM-DD | **Last validated:** YYYY-MM-DD

**Related:** [[brain/X]]
```

Probationary `[P]` → validated `[V]` after 3 successful re-uses. Track the count in the body.

### Mistake entry

Use the structure from `brain/INTENTS.md` "Diagnose why you made a mistake":
- **Failure** (1-2 sentences observable)
- **Why it slipped** (root cause)
- **Prevention** (concrete rules, ideally including a system rail)
- **Tag** (semantic tag)

If the prevention is regex-detectable, also add an entry to `memory/ANTI_PATTERNS.json` so `scripts/hooks/anti_pattern_hook.py` flags future occurrences.

## Execution Protocol

1. **Classify.** Decision / Pattern / Mistake / Reflection / Anti-pattern. Ask CC if ambiguous — never guess.
2. **Compose the entry** per the matching shape above. Always include today's date (compute it — never quote from context).
3. **Cross-link.** Every entry MUST link to ≥ 2 related files via `[[wiki-link]]` syntax. The Obsidian graph stays connected.
4. **Append, don't overwrite.** Insert at the TOP of the target file (newest first), below the frontmatter.
5. **Update frontmatter.** Bump `last_updated:` on the target file.
6. **Update MEMORY.md index** if the entry is high-leverage (something future-CC needs without grepping). One-line pointer: `- [Title](file.md) — one-line hook`.
7. **Confirm in chat.** "Logged <category> to memory/<file>.md: '<title>'. <N> wiki-links added."

## Anti-Patterns

- ❌ Quoting today's date from the system reminder instead of computing it. Always compute (`python -c "from datetime import date; print(date.today().isoformat())"`).
- ❌ One-line entries with no Why. Future-CC won't understand the decision context.
- ❌ Zero wiki-links. Disconnected entries decay into orphan trivia.
- ❌ Writing a mistake without a prevention. Identifying failure without fixing it is theatre.
- ❌ Editing an old entry to update facts. Append a new entry that supersedes it; keep the original for the audit trail.

## When NOT to Journal

- Trivial fixes (typo, import order, CSS tweak) — git log is the audit trail
- Anything the code already documents in itself — don't restate WHAT, only the non-obvious WHY
- Conversational context that's only useful in the current session — that's plan/todo territory, not memory

## Integration

- **memory/DECISIONS.md / PATTERNS.md / MISTAKES.md** — the target files
- **memory/MEMORY.md** — the index pointing to high-leverage entries
- **brain/INTENTS.md** — the "Log a decision or pattern" playbook routes here
- **scripts/hooks/anti_pattern_hook.py** + **memory/ANTI_PATTERNS.json** — the regex enforcement layer for anti-patterns

## Obsidian Links
- [[memory/DECISIONS]] | [[memory/PATTERNS]] | [[memory/MISTAKES]] | [[memory/SELF_REFLECTIONS]]
- [[brain/INTENTS]] | [[skills/silver-platter/SKILL.md]] | [[skills/integrations-sync/SKILL.md]]
