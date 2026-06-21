---
name: risk-management
description: Business risk identification, assessment, monitoring, and mitigation for CC's empire — revenue concentration, operational, financial, reputation, legal, and technology risk
tags: [skill, risk, management, ceo]
triggers: ["risk management", "use risk management", "run risk management", "business risk identification"]
tier: standard
---

# Risk Management — Business Continuity & Threat Monitoring

> **Note (2026-05-18):** R-001 (primary retainer concentration = 94% of MRR) **MATERIALIZED** when the primary retainer ended. The playbook below is now the **active recovery framework**, not a hypothetical. Current state: brain/STATE.md (~$371 confirmed). Risk register: brain/RISK_REGISTER.md.

## Overview

Identify, assess, and mitigate risks before they become crises. A CEO who only reacts to fires is already losing.

## Risk Categories

### 1. Revenue Risk
| Risk | Current Exposure | Severity | Mitigation |
|------|-----------------|----------|------------|
| Client concentration | 94% from primary retainer (HHI: 0.88) | CRITICAL | Diversify: close 4-5 new clients at $400-500/mo |
| Single revenue stream | OASIS retainers only | HIGH | Launch PropFlow, Nostalgic Requests monetization |
| Pricing power | No published pricing, custom quotes only | MEDIUM | Develop tiered packages (Good/Better/Best) |
| Market dependence | HVAC + wellness only | MEDIUM | Expand to new verticals (real estate, ecommerce, professional services) |
| Seasonality | HVAC demand seasonal | LOW | Balance with non-seasonal verticals |

### 2. Operational Risk
| Risk | Current Exposure | Severity | Mitigation |
|------|-----------------|----------|------------|
| Single point of failure (CC) | CC does everything | CRITICAL | Build SOPs, hire VA, systematize delivery |
| Tool dependency | n8n, Supabase, Vercel, Stripe | MEDIUM | Document alternatives, no single-vendor lock-in |
| API/MCP failures | Credential-dependent services break | MEDIUM | CLI-first architecture (already implemented) |
| Data loss | Git + Supabase, no formal backup strategy | MEDIUM | Weekly backups, Supabase point-in-time recovery |
| Scope creep on client projects | No formal change management | MEDIUM | SOP-013 + project-management skill |

### 3. Financial Risk
| Risk | Current Exposure | Severity | Mitigation |
|------|-----------------|----------|------------|
| Cash flow timing | Retainer billing but project delivery | MEDIUM | Collect upfront or 50% deposit on projects |
| Currency risk | Revenue in USD, expenses in CAD | LOW | Monitor CAD/USD, consider USD account |
| Tax liability | Growing income, approaching $80K threshold | MEDIUM | Atlas handles tax optimization, quarterly reviews |
| Under-pricing | Potential value gap | MEDIUM | Regular competitive pricing analysis |

### 4. Reputation Risk
| Risk | Current Exposure | Severity | Mitigation |
|------|-----------------|----------|------------|
| Client dissatisfaction | No NPS system (being built) | MEDIUM | Client health scoring, proactive check-ins |
| Negative reviews | No reputation monitoring | LOW | Set up Google Alerts, monitor G2/Capterra |
| Brand inconsistency | Multiple brands, one person | LOW | Brand guidelines skill, content templates |
| Social media misstep | Public content, personal brand | LOW | Content review before publishing |

### 5. Legal & Compliance Risk
| Risk | Current Exposure | Severity | Mitigation |
|------|-----------------|----------|------------|
| No formal contracts | Some clients on handshake | HIGH | Standardize contracts via proposal-generation skill |
| IP ownership unclear | Client work IP not assigned | MEDIUM | Add IP clause to all contracts |
| Privacy/data handling | Processing client data | MEDIUM | Privacy policy, data handling SOP |
| CRA compliance | Growing complexity | MEDIUM | Atlas manages quarterly, accounting-advisor skill |

### 6. Technology Risk
| Risk | Current Exposure | Severity | Mitigation |
|------|-----------------|----------|------------|
| AI model changes | Dependent on Claude, Gemini | MEDIUM | Multi-model architecture, no single-model lock-in |
| Supabase downtime | Business data in cloud | LOW | Supabase has 99.9% SLA, local backups |
| GitHub outage | Code hosting | LOW | Local git repos are complete copies |
| Security breach | API keys, client data | HIGH | .env.agents security, RLS, hooks automation |

