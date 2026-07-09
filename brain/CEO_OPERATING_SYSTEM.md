---
tags: [brain, ceo, operating-system]
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
---
# CEO Operating System — Bravo V5.5

> The complete operating framework for running CC's business empire autonomously.
> Every CEO function is mapped to a skill, script, or workflow.

## The CEO's 7 Domains

### 1. Revenue & Growth
**Goal:** Hit $10,000 USD Net MRR by September 30, 2026 ($5K achieved 2026-06-20 — BreezeAdvance deal)

| Function | Tool | Command |
|----------|------|---------|
| Pipeline management | `scripts/lead_engine.py` | Track leads, score, nurture |
| Revenue tracking | `scripts/revenue_engine.py` | MRR dashboard, forecasts |
| Client health monitoring | `scripts/client_health.py` | `/client-health` |
| Proposal generation | `scripts/proposal_generator.py` | `/proposal` |
| Financial modeling | `scripts/financial_model.py` | `/financial-model` |
| Pricing strategy | `skills/scaling-playbook/SKILL.md` | Tier-based evolution |

### 2. Strategy & Planning
**Goal:** Make informed, data-driven decisions about where to allocate resources

| Function | Tool | Command |
|----------|------|---------|
| OKR management | `skills/strategic-planning/SKILL.md` | Quarterly set, weekly check-in |
| Competitive intelligence | `scripts/competitive_intel.py` | `/competitive-report` |
| Scenario planning | `skills/financial-modeling/SKILL.md` | Bull/base/bear models |
| Quarterly business review | Combined workflow | `/qbr` |
| Strategic review | Combined workflow | `/strategic-review` |

### 3. Client Success
**Goal:** Zero surprise churn. Every client is GREEN or being actively managed.

| Function | Tool | Command |
|----------|------|---------|
| Health scoring | `scripts/client_health.py` | `/client-health` |
| Churn prediction | `skills/client-success/SKILL.md` | 14 warning triggers |
| Retention playbooks | `skills/client-success/SKILL.md` | Tier-specific actions |
| NPS collection | `skills/client-success/SKILL.md` | Quarterly cadence |
| Client check-ins | `data/templates/emails/client-checkin.md` | Monthly template |

### 4. Operations & Delivery
**Goal:** Every project delivered on time, on budget, with happy clients.

| Function | Tool | Command |
|----------|------|---------|
| Project management | `skills/project-management/SKILL.md` | Phase gates, milestones |
| Meeting automation | `skills/meeting-automation/SKILL.md` | `/meeting-prep` |
| SOP management | `skills/sop-breakdown/SKILL.md` | Process documentation |
| Workflow automation | `scripts/integrations/n8n_tool.py` | 47+ n8n workflows |
| Code shipping | `skills/ship/SKILL.md` | `/ship` |

### 5. Team & People
**Goal:** Scale from solo to small team without losing quality or culture.

| Function | Tool | Command |
|----------|------|---------|
| Hiring | `skills/team-management/SKILL.md` | Role definition, interviews |
| Onboarding | `skills/team-management/SKILL.md` | `/onboard-team-member` |
| 1:1s | `skills/team-management/SKILL.md` | Weekly + monthly templates |
| Performance reviews | `skills/team-management/SKILL.md` | Quarterly cadence |
| Delegation | `skills/team-management/SKILL.md` | RACI framework |

### 6. Content & Brand
**Goal:** Consistent content engine that generates inbound leads.

| Function | Tool | Command |
|----------|------|---------|
| Content creation | `../CMO-Agent/skills/content-engine/SKILL.md` | `/content` |
| Social publishing | `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | `/post` |
| Brand voice | `../CMO-Agent/skills/brand-guidelines/SKILL.md` | Consistency enforcement |
| Template library | `data/templates/content/` | LinkedIn, X, IG templates |

### 7. Intelligence & Learning
**Goal:** The system gets smarter every session.

| Function | Tool | Command |
|----------|------|---------|
| Knowledge management | `skills/knowledge-management/SKILL.md` | `/knowledge-maintenance` |
| Memory system | `skills/memory-management/SKILL.md` | MemoryBox architecture |
| Self-healing | `skills/self-healing/SKILL.md` | 5-dimension monitoring |
| Weekly retro | `skills/retro/SKILL.md` | `/retro` |
| Pattern extraction | `skills/retro/SKILL.md` | Insights-to-rules pipeline |

## CEO Daily Rhythm

| Time | Activity | Tool |
|------|---------|------|
| Morning | CEO Briefing (5 North Star metrics + priorities) | `/briefing` |
| Mid-day | Execute #1 priority (revenue, content, or delivery) | Varies |
| Afternoon | Pipeline & follow-ups | `/meeting-prep`, email templates |
| End of day | State sync (memory update, session log) | Auto (session protocol) |
| Friday | Client health review | `/client-health` |
| Sunday | Knowledge maintenance | `/knowledge-maintenance` |
| Monthly | Competitive report + investor update | `/competitive-report`, `/investor-update` |
| Quarterly | QBR + OKR refresh + strategic review | `/qbr`, `/strategic-review` |

## Scaling Triggers

| MRR | What Unlocks | Reference |
|-----|-------------|-----------|
| $2K-$5K | Systematize delivery, SOPs, content engine | `skills/scaling-playbook/SKILL.md` |
| $5K-$10K | First hire (VA), automate admin | `skills/team-management/SKILL.md` |
| $10K-$25K | Build team (2-3), productize, raise prices | `skills/scaling-playbook/SKILL.md` |
| $25K+ | Management layer, enterprise clients | `skills/team-management/SKILL.md` |

## Cross-Agent Integration

| Agent | Domain | Relationship |
|-------|--------|-------------|
| **Bravo (this system)** | **CTO + Integrator** — runs CEO operations on behalf of CC | Owns all 7 domains above, executes CC's strategic direction |
| **Atlas** | CFO — capital, tax, trading, FIRE | Handles financial strategy, tax optimization |

**CC is the Visionary CEO.** Bravo is his CTO/Integrator — technical architecture + day-to-day operations. Atlas is CFO. Maven is CMO. Aura is Home/Life. Bravo READs Atlas/Maven/Aura context; they READ Bravo context. Neither writes to the other's repo. Full framework: [[brain/CANONICAL_ROLES]] | [[brain/C_SUITE_ARCHITECTURE]].

## Obsidian Links
- [[brain/SOUL]] | [[brain/STATE]] | [[brain/AGENTS]]
- [[brain/CAPABILITIES]] | [[brain/DASHBOARD]]
- [[skills/strategic-planning/SKILL]] | [[skills/client-success/SKILL]]
- [[../CMO-Agent/skills/competitive-intelligence/SKILL]] | [[skills/financial-modeling/SKILL]]
- [[skills/team-management/SKILL]] | [[skills/ceo-dashboard/SKILL]]
- [[skills/scaling-playbook/SKILL]] | [[skills/knowledge-management/SKILL]]
