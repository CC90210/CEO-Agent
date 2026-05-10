---
name: memory-management
description: MemoryBox system for preventing bloat, scoring confidence, compressing archives, and maintaining memory hygiene. Plus the V6 hybrid retrieval surface (FTS5 lexical + LanceDB/ONNX semantic + RRF) that replaces whole-file Reads. Ensures cross-session intelligence without context window overflow.
triggers: [memory, bloat, archive, compress, session log, confidence, MemoryBox, retrieval, hybrid search, semantic, embedding, RRF, fastembed, LanceDB]
tier: core
dependencies: []
---

# Memory Management (MemoryBox)

## Overview

Memory is Bravo's most critical asset. Without active management, memory files grow until they bloat the context window, cause hallucinations, or crash sessions. MemoryBox prevents this — and V6 BUILD 2 ships a hybrid retrieval surface (`scripts/memory_retriever.py`) that lets the agent pull the EXACT chunk it needs without loading the whole tier.

## V6 Hybrid Retrieval (the default path for "recall something")

**Do NOT `Read memory/MISTAKES.md` to find a past lesson.** Run:

```bash
python scripts/memory_retriever.py query "price objections" --explain
```

This returns ≤5 ranked snippets with file:line refs in under 10ms. Each snippet carries the H2/H3 heading so the surrounding context is preserved. Only escalate to whole-file `Read` if the snippet's heading suggests context outside the chunk window matters.

### How it works (in one paragraph)

Two indexes are built and kept in sync: an FTS5 BM25 lexical index (`state/memory_index.db`) and a LanceDB vector store (`state/memory_lance/`) with L2-normalized 384-dim embeddings from `fastembed`'s ONNX MiniLM-L6-v2 model. Every query runs both legs independently, then merges by Reciprocal Rank Fusion (RRF) with `k=60`: a chunk's score is the sum of `1/(60+rank)` across each ranking it appears in. The top-K by RRF wins. The lexical leg catches the keyword case; the semantic leg catches the conceptual case ("price objections" finds "cost resistance"). Hybrid catches both.

### CLI reference

```bash
# Default — hybrid retrieval
python scripts/memory_retriever.py query "..."

# Mode flags (mutually exclusive)
python scripts/memory_retriever.py query "..." --lexical-only    # FTS5 only (V6 BUILD 1 behavior)
python scripts/memory_retriever.py query "..." --semantic-only   # LanceDB cosine only

# Result introspection
python scripts/memory_retriever.py query "..." --explain         # show lex_rank, sem_rank, rrf_score
python scripts/memory_retriever.py query "..." --kind {skill,memory,brain,entry}
python scripts/memory_retriever.py query "..." --json --limit 10

# Index management
python scripts/memory_retriever.py build [--force] [--lexical-only]
python scripts/memory_retriever.py update                        # incremental (hash-skipped)
python scripts/memory_retriever.py status                        # both legs' health
```

### When to pick which mode

| Mode | When |
|------|------|
| **hybrid** (default) | Always, unless you have a specific reason not to. RRF catches both keyword and concept. |
| **lexical-only** | Searching for an exact identifier (`SUPABASE_SERVICE_ROLE_KEY`, `req-7fed684e`, `BUILD 4-G`). Tokens, not concepts. |
| **semantic-only** | Exploring a fuzzy topic where you know the concept but not the vocabulary the corpus uses. Rare — hybrid does this better. |
| **--explain** | Debugging "why did this rank where it did?" Surfaces lex_rank + sem_rank + rrf_score per hit. |

### Operational rules

- **The PostToolUse hook keeps the index warm.** Every Edit/Write inside `memory/`, `skills/`, `brain/`, or the five entry-point markdown files fires `memory_retriever.py update` in the background. Update is incremental (source-hash gated) so no-op edits cost nothing.
- **Full rebuild after a corpus drift** (file deletions, mass renames, scope changes): `python scripts/memory_retriever.py build --force`. Takes ~60 seconds end-to-end for the current corpus (226 sources / 2,857 chunks / 2,857 embeddings).
- **The semantic leg is OPTIONAL on a fresh checkout.** If `fastembed`/`lancedb` aren't installed, build runs FTS5-only and query degrades to `--lexical-only` automatically. No code change required to add semantic later.
- **Token output cap remains 1500 tokens per query** — the hybrid upgrade adds recall, not output volume.

## Five-Gate Knowledge Filter

Every memory write must pass through all five gates before being stored. Run these in order. Stop at the first gate that fails.

**Gate 1: VALUE** — Does this information change how the agent acts? If not, discard.
**Gate 2: ALIGNMENT** — Does this fit an existing memory category? If not, is it worth creating one?
**Gate 3: REDUNDANCY** — Does a memory already capture this? If yes, update existing instead of creating new.
**Gate 4: FRESHNESS** — Is this time-sensitive? If yes, set a decay trigger. If timeless, mark as stable.
**Gate 5: PLACEMENT** — Which tier does this belong in? (Tier 1-5). Place it correctly.

