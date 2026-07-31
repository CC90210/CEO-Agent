---
description: "Defines the four-agent operating system architecture with roles, scopes, decision rights, and communication protocols"
tags: [architecture, c-suite, multi-agent]
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
---
# AGENT ARCHITECTURE — Four-Agent Operating Model

> **Purpose:** Defines the organizational structure, decision rights, communication protocols, and inter-agent conventions for CC's full AI operating system — the C-Suite (business) + Aura (life/home).
> **Last updated:** 2026-04-18

## The Four Agents

```
CC (Final Authority — human decision-maker)
│
├── Bravo (CEO)     — Strategy, clients, partnerships, vision
│   Project: C:\Users\User\Business-Empire-Agent
│   GitHub: CC90210/CEO-Agent
│   Pulse:   data/pulse/ceo_pulse.json
│   Orchestrates apps: ig-setter-pro (PULSE)
│
├── Atlas (CFO)     — Money, tax, research, compliance, wealth
│   Project: C:\Users\User\APPS\CFO-Agent
│   GitHub: CC90210/CFO-Agent
│   Pulse:   data/pulse/cfo_pulse.json
│
├── Maven (CMO)     — Brand, content, ads, funnels, growth, multi-client marketing
│   Project: C:\Users\User\CMO-Agent
│   GitHub: CC90210/CMO-Agent
│   Pulse:   data/pulse/cmo_pulse.json
│   Orchestrates apps: ad-engine (Remotion + Meta Ads + Shopify)
│
├── Aura (Life/Home) — CC's personal life + apartment agent. Habits,
│   accountability, routines, presence detection, voice/clap triggers,
│   smart-home control. Lives WITH CC (and roommate Adon).
│   Project: C:\Users\User\AURA
│   GitHub:  CC90210/Aura-Home-Agent
│   Pulse:   data/pulse/aura_pulse.json (create on first joint session)
│   Orchestrates: Home Assistant (RPi5 hub), voice agent, smart mirror,
│                 ESP32 sensors, Govee/Sonos/locks/cameras
│
└── Lex (Legal/Counsel) — In-house counsel: contract drafting, review,
    legal-risk triage. The first VERTICAL PRODUCT agent (sold to tenants,
    not just internal). Not a licensed attorney — never gives legal advice
    (UPL gate). Product-first + multi-tenant.
    Project: C:\Users\User\APPS\Lex-Agent
    GitHub:  CC90210/Lex-Agent
    Pulse:   data/pulse/lex_pulse.json (create on first session)
```

> **Fleet expansion (2026-06-18):** Lex (legal/counsel) is the first vertical *product* agent — sold to tenants, architected multi-tenant from day one. Sales/SDR and Customer-Support agents are next on the roadmap. The "four-agent" framing below describes the core C-suite + life agents; vertical product agents extend the fleet on the same forge + command-center + RLS pattern.

## Business vs Life Scope (the big split)

The 4 agents divide along two axes:

| Scope | Agents | Mission |
|-------|--------|---------|
| **Business** (C-Suite) | Bravo + Atlas + Maven | Run OASIS AI + client portfolio — revenue, money, marketing |
| **Life / Home** | Aura | CC's apartment, habits, routines, health, accountability |

These don't overlap operationally — Aura never touches business ops, and the C-Suite never controls the thermostat. But they **do** share awareness via pulses: if Atlas says "runway is tight," Aura might suggest skipping takeout. If Bravo closes a big deal, Aura celebrates it in the apartment. If Maven has a video shoot tomorrow, Aura sets the lighting.

## Shared Browser Intelligence Layer

Browser Harness is the shared direct-browser layer across Bravo, Atlas, Maven, Aura, and Hermes/client agents. Bravo owns the installation, diagnostics, safety rules, and starter domain-skill library in `browser/`. Each agent inherits the power but not unlimited permission:

| Agent | Browser Scope | Hard Gate |
|---|---|---|
| Bravo | business dashboards, GitHub, Supabase, Vercel, n8n, Stripe read-only, Google Workspace, client portals | no outbound/admin/production/destructive action without CC approval |
| Atlas | finance, tax, bank, accounting, Stripe finance views | no money movement, filing, refund, subscription, or bank change without CC approval |
| Maven | content platforms, ad dashboards, analytics, Canva, LinkedIn/X | no publish, DM, campaign, budget, or billing change without CC approval |
| Aura | home dashboards, router/local devices, Home Assistant | no locks, cameras, alarms, resets, or privacy-sensitive views without CC approval |
| Hermes/client agents | supplier portals, warehouse/order systems, client workflows | per-client approval profile and audit trail required |

