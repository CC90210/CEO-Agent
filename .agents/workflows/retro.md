---
description: Weekly retrospective — analyze commits, scores, patterns, and improvement actions
---

## V6.0 retrieval-first

The legacy retro pulled `MISTAKES.md`, `SELF_REFLECTIONS.md`, `SESSION_LOG.md` whole — ~50KB of markdown injected into context just to compute a few numbers. The DB already has the canonical record of every session_log + transaction, and FTS5 surfaces the relevant pattern chunks in milliseconds.

**One-shot data pull (replaces 4 whole-file reads):**

```bash
# Live operational state — last tick, transaction count, open tasks per bucket
python scripts/state/state_manager.py status

# Last week of session activity (chunk-level, not whole-file)
python scripts/core/memory_retriever.py query "<this-week's-theme>" --kind memory --limit 12

# Mistakes that recurred (the ones worth a CLAUDE.md rule)
python scripts/core/memory_retriever.py query "recurring mistake root cause" --kind memory --limit 8

# Skills that ticked frequently in session_log (high-activation = healthy)
python scripts/core/memory_retriever.py query "<core skill keyword>" --kind skill --limit 6
```

Use whole-file `Read` only when a snippet's heading suggests context outside the chunk window matters.

## Steps

1. Load `skills/retro/SKILL.md` for the full retrospective protocol.

2. **Data Collection** (Phase 1):
   - Git activity across all app repos (last 7 days): `git log --since='7 days ago' --oneline`
   - Files changed in Business-Empire-Agent: `git diff --stat origin/main...HEAD`
   - V6.0 DB stats: `python scripts/state/state_manager.py status` → session_log_count, transaction_count, agents[], open_tasks_by_bucket
   - Targeted memory pulls via `memory_retriever query` (see V6.0 block above) — NOT whole-file reads

3. **Metric Calculation** (Phase 2):
   - Commits, files changed, features shipped, bugs fixed
   - Skills added/updated (count `state_transaction` rows where `op='upsert_task'` or grep skills/ git diff)
   - Mistakes logged (count `memory_retriever query` hits in MISTAKES.md filtered to last 7 days)
   - Task completion rate (`active_task` rows closed in window / opened in window — both available from `state_manager.py task list`)

4. **Scoring** (Phase 3 — 0-10 scale):
   - Shipping Velocity, Code Quality, Memory Health, Agent Coordination
   - **Memory Health subscores from V6.0 telemetry:**
     - DB drift count (`state/v6_drift.log` lines, ideally zero)
     - Hook block events (`state/exec_guard.log` blocked-count — high = LLM is fighting the rails)
     - FTS5 staleness (`memory_retriever.py status` `last_indexed` vs now)

5. **Improvement Actions** (Phase 4):
   - For every dimension scored below 7, generate 2 specific actions
   - Prefer actions that get logged to the DB so the next retro sees them in `state_transaction`

6. **Trend Analysis** (Phase 5):
   - Compare against previous retros via FTS5 query: `memory_retriever query "Weekly Retro Report" --kind memory --limit 5`
   - Identify recurring patterns (same dimension scoring <7 two retros in a row → escalate)

7. **Memory Update** (Phase 6):
   - New patterns → PATTERNS.md (PostToolUse hook reindexes automatically)
   - Recurring mistakes → MISTAKES.md
   - **Single retro audit entry to the DB:**
     ```bash
     python scripts/state/state_manager.py log --agent bravo \
       --note "Weekly retro YYYY-MM-DD: shipping=N/10, quality=N/10, memory=N/10, coord=N/10" \
       --artifacts "memory/PATTERNS.md,memory/MISTAKES.md"
     ```
     Single row, fully searchable, replaces the old "append to SESSION_LOG.md" step.

8. **Insights Pipeline**:
   - Extract session patterns → promote to skills, SOPs, or CLAUDE.md rules
   - Run `/evolve` for the deeper promotion pass (it shares this retrieval pattern)

9. Output the Weekly Retro Report.

## Why retrieval-first matters here
Retros that pull entire memory files burn ~50K tokens before the analysis even starts. With FTS5, the same retro pulls 4 chunks × ~300 tokens = ~1.2K tokens. That's a 40× context reduction with no loss of signal — every chunk carries its file:line ref so the analyst can drill into the full file ONLY for the specific entry that warrants it.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]] | [[.agents/workflows/evolve]] | [[skills/retro/SKILL]]
