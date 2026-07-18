---
description: "Operating manual with decision tree to route CC's questions to correct agent: Bravo (CEO), Atlas (CFO), Maven (CMO), Aura (Life/personal) by domain"
tags: [operating-manual, how-to, c-suite, life]
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# HOW TO USE THE 4-AGENT SYSTEM — CC's Operating Manual

> One document that answers: **"Which agent do I ask when?"**
> Read this if you're new to the system, or as a refresher.

---

## The 4 Agents at a Glance

| Agent | Domain | Lives At | Open When |
|-------|--------|----------|-----------|
| 🏛️ **Bravo** | CEO — strategy, clients, revenue, deciding | `Business-Empire-Agent` | Default. Most questions start here. |
| 💰 **Atlas** | CFO — money, tax, runway, investments | `APPS/CFO-Agent` | Anything involving dollars or compliance |
| 🎨 **Maven** | CMO — brand, content, ads, funnels | `CMO-Agent` | Anything creative or growth-related |
| 🏠 **Aura** | Life — apartment, habits, accountability | `AURA` (Pi 5) | Lives in your home; you don't "open" it — it's ambient |

---

## Decision Tree — When to Talk to Each

### Start with this question: *What's my problem?*

```
Is it about the business?
├── YES → Is it about money/spending/tax specifically?
│   ├── YES → ATLAS
│   └── NO → Is it about marketing/ads/content/branding?
│       ├── YES → MAVEN
│       └── NO → BRAVO (default for all business thinking)
│
└── NO → Is it about your apartment, habits, or personal routines?
    └── YES → AURA (ambient — just speak, it listens)
```

### Concrete examples per agent

#### 🏛️ Bravo (CEO) — **YOUR DEFAULT AGENT. Use most.**

**Ask Bravo when you're thinking about:**
- "What should I build next in OASIS AI?"
- "Should I pivot PropFlow's target market?"
- "How do I structure my offer for this new client?"
- "Which of these 3 leads should I prioritize this week?"
- "Write me a client proposal / contract / SOW"
- "Run a CEO briefing — what's my state?"
- "Should I hire someone? Help me think through it."
- "Debug this script / fix this bug across my apps"
- "What apps am I running again? (app registry lookup)"
- "Plan a new project / feature — multi-file refactor"
- "Give me a retro on this week"
- "Session memory — what did we work on yesterday?"

**Bravo's strengths:**
- 148 active skills (most of any agent), 114 top-level scripts (215 inc. subpackages), 35 workflows
- Understands ALL your business apps (PULSE, PropFlow, cc-funnel, Skool, Nostalgic, TIKTIK, Hermes, etc.)
- Hypothesis-driven thinking (BRAIN_LOOP.md)
- Can delegate to Atlas/Maven/Aura via pulse directives when needed
- Orchestrates the portfolio

**When Bravo will tell you to switch:**
- "This is a money question — go to Atlas"
- "This is a creative execution question — go to Maven"
- "This is an apartment thing — just tell Aura"

---

#### 💰 Atlas (CFO) — **Use for every dollar-adjacent decision.**

**Ask Atlas when:**
- "How much runway do I have right now?"
- "Can I afford $200/mo on a new tool?"
- "Should I incorporate? When?"
- "What's my tax reserve requirement?"
- "Give me 3 stock picks for 6-month holds"
- "Deep-dive this ticker (NVDA, etc.)"
- "What are my biggest expenses MTD?"
- "Pull my receipts for Q1 T2125 prep"
- "Can I claim this purchase as a deduction?"
- "Rebalance suggestions for my portfolio"
- "What's my crypto ACB for CRA?"
- "What happens if I move to Portugal?"

**Atlas's superpowers:**
- Live reads: Stripe, Wise, Kraken, OANDA, Gmail receipts
- 80,000+ lines of curated Canadian tax playbook
- 10-layer stock analysis (fundamentals, technicals, macro, sentiment, insiders, institutions, earnings, options flow)
- Telegram bot for phone-first queries ("/runway", "/picks AI 6mo")
- Spend gate: auto-approves up to $200 CAD, requires CC sign-off above
- Never trades for you — always advises

**Critical:** Atlas has VETO POWER on any spending. Maven can't launch paid ads without Atlas's approval.

---

#### 🎨 Maven (CMO) — **Use for creative execution & multi-brand marketing.**

