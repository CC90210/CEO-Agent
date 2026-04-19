---
tags: [audit, agents, gaps, completeness]
wiki-links: [[brain/CAPABILITIES]] [[brain/AGENTS]] [[brain/C_SUITE_ARCHITECTURE]]
---

# AGENT GAP AUDIT — Deep Capability Analysis (2026-04-18)

Audit of CC's 4-agent system: Bravo (CEO), Atlas (CFO), Maven (CMO), Aura (Life/Home).
Completeness baseline: What a real-world CEO/CFO/CMO/Life-Agent needs to operate independently.

---

## BRAVO (CEO) — Business-Empire-Agent

Current State: 142 skills, 33 workflows, 47+ scripts, 16 file-based agents

| Capability | Current State | Gap Severity | Proposed Fix |
|---|---|---|---|
| Strategic Planning | COMPLETE | None | Monitor quarterly |
| Client ICP + lead scoring | COMPLETE | None | Integrate CAC ROI tracking |
| Revenue ops (MRR, churn, health) | COMPLETE | None | Add cohort-based retention analysis |
| Pricing + proposals | COMPLETE | None | A/B test tiers on new brands |
| Sales methodology | COMPLETE | None | Record win/loss patterns |
| Hiring playbooks | COMPLETE | Low | Test on real hire |
| Delegation patterns | COMPLETE | None | Verify in practice |
| Retros + self-improvement | COMPLETE | Low | Run after big failures |
| Knowledge sourcing | PARTIAL | Low | Expand frameworks beyond HBR/YC |
| Meeting automation | COMPLETE | Low | Add post-call action extraction |
| Partnership eval framework | PARTIAL | Medium | Create formal checklist skill |
| LTV/CAC per brand | PARTIAL | Medium | Add unit_economics.py script |
| Content ROI attribution | PARTIAL | Medium | Wire Maven pulse to attribution.py |

Bravo is 9/10 complete.

---

## ATLAS (CFO) — CFO-Agent

Current State: 16 skills, financial planning, tax strategy, stock research

| Capability | Current State | Gap Severity | Proposed Fix |
|---|---|---|---|
| 13-week cashflow modeling | COMPLETE | None | Add stress scenarios |
| Runway calculation | COMPLETE | None | Export weekly report |
| Tax (T2125, crypto, FHSA) | COMPLETE | None | Pre-plan 2026 estimate |
| Stock research | COMPLETE | None | Integrate MarketWatch RSS |
| Receipt automation | COMPLETE | None | Validate quarterly |
| Cross-border tax | COMPLETE | None | Pre-plan Montreal move |
| Live API reads | COMPLETE | None | Add threshold alerts |
| Portfolio rebalancing | COMPLETE | None | Send recommendations |
| LTV/CAC calculations | GAP | High | Add validate_unit_economics.py |
| Unit economics per brand | GAP | High | Create brand_economics.py |
| Knowledge sourcing | COMPLETE | None | Contract CPA briefing |
| Spending gate on campaigns | COMPLETE | None | Alert burn threshold |

Atlas is 8.5/10 complete.

---

## MAVEN (CMO) — CMO-Agent

Current State: 11 workflows, competitive intel, lead management, campaigns

| Capability | Current State | Gap Severity | Proposed Fix |
|---|---|---|---|
| Content engine | COMPLETE | None | Quarterly voice audit |
| Elite video production | COMPLETE | None | Build per-brand templates |
| Paid ads | COMPLETE | Low | Finalize OAuth2 |
| Funnel management | COMPLETE | None | Test BOFU sequences |
| Lead management | COMPLETE | None | Monitor SLA adherence |
| Competitive intelligence | COMPLETE | None | Add quarterly feature table |
| Audience research | COMPLETE | None | Run validation interviews |
| A/B testing frameworks | COMPLETE | Low | Enforce n=500 minimum |
| Attribution modeling | GAP | High | Create attribution_model.py |
| Marketing research | COMPLETE | Low | Finalize Ahrefs wrapper |
| Knowledge sourcing | GAP | High | Create MARKETING_PLAYBOOK_CANON.md |
| Brand voice management | PARTIAL | Medium | Add voice_consistency_check.py |
| Ad creative production | COMPLETE | None | Expand to 10+ templates |
| Email marketing | COMPLETE | None | Test subject line A/B |
| Lead pipeline visibility | PARTIAL | Low | Add Slack alerts |
| Performance dashboard | GAP | Medium | Build /perf-dashboard workflow |

Maven is 7.5/10 complete.

---

## AURA (Life/Home) — AURA

Current State: 3 skills, Home Assistant MCP, voice agent, dashboard

| Capability | Current State | Gap Severity | Proposed Fix |
|---|---|---|---|
| Habit tracking + streaks | COMPLETE | None | Add weekly reflection |
| Sleep/energy monitoring | COMPLETE | None | Integrate Apple Health |
| Presence detection | COMPLETE | None | Validate geofence |
| Accountability nudges | COMPLETE | None | Track effectiveness |
| Multi-resident privacy | COMPLETE | None | Quarterly audit |
| Voice pipeline | COMPLETE | None | Profile latency |
| Weekly reflections | COMPLETE | None | Turn into action items |
| Apartment control | COMPLETE | None | Add Guest Mode |
| Knowledge sourcing | GAP | Low | Add BEHAVIORAL_DESIGN_CANON.md |
| Business context integration | COMPLETE | None | Add stress detection |
| Mobile dashboard | COMPLETE | None | Add habit heatmap |
| Data export / analytics | GAP | Low | Create aura_analytics.py |

Aura is 8.5/10 complete.

---

## PRIORITY FIXES

Tier 1 (This Week):
1. Maven: Multi-touch attribution pipeline
2. Aura: Create data/pulse/aura_pulse.json
3. Atlas: Unit economics validator

Tier 2 (Next 2 Weeks):
1. Maven: Marketing knowledge canon
2. Bravo: Cohort retention analytics
3. Maven: Real-time performance dashboard

Tier 3 (Nice-to-Have):
1. Aura: Behavioral design canon
2. Aura: Personal analytics export
3. Maven: Voice consistency checker

---

## SYSTEM COMPLETENESS

| Agent | Current | Target | Key Gaps |
|---|---|---|---|
| Bravo (CEO) | 9/10 | 9.5/10 | Cohort analytics, unit validation |
| Atlas (CFO) | 8.5/10 | 9.5/10 | Unit validators, alerts |
| Maven (CMO) | 7.5/10 | 9/10 | Attribution, canon, dashboard |
| Aura (Life) | 8.5/10 | 9/10 | Pulse, canon, analytics |
| System Avg | 8.4/10 | 9.3/10 | 3 critical + 5 medium fixes |

Audit high confidence. Gaps are real, fixes feasible (1-2 scripts each).

---

Obsidian Links: [[brain/CAPABILITIES]] [[brain/AGENTS]] [[brain/C_SUITE_ARCHITECTURE]]