## Risk Assessment Matrix

| Probability → | Low | Medium | High |
|---|---|---|---|
| **High Impact** | MONITOR | MITIGATE | CRITICAL |
| **Medium Impact** | ACCEPT | MONITOR | MITIGATE |
| **Low Impact** | ACCEPT | ACCEPT | MONITOR |

## Risk Review Cadence

| Cadence | Review | Tool |
|---------|--------|------|
| Weekly | Revenue risk (client health, pipeline) | `/client-health`, `/briefing` |
| Monthly | Operational + reputation risk | `/competitive-report` |
| Quarterly | All categories (part of QBR) | `/qbr`, `/strategic-review` |
| Annually | Full risk register refresh | Manual + Bravo analysis |

## Crisis Response Tiers

### Tier 1: AUTO-HANDLE (No CC needed)
- MCP server failure → switch to CLI tool
- Build failure → auto-fix, re-run
- Memory bloat → compress archives
- Stale data → refresh from source

### Tier 2: ALERT CC (Action within 24 hours)
- Client health drops to ORANGE → draft outreach, present to CC
- Competitor major move → update battlecard, recommend response
- Revenue drops 10%+ MoM → flag with analysis and action plan
- Security warning → investigate, present findings

### Tier 3: EMERGENCY (Immediate CC action required)
- Client health drops to RED → call CC immediately
- Security breach detected → halt operations, secure credentials
- Payment failure (Stripe) → alert CC, prepare manual invoice
- Legal notice received → document everything, recommend counsel
- Primary retainer churn signal → activate retention playbook immediately

### Tier 4: BUSINESS CONTINUITY (Existential risk)
- Primary retainer churns (94% revenue loss) → Execute diversification emergency plan:
  1. Activate all pipeline leads immediately
  2. Reduce expenses to minimum ($184/mo overhead)
  3. Launch aggressive outreach campaign (50 prospects/week)
  4. Consider interim consulting gigs for cash flow
  5. Accelerate PropFlow/Nostalgic monetization
- Health emergency (CC unable to work) → Dead man's switch:
  1. All client deliverables have documented SOPs
  2. Automated systems continue running (n8n workflows, crons)
  3. Contact list for emergency handoff to Adon
  4. 90-day runway at minimum burn

## Top-Client Churn Contingency (Detailed)

Since the primary retainer represents 94% of revenue, this scenario gets its own playbook:

**Early Warning Signs:**
- Response time increasing (>48 hours)
- Mentions of "budget review" or "exploring options"
- Reduced scope requests
- Skipped or shortened check-in calls
- Payment delays (even 1-2 days is a signal at this concentration)

**If the Primary Retainer Shows Warning Signs:**
1. Immediate proactive value demonstration — send metrics summary, ROI proof
2. Schedule in-person or video call (not email — too easy to ignore)
3. Ask directly: "Is there anything about the engagement that's not working?"
4. Prepare 3 response plays: (A) Adjust scope/pricing, (B) Add value, (C) Lock in with longer commitment
5. Simultaneously accelerate pipeline — close 2-3 new clients within 30 days

**If the Primary Retainer Churns:**
1. Immediate: Cut non-essential expenses, preserve 3-month runway
2. Week 1: Contact all warm leads, launch 25+ cold outreach emails
3. Week 2: Offer reduced-rate "onboarding special" to fast-track new clients
4. Week 3-4: Close 2-3 clients at $500-$1,000/mo each
5. Month 2-3: Rebuild to $5K MRR diversified across 8-10 clients
6. Post-mortem: Analyze what happened, update risk management, never exceed 40% concentration again


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[brain/CEO_OPERATING_SYSTEM]] | [[brain/STATE]] | [[brain/CAPABILITIES]]
- [[skills/client-success/SKILL.md]] | [[skills/financial-modeling/SKILL.md]]
- [[skills/strategic-planning/SKILL.md]] | [[skills/scaling-playbook/SKILL.md]]
