---
adr: 11
title: "Typed memory taxonomy with declared update semantics"
status: accepted
date: 2026-07-18
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0011 — Typed memory taxonomy with declared update semantics

## Context

The volcengine/OpenViking audit (2026-07-18, plan `~/.claude/plans/i-m-dropping-you-a-elegant-truffle.md`) surfaced that our memory substrate's update semantics were **ad-hoc and undocumented**: bravo_sleep appends, auto_dream prunes, memory_aging archives — but nothing declared which files may be merged, which are append-only, and which are immutable records. OpenViking bakes this into an 8-category schema (AGPLv3 — patterns-only per the twentyhq precedent). The same audit confirmed: no per-run audit artifact for memory mutations, no dedup beyond a blind 7-day topic-hash cooldown, no abstraction layer in the retriever (`description:` on ~9.5% of brain files), and retrieval ranking that ignored the freshness decay `memory_aging.py` already computes.

## Decision

**1. Every memory surface declares its update semantics** (the taxonomy, adapted to our files — not OpenViking's 8 labels verbatim):

| Surface | Semantics | Writers |
|---|---|---|
| `memory/MISTAKES.md` | **append-only** (dated entries; never rewritten) | bravo_sleep, operator |
| `memory/PATTERNS.md` | **mergeable** — entries promote `[P]`→`[V]`, decay out after 180d | bravo_sleep, auto_dream (promotion), operator |
| `memory/DECISIONS.md` | **immutable record** — superseded by new entries, never edited | bravo_sleep, operator |
| `memory/ACTIVE_TASKS.md` | **mutable-current** — always rewritten to now-truth; 7-day staleness gate | operator turns |
| `memory/SESSION_LOG.md` | **immutable-generated** — state_sync only; state_guard enforces | state_sync |
| `brain/USER.md` / profile | **mergeable** — freshest fact wins (the 2026-07-18 Ontario→Quebec staleness in Atlas's copy is the cautionary case) | operator turns |
| `brain/TOOL_SHED.md`, `knowledge/` | **curated-mergeable** — hand-edited, per-entry status/confidence | operator turns |

**2. Sleep consolidation runs a dedup state machine** (OpenViking's candidate-level decisions, ours): cooldown check → lexical near-dup probe via `memory_retriever` → batched judge verdict `create | skip` for candidates with evidence. **`merge` is deliberately NOT adopted** — the markdown layer is append-only by design (rule 1); PATTERNS promotion is the merge analog and stays in auto_dream.

**3. Every sleep run writes an audit artifact** — `state/memory_diff/<stamp>.json` with every proposal's decision + duplicate evidence, **even when empty** (an absent artifact is indistinguishable from a crashed run).

**4. The retriever carries an L1 abstract layer**: each file's `description:` frontmatter is indexed as an FTS5/LanceDB `abstract` column (migration 003); `scripts/core/abstract_backfill.py` LLM-backfills missing descriptions via the local CLI. Freshness now reaches ranking: hybrid-mode scores are multiplied by a file-age factor (floor 0.7, opt-out `EMPIRE_FRESHNESS_RANK=0`).

**5. Anti-pollution guard**: session-log lines carrying injected-context markers (`<system-reminder`, `## Relevant Memory`, …) are excluded from sleep-consolidation input — injected retrieval context must never be re-captured as activity (the self-referential loop OpenViking's plugin authors had to fix; our PreCompact hook already covers the pre-mutation commit case).

**6. Tier vocabulary clarification** (recorded, not renamed): `context_manager.py` T1/T2/T3 = *file-load tiers*; `user_prompt_submit.py` T1/T2/T3 = *retrieval-triage tiers*. Two different systems sharing a name — documented apart; OpenViking's L0/L1/L2 maps onto neither (L1 = the abstract column above).

**7. mem0 verdict**: dormant (opt-in `--mem0` flag, no cron passes it, depends on the dead metered API key, redundant with LanceDB). Stays gated-off as-is; retirement is CC's call. **No new vector stores** — LanceDB is the one active semantic index.

**8. Noted for future** (not wired): OpenViking's AST-skeleton-instead-of-LLM-summary trick for code files — apply to knowledge/ compilation if code-heavy pages ever land. Test-intent taxonomy (code-correctness vs data-quality vs behavior) is an authoring convention for `scripts/tests/`, not a reorganization.

## Consequences

**Positive:** memory mutations are auditable + reversible; repeated-lesson noise drops (retrieval-checked dedup beats blind cooldown); abstract-bearing files are findable by what they ARE, not just their prose; stale memories stop outranking fresh ones.
**Negative:** one extra haiku call per sleep run when near-dups exist; migration 003 forced a one-time full re-embed (~3.4k chunks); `state/memory_diff/` accumulates (bounded: one small JSON/night; tmp-hygiene cron can prune >90d).
**Neutral:** knowledge/ stays out of retrieval scope (no-RAG boundary, ADR-0002 adjacent); the Supabase episodic/semantic/procedural tiering (007_tiered_memory.sql) remains disconnected — superseding it is a separate decision.

## Enforcement

- `state/memory_diff/` presence per nightly run — a missing artifact after a scheduled run = investigate.
- `python scripts/core/memory_retriever.py query "<term from a backfilled description>"` — abstract matches rank.
- Review-time: new memory files declare their row in the table above (this ADR is the registry).

## References

- Pattern source: <https://github.com/volcengine/OpenViking> (AGPLv3 — patterns only, zero code) · docs/en/concepts/02+06+08
- Related: [ADR-0001](0001-skill-dependency-classification.md) · [ADR-0002](0002-context-md-canonical-vocabulary.md) · [ADR-0010](0010-external-resource-catalog.md)
- Code: `scripts/bravo_sleep.py` (state machine + audit) · `scripts/core/memory_retriever.py` (`_extract_description`, `_freshness_factor`, migration 003) · `scripts/core/abstract_backfill.py`
