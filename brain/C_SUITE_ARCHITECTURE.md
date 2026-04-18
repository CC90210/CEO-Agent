---
tags: [architecture, c-suite, multi-agent]
---

# C-SUITE ARCHITECTURE — Three-Agent Operating Model

> **Purpose:** Defines the organizational structure, decision rights, communication protocols, and inter-agent conventions for CC's AI C-Suite.
> **Last updated:** 2026-04-18

## The Board

```
CC (Board Chair — human decision-maker, final authority)
│
├── Atlas (CFO)     — Money, tax, research, compliance, wealth
│   Project: C:\Users\User\APPS\CFO-Agent
│   GitHub: CC90210/CFO-Agent
│   Pulse: data/pulse/cfo_pulse.json
│
├── Bravo (CEO)     — Strategy, clients, revenue, partnerships, vision
│   Project: C:\Users\User\Business-Empire-Agent
│   GitHub: CC90210/CEO-Agent
│   Pulse: data/pulse/ceo_pulse.json
│
└── Maven (CMO)     — Brand, content, ads, funnels, distribution, growth, research
    Project: C:\Users\User\Marketing-Agent
    GitHub: CC90210/Marketing-Agent
    Pulse: data/pulse/cmo_pulse.json
    Orchestrates: shopify-ad-engine, ig-setter-pro, cc-funnel
```

## Decision Rights Matrix

| Question | Owner | Advisor |
|----------|-------|---------|
| "How much runway do I have?" | Atlas | — |
| "Which client to pursue?" | Bravo | Maven (market fit), Atlas (pricing) |
| "What content to post?" | Maven | Bravo (brand alignment) |
| "Should I raise prices?" | Bravo | Atlas (tax impact), Maven (positioning) |
| "Can I afford paid ads?" | Atlas (spend gate) | Maven (execution plan) |
| "Incorporate now or wait?" | Atlas | — |
| "What's the brand voice?" | Maven | Bravo (strategic direction) |
| "Should I hire?" | Bravo | Atlas (cost model), Maven (marketing ROI) |
| "What vertical to target next?" | Bravo | Maven (market research), Atlas (revenue model) |
| "Should I pivot a product?" | Bravo | Maven (competitive intel), Atlas (financial viability) |

## Conflict Resolution Protocol

1. **Atlas** has veto power on any **spend** decision (capital preservation > growth)
2. **Bravo** has veto power on any **client-facing** decision (strategy > tactics)
3. **Maven** executes within the budget Atlas approves and the strategy Bravo sets
4. When agents disagree → **CC decides** (board chair tiebreaker)

## 3-Way Pulse Protocol

### Schema Overview

Each agent maintains a pulse file that others read:

| Pulse File | Writer | Location | Readers | Key Data |
|------------|--------|----------|---------|----------|
| `ceo_pulse.json` | Bravo | `Business-Empire-Agent/data/pulse/` | Atlas, Maven | MRR, strategy, client health, directives |
| `cfo_pulse.json` | Atlas | `APPS/CFO-Agent/data/pulse/` | Bravo, Maven | Runway, spend gate, tax deadlines, FX rates |
| `cmo_pulse.json` | Maven | `Marketing-Agent/data/pulse/` | Bravo, Atlas | Content pipeline, ad performance, funnel metrics, brand health |

### Read Protocol

| Agent | On Session Start, Read: |
|-------|------------------------|
| **Bravo** | `cfo_pulse.json` (runway), `cmo_pulse.json` (brand health, funnel metrics) |
| **Atlas** | `ceo_pulse.json` (revenue targets), `cmo_pulse.json` (ad spend for cashflow/tax) |
| **Maven** | `ceo_pulse.json` (strategy directives), `cfo_pulse.json` (spend gate approval) |

### Write Protocol

- Each agent updates **only its own** pulse file
- Write on: session end, significant state change, or when data requested by another agent changes
- Never modify another agent's pulse file — that's a sovereignty violation

### Spend Gate Flow

```
Maven wants to run $500 Meta campaign
  → Maven writes spend_request_cad: 500 to cmo_pulse.json
  → Atlas reads cmo_pulse.json, checks runway
  → Atlas writes spend_approved_by_atlas: true to cfo_pulse.json
  → Maven reads cfo_pulse.json, confirms approval
  → Maven launches campaign
  → Maven updates cmo_pulse.json with actual spend
  → Atlas reads and factors into cashflow model
```

## File Ownership Rules

