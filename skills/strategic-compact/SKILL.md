---
name: strategic-compact
description: Use this skill whenever the user asks about the strategic compact, setting goals, defining business strategy, OKRs, company operating principles, or top-level mission planning.
triggers: [strategic compact, goals, business strategy, OKR, mission planning, operating principles]
tier: specialized
dependencies: []
---

# Strategic Compact Skill

Manage session context by compacting at logical boundaries rather than arbitrary limits.

## When to Activate
- Working on multi-phase tasks (Research -> Plan -> Implement -> Test).
- Switching between unrelated tasks within the same session.
- After completing a major milestone and starting new work.
- When responses slow down or become less coherent (context pressure).

## Compaction Decision Guide

| Phase Transition | Compact? | Why |
|---|---|---|
| Research -> Planning | **Yes** | Research context is bulky; plan is the distilled output. |
| Planning -> Implementation | **Yes** | Plan is in a file; free up context for implementation. |
| Implementation -> Testing | **Maybe** | Keep if tests reference recent code; compact if switching focus. |
| Debugging -> Next feature | **Yes** | Debug traces pollute context for unrelated work. |
| Mid-implementation | **No** | Losing variable names, file paths, and partial state is costly. |
| After a failed approach | **Yes** | Clear the dead-end reasoning before trying a new approach. |

## What Survives Compaction
- Subagent Registry (`brain/AGENTS.md`)
- Task lists (`memory/ACTIVE_TASKS.md`)
- Memory files (`memory/*.md`)
- Git state
- Files on disk

## Best Practices
- **Distill before compacting**: Save important research findings, plans, or architectural decisions to a file before clearing the session history.
- **Use custom summaries**: When compacting, provide a summary of what should be remembered: `/compact Focus on implementing the auth middleware next.`
- **Don't compact mid-implementation**: Preserve context for related changes to avoid hallucinating file names or logic.
- **Clear the "dead-end"**: If an approach fails, compact to remove the confusing "noise" from the session context.

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
