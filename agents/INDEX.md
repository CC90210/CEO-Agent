---
tags: [agents, index]
---

# Agents — Subagent Registry

> 16 internal agents + 1 external (Codex). Full orchestration matrix in [[brain/AGENTS]].
> All agents upgraded V5.5+: Decision Autonomy, Quality Gates, Anti-Patterns, Escalation Protocol, Output Format, Performance Metrics, Collaboration Rules.
> [[brain/DASHBOARD]] | [[brain/CAPABILITIES]]

## Architecture Tier (Opus)
- [[agents/architect]] — System design, schema, cross-service planning. Options with completeness scores. Advisory only.

## Implementation Tier (Sonnet)
- [[agents/writer]] — Code implementation, TDD, bug fixes. TypeScript/Next.js/Supabase specialist.
- [[agents/researcher]] — Market research, documentation lookup, OpenCLI. 3-source triangulation required.
- [[agents/content-creator]] — Brand voice, proposals, investor updates. Platform-specific optimization rules.
- [[agents/video-editor]] — Video/audio production pipeline. CRF 18, word-level Whisper captions, audio normalization.
- [[agents/chief-of-staff]] — Client comms, team management, meeting prep, churn signal detection.
- [[agents/revenue-hunter]] — Sales outreach, NEPQ framework, lead scoring model, pipeline management.
- [[agents/reviewer]] — Security audit, code quality, pre-ship review. Two-pass: structural + adversarial.
- [[agents/debugger]] — Error resolution, root-cause-first, 5 Whys, bisect strategy.
- [[agents/workflow-builder]] — n8n automation creation. Webhook-first, idempotency required.
- [[agents/meta-agent]] — Generate new subagent definitions. Full 7-section template required.

## Operations Tier (Haiku)
- [[agents/social-publisher]] — Cross-platform social media posting. Platform limits enforced, 20-post monthly budget.
- [[agents/git-ops]] — Git operations, branch management, PRs. Secret scan before every commit.
- [[agents/documenter]] — Documentation updates, changelogs. Wiki-link preservation mandatory.
- [[agents/explorer]] — File search, codebase navigation, analysis. READ-ONLY, file:line citations required.

## External
- [[agents/codex-agent]] — OpenAI Codex executor (backend, debugging, adversarial review). Verbatim output to CC.
- See [[skills/codex-delegation/SKILL]] for routing matrix
