---
tags:
  - dashboard
  - pinned
aliases:
  - Home
  - HQ
---

# Command Center

> **North Star:** $5,000 USD Net MRR by May 15, 2026
> **Current MRR:** ~$2,691 USD | **Gap:** ~$2,309

---

## Quick Navigation

### Core Intelligence
- [[brain/SOUL]] — Identity & values (IMMUTABLE)
- [[brain/STATE]] — Current operational state
- [[brain/AGENTS]] — 15 subagent registry
- [[brain/BRAIN_LOOP]] — 10-step reasoning protocol
- [[brain/CAPABILITIES]] — Tools, MCPs, skills registry
- [[brain/APP_REGISTRY]] — App routing table
- [[brain/GROWTH]] — Skill evolution tracker

### Active Work
- [[memory/ACTIVE_TASKS]] — Current task board
- [[memory/SESSION_LOG]] — All agent activity
- [[memory/LEAD_TRACKER.csv|LEAD_TRACKER]] — Pipeline (CSV)

### Knowledge Base
- [[memory/PATTERNS]] — Validated patterns
- [[memory/MISTAKES]] — Root causes & prevention
- [[memory/DECISIONS]] — Architecture decisions
- [[memory/SOP_LIBRARY]] — Standard procedures
- [[memory/LONG_TERM]] — Persistent facts

### CEO Operating System
- [[brain/CEO_OPERATING_SYSTEM]] — 7 domains, daily rhythm, scaling triggers
- [[skills/strategic-planning/SKILL]] — OKRs, quarterly planning
- [[skills/client-success/SKILL]] — Health scoring, churn prevention, NPS
- [[skills/competitive-intelligence/SKILL]] — Market research, `/competitive-report`
- [[skills/financial-modeling/SKILL]] — Unit economics, scenario planning
- [[skills/team-management/SKILL]] — Hiring, onboarding, 1:1s, RACI
- [[skills/scaling-playbook/SKILL]] — Growth tiers, pricing evolution
- [[skills/knowledge-management/SKILL]] — `/knowledge-maintenance`
- [[skills/project-management/SKILL]] — Phase gates, milestones
- [[skills/meeting-automation/SKILL]] — `/meeting-prep`, follow-up
- [[skills/brand-guidelines/SKILL]] — Voice, tone, visual consistency
- [[skills/content-engine/SKILL]] — Daily content rhythm

### Brand Context
- [[APPS_CONTEXT/OASIS_AI_CLAUDE]] — OASIS AI Solutions
- [[APPS_CONTEXT/PROPFLOW_CLAUDE]] — PropFlow
- [[APPS_CONTEXT/NOSTALGIC_REQUESTS_CLAUDE]] — Nostalgic Requests
- [[APPS_CONTEXT/CONTENT_BRAND_CLAUDE]] — Kona Makana

---

## Agent Registry
| Agent | Model | File |
|-------|-------|------|
| Architect | Opus | [[agents/architect]] |
| Writer | Sonnet | [[agents/writer]] |
| Reviewer | Sonnet | [[agents/reviewer]] |
| Debugger | Sonnet | [[agents/debugger]] |
| Researcher | Sonnet | [[agents/researcher]] |
| Content Creator | Sonnet | [[agents/content-creator]] |
| Social Publisher | Haiku | [[agents/social-publisher]] |
| Video Editor | Sonnet | [[agents/video-editor]] |
| Chief of Staff | Sonnet | [[agents/chief-of-staff]] |
| Git Ops | Haiku | [[agents/git-ops]] |
| Revenue Hunter | Sonnet | [[agents/revenue-hunter]] |
| Workflow Builder | Sonnet | [[agents/workflow-builder]] |
| Documenter | Haiku | [[agents/documenter]] |
| Explorer | Haiku | [[agents/explorer]] |
| Meta-Agent | Sonnet | [[agents/meta-agent]] |

---

## Skills (60 total)
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
