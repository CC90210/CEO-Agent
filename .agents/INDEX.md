---
tags: [agents, hub, index]
---

# .agents/ — Workflow + Plan Hub

> Top-level index for `.agents/`. Links workflows (slash-command triggers) and plans (one-shot implementation specs) so the Obsidian graph treats them as part of the connected knowledge graph instead of orphans.
>
> Parent: [[brain/INDEX]] · Sibling hubs: [[.claude/INDEX]] · [[.gemini/INDEX]]

## Workflows
- [[.agents/workflows/INDEX]] — full registry (40+ slash-command-triggered workflows)

## Plans (active implementation specs)
- [[.agents/plans/INDEX]] — active plan registry; completed plans stay behind the archive boundary

## Why this directory is dot-prefixed
`.agents/` is a tool-config dir read by Claude Code, Anti-Gravity IDE, and the Gemini CLI to discover slash commands. Files inside aren't user-facing prose — they're machine-loaded prompt templates. Kept in the graph for completeness so a future-CC searching for "where did the `/ship` workflow live" can find it via PageRank from this hub.
