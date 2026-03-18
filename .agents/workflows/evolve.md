---
description: Extract patterns from recent sessions and promote them to skills, SOPs, or CLAUDE.md rules
---
// turbo-all

## Trigger
`/evolve` — Run after significant work sessions or weekly as part of /retro

## Purpose
Automatically extract behavioral patterns from session data and promote them through the maturity pipeline: observation → pattern → skill/SOP/rule.

## Steps

### 1. Gather Raw Material
Read these files for pattern signals:
- `memory/SESSION_LOG.md` — last 7 days of activity
- `memory/MISTAKES.md` — recent error entries
- `memory/PATTERNS.md` — existing patterns (check for PROBATIONARY ones ready to promote)
- `memory/SELF_REFLECTIONS.md` — failure analyses
- `memory/SOP_LIBRARY.md` — SOPs with execution counts

### 2. Identify Candidates
Look for:
- **Repeated success patterns** (same approach used 3+ times with good results) → candidate for VALIDATED promotion or new SOP
- **Repeated failure patterns** (same mistake 2+ times) → candidate for CLAUDE.md rule or hook
- **PROBATIONARY patterns** with 3+ successful sessions → ready for VALIDATED promotion
- **Implicit skills** (multi-step workflows CC requests repeatedly but no skill exists) → candidate for new skill
- **Stale patterns** (not used in 30+ days, low activation score) → candidate for archival

### 3. Classify and Act

For each candidate:

**If repeated success → Promote pattern:**
- Move from [PROBATIONARY] to [VALIDATED] in PATTERNS.md
- If it's a multi-step workflow, create a new SOP in SOP_LIBRARY.md
- If it's a reusable capability, create a new skill in skills/

**If repeated failure → Create prevention:**
- Draft a rule for CLAUDE.md (1-2 sentences, includes "why")
- Consider if a hook could enforce it automatically
- Add to MISTAKES.md if not already there

**If implicit skill → Generate skill:**
- Use the meta-agent pattern to create a new skill file
- Tag as [PROBATIONARY]
- Register in CLAUDE.md skills section

**If stale → Archive:**
- Move to memory/ARCHIVES/ with date stamp
- Remove from active memory files
- Update any cross-references

### 4. Report
Output a summary:
```
## Evolution Report — [DATE]
**Patterns promoted:** X ([PROBATIONARY] → [VALIDATED])
**New rules added:** X (to CLAUDE.md)
**New skills created:** X
**Stale items archived:** X
**No action needed:** X (most common — this is correct)
```

### 5. Apply Five-Gate Filter
Before writing ANYTHING, run each candidate through the Five Gates:
1. VALUE — Will this change future behavior?
2. ALIGNMENT — Does it fit existing categories?
3. REDUNDANCY — Does something already capture this?
4. FRESHNESS — Is it time-sensitive?
5. PLACEMENT — Which tier/file does it belong in?

Most candidates will be filtered out. This is correct. Only high-signal patterns survive.
