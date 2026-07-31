---
name: sop-breakdown
description: Automatically creates, refines, and executes Standard Operating Procedures. Triggers when a process is repeated 3+ times or when CC requests an SOP. Extracts steps from observed behavior, tracks success rates, and evolves SOPs over time.
triggers: [SOP, standard operating procedure, process, repeated task, workflow template]
tier: standard
dependencies: [memory-management]
tags: [skill, sop-breakdown]
last_updated: 2026-06-20
---

# SOP Breakdown Engine

## Overview

Every repeated process in CC's business should become a documented, trackable, improvable SOP. This skill handles the full lifecycle: detection → creation → execution → refinement → retirement.

## SOP Lifecycle

### Phase 1: Pattern Detection
Monitor for repeated task patterns:
- Same type of task executed 3+ times with similar steps
- CC explicitly requests "make this a process" or "create an SOP"
- A command is used repeatedly with the same flow

**Detection Criteria:**
- 3+ occurrences of similar task type
- Steps overlap by >70%
- Consistent success/failure pattern

### Phase 2: SOP Drafting
When a pattern is detected, draft an SOP:

```markdown
### SOP-[ID]: [Descriptive Name]
**Category:** [content/code/deploy/research/automation/admin/client/finance]
**Trigger:** [What activates this SOP — user command, event, schedule]
**Prerequisites:** [What must be true before starting]
**Steps:**
1. [Specific, actionable step with expected output]
2. [Step with decision point: IF condition THEN step A ELSE step B]
3. [Step with tool reference: Use [tool] to [action]]
**Success Criteria:** [Measurable outcomes]
**Failure Handling:** [What to do if a step fails]
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** [Who is responsible — Bravo, CC, Adon]
```

### Phase 3: Execution Tracking
When executing an SOP:
1. Log execution start time
2. Execute each step, noting deviations
3. Record outcome (success/partial/failure)
4. Update execution count and success rate
5. Note any steps that were skipped, modified, or added

### Phase 4: Refinement
After every 5 executions, review the SOP:
- Are there steps that are always skipped? → Remove them
- Are there steps that are always added? → Include them
- Has the success rate dropped? → Investigate and fix
- Has a better approach emerged? → Update steps

### Phase 5: Retirement
Retire an SOP when:
- It hasn't been used in 90+ days
- The underlying process no longer exists
- It has been replaced by a better SOP or automation
- Move to "Retired SOPs" section in SOP_LIBRARY.md

## SOP Categories

| Category | Description | Examples |
|----------|-------------|----------|
| **content** | Content creation & publishing | Social posts, blog writing, video scripts |
| **code** | Development workflows | Bug fixing, feature building, code review |
| **deploy** | Deployment & CI/CD | Git → PR → Vercel → merge |
| **research** | Market & competitive intelligence | Playwright research, trend analysis |
| **automation** | n8n & workflow creation | Workflow building, trigger setup |
| **admin** | System maintenance | Heartbeat, self-heal, cleanup, audit |
| **client** | Client-facing processes | Onboarding, reporting, deliverables |
| **finance** | Revenue & payments | Stripe operations, invoicing, pricing |

## Quick SOP Creation Template

When CC says "Create an SOP for [process]":

1. Ask clarifying questions:
   - What triggers this process?
   - What are the expected inputs and outputs?
   - Who is responsible for each step?
   - What does success look like?

2. Observe or ask CC to walk through the process once

3. Document using the SOP format above

4. Add to `memory/SOP_LIBRARY.md`

5. Log to Supabase `sops` table (when available)

## Integration with Brain Loop

The Brain Loop (Step 2: RECALL) checks SOP_LIBRARY.md for relevant SOPs before planning a task. If an SOP exists, follow it. If no SOP exists but the task is a candidate, note it for future SOP creation.


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