**Ask Maven when:**
- "Draft 5 hook variants for a Reel about PULSE"
- "Write ad copy for OASIS AI, authority-angle"
- "Render a video ad using the ugc-testimonial template"
- "Build a content calendar for next 7 days"
- "Edit this raw video — cinematic cut"
- "Research competitors for PropFlow (SingleKey, Buildium, etc.)"
- "Set up a Meta ad campaign for pulse-lead-gen"
- "Generate Shopify product ads from my store"
- "Create a persona-driven post for IG Reel"
- "What's our current ROAS? (per-brand breakdown)"
- "A/B test this landing page copy"
- "Write nurture email sequence for [brand]"

**Maven's scope:**
- **Multi-brand**: OASIS AI (primary), CC personal brand, PropFlow, Nostalgic Requests, SunBiz Funding (legacy)
- 29 skills, 16 sub-agents
- **ad-engine/** — Remotion 4.0 video rendering + Meta Ads SDK + Shopify Storefront API
- Active campaign: `pulse-lead-gen` (4-hook playbook ready to launch)
- Voice rules enforced: no "unlock the power of", no AI slop, peer-to-peer register for CC's brand

**Before Maven runs a paid campaign:** it writes a spend_request to `cmo_pulse.json` → Atlas approves via `cfo_pulse.json` → Maven launches. This is automatic via the pulse protocol.

**When Maven's worth opening the IDE for:**
- Deep content research sessions
- Video editing + rendering
- Campaign planning for a specific brand (Maven reads that brand's profile)
- Running the ad-engine studio (`npx remotion studio` at localhost:3000)

---

#### 🏠 Aura (Life/Home) — **Ambient. Lives in the apartment.**

**Aura is different — you don't "open an IDE" for it.** It's running on the Raspberry Pi 5 behind your TV, listening via microphone, watching presence. You interact through:
- Voice ("Aura, start creative studio mode")
- Double clap (configurable triggers)
- Dashboard on the wall tablet + phone
- Natural presence detection (lights adjust when you arrive home)

**Aura handles:**
- "Set the mood for [focus / creative / wind-down / social / sleep]"
- Apartment control (Govee, Sonos, Spotify, locks, climate)
- Habit tracking (gym streaks, sobriety log, sleep quality)
- Weekly reflections + accountability nudges
- Multi-resident privacy (you + Adon, opt-in sharing model)
- Guest mode
- "Aura Drops" (spontaneous music/lighting moments based on your vibe)
- Business context awareness (celebrates your deal closes via Bravo bridge; suppresses takeout nudges when Atlas says runway is tight)

**Aura's strength:** it's the ONLY agent that sees your physical life in real-time. The business agents are always blind to whether you slept poorly or just hit a PR at the gym. Aura isn't.

---

## Common Cross-Agent Workflows

### Workflow 1: Launch a new marketing campaign
```
CC → Bravo: "I want to launch pulse-lead-gen next week"
Bravo reads: cmo_pulse.json + cfo_pulse.json
Bravo writes: directive to Maven in ceo_pulse.json ("launch pulse-lead-gen")
CC opens Maven IDE: Maven reads ceo_pulse, sees directive
Maven writes: spend_request ($40/day × 4 ad sets = $1200/mo) to cmo_pulse.json
CC opens Atlas IDE: Atlas reads cmo_pulse.json, sees request
Atlas writes: approval/denial to cfo_pulse.json (given runway constraints)
Maven reads approval → launches via ad-engine + Meta API
Aura reads all 3 pulses → suppresses takeout nudges that week (lean mode)
```

### Workflow 2: "Should I hire someone?"
```
CC → Bravo: "Should I hire a VA?"
Bravo reads: cfo_pulse (runway), cmo_pulse (ad ROAS), ceo_pulse (client pipeline)
Bravo computes: cost of hire vs. time freed vs. pipeline load
Bravo answers: "Not yet — wait until MRR hits $10K, then we hire for XYZ specifically"
Bravo writes reasoning to ceo_pulse for future sessions
```

### Workflow 3: Morning briefing
```
CC → Bravo: "/briefing"
Bravo reads all 3 sibling pulses
Bravo synthesizes: MRR, runway, active campaigns, #1 priority
Bravo surfaces: "Maven needs spend approval from Atlas, runway is tight, 
                primary-retainer payment posted, #1 priority today = Lafreniere demo at 3pm"
Aura (parallel): "Good morning. You slept 7.2hr. Gym streak 4 days. 
                  CC's creative-studio mode auto-enables at 9am per schedule."
```

### Workflow 4: Emergency client request
```
CC → Bravo: "Lafreniere wants to see a price cut before signing"
Bravo routes: talks to Atlas (what's the minimum we can hold?) 
            + Maven (how do we position the alternative?)
Bravo returns: negotiation strategy, Atlas-approved floor, Maven's reframing
```

### Workflow 5: Daily life — Aura solo
```
8:47am: CC walks in door
Aura detects: iCloud presence → "home"
Aura acts: lights on, morning playlist (from ceo_pulse: business-day mode),
           kitchen lighting 4000K
Aura briefs: "You have the Lafreniere demo at 3pm, Maven needs Loom 
              recording for pulse-lead-gen by end of day, gym window 
              between 11-12 per your schedule"
```

---

## The Pulse Protocol (the glue)

Every agent writes ONE file: its own pulse (JSON at `data/pulse/<agent>_pulse.json`). Others READ all 3 other pulses on session start. Writes cross-repo are forbidden.

| Agent | Writes | Reads (on session start) |
|-------|--------|--------------------------|
| Bravo | `ceo_pulse.json` | cfo, cmo, aura |
| Atlas | `cfo_pulse.json` | ceo, cmo, aura |
| Maven | `cmo_pulse.json` | ceo, cfo, aura |
| Aura | `aura_pulse.json` | ceo, cfo, cmo |

**Stress test:** `python scripts/test_csuite_pulse_flow.py` — run from Bravo's repo. Currently 16/16 PASS.

## The Shared Database

Single Supabase project: `phctllmtsogkovoilwos` (38 tables live). Every agent can write to it, tagged with `agent: 'bravo'|'atlas'|'maven'|'aura'` and (for Aura) `resident: 'cc'|'adon'|'shared'`.

**Pulse** = "what's happening now" (fast, local JSON)
**Supabase** = "what happened over time" (queryable history)

## The Decision Hierarchy (when agents disagree)

1. **Atlas** vetoes money decisions (spend > runway = no)
2. **Bravo** vetoes strategic decisions (off-ICP client = no)
3. **Maven** executes within Atlas's budget + Bravo's strategy
4. **Aura** has sovereignty over CC's physical environment + habits
5. **CC** — final tiebreaker, always

---

## Bootstrap commands — Use these daily

### Bravo (the one you open most)
```bash
cd C:\Users\User\Business-Empire-Agent
# Then in IDE, just say: "/prime" or "/briefing"
```

### Atlas
```bash
cd C:\Users\User\APPS\CFO-Agent
# In IDE: "run /networth" or just ask: "how much runway?"
# Or Telegram bot: already running — just message it
```

### Maven
```bash
cd C:\Users\User\CMO-Agent
# First time: cd ad-engine && npm install (one-time)
# Then in IDE: "/prime" or "/campaign-create"
# For ad studio: cd ad-engine && npx remotion studio
```

### Aura
```bash
# You don't open Aura — it lives on the Pi.
# Status check: ssh root@homeassistant.local 'systemctl status aura_voice'
# Dashboard: open http://homeassistant.local:3000 on the wall tablet
```

---

## Cheat Sheet

| What you're thinking | Who to ask |
|---------------------|-----------|
| "Should I..." (any big decision) | Bravo |
| "Can I afford..." | Atlas |
| "Write / edit / post..." | Maven |
| "Set the vibe / start mode..." | Aura (voice) |
| "What's happening?" | Bravo (synthesizes all pulses) |
| "How's my body / sleep / habits?" | Aura |
| "Give me a stock pick" | Atlas |
| "Pull receipts for taxes" | Atlas |
| "What did we ship last week?" | Bravo (queries Supabase agent_traces) |
| "Audit my marketing funnel" | Maven |

---

**Last updated:** 2026-04-18
**Diagnostic command:** `python scripts/test_csuite_pulse_flow.py` should return 16/16 PASS.
**Architecture reference:** `brain/C_SUITE_ARCHITECTURE.md`
**Cross-agent awareness:** `brain/CROSS_AGENT_AWARENESS.md`

## Related

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