| Domain | Owner | Others May |
|--------|-------|------------|
| `brain/`, `memory/`, `skills/` in Business-Empire-Agent | Bravo | READ only |
| `brain/`, `memory/`, `skills/` in CFO-Agent | Atlas | READ only |
| `brain/`, `memory/`, `skills/` in Marketing-Agent | Maven | READ only |
| `data/pulse/ceo_pulse.json` | Bravo | READ only |
| `data/pulse/cfo_pulse.json` | Atlas | READ only |
| `data/pulse/cmo_pulse.json` | Maven | READ only |

**Golden rule:** Update in-place, don't spawn. Each agent modifies only files in its own project.

## Cross-Agent Read Access (Delegation & Orchestration)

Every agent has **full read access** to every other agent's file tree. This is non-negotiable — it's how intelligent delegation works without duplicating knowledge.

| Read | What to Look For |
|------|-----------------|
| `../Business-Empire-Agent/brain/` | Current strategy, OKRs, decision matrix, CEO directives |
| `../Business-Empire-Agent/skills/` | CEO-domain capabilities (revenue-ops, client-success, sales-closing, NEPQ, meeting-automation) |
| `../CFO-Agent/brain/` | Runway, tax rules, FX context, wealth strategy |
| `../CFO-Agent/skills/` | Financial skills (tax-canada, trading-execution, wealth-projection) |
| `../Marketing-Agent/brain/clients/` | Brand voice, target ICP, active campaigns per brand |
| `../Marketing-Agent/skills/` | Marketing skills (content-engine, ad-copywriting, funnel-management, elite-video-production) |
| `../*/data/pulse/*.json` | Real-time state sync (runway, spend gate, MRR, funnel metrics) |

**Write rule:** Every agent writes **only** inside its own project directory. Never reach across to modify another agent's files — that's a sovereignty violation. If you need another agent to change something, update your pulse with a request; they'll read it and act.

**Delegation example:**
```
User asks Bravo: "Plan a Meta ad for PULSE"
  → Bravo reads ../Marketing-Agent/skills/content-engine/SKILL.md
  → Bravo reads ../Marketing-Agent/brain/clients/oasis-ai.md
  → Bravo writes a strategic brief to ceo_pulse.json
  → User reopens Maven: Maven reads ceo_pulse.json
  → Maven executes the ad launch
```

**Tool sharing:** Each agent's `scripts/` directory is a set of CLI tools. Other agents may *invoke* (not modify) these scripts via subprocess. If Bravo needs to send an email, it can shell out to `../Marketing-Agent/scripts/email_engine.py` (or the local Bravo copy still in Business-Empire-Agent during transition).

## Maven (CMO) — Full Scope

### What Maven Owns

