---
name: codex-delegation
description: Intelligent routing between Bravo and Codex — decides when to delegate tasks to Codex vs handle internally
tags: [skill]
---

# Codex Delegation — Intelligent Dual-AI Routing

> **Purpose:** Bravo and Codex are complementary AI engines. This skill determines WHEN and HOW
> to delegate work to Codex for maximum leverage — two AIs working in parallel, each on their strengths.

## The Dual-AI Architecture

```
CC → Bravo (Claude Opus 4.6)           CC → Codex (GPT-5.4)
├── Architecture & planning             ├── Backend implementation
├── Frontend & UI                       ├── Deep debugging
├── Creative & brand voice              ├── Adversarial code review
├── Business ops & strategy             ├── Parallel task execution
├── Orchestration & memory              ├── Root-cause analysis
└── Client communications               └── Write-capable rescue tasks
```

## Delegation Decision Matrix

### Auto-Delegate to Codex (No CC approval needed)

| Task Type | Codex Command | Why Codex |
|-----------|---------------|-----------|
| Pre-ship code review | `/codex:review --background` | Second pair of AI eyes catches Bravo's blind spots |
| Architecture challenge | `/codex:adversarial-review` | Questions assumptions Bravo might accept |
| Backend bug with stack trace | `/codex:rescue investigate [bug]` | Codex excels at systematic root-cause |
| Heavy backend implementation | `/codex:rescue --background [task]` | Runs parallel while Bravo does other work |
| Test suite debugging | `/codex:rescue fix the failing tests` | Codex is strong at test diagnosis |

### Keep in Bravo (Never delegate)

| Task Type | Why Bravo |
|-----------|-----------|
| Frontend/UI components | Bravo has better design sense and CC's brand voice |
| Content creation (posts, copy) | Bravo owns CC's authentic voice |
| Business strategy & client comms | Bravo has full business context |
| Memory/state/orchestration | Bravo's infrastructure — Codex has no access |
| Skool/social media automation | Bravo has the MCP and CLI integrations |
| Cross-file sync (brain/, memory/) | Bravo's domain knowledge required |
| Simple fixes (< 3 files) | Delegation overhead > task effort |

### Ask CC (Judgment call)

| Task Type | Why Ask |
|-----------|---------|
| Full feature implementation | Split work or assign to one AI? |
| Refactoring > 10 files | Coordination risk between two AIs |
| Security-sensitive changes | Need explicit human review |

## Parallel Execution Patterns

### Pattern 1: Review While Building
```
Bravo: Implements feature in frontend
Codex: /codex:review --background (reviews existing changes)
Result: By the time Bravo ships, Codex review is ready
```

### Pattern 2: Dual Investigation
```
Bravo: Debugs frontend rendering issue
Codex: /codex:rescue --background investigate the API timeout
Result: Two bugs investigated simultaneously
```

### Pattern 3: Implement + Adversarial Check
```
Bravo: Writes the implementation
Codex: /codex:adversarial-review --background challenge the caching design
Result: Design validated before ship
```

### Pattern 4: Bravo Orchestrates, Codex Implements
```
Bravo: Creates SPARC spec + architecture (Phases 1-3)
Codex: /codex:rescue implement the backend per the spec in .agents/plans/
Bravo: Reviews Codex output, handles frontend + docs
Result: Full-stack feature with parallel execution
```

## Integration with Task Routing

When the task routing skill (`skills/task-routing/SKILL.md`) classifies a task:

| Complexity | Codex Role |
|-----------|------------|
| TRIVIAL | None — Bravo handles inline |
| SIMPLE | None — single agent sufficient |
| MODERATE | Optional: `/codex:review` after Bravo implements |
| COMPLEX | Recommended: Codex handles backend, Bravo handles frontend/orchestration |
| ARCHITECTURAL | Required: `/codex:adversarial-review` on the architecture before implementation |

## Integration with Ship Pipeline

Add to `skills/ship/SKILL.md` Phase 4 (Code Review):

After Bravo's code review, optionally run:
```
/codex:adversarial-review --background --base main
```

This gives a dual-AI review before shipping — Bravo catches implementation issues, Codex challenges design decisions.

## Commands Quick Reference

```bash
# Standard review (second opinion)
/codex:review --background

# Challenge the design
/codex:adversarial-review --background challenge the auth design

# Delegate a task
/codex:rescue --background investigate why the API returns 500

# Quick fix with specific model
/codex:rescue --model spark fix the TypeScript error in api/route.ts

# Check progress
/codex:status

# Get results
/codex:result

# Cancel
/codex:cancel
```

## Anti-Patterns (Never Do These)

1. **Don't delegate AND do the same work.** If Codex is investigating a bug, Bravo works on something else.
2. **Don't delegate memory/state tasks.** Codex has no access to brain/, memory/, or Supabase.
3. **Don't delegate content creation.** Codex doesn't have CC's brand voice context.
4. **Don't run Codex on trivial tasks.** The startup overhead makes it slower than Bravo for small fixes.
5. **Don't ignore Codex results.** Always present Codex output verbatim to CC.

## Obsidian Links
- [[agents/codex-agent]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]]
- [[skills/task-routing/SKILL]] | [[skills/ship/SKILL]] | [[skills/code-review/SKILL]]
