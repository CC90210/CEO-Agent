---
tags: [brand, skool, primary_retainer, context, revenue, community]
---

> **ROUTING:** Not an app — Skool is a SaaS community. Automation via `scripts/skool_engine.py` + `scripts/skool_watchdog.py`
> [[brain/DASHBOARD]] | [[brain/APP_REGISTRY]] | [[brain/RISK_REGISTER]]

# the prior community — Skool Community Partnership with the prior client

## Overview

the prior community is a Skool community owned by the prior client where CC serves as the Head Coach. CC built the entire curriculum, runs 1-on-1 coaching calls, and is responsible for member retention. The community teaches members how to build AI automation agencies.

**Platform:** Skool.com (third-party SaaS — no source code)
**Community name:** the prior community
**CC's role:** Head Coach + Curriculum Architect
**the primary retainer's role:** Community Owner + Sales/Marketing

## Revenue Structure

**CC's compensation from the partnership:**
- **Flat retainer:** $2,500 USD/month (paid 1st of each month via bank transfer)
- **Revenue share:** 15% of Gross Community Revenue (paid within 7 business days of month-end)
- **Current MRR contribution to CC:** ~$2,951 USD/mo ($2,500 flat + $451 rev share on ~$3,007 community MRR)

**Community metrics (as of 2026-03):**
- 158 paying members
- 63% engagement rate
- 100% retention (last 30 days)
- 159 new signups last 30 days
- 5.5% visitor→paid conversion

## Contract Status

Formal coaching partnership agreement drafted 2026-04-10 (Google Doc at `docs.google.com/document/d/1GCCimdMb9_oiErw0PH-ApoLiW7CZw7vu6_mVSLb_8jk`). Key protections:
- 12-month initial term with auto-renewal
- IP rights: Coach retains full ownership of curriculum/content
- Non-replacement clause: new team additions don't reduce CC's role/compensation
- 60-day notice period after initial term
- Ontario, Canada governing law

## Concentration Risk (R-001 in RISK_REGISTER)

**Current status:** 94% of CC's $3,322 USD MRR comes from this single relationship. This is the #1 revenue risk.

**Mitigation plan:**
1. Diversify OASIS AI client base (target: 2 new $500+/mo retainers)
2. Launch Gritly SaaS as independent revenue stream
3. Formalize contract protections (DONE 2026-04-10)
4. Maintain curriculum IP ownership (DONE in contract Section 4)

## CC's Contributions

**Non-delegable (only CC does these):**
- 1-on-1 coaching calls (direct member interaction)
- Course curriculum design and updates
- Video recordings explaining core concepts
- Community engagement and support
- Retention-focused relationship building

**Automatable (handled by Bravo):**
- Member analytics and health scoring
- Content planning and scheduling
- Community activity monitoring (via `skool_watchdog.py`)
- Lead qualification for community signups

## Automation Layer

**Scripts:**
- `scripts/skool_engine.py` — V2 research-enhanced Skool automation daemon
- `scripts/skool_watchdog.py` — Monitoring and alerting daemon

**Workflows:**
- `.agents/workflows/skool-push.md` — Publish content to Skool community
- `.agents/workflows/skool-edit.md` — Edit existing community content

**Skill:**
- `skills/skool-automation/SKILL.md` — Full automation spec

## the prior client — Relationship Context

primary retainer is a friend first, business partner second. CC explicitly chose this as a relationship-based partnership rather than a contract-heavy arrangement. The 2026-04-10 contract was created to formalize the verbal agreement without damaging the friendship — protective but not adversarial.

**Key relationship dynamics:**
- primary retainer handles sales, marketing, and community ownership
- CC handles coaching, curriculum, and member success
- Both support each other's independent ventures (non-exclusive partnership)
- Communication is direct and trust-based

**Known upcoming concern (2026-04-10):** primary retainer mentioned possibly hiring another coach with more technical background. The contract's Section 7 (Team Expansion and Role Protection) explicitly protects CC's compensation and role against this scenario.

## North Star Connection

This community contributes to CC's $5,000 USD Net MRR goal by May 15, 2026:
- Baseline: $2,951/mo from this partnership
- Gap to goal: ~$1,678/mo (target: OASIS AI + Gritly + diversification)

## Key References

- Contract Google Doc: https://docs.google.com/document/d/1GCCimdMb9_oiErw0PH-ApoLiW7CZw7vu6_mVSLb_8jk/edit
- Risk tracking: `brain/RISK_REGISTER.md` (R-001)
- OKRs: `brain/OKRs.md` (Skool MRR targets)
- Session logs: `memory/SESSION_LOG.md` (ongoing)

## Obsidian Links

- [[brain/APP_REGISTRY]] | [[brain/DASHBOARD]] | [[brain/STATE]] | [[brain/RISK_REGISTER]]
- [[APPS_CONTEXT/INDEX]]
