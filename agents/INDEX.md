---
tags: [agents, index]
---

# Agents — Subagent Registry

> 13 internal agents + 5 VoltAgent drop-ins + 1 external (Codex). Full orchestration matrix in [[brain/AGENTS]].
> Content / video / social publishing agents live in Maven ([[../CMO-Agent]]), not here.
> All agents upgraded V5.5+: Decision Autonomy, Quality Gates, Anti-Patterns, Escalation Protocol, Output Format, Performance Metrics, Collaboration Rules.
> [[brain/DASHBOARD]] | [[brain/CAPABILITIES]]

## Architecture Tier (Opus)
- [[agents/architect]] — System design, schema, cross-service planning. Options with completeness scores. Advisory only.

## Implementation Tier (Sonnet)
- [[agents/writer]] — Code implementation, TDD, bug fixes. TypeScript/Next.js/Supabase specialist.
- [[agents/researcher]] — Market research, documentation lookup, OpenCLI. 3-source triangulation required.
- [[agents/chief-of-staff]] — Client comms, team management, meeting prep, churn signal detection.
- [[agents/revenue-hunter]] — Sales outreach, NEPQ framework, lead scoring model, pipeline management.
- [[agents/reviewer]] — Security audit, code quality, pre-ship review. Two-pass: structural + adversarial.
- [[agents/debugger]] — Error resolution, root-cause-first, 5 Whys, bisect strategy.
- [[agents/workflow-builder]] — n8n automation creation. Webhook-first, idempotency required.
- [[agents/meta-agent]] — Generate new subagent definitions. Full 7-section template required.

## Operations Tier (Haiku)
- [[agents/git-ops]] — Git operations, branch management, PRs. Secret scan before every commit.
- [[agents/documenter]] — Documentation updates, changelogs. Wiki-link preservation mandatory.
- [[agents/explorer]] — File search, codebase navigation, analysis. READ-ONLY, file:line citations required.

## VoltAgent Drop-Ins (2026-04-21 — `agents/voltagent/`)
From [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) — drop-in personas, fully compatible with Claude Code agent schema.
- [[agents/voltagent/security-auditor]] — SOC2/HIPAA/PCI/GDPR pre-ship audits (Opus)
- [[agents/voltagent/code-reviewer]] — Parallel structural + adversarial review (Sonnet)
- [[agents/voltagent/competitive-analyst]] — Competitor benchmarking + positioning strategy (Sonnet)
- [[agents/voltagent/market-researcher]] — Market sizing, TAM/SAM/SOM, trend analysis (Sonnet)
- [[agents/voltagent/api-designer]] — REST/GraphQL API contracts + OpenAPI specs (Sonnet)

## External
- [[agents/codex-agent]] — OpenAI Codex executor (backend, debugging, adversarial review). Verbatim output to CC.
- See [[skills/codex-delegation/SKILL]] for routing matrix