Browser Harness is for authenticated UI work and compounding domain skills. It never bypasses the V5.6 outbound chokepoint or the finance/production safety gates.

## PULSE vs Agents (important clarification)

**PULSE** (ig-setter-pro) is an **app**, not an agent. It's CC's DM automation product (ManyChat replacement). It's one of many apps in the OASIS portfolio — alongside PropFlow, Nostalgic Requests, cc-funnel, TIKTIK, Skool community, etc. The 4 agents OPERATE these apps; they are not themselves apps.

## Decision Rights Matrix

| Question | Owner | Advisor(s) |
|----------|-------|-----------|
| "How much runway do I have?" | **Atlas** | — |
| "Which client to pursue?" | **Bravo** | Maven (market fit), Atlas (pricing) |
| "What content to post?" | **Maven** | Bravo (brand alignment) |
| "Should I raise prices?" | **Bravo** | Atlas (tax impact), Maven (positioning) |
| "Can I afford paid ads?" | **Atlas** (spend gate) | Maven (execution plan) |
| "Incorporate now or wait?" | **Atlas** | — |
| "What's the brand voice?" | **Maven** | Bravo (strategic direction) |
| "Should I hire?" | **Bravo** | Atlas (cost model), Maven (marketing ROI) |
| "What vertical to target next?" | **Bravo** | Maven (market research), Atlas (revenue model) |
| "Should I pivot a product?" | **Bravo** | Maven (competitive intel), Atlas (financial viability) |
| "What's my apartment status?" | **Aura** | — |
| "Am I hitting my daily habits?" | **Aura** | — |
| "Should I go to the gym now?" | **Aura** (checks presence + schedule) | — |
| "Turn on creative-studio lighting" | **Aura** | — |
| "What did I accomplish this week?" | **Aura** (weekly_reflections.json) | Bravo (business side) |

## Conflict Resolution Protocol

1. **Atlas** has veto power on any **spend** decision (capital preservation > growth)
2. **Bravo** has veto power on any **client-facing / strategic** decision (strategy > tactics)
3. **Maven** executes within the budget Atlas approves and the strategy Bravo sets
4. **Aura** has domain sovereignty over CC's physical environment + habits — business agents can READ Aura's state but cannot override Aura's guest-mode, roommate-sensitive routines, or sleep protection
5. When agents disagree → **CC decides** (final authority)

## 4-Way Pulse Protocol

### Schema Overview