```
┌─────────────────────────────────────────────────────┐
│                    MAVEN (CMO)                       │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   CONTENT    │  │  DISTRIBUTION │  │  ANALYTICS │ │
│  │   ENGINE     │  │    ENGINE     │  │   ENGINE   │ │
│  │             │  │              │  │            │ │
│  │ • Copywriting│  │ • Meta Ads   │  │ • ROAS     │ │
│  │ • Video Gen  │  │ • Google Ads │  │ • CAC      │ │
│  │ • Image Gen  │  │ • Instagram  │  │ • LTV      │ │
│  │ • Email Copy │  │ • TikTok     │  │ • Funnel   │ │
│  │ • Blog/SEO   │  │ • LinkedIn   │  │ • A/B Test │ │
│  │ • UGC Sim    │  │ • Email      │  │ • Cohort   │ │
│  │ • Podcast    │  │ • Skool      │  │            │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬─────┘ │
│         │                │                  │       │
│  ┌──────▼────────────────▼──────────────────▼─────┐ │
│  │              FUNNEL ENGINE                      │ │
│  │  Awareness → Interest → Consideration → Action  │ │
│  │  cc-funnel + ig-setter + shopify-ad-engine +    │ │
│  │  Marketing-Agent (campaign management)          │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │              BRAND INTELLIGENCE                  │ │
│  │  • Competitive analysis    • Market trends       │ │
│  │  • Audience psychology     • Positioning          │ │
│  │  • Brand voice enforcement • Content calendar     │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### CC's Key Requirements for Maven
1. **Content creation** — Full pipeline from ideation to publication
2. **Content editing** — Video editing (Remotion + FFmpeg), image generation (Gemini Imagen)
3. **Full marketing advice** — Not just execution, but strategic counsel at CMO level
4. **Deep research** — Market research, competitive intelligence, trend analysis
5. **Cutting-edge, innovative, creative, logical** — This is a next-gen marketing brain, not a template bot

### Existing Assets Maven Orchestrates

| System | Location | Status | Purpose |
|--------|----------|--------|---------|
| Marketing-Agent (HQ) | `C:\Users\User\Marketing-Agent` | Production | 16 agents, 19 skills, Meta + Google Ads |
| Shopify Ad Engine | `C:\Users\User\APPS\shopify-ad-engine` | Available | Remotion video ad pipeline, 5 templates |
| IG Setter Pro | `C:\Users\User\APPS\ig-setter-pro` | Deployed | Instagram DM automation, Vercel live |
| CC Funnel | `C:\Users\User\APPS\cc-funnel` | Live | Lead capture → Supabase → Telegram |

### Skills Migration (from Bravo → Maven)

| Skill | Current Location | Migration Status |
|-------|-----------------|-----------------|
| content-engine | Business-Empire-Agent/skills/ | PENDING |
| email-marketing | Business-Empire-Agent/skills/ | PENDING |
| funnel-management | Business-Empire-Agent/skills/ | PENDING |
| brand-guidelines | Business-Empire-Agent/skills/ | PENDING |
| growth-engine | Business-Empire-Agent/skills/ | PENDING |
| competitive-intelligence | Business-Empire-Agent/skills/ | PENDING |
| elite-video-production | Business-Empire-Agent/skills/ | PENDING |
| lead-management | Business-Empire-Agent/skills/ | PENDING |
| linkedin-outreach | Business-Empire-Agent/skills/ | PENDING |
| persona-content-creator | Business-Empire-Agent/skills/ | PENDING |
| content-studio/ | Business-Empire-Agent/ | PENDING |

### Skills Staying with Bravo (CEO)

| Skill | Reason |
|-------|--------|
| revenue-operations | Core CEO function |
| sales-closing | Client-facing, CEO owns |
| sales-methodology | NEPQ framework, CEO domain |
| client-success | Client delivery, CEO responsibility |
| investor-communications | Strategic, CEO only |
| strategic-planning | OKRs, vision, CEO core |
| team-management | Hiring/firing, CEO authority |
| meeting-automation | Calendar, follow-ups, CEO ops |
| project-management | Delivery tracking, CEO oversight |
| ceo-dashboard | North star metrics, CEO view |

## Implementation Roadmap

### Phase 1: Architecture (This Session ✅)
- [x] Fix stale Atlas reference in AGENTS.md
- [x] Add Maven (CMO) entry to AGENTS.md
- [x] Add CMO routing rows to decision matrix
- [x] Create `ceo_pulse.json` schema
- [x] Create `cmo_pulse.json` schema
- [x] Create this architecture document
- [x] Update STATE.md and SESSION_LOG.md

### Phase 2: Maven Identity Transformation (Next Session — IN Marketing-Agent/)
- [ ] Rewrite `SOUL.md` — AdVantage V2.0 → Maven V1.0 (multi-client CMO, not single-client ad manager)
- [ ] Rewrite `CLAUDE.md` — Add CC's brands (OASIS AI, PropFlow, Nostalgic Requests), multi-client routing, pulse protocol
- [ ] Create `GEMINI.md` — Maven entry point for Gemini CLI runtime
- [ ] Create `ANTIGRAVITY.md` — Maven entry point for Antigravity IDE runtime
- [ ] Add `data/pulse/` directory with cmo_pulse.json read/write logic
- [ ] Add cross-agent pulse reading (ceo_pulse.json, cfo_pulse.json)

### Phase 3: Skill Migration (Requires CC Approval)
- [ ] Copy 10 marketing skills from Business-Empire-Agent → Marketing-Agent
- [ ] Move content-studio/ Remotion setup to Marketing-Agent
- [ ] Adapt skills to Maven's voice and multi-client context
- [ ] Remove migrated skills from Bravo's active routing (keep as READ references)
- [ ] Update both agents' CAPABILITIES.md

### Phase 4: Multi-Client Expansion
- [ ] Add OASIS AI client profile to Maven's brain/
- [ ] Add PropFlow client profile
- [ ] Add Nostalgic Requests client profile
- [ ] Add CC's personal brand profile
- [ ] Client routing in CLAUDE.md — detect which brand from context

### Phase 5: Integration Testing
- [ ] Verify 3-way pulse read/write works across all agents
- [ ] Test spend gate flow end-to-end
- [ ] Verify routing: marketing question → Maven, not Bravo
- [ ] Verify content pipeline: Maven creates → Bravo approves strategy → Late publishes

## Obsidian Links
- [[brain/SOUL]] | [[brain/AGENTS]] | [[brain/STATE]]
- [[brain/ORCHESTRATION]] | [[brain/APP_REGISTRY]]
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]]
