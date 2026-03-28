---
tags: [proposals]
---

# Generated Proposals

This directory stores proposals generated for OASIS AI Solutions clients and partners.

## Naming Convention

`YYYY-MM-DD_client-name_type.md`

Examples:
- `2026-03-28_bennett-hvac_retainer.md`
- `2026-04-01_smith-wellness_project.md`
- `2026-04-15_acme-corp_consulting.md`

## Proposal Types

| Type | Description | Template Source |
|------|-------------|----------------|
| `retainer` | Monthly retainer for ongoing automation services | `data/templates/proposals/retainer-proposal.md` |
| `project` | One-time project with fixed scope and deliverables | `data/templates/proposals/project-sow.md` |
| `consulting` | Strategy and advisory engagement | `data/templates/proposals/consulting.md` |
| `propflow` | PropFlow agency partnership or white-label | `data/templates/proposals/propflow-agency.md` |

## Workflow

1. CC describes the client situation and desired outcome
2. Bravo pulls the relevant template from `data/templates/proposals/`
3. Bravo customizes using client context from lead tracker and session logs
4. Output saved to this directory as `YYYY-MM-DD_client-name_type.md`
5. CC reviews, customizes, and sends
6. Outcome logged in `memory/SESSION_LOG.md` and lead tracker updated

## Status Tracking

Add a status line at the top of each proposal file:

```
**Status:** Draft | Sent | Under Review | Signed | Lost
**Sent Date:** YYYY-MM-DD
**Value:** $X,XXX/month or $X,XXX project
**Decision Date:** YYYY-MM-DD (if known)
```

## Archiving

Won and lost proposals both provide value:
- Won: use as reference for what resonated
- Lost: record the objection in `memory/MISTAKES.md` or `memory/PATTERNS.md`

Move proposals to `memory/ARCHIVES/proposals-YYYY.md` after 90 days.

## Obsidian Links
- [[skills/proposal-generation/SKILL]] | [[skills/knowledge-management/SKILL]]
- [[memory/SESSION_LOG]] | [[brain/STATE]]