The most common outcome of running the Five Gates is: **DO NOTHING.**
Most observations are not worth persisting. Only write when the information will change future behavior.

---

## Memory Architecture

### Tier 1: Brain (Always Loaded)
**Files:** `brain/SOUL.md`, `brain/USER.md`, `brain/STATE.md`
**Budget:** <2500 lines combined (V5.5: 17 agents, 180 skills, CEO OS — structural files scale with system)
**Rule:** Loaded at every session start. Must be concise but complete.

### Tier 2: Active Memory (Loaded on Demand)
**Files:** `memory/ACTIVE_TASKS.md`, `memory/LONG_TERM.md`, `memory/SOP_LIBRARY.md`
**Budget:** <300 lines each
**Rule:** Read during Brain Loop Step 2 (RECALL). Only when relevant.

### Tier 3: Reference Memory (Loaded When Needed)
**Files:** `memory/PATTERNS.md`, `memory/MISTAKES.md`, `memory/DECISIONS.md`
**Budget:** <200 lines each
**Rule:** Read when debugging, planning, or reviewing. Not every session.

### Tier 4: Log Memory (Write-Mostly)
**Files:** `memory/SESSION_LOG.md`, `memory/SELF_REFLECTIONS.md`, `memory/daily/*.md`
**Budget:** Unlimited (compressed regularly)
**Rule:** Written to frequently, read rarely. Compressed when bloated.

### Tier 5: Archive (Cold Storage)
**Files:** `memory/ARCHIVES/*.md`
**Budget:** Unlimited
**Rule:** Historical data. Only accessed for monthly audits or deep investigations.

## Confidence Scoring

Every memory entry gets a confidence score:

| Score | Meaning | Action |
|-------|---------|--------|
| 0.95-1.0 | Verified fact | Persist in LONG_TERM.md |
| 0.8-0.94 | High confidence | Persist, verify quarterly |
| 0.5-0.79 | Medium confidence | Keep in active memory, verify monthly |
| 0.2-0.49 | Low confidence | Flag for verification, don't rely on |
| 0.0-0.19 | Speculation | Don't store. Use only in session context. |

### Confidence Decay
- Facts not re-verified in 30 days: confidence -= 0.1
- Facts not re-verified in 90 days: confidence -= 0.3
- Facts contradicted by evidence: immediately review
- Facts confirmed by evidence: confidence += 0.05 (cap at 1.0)

## Bloat Prevention Rules

### SESSION_LOG.md
- **Threshold:** 200 lines
- **Action:** Compress entries older than 14 days → `memory/ARCHIVES/sessions-YYYY-MM.md`
- **Keep:** Last 10 session entries in active file

### ACTIVE_TASKS.md
- **Threshold:** 50 items
- **Action:** Completed tasks older than 7 days → remove from file
- **Keep:** All in-progress, blocked, and recent completed items

### MISTAKES.md
- **Threshold:** 30 entries
- **Action:** Deduplicate. Merge similar mistakes. Archive resolved ones.
- **Keep:** Active prevention strategies only

### PATTERNS.md
- **Threshold:** 30 entries
- **Action:** Promote high-confidence patterns to SOPs. Archive low-use patterns.
- **Keep:** Active patterns with recent usage

### daily/ logs
- **Threshold:** 30 days of logs
- **Action:** Compress months older than current → `memory/ARCHIVES/daily-YYYY-MM.md`
- **Keep:** Last 30 days

## Memory Sync Protocol (File ↔ Supabase)

When Supabase is available:

### Session Start
1. Read local memory files
2. Query Supabase for any updates from other agent interfaces
3. Merge: Supabase wins on newer timestamps
4. Update local files with merged data

### Session End
1. Write session data to local files
2. Sync to Supabase `memories`, `session_logs`, `daily_logs` tables
3. Confirm sync success

### Conflict Resolution
- Newer timestamp wins
- Higher confidence score wins (for memory facts)
- If truly ambiguous: flag for CC's review

## Memory Hygiene Checklist (Monthly)

```
[ ] SESSION_LOG.md under 200 lines
[ ] ACTIVE_TASKS.md under 50 items
[ ] MISTAKES.md under 30 entries (no duplicates)
[ ] PATTERNS.md under 30 entries (no duplicates)
[ ] LONG_TERM.md — all facts still valid? Confidence scores current?
[ ] SOP_LIBRARY.md — all SOPs still relevant? Success rates accurate?
[ ] daily/ — older than 30 days archived?
[ ] brain/ files — under 2500 lines combined?
[ ] No orphaned references (links to deleted files)?
[ ] Supabase sync current (if available)?
```

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
