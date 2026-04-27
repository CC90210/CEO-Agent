---
tags: [gemini, hub, agent-routing]
---

# Gemini CLI — Bravo Mirror

> Gemini CLI uses this directory for its rules + workflows. Mirrors `.agents/workflows/` for the Claude side. Both surfaces share the same brain at `[[brain/STATE]]` and `[[brain/SOUL]]`.

## Rules
- [[.gemini/rules/CLAUDE]] — shared rule sheet readable by both Claude and Gemini

## Workflows
- [[.gemini/workflows/cli-anything]] — turn any CLI into an agent-native wrapper
- [[.gemini/workflows/client-onboard]] — full client onboarding sequence
- [[.gemini/workflows/commit]] — smart conventional commit
- [[.gemini/workflows/content]] — content pipeline trigger
- [[.gemini/workflows/debug]] — systematic-debugging routing
- [[.gemini/workflows/health]] — health / self-audit
- [[.gemini/workflows/n8n]] — n8n workflow build/audit
- [[.gemini/workflows/post]] — full post pipeline (record -> render -> caption -> distribute)
- [[.gemini/workflows/prime]] — full context load
- [[.gemini/workflows/research]] — multi-source research
- [[.gemini/workflows/status]] — current operational state read
- [[.gemini/workflows/sync]] — state-sync + memory write

## Obsidian Links
- [[GEMINI]] | [[CLAUDE]] | [[brain/QUICK_REFERENCE]] | [[brain/CAPABILITIES]] | [[brain/AGENTS]]