> Local pulse spec: [[data/pulse/README]] (Bravo's CEO-side write contract).

Each agent maintains a pulse file that others read:

| Pulse File | Writer | Location | Readers | Key Data |
|------------|--------|----------|---------|----------|
| `ceo_pulse.json` | Bravo | `Business-Empire-Agent/data/pulse/` | Atlas, Maven, Aura | MRR, strategy, client health, directives |
| `cfo_pulse.json` | Atlas | `APPS/CFO-Agent/data/pulse/` | Bravo, Maven, Aura | Runway, spend gate, tax deadlines, FX rates |
| `cmo_pulse.json` | Maven | `CMO-Agent/data/pulse/` | Bravo, Atlas, Aura | Content pipeline, ad perf, funnel metrics, brand health |
| `aura_pulse.json` | Aura | `AURA/data/pulse/` | Bravo, Atlas, Maven | Presence, mood, habit streaks, sleep/energy, guest mode, apartment status |

### Read Protocol

| Agent | On Session Start, Read: |
|-------|------------------------|
| **Bravo** | `cfo_pulse.json` (runway), `cmo_pulse.json` (brand health), `aura_pulse.json` (CC's energy/availability) |
| **Atlas** | `ceo_pulse.json` (revenue), `cmo_pulse.json` (ad spend), `aura_pulse.json` (lifestyle spend patterns) |
| **Maven** | `ceo_pulse.json` (directives), `cfo_pulse.json` (spend gate), `aura_pulse.json` (CC's creative availability) |
| **Aura** | All 3 C-Suite pulses (to know if CC just closed a deal, is in a lean week, or has a content shoot scheduled) |

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
| `brain/`, `memory/`, `skills/` in CMO-Agent | Maven | READ only |
| `brain/`, `memory/`, `skills/`, `content-studio/`, `ad-engine/` in CMO-Agent | Maven | READ only |
| `brain/`, `memory/`, `skills/` in Aura-Home-Agent | Aura | READ only |
| `data/pulse/ceo_pulse.json` | Bravo | READ only |
| `data/pulse/cfo_pulse.json` | Atlas | READ only |
| `data/pulse/cmo_pulse.json` | Maven | READ only |

**Golden rule:** Update in-place, don't spawn. Each agent modifies only files in its own project.

## Shared Database (All 3 Agents)

All three C-Suite agents share a single **Supabase project** (`phctllmtsogkovoilwos`) as their long-term memory and cross-agent analytics layer. See [`../CMO-Agent/brain/SHARED_DB.md`](../../CMO-Agent/brain/SHARED_DB.md) for the full schema + conventions.

| Layer | Where | Purpose |
|-------|-------|---------|
| **Now-state (pulse)** | Each agent's `data/pulse/*.json` | Fast, local, survives DB outages |
| **Long-term memory** | Shared Supabase `phctllmtsogkovoilwos` | Traces, patterns, session logs, skill activation |
| **App-specific data** | Each app's own DB (Turso for PULSE, etc.) | App sovereignty |

Every Supabase row written by any agent MUST include `agent: 'bravo' | 'atlas' | 'maven'` for filtering and audit. RLS enforces that an agent can only write rows with its own name.

## Cross-Agent Read Access (Delegation & Orchestration)

Every agent has **full read access** to every other agent's file tree. This is non-negotiable — it's how intelligent delegation works without duplicating knowledge.

| Read | What to Look For |
|------|-----------------|
| `C:\Users\User\Business-Empire-Agent\brain\` | Current strategy, OKRs, decision matrix, CEO directives |
| `C:\Users\User\Business-Empire-Agent\skills\` | CEO-domain capabilities (revenue-ops, client-success, sales-closing, NEPQ, meeting-automation) |
| `C:\Users\User\APPS\CFO-Agent\brain\` | Runway, tax rules, FX context, wealth strategy |
| `../CFO-Agent/skills/` | Financial skills (tax-canada, trading-execution, wealth-projection) |
| `../CMO-Agent/brain/clients/` | Brand voice, target ICP, active campaigns per brand |
| `C:\Users\User\CMO-Agent\brain\clients\` | Brand voice, target ICP, active campaigns per brand |
| `C:\Users\User\CMO-Agent\skills\` | Marketing skills (content-engine, ad-copywriting, funnel-management, elite-video-production) |
| `C:\Users\User\CMO-Agent\ad-engine\` | Remotion video ad templates + Meta Ads SDK |
| Pulse files (`data/pulse/*.json`) | Real-time state sync across all 3 agent repos |

**Write rule:** Every agent writes **only** inside its own project directory. Never reach across to modify another agent's files — that's a sovereignty violation. If you need another agent to change something, update your pulse with a request; they'll read it and act.

**Delegation example:**
```
User asks Bravo: "Plan a Meta ad for PULSE"
  → Bravo reads ../CMO-Agent/skills/content-engine/SKILL.md
  → Bravo reads ../CMO-Agent/brain/clients/oasis-ai.md
  → Bravo writes a strategic brief to ceo_pulse.json
  → User reopens Maven: Maven reads ceo_pulse.json
  → Maven executes the ad launch
```

**Tool sharing:** Each agent's `scripts/` directory is a set of CLI tools. Other agents may *invoke* (not modify) these scripts via subprocess. If Bravo needs to send an email, it can shell out to `../CMO-Agent/scripts/integrations/email_engine.py` (or the local Bravo copy still in Business-Empire-Agent during transition).

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
| Marketing-Agent (HQ) | `C:\Users\User\CMO-Agent` | Production | 16 agents, 19 skills, Meta + Google Ads |
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
| ../CMO-Agent/content-studio/ | Business-Empire-Agent/ | PENDING |

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

### Phase 2: Maven Identity Transformation (Next Session — IN CMO-Agent/)
- [ ] Rewrite `SOUL.md` — AdVantage V2.0 → Maven V1.0 (multi-client CMO, not single-client ad manager)
- [ ] Rewrite `CLAUDE.md` — Add CC's brands (OASIS AI, PropFlow, Nostalgic Requests), multi-client routing, pulse protocol
- [ ] Create `GEMINI.md` — Maven entry point for Gemini CLI runtime
- [ ] Create `ANTIGRAVITY.md` — Maven entry point for Antigravity IDE runtime
- [ ] Add `data/pulse/` directory with cmo_pulse.json read/write logic
- [ ] Add cross-agent pulse reading (ceo_pulse.json, cfo_pulse.json)

### Phase 3: Skill Migration (Requires CC Approval)
- [ ] Copy 10 marketing skills from Business-Empire-Agent → Marketing-Agent
- [ ] Move ../CMO-Agent/content-studio/ Remotion setup to Marketing-Agent
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
