---
name: crisis-response
description: Structured crisis response protocols for business emergencies — P0 through P3 classification, pre-built response plans, and communication templates
tags: [skill, crisis, response, ceo]
---

# Crisis Response — Emergency Protocols

## Overview

When things go wrong, speed and clarity matter more than perfection. This skill provides pre-built response plans so Bravo can act fast without waiting for CC to think through the playbook in real-time.

## Crisis Classification

| Level | Description | Response Time | Who Decides |
|-------|------------|---------------|-------------|
| **P0 — Critical** | Business survival at risk (major client churn, security breach, legal threat) | Immediate | CC |
| **P1 — High** | Significant revenue or reputation impact (client RED, public incident) | Within 4 hours | CC with Bravo recommendation |
| **P2 — Medium** | Operational disruption (tool outage, delivery delay, team issue) | Within 24 hours | Bravo, CC informed |
| **P3 — Low** | Minor inconvenience (cosmetic issue, non-urgent bug, preference conflict) | Within 1 week | Bravo auto-handles |

## Pre-Built Response Plans

### Plan A: Client Emergency (P0-P1)
**Trigger:** Client health score drops to RED, or client explicitly expresses major dissatisfaction.

1. **Assess (5 min):** What happened? What's the impact? What does the client want?
2. **Contain (15 min):** Acknowledge the issue directly. No deflection, no excuses.
3. **Communicate (1 hour):** Personal call or video from CC. Draft talking points:
   - "I take this seriously."
   - "Here's what I understand happened."
   - "Here's what we're doing about it right now."
   - "Here's how we'll prevent it from happening again."
4. **Fix (24-48 hours):** Execute the fix. Over-communicate progress.
5. **Follow up (1 week):** Check in to confirm satisfaction. Offer goodwill gesture if appropriate.
6. **Post-mortem:** Log to MISTAKES.md, update risk register, create prevention SOP.

### Plan B: Revenue Emergency (P0)
**Trigger:** MRR drops 20%+ in a single month, or major client gives notice.

1. **Assess:** Calculate new runway at current burn rate
2. **Preserve:** Cut non-essential expenses immediately
3. **Activate:** Launch emergency pipeline activation:
   - Contact all warm leads in pipeline
   - Send 25+ cold outreach emails
   - Offer fast-track onboarding incentive
   - Reach out to Adon's network for referrals
4. **Diversify:** Never let any client exceed 40% of revenue again
5. **Communicate:** If investors/advisors exist, proactive update
6. **Log:** Full post-mortem in DECISIONS.md

### Plan C: Security Breach (P0)
**Trigger:** Exposed credentials, unauthorized access, data leak.

1. **STOP:** Halt all operations immediately
2. **Rotate:** Change all affected credentials within 1 hour
3. **Assess:** What was exposed? What data was accessible? Who is affected?
4. **Contain:** Revoke compromised tokens, update .env.agents, regenerate API keys
5. **Notify:** If client data involved, notify affected clients within 24 hours
6. **Harden:** Add new hooks/checks to prevent recurrence
7. **Document:** Full incident report in MISTAKES.md

### Plan D: Tool/Infrastructure Outage (P2)
**Trigger:** Critical tool goes down (Supabase, Stripe, n8n, Vercel).

1. **Identify:** Which tool? What's the impact scope?
2. **Workaround:** Switch to backup method:
   - Supabase down → local data cache, manual operations
   - Stripe down → manual invoicing, record payments manually
   - n8n down → execute critical workflows manually
   - Vercel down → static pages still served from CDN
3. **Monitor:** Check status page, set alert for recovery
4. **Communicate:** If client-facing impact, proactive notification
5. **Resume:** When service recovers, verify data consistency

### Plan E: Team/Contractor Emergency (P1-P2)
**Trigger:** Contractor quits, underperforms, or becomes unavailable.

1. **Assess:** What work was in progress? What's at risk?
2. **Contain:** Secure access (revoke credentials), collect deliverables
3. **Reassign:** Transfer work to CC or another team member
4. **Replace:** If needed, begin hiring process using `skills/team-management/SKILL.md`
5. **Communicate:** Update affected clients on any timeline changes

## Communication Templates

### Client Apology
"[Client Name], I want to address [issue] directly. This fell below the standard I hold myself to, and I take full responsibility. Here's what happened: [brief explanation]. Here's what I'm doing about it: [specific actions]. I'll follow up with you on [date] to confirm this is fully resolved."

### Outage Notification
"Quick heads-up — [service] is experiencing an issue that may affect [specific impact]. I'm monitoring it closely and will have an update within [timeframe]. In the meantime, [workaround if applicable]."

### Internal Post-Mortem Header
```
## Incident: [Brief Description]
**Date:** [YYYY-MM-DD]
**Severity:** P0/P1/P2/P3
**Duration:** [X hours/days]
**Impact:** [What was affected]
**Root Cause:** [Why it happened]
**Resolution:** [What fixed it]
**Prevention:** [What will prevent recurrence]
```

## Obsidian Links
- [[skills/risk-management/SKILL]] | [[brain/CEO_OPERATING_SYSTEM]]
- [[memory/MISTAKES]] | [[memory/DECISIONS]]
- [[skills/client-success/SKILL]] | [[skills/self-healing/SKILL]]
