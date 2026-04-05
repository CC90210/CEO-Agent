---
tags: [agents, index]
---

# Agents — Subagent Registry

> 16 internal agents + 1 external (Codex). Full orchestration matrix in [[brain/AGENTS]].
> [[brain/DASHBOARD]] | [[brain/CAPABILITIES]]

## Architecture Tier (Opus)
- [[agents/architect]] — System design, schema, cross-service planning

## Implementation Tier (Sonnet)
- [[agents/writer]] — Code implementation, TDD, bug fixes
- [[agents/researcher]] — Market research, documentation lookup, OpenCLI
- [[agents/content-creator]] — Brand voice, proposals, investor updates
- [[agents/video-editor]] — Video/audio production pipeline
- [[agents/chief-of-staff]] — Client comms, team management, meeting prep
- [[agents/revenue-hunter]] — Sales outreach, pricing strategy, lead hunting
- [[agents/reviewer]] — Security audit, code quality, pre-ship review
- [[agents/debugger]] — Error resolution, root-cause analysis
- [[agents/workflow-builder]] — n8n automation creation
- [[agents/meta-agent]] — Generate new subagent definitions

## Operations Tier (Haiku)
- [[agents/social-publisher]] — Cross-platform social media posting
- [[agents/git-ops]] — Git operations, branch management, PRs
- [[agents/documenter]] — Documentation updates, changelogs
- [[agents/explorer]] — File search, codebase navigation, analysis

## External
- [[agents/codex-agent]] — OpenAI Codex executor (backend, debugging, adversarial review)
- See [[skills/codex-delegation/SKILL]] for routing matrix
