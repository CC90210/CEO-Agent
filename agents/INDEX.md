---
tags: [agents, index]
---

# Agents — Subagent Registry

> Roster counts live in `brain/CAPABILITY_GRAPH.json` totals (32 agent nodes as of V7.2.0) — do not hand-count here; hardcoded numbers drift. Full orchestration matrix in [[brain/AGENTS]].
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

## Agency Imports (V7.2.0 — [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents), MIT, hand-scoped)
Cherry-picked to close confirmed-zero-coverage roles; every file carries explicit `tools:`/`model:` scoping. Never bulk-import from the source repo.
- [[agents/testing-test-automation-engineer]] — E2E/integration test engineering, flake root-causing, Playwright-first (Sonnet, write-enabled)
- [[agents/testing-accessibility-auditor]] — WCAG/508 audits of live UIs (Sonnet, audit-only)
- [[agents/engineering-database-reliability-engineer]] — Supabase/Postgres reliability, zero-downtime migrations, RLS-safe evolution (Sonnet, propose-only)
- [[agents/engineering-devops-automator]] — CI/CD design: GitHub Actions, deploy gates, rollback (Sonnet, write-enabled)
- [[agents/engineering-incident-response-commander]] — Multi-service incident triage/containment/post-mortem (Sonnet, coordinate-only)
- [[agents/security-ai-generated-code-auditor]] — Audits AI-authored diffs for injected vulns/secrets/plausible-but-wrong logic (Sonnet, read-only)
- [[agents/product-manager]] — Roadmaps, PRDs, outcome measurement across the app portfolio (Sonnet)
- [[agents/project-management-project-shepherd]] — Cross-project status shepherding + dependency tracking (Haiku, read-only)
- [[agents/specialized-mcp-builder]] — MCP server design/build/audit incl. Rule 4 config sync (Sonnet, write-enabled)
- [[agents/sales-discovery-coach]] — INBOUND qualification-call coaching; advisory only, never outreach (Haiku, Read-only)

## Quality Gate (Claude Code Native)
- [[.claude/agents/validator]] — Haiku validator. Scores sub-agent outputs against success criteria. Catches hallucinated claims, silent failures, scope violations before results reach CC. Fire after every parallel spawn or Codex file-modifying task. Closes Anthropic's Observability-Evaluation Gap.

## External
- [[agents/codex-agent]] — OpenAI Codex executor (backend, debugging, adversarial review). Verbatim output to CC.
- See [[skills/codex-delegation/SKILL]] for routing matrix
