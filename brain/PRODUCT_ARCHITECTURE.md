---
tags: [product, architecture, business-in-a-box, clonable]
---

# PRODUCT ARCHITECTURE — Business in a Box

> How CC's 4-agent C-Suite becomes a distributable product: every solo founder clones the repos, customizes a thin personalization layer, and has a working CEO/CFO/CMO (+ optional Life agent) in under 60 minutes.

## The Product

**Name (working):** *Business in a Box — Your AI C-Suite*
**What it is:** 3 core AI agents (CEO, CFO, CMO) + optional 4th (Life) that clone, customize, and run on a solo founder's laptop. Not a SaaS. Not a chatbot. A full executive team in 4 git repos.
**Target buyer:** solo founder, agency owner, consultant, SaaS dev doing $0-50K MRR who can't afford to hire a real exec team yet and is tired of chatbot wrappers.
**Differentiator:** not "ask GPT to pretend to be a CFO." Real sovereign agents with shared state (pulse protocol), per-role deep skills, cross-agent coordination, 4-layer memory (markdown + Obsidian + Supabase + claude-mem).

## Two-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   CORE LAYER (canonical, shipped, shared by every buyer)    │
│   ────────────────────────────────────────────────────      │
│   • skills/ — 80+ canonical playbooks (OKRs, NEPQ, 13-week  │
│     cashflow, funnel math, stock research, etc.)             │
│   • agents/ — sub-agent definitions (writer, debugger, etc.) │
│   • brain/ core docs — SOUL template, BRAIN_LOOP,           │
│     INTERACTION_PROTOCOL, C_SUITE_ARCHITECTURE,             │
│     CROSS_AGENT_AWARENESS, SHARED_DB                         │
│   • scripts/ — 50+ CLI tools (supabase_tool, pulse_client,   │
│     stripe_tool, google_tool, email_engine, etc.)            │
│   • Vertical packs — agency, saas, ecom, coaching, creator,  │
│     local-service (pluggable knowledge modules)              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              +
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   PERSONAL LAYER (per-buyer, gitignored, NOT shipped)       │
│   ────────────────────────────────────────────────────      │
│   • personal/USER.md — owner profile, goals, values          │
│   • personal/brands/ — list of brands/clients, voice, ICP    │
│   • personal/ledger/ — financial accounts, bank info         │
│   • personal/goals/ — OKRs, quarterly targets                │
│   • .env.agents — credentials (gitignored)                   │
│   • data/pulse/*.json — live state (gitignored)              │
│   • memory/ — session logs, mistakes, patterns (per-buyer    │
│     learning, gitignored OR separate private repo)           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## What Goes Where (decision tree for every file)

**Is it useful to EVERY solo founder?** → Core layer (git-tracked)
**Is it specific to the buyer's business or person?** → Personal layer (gitignored OR `personal/` dir)
**Is it infrastructure that should be configured (not content)?** → .env.agents.template with placeholder keys

### Examples

| File | Layer | Why |
|------|-------|-----|
| `skills/strategic-planning/SKILL.md` | CORE | OKR framework same for everyone |
| `skills/client-success/SKILL.md` | CORE | Health scoring methodology universal |
| `brain/SOUL.md` | CORE (template) + PERSONAL (filled) | Template ships with structure; buyer fills their identity |
| `brain/USER.md` | PERSONAL | CC-specific → must be buyer-specific |
| `brain/clients/*.md` | PERSONAL | Each buyer's clients/brands |
| `data/pulse/ceo_pulse.json` | PERSONAL | Live financial state, MRR figures |
| `skills/content-engine/SKILL.md` | CORE | Content voice framework + calibration rules |
| `memory/MISTAKES.md` | PERSONAL (template empty in CORE) | Each buyer accumulates their own |
| `.env.agents` | PERSONAL (gitignored) | Credentials |
| `.env.agents.template` | CORE | Documents what keys are needed |

## Distribution Model

### Option A — Public template, buyer forks
```
CC90210/CEO-Agent (public template, read-only)
    └─ buyer forks → buyer/CEO-Agent-private (their customized fork)
        └─ runs on their machine
        └─ `git pull upstream main` to get new skills over time
        └─ merge conflicts resolve to: always take upstream for core/, always take theirs for personal/
```

**Pros**: free to distribute, standard GitHub flow, buyers own their data
**Cons**: buyer needs git literacy; upstream merges require conflict resolution

### Option B — Paid template marketplace
Same as A but gated: buyer gets an install key after purchase, unlock via GitHub private template → clone.

### Option C — Managed hosted version
CC runs the infrastructure, buyer pays monthly, buyer's data stored in CC's Supabase project (multi-tenant with RLS).

**Recommendation for V1**: Option A with an optional managed-setup upsell ($500-$2K one-time "I'll install it on your machine + configure your env") while we prove the product-market fit. Migrate to Option B when we have 10+ paying customers.

## Clone Flow (Buyer Experience)

```bash
# 1. Clone the 3 core agents (life agent optional)
git clone https://github.com/cc90210/CEO-Agent.git
git clone https://github.com/cc90210/CFO-Agent.git
git clone https://github.com/cc90210/CMO-Agent.git

# 2. Customize the personalization layer
cd CEO-Agent/personal
cp USER.template.md USER.md
# Fill in: your name, business, goals, values

cp brands/example-brand.md brands/my-brand.md
# Fill in: your brand voice, ICP, competitors

cp .env.agents.template ../.env.agents
# Fill in: your API keys

# 3. Bootstrap the shared Supabase
python scripts/setup_shared_db.py
# Creates the Supabase project + schema for your agents

# 4. Run first session
# Open CEO-Agent in Claude Code / Cursor / VSCode
# Say: "hi"
# Agent reads SOUL + USER + pulse, greets you
```

## Vertical Packs (pluggable)

Each buyer picks ONE vertical at install. Pack unlocks vertical-specific skills + templates + knowledge:

| Vertical | What the pack adds to CMO | What it adds to CEO | What it adds to CFO |
|----------|---------------------------|--------------------|--------------------|
| **Agency** | Utilization math, SOW templates, retainer pricing | Client concentration tracking, scope creep guard | Project-based cashflow, receivables aging |
| **SaaS** | Freemium funnel, trial-conversion optimization | MRR cohort analysis, churn triage | LTV/CAC per cohort, net-revenue retention |
| **E-commerce/DTC** | Shopify abandoned cart, product ad templates, LTV segmentation | AOV/repeat-rate levers, seasonality planning | COGS calculation, inventory cashflow |
| **Coaching/Info-products** | Webinar funnel, high-ticket sales page, email sequences | Cohort ops, offer refinement | Payment plan cashflow, tax on earned income |
| **Creator/Personal Brand** | Content-engine with platform-native hooks, audience research | Collab deal structuring, sponsorship rates | Creator tax (1099, T2125), income smoothing |
| **Local Service** | Meta lead ads, Google LSA, local SEO, reputation mgmt | Crew ops, seasonal demand | Job-costing, trade tax deductions |

Each pack = a folder under `skills/verticals/<vertical>/` installed on buyer opt-in. CC's own instance ships with **Agency + Creator** packs activated (for OASIS + his personal brand).

## What CC's Instance Looks Like (reference implementation)

CC's 4-agent setup becomes the flagship reference customer. In marketing:
- "This is the same system running my agency, OASIS AI, which hit $5K MRR using these exact agents."
- Public commit history on GitHub = proof it's real.
- CC's content ("here's how I used Bravo to close my biggest client") = organic marketing for the product.

CC's personal layer (brands/clients profiles, SunBiz history, etc.) stays in his own fork, private.

## Update Path for Buyers

When CC ships improvements to core skills:
```bash
# Buyer, in their fork:
git remote add upstream https://github.com/cc90210/CEO-Agent.git
git fetch upstream
git merge upstream/main

# Conflicts: .gitattributes merge strategies enforce:
#   core/  → always take upstream
#   personal/ → always take ours
#   brain/  → 3-way merge (manual for critical docs, auto for peripherals)
```

Documented in each agent's `UPGRADE.md`.

## Self-Improvement Skill = Product Differentiator

The `self-improvement-protocol/` skill we just built is not just infrastructure — it's **the pitch.** Other AI wrapper products are static; this one heals itself, optimizes itself, develops new skills, learns from mistakes. Every agent improves for every buyer continuously. That story sells.

## Pricing (proposed tiers)

| Tier | What you get | Price |
|------|--------------|-------|
| **Starter** | 3 core agents (CEO + CFO + CMO), 1 vertical pack, install guide, community support | **$497 one-time** |
| **Pro** | Starter + Life agent (Aura), 2 more vertical packs, 1-hour onboarding call with CC, priority support | **$1,497 one-time** |
| **Managed Install** | Pro + CC/OASIS sets it up on your machine, configures your env, runs first week with you | **$3,997 one-time** |
| **Fractional** | Managed Install + monthly 1-hour strategy call + priority skill requests | **$497/mo recurring** |

(Price points to validate; tune after first 10 buyers.)

## Compliance / Legal

- Each buyer's instance runs on their own machine with their own API keys — no data touches CC's infrastructure (unless they choose hosted)
- No fiduciary/legal/medical advice claims — Atlas advises, never auto-transacts; CMO never sends without buyer approval; CEO never signs contracts
- Open-source license: core repos MIT (or Apache 2.0); personal folder never touched
- Terms of Service: buyers acknowledge "this is a tool, not a replacement for a human CPA/lawyer/exec"

## Rollout Roadmap

**Phase 1 — clean split (this session + next)**
- [ ] Move CC-specific content in each agent to `personal/` directories
- [ ] Create `.template` versions of SOUL.md, USER.md, brand docs
- [ ] Document clone + customize flow in each agent's README
- [ ] Write vertical-pack skeleton (6 verticals, placeholder skills)

**Phase 2 — CC's own fork (after split)**
- [ ] CC's fork becomes private: `cc90210-personal/CEO-Agent-private`
- [ ] Public repos become the product: `cc90210/CEO-Agent`, `CFO-Agent`, `CMO-Agent`, `Aura-Home-Agent`
- [ ] Populate vertical packs with real playbooks (from research — see PRODUCT_VERTICALS.md)

**Phase 3 — launch prep**
- [ ] Landing page
- [ ] Loom walkthrough (CC demos his own setup)
- [ ] Sell to 5 beta customers at 50% discount
- [ ] Iterate based on install friction

**Phase 4 — scale**
- [ ] Gumroad or Stripe checkout for Starter/Pro tiers
- [ ] Managed Install offered via booking (calendar.app.google)
- [ ] Skool community for buyer support
- [ ] CC's content becomes top-of-funnel

## Related Docs

- [[C_SUITE_ARCHITECTURE]] — governance
- [[CROSS_AGENT_AWARENESS]] — pulse protocol
- [[RAG_SYSTEM]] — memory stack
- `skills/self-improvement-protocol/SKILL.md` — the self-healing/evolving loop every agent runs
- `brain/CANONICAL_ROLES.md` (being written) — canonical CEO/CFO/CMO scope
- `brain/PRODUCT_VERTICALS.md` (being written) — vertical packs + lead management + marketing research
- `brain/AGENT_GAP_AUDIT.md` (being written) — current state vs canonical

## The Meta-Point

What CC is building **is exactly what every solo founder needs** — and he's dogfooding it by building his own business with it. That's the most powerful possible product-market fit signal: the founder uses the product every day, and the product gets better every day because the founder ships improvements.
