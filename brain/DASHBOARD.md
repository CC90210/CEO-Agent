---
description: "Navigation hub for Bravo's brain files, operational state, agents, active tasks, knowledge base, and CEO Operating System; agents use it to discover system resources"
tags:
  - dashboard
  - pinned
aliases:
  - Home
  - HQ
last_updated: 2026-08-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# Command Center

> Revenue / MRR → Atlas (CFO-Agent) owns reporting. This file is navigation only.

---

## Quick Navigation

### Core Intelligence
- [[brain/INDEX]] — Brain directory overview
- [[brain/SOUL]] — Identity & values (IMMUTABLE)
- [[brain/STATE]] — Current operational state
- [[brain/USER]] — CC's profile & preferences
- [[brain/AGENTS]] — 17 subagent registry (incl. Codex)
- [[brain/BRAIN_LOOP]] — 10-step reasoning + multi-hypothesis
- [[brain/CAPABILITIES]] — Tools, MCPs, skills registry
- [[brain/APP_REGISTRY]] — 12 app routing table
- [[brain/GROWTH]] — Skill evolution tracker
- [[brain/CHANGELOG]] — Self-modification audit trail

### Active Work
- [[memory/ACTIVE_TASKS]] — Current task board
- [[memory/SESSION_LOG]] — All agent activity (cross-AI)
- `memory/LEAD_TRACKER.csv` — Pipeline (CSV)
- `../CMO-Agent/brain/CONTENT_BIBLE` (Maven canonical) — Content Bible + outreach

### Knowledge Base
- [[memory/PATTERNS]] — Validated patterns
- [[memory/MISTAKES]] — Root causes & prevention
- [[memory/DECISIONS]] — Architecture decisions
- [[memory/SOP_LIBRARY]] — Standard procedures
- [[memory/LONG_TERM]] — Persistent facts
- [[memory/SELF_REFLECTIONS]] — Reflexion protocol entries

### CEO Operating System
- [[brain/CEO_OPERATING_SYSTEM]] — 7 domains, daily rhythm, scaling triggers
- [[brain/OKRs]] — Q2 2026 objectives & key results
- [[brain/RISK_REGISTER]] — 10 tracked risks
- [[skills/strategic-planning/SKILL]] — OKRs, quarterly planning
- [[skills/client-success/SKILL]] — Health scoring, churn prevention, NPS
- [[../CMO-Agent/skills/competitive-intelligence/SKILL]] — Market research, `/competitive-report`
- [[skills/financial-modeling/SKILL]] — Unit economics, scenario planning
- [[skills/team-management/SKILL]] — Hiring, onboarding, 1:1s, RACI
- [[skills/scaling-playbook/SKILL]] — Growth tiers, pricing evolution
- [[skills/knowledge-management/SKILL]] — `/knowledge-maintenance`
- [[skills/project-management/SKILL]] — Phase gates, milestones
- [[skills/meeting-automation/SKILL]] — `/meeting-prep`, follow-up
- [[skills/sales-methodology/SKILL]] — NEPQ framework, objection handling
- [[../CMO-Agent/skills/content-engine/SKILL]] — Daily content rhythm

### Automations
- ~~skool-automation~~ — Archived 2026-05-18, see `skills/_archive/skool-automation/`
- [[skills/codex-delegation/SKILL]] — Dual-AI execution (Bravo + Codex)
- [[skills/cli-anything/SKILL]] — CLI wrapper generation
- [[skills/browser-automation/SKILL]] — Playwright MCP
- [[skills/hooks-automation/SKILL]] — Claude Code hooks

### Brand Context
- [[APPS_CONTEXT/OASIS_AI_CLAUDE]] — OASIS AI Solutions
- [[APPS_CONTEXT/PROPFLOW_CLAUDE]] — PropFlow
- [[APPS_CONTEXT/NOSTALGIC_REQUESTS_CLAUDE]] — Nostalgic Requests
- [[APPS_CONTEXT/CONTENT_BRAND_CLAUDE]] — Conaugh McKenna

### Resources
- [[proposals/README]] — Generated proposals directory
- [[skills/INDEX]] — Active skills registry

---

## Agent Registry (17 agents)
| Agent | Model | File |
|-------|-------|------|
| Architect | Opus | `.claude/agents/architect.md` |
| Writer | Sonnet | [[agents/writer]] |
| Reviewer | Sonnet | [[.claude/agents/code-reviewer]] |
| Debugger | Sonnet | `.claude/agents/debugger.md` |
| Researcher | Sonnet | `.claude/agents/researcher.md` |
| Chief of Staff | Sonnet | [[agents/chief-of-staff]] |
| Git Ops | Haiku | [[agents/git-ops]] |
| Revenue Hunter | Sonnet | [[agents/revenue-hunter]] |
| Workflow Builder | Sonnet | [[agents/workflow-builder]] |
| Documenter | Haiku | [[agents/documenter]] |
| Explorer | Haiku | [[agents/explorer]] |
| Meta-Agent | Sonnet | [[agents/meta-agent]] |
| ~~Skool Engine~~ | _archived 2026-05-18_ | `scripts/_archive/skool/` |
| Codex Executor | GPT-5.4 | [[skills/codex-delegation/SKILL]] |

---

## Automation Status
| System | Status | Frequency |
|--------|--------|-----------|
| Bravo Scheduler (PM2) | Running | 60s poll |
| Telegram Bot (PM2) | Running | Always-on |
| Skool Community V2 | Archived (2026-05-18) | Paused — preserved for CC's own community |
| Email Inbox Monitor | Active | Every 5 min |
| Funnel Lead Sync | Active | Every 5 min |
| Content Publisher | Active | 9am/1pm/7pm |
| Stripe Revenue Sync | Active | Daily 6am |
| Lead Follow-up | Active | Daily 8am |
| Weekly MRR Report | Active | Monday 9am |

---

## Skills (179+ total)
> Use Dataview query in reading mode to see full skill list with metadata

---

## Live Queries

### Recently Modified Files
```dataview
TABLE file.mtime AS "Last Modified"
FROM ""
WHERE file.name != "DASHBOARD"
SORT file.mtime DESC
LIMIT 10
```

### All Skills
```dataview
TABLE tags AS "Tags", file.mtime AS "Updated"
FROM "skills"
WHERE file.name = "SKILL"
SORT file.mtime DESC
```

### Active Memory Files
```dataview
TABLE file.size AS "Size", file.mtime AS "Updated"
FROM "memory"
SORT file.mtime DESC
```

## Vault Navigation — Hub Index Files
- [[skills/INDEX]] — 180 skills (core, GWS, recipes, personas)
- [[.agents/workflows/INDEX]] — 30 automated workflows
- [[APPS_CONTEXT/INDEX]] — 6 brand context files
- [[../CMO-Agent/content-studio/INDEX]] — Video production + Remotion rules
- [[data/INDEX]] — Templates (email, content, documents)
- [[_templates/INDEX]] — Obsidian note templates
- [[docs/INDEX]] — Legal + technical docs
- [[courses/INDEX]] — Training frameworks
- [[media/INDEX]] — Brand assets + outreach
- [[.rules/INDEX]] — Gemini CLI rules
- [[memory/MEMORY_INDEX]] — 3-layer memory architecture
- [[ARCHITECTURE]] — System engineering design
- [[README]] — Project overview

## Related

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
