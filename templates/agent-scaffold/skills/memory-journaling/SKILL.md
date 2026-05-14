---
name: memory-journaling
description: Structured decision and pattern logging for {{AGENT_NAME}}. Guides the agent through writing high-quality entries to memory/DECISIONS.md, memory/PATTERNS.md, or memory/MISTAKES.md with proper frontmatter, cross-links, and version tags. V6.7 default skill.
tags: [skill, memory, journaling, decisions, patterns]
triggers: ["log a decision", "journal this", "memory journal", "log this pattern", "record this", "save this learning"]
owner: {{agent_name}}
tier: T1
risk: low
canonical_pattern: ../../../Business-Empire-Agent/skills/memory-journaling/SKILL.md
---

# Memory Journaling — {{AGENT_NAME}} Structured Logging

## Overview

Memory drifts when entries are written ad-hoc — bullet here, paragraph there, no cross-links, no `last_updated` field, dates omitted. This skill enforces structure: every journal entry has a category, a date, a body shape per category, wiki-links to related files, and a freshness tag.

**When to invoke:**
- Operator says "log this" / "journal that" / "save this learning"
- After a non-obvious decision (architectural, business, commitment)
- After a pattern proves itself (validated approach worth repeating)
- After a mistake (see "Diagnose why you made a mistake" intent for the route here)

**Trigger:** `/journal <category>`, "log a decision", "save this pattern"

## Category Routing

| Category | File | Use for |
|----------|------|---------|
| **Decision** | `memory/DECISIONS.md` | Architectural / business / commitment choices |
| **Pattern** | `memory/PATTERNS.md` | Validated approaches worth repeating |
| **Mistake** | `memory/MISTAKES.md` | Failure modes — what went wrong, why, prevention |
| **Reflection** | `memory/SELF_REFLECTIONS.md` (if present) | Agent introspection, growth observations |

## Entry Shapes

### Decision entry

```markdown
## YYYY-MM-DD — <one-line title>

**Context:** Situation. Constraints.

**Decision:** What we chose. Specific.

**Why:** Reasoning. Tradeoffs accepted.

**Alternatives rejected:** What else was on the table + why we passed.

**Related:** [[brain/X]] | [[skills/Y/SKILL]] | (commit hash if applicable)
```

### Pattern entry

```markdown
## [P] / [V] — <pattern name>

**Pattern:** One sentence.
**When:** Trigger condition.
**How:** Step-by-step.
**Why it works:** Mechanism.
**Uses:** N (increment per re-use; [P] → [V] at 3)
**First seen:** YYYY-MM-DD | **Last validated:** YYYY-MM-DD
**Related:** [[brain/X]]
```

### Mistake entry

- **Failure** (1-2 sentences observable)
- **Why it slipped** (root cause)
- **Prevention** (concrete rules, ideally a system rail not just "I will remember")
- **Tag** (semantic tag)

## Execution Protocol

1. **Classify** Decision / Pattern / Mistake / Reflection. Ask if ambiguous.
2. **Compose** per the matching shape. Compute today's date — never quote from context.
3. **Cross-link** ≥ 2 related files via `[[wiki-link]]`. Keep the Obsidian graph connected.
4. **Append at TOP** of target file (newest first), below frontmatter.
5. **Bump `last_updated:`** on the target file.
6. **Update MEMORY index** if high-leverage.
7. **Confirm in chat:** "Logged <category> to memory/<file>.md: '<title>'. <N> wiki-links."

## Anti-Patterns

- ❌ Quoting today's date from system context. Always compute.
- ❌ One-line entries with no Why.
- ❌ Zero wiki-links. Decays into orphan trivia.
- ❌ Mistake without a prevention.
- ❌ Editing an old entry to update facts. Append a superseding entry; preserve original.

## When NOT to Journal

- Trivial fixes (typo, import order)
- Anything the code already self-documents
- Ephemeral session context

## Integration

- **memory/DECISIONS.md / PATTERNS.md / MISTAKES.md** — target files
- **brain/INTENTS.md** — "Log a decision or pattern" playbook routes here

## Obsidian Links
- [[memory/DECISIONS]] | [[memory/PATTERNS]] | [[memory/MISTAKES]]
- [[brain/INTENTS]] | [[skills/silver-platter/SKILL]] | [[skills/integrations-sync/SKILL]]
