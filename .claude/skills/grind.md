---
description: "Go into grind mode — autonomous deep work across the entire Business-Empire-Agent ecosystem. Runs diagnostics, fixes issues, compacts memory, and makes proactive improvements."
---

# Grind Mode — Autonomous Deep Work

CC wants to relax while Bravo handles everything. Run the full pipeline:

## Phase 1: System Health (2 min)
1. Run `python scripts/memory_aging.py health` — get letter grade
2. Run `python scripts/context_manager.py status` — check SESSION_LOG size
3. If SESSION_LOG > 200 lines: `python scripts/context_manager.py compact`
4. Check `memory/ACTIVE_TASKS.md` — flag anything stale (> 7 days without update)
5. Run Codex setup check: `export CLAUDE_PLUGIN_ROOT="/c/Users/User/.claude/codex-plugin" && node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" setup --json 2>/dev/null`

## Phase 2: Fix Everything (5-10 min)
1. Check all Python scripts compile: `python -m py_compile scripts/*.py`
2. Grep for broken [[wiki-links]] — fix any that point to deleted files
3. Grep for stale @references in CLAUDE.md — fix any that point to missing files
4. Check CAPABILITIES.md counts against actual file counts
5. Run `git status` — any untracked files that should be committed?
6. Fix any issues found — use Fix-First methodology (auto-fix mechanical, ask for judgment)

## Phase 3: Proactive Improvements (10-20 min)
Pick 2-3 high-impact improvements from this list:
- Update brain/STATE.md with current operational status
- Clean up PATTERNS.md — promote [PROBATIONARY] patterns with 3+ uses, archive unused
- Clean up MISTAKES.md — deduplicate, merge similar entries
- Run referential integrity scan after any file changes
- Update SESSION_LOG.md with what was done
- If Codex is available: delegate a background adversarial review on recent changes

## Phase 4: Report (1 min)
Output a compact summary:
```
## Grind Report — [DATE]
**Health:** [letter grade] → [new grade]
**Fixed:** [count] issues
**Improved:** [list]
**Committed:** [hash] — [message]
```

## Rules
- Fix-First: auto-fix mechanical issues, ask CC only for judgment calls
- Don't touch .env files or .obsidian/
- Commit everything at the end with `bravo: grind — [summary]`
- Update SESSION_LOG.md with what was done