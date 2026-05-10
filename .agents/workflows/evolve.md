---
description: Extract patterns from recent sessions and promote them to skills, SOPs, or CLAUDE.md rules
---
// turbo-all

## Trigger
`/evolve` — Run after significant work sessions or weekly as part of /retro

## Purpose
Automatically extract behavioral patterns from session data and promote them through the maturity pipeline: observation → pattern → skill/SOP/rule.

## V6.0 retrieval-first (replaces flat-file reads)

Whole-file `Read` of `MISTAKES.md`/`PATTERNS.md`/`SESSION_LOG.md` was the old way. Tier-2 loads pulled ~104K tokens for what's usually a 5-snippet question. Use the FTS5 retriever — it returns ranked chunks with file:line refs in <10ms.

```bash
# Last week of session log (used for "what happened recently")
python scripts/state_manager.py status                              # latest tick + last_session_log
python scripts/memory_retriever.py query "recent mistake correction" --kind memory --limit 8

# Existing patterns ready for [PROBATIONARY] → [VALIDATED] promotion
python scripts/memory_retriever.py query "PROBATIONARY pattern"     --kind memory --limit 10

# SOPs with their execution counts
python scripts/memory_retriever.py query "SOP-ID success rate"      --kind memory --limit 5

# Skill-shaped capabilities the operator keeps re-asking for
python scripts/memory_retriever.py query "<recurring task you noticed>" --kind skill --limit 3
```

Only `Read` a full file when a snippet doesn't carry enough context. `MISTAKES.md` is rare — most queries don't need its 27KB body, just three relevant entries.

## Steps

### 1. Gather Raw Material (retrieval-driven)

Run the canonical four queries:

| Query | Purpose | File scope |
|-------|---------|-----------|
| `memory_retriever query "<topic-of-interest> mistake" --kind memory` | Pull root-cause entries that match the focus area | MISTAKES.md (chunk-level) |
| `memory_retriever query "PROBATIONARY" --kind memory` | Find patterns ready for promotion (used 3+ times) | PATTERNS.md |
| `memory_retriever query "<recurring-verb>" --kind skill` | Spot multi-step asks that should become skills | skills/*/SKILL.md |
| `memory_retriever query "stale unused" --kind memory` | Identify archival candidates | All memory files |

For weekly retrospective context, use `state_manager.py status` to get the last 7 days of `session_log` rows directly from the DB. Faster than parsing markdown, and the DB has the canonical agent + tick fields the markdown summary loses.

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
- If it's a reusable capability, create a new skill in skills/ (the PostToolUse `retriever_postedit` hook will reindex automatically)

**If repeated failure → Create prevention:**
- Draft a rule for CLAUDE.md (1-2 sentences, includes "why")
- Consider if a hook could enforce it automatically (extend [scripts/exec_guard.py](scripts/exec_guard.py) blocklist if it's a destructive command class)
- Add to MISTAKES.md if not already there
- Then `python scripts/state_manager.py log --note "Added prevention rule for <pattern>"` so the change is in the audit trail

**If implicit skill → Generate skill:**
- Use the meta-agent pattern to create a new skill file
- Tag as [PROBATIONARY]
- Register in CLAUDE.md skills section
- Run `python scripts/memory_retriever.py update` to absorb the new SKILL.md (or let the PostToolUse hook fire on save)

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
**Logged to state_manager:** Y entries
```

### 5. Apply Five-Gate Filter
Before writing ANYTHING, run each candidate through the Five Gates:
1. VALUE — Will this change future behavior?
2. ALIGNMENT — Does it fit existing categories?
3. REDUNDANCY — Does something already capture this? (Check via `memory_retriever query` first.)
4. FRESHNESS — Is it time-sensitive?
5. PLACEMENT — Which tier/file does it belong in?

Most candidates will be filtered out. This is correct. Only high-signal patterns survive.

### 6. Close the loop
After promoting / archiving / adding rules, write a single audit entry:

```bash
python scripts/state_manager.py log --note "Evolve cycle: promoted N patterns, added M rules, archived K stale entries"
```

This makes the next `/retro` run see the evolution event in the DB without parsing markdown.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]] | [[.agents/workflows/retro]]
