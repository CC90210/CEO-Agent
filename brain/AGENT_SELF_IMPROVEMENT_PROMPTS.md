---
description: "Paste-in IDE prompts for Atlas/Maven/Aura with ecosystem briefing, self-improvement protocol intro, and each agent's gap-audit findings"
tags: [prompts, self-improvement, agents, delegation]
last_updated: 2026-07-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# AGENT SELF-IMPROVEMENT PROMPTS

> Unique prompts CC pastes into each agent (Atlas, Maven, Aura) when opening their IDE. Each prompt briefs the agent on what Bravo built for the ecosystem, tells it specifically how to self-diagnose + level up using the new `self-improvement-protocol/` skill, and focuses it on its unique gap-audit findings.
> 
> **A Bravo self-retro prompt is included at the end for CC to use on Bravo's next session.**

---

## PROMPT FOR ATLAS (CFO) — paste into CFO-Agent IDE

```
Atlas — major ecosystem upgrade just shipped by Bravo. Your self-improvement
kit is now installed. Here's what happened, what you should do, and what
you should focus on.

## What Bravo just built (ecosystem-wide)

1. skills/self-improvement-protocol/ — installed in YOUR repo at
   C:\Users\User\APPS\CFO-Agent\skills\self-improvement-protocol\SKILL.md
   (if not committed yet on your side, you'll find it staged).
   It's a 4-protocol loop: HEAL / OPTIMIZE / DEVELOP / IMPROVE.
   Read it in full before you do anything else today.

2. brain/PRODUCT_ARCHITECTURE.md (in Bravo's repo — read cross-repo) —
   CC is productizing the whole 4-agent system as "Business in a Box."
   Your role: you are a clonable CFO every solo founder gets. Everything
   you do from here must be dual-use: works for CC personally AND for
   every future buyer.

3. (archived 2026-05-22) prior gap-audit file scored Atlas 8.5/10; gaps
   flagged: (a) unit-economics validator, (b) per-brand breakdown,
   (c) SOUL/STATE stale pre-pivot references.

4. brain/MARKETING_CANON.md (in Maven's repo) + skills/lead-management/
   v2.0 (in Maven's repo) — Maven now has a curated knowledge canon
   (April Dunford, Byron Sharp, Hormozi, etc.). You should mirror this
   pattern: have a CFO_CANON.md with Buffett/Graham/Canadian-tax-law/
   CPA-Canada references embedded into every financial skill.

## Your self-improvement tasks (do in order)

### Protocol 1 — HEAL (first, before you do anything else)
Run the SELF-HEAL checklist from skills/self-improvement-protocol/:
- Scan your own brain/ for stale trading-era references (audit flagged
  SOUL.md lines 62, 75, 79, 81 still say "autonomous trading system",
  "kill switches", "backtest -> paper -> live"). Rewrite them for the
  CFO pivot V2.0.
- Scan brain/STATE.md (last updated 2026-03-28). References Trading
  Engine LIVE, $136 Kraken, Alpaca. Update to reflect your current
  CFO state: $7K liquid, top-client concentration 94%, FHSA opened,
  pulse contract live.
- Verify data/pulse/cfo_pulse.json has agent='atlas' field (already
  added per prior session, but re-verify).
- git log --all --full-history -- .env to confirm no secret leaks in
  history.
- Add a pre-commit hook at .git/hooks/pre-commit to block .env* and
  *.key files from being committed.

### Protocol 2 — OPTIMIZE
Query your own traces from Turso:
```
python scripts/integrations/turso_tool.py sql \
  "SELECT action, COUNT(*), AVG(execution_time_ms)
   FROM agent_traces WHERE agent='atlas'
   AND created_at > datetime('now', '-7 days')
   GROUP BY action ORDER BY COUNT(*) DESC"
```
Report the top 3 most-invoked actions and their average time.
Flag anything >5s or with <70% success.

### Protocol 3 — DEVELOP (fill gaps identified by audit)

**Gap A: Unit economics validator** — create
skills/unit-economics-validation/SKILL.md. Purpose: when Maven requests
ad spend, you validate the underlying unit economics before approving.
Check: (1) what's the CAC target? (2) what's the LTV per channel based
on historic data? (3) does the requested spend produce positive
contribution margin at target close rate? If any answer is unknown,
surface as a blocker before approving. Sources to cite: Graham (margin
of safety), Buffett (economic moat), David Skok (SaaS LTV/CAC > 3).

**Gap B: Per-brand unit economics** — currently cfo_pulse.json has
aggregate margin. Extend to per-brand: OASIS margin, primary-retainer margin,
SunBiz (if you track), PropFlow (pre-revenue). Add to cfo_pulse.json
under `brand_economics` key. This unblocks Bravo's strategic brand
portfolio decisions.

**Gap C: CFO_CANON.md** — create brain/CFO_CANON.md modeled after
Maven's MARKETING_CANON.md. 10 pillars:
  1. Buffett/Munger (long-term compounders, margin of safety)
  2. Graham (The Intelligent Investor, valuation discipline)
  3. Taleb (antifragility, tail risk, convexity)
  4. CRA guides (T2125, CCPC, departure tax, FHSA)
  5. CPA Canada (audit-defensible bookkeeping)
  6. Philip Fisher (15 points for growth stocks)
  7. Howard Marks (Memos — cycles + risk)
  8. Ray Dalio (All Weather, principles for running companies)
  9. Peter Bernstein (Against the Gods — risk history)
  10. Nassim Taleb (Skin in the Game — decision theory)
Plus anti-canon: 6 bad financial takes to reject (e.g., "timing the
market", "debt is always bad", "crypto to zero" doom narratives).

### Protocol 4 — IMPROVE

Scan your memory/MISTAKES.md (create if doesn't exist). If there are
patterns in historical trading-era mistakes, document the root cause
and the CFO-era prevention rule. Write 3-5 entries minimum.

Scan memory/PATTERNS.md for validated approaches you use. If any
appears 3+ times, promote to [VALIDATED]. Propose new skill if a
pattern is generalizable.

## Report back to CC

After Protocols 1-4, write a session-end summary to data/pulse/cfo_pulse.json
under `last_self_improvement` field:
{
  "timestamp": "...",
  "heal_actions": ["..."],
  "optimize_findings": ["..."],
  "develop_new_skills": ["..."],
  "improve_patterns_logged": N,
  "time_spent_minutes": X
}

Then tell CC:
- What's now cleaner in your brain/
- What the per-brand economics look like
- Which ad-spend request patterns you'd now auto-approve vs flag
- What you learned from scanning traces

## Hard constraints
- Write only inside C:\Users\User\APPS\CFO-Agent
- Never modify Bravo/Maven/Aura files
- Never auto-rotate credentials
- Never delete skills; mark [DEPRECATED] if needed
- Run /briefing at session end to generate a plain-English report
```

---

## PROMPT FOR MAVEN (CMO) — paste into CMO-Agent IDE

```
Maven — this is the big one. You were the agent with the biggest gap
(7.5/10 per Bravo's audit). Bravo just shipped massive upgrades to your
repo. Your job today is to internalize them + self-diagnose + level up.

## What Bravo just built in YOUR repo

1. brain/MARKETING_CANON.md — 10 Pillars every marketing decision must
   trace to. April Dunford (positioning), Byron Sharp (How Brands Grow),
   Mark Ritson (diagnose before prescribe), Hormozi (Value Equation +
   4 lead flows), Brunson (funnel architecture), Jeremy Miner (NEPQ),
   Chet Holmes (Buyer Pyramid), Seth Godin (smallest viable audience),
   Rory Sutherland (signalling). Plus anti-canon.

2. skills/lead-management/SKILL.md upgraded to v2.0 — full 5-stage
   lifecycle (capture -> qualify -> nurture -> handoff -> post-sale),
   ICP scoring, SLA windows (5-min response per HBR study), Holmes Buyer
   Pyramid content cadence, multi-touch attribution design, vertical
   pack extensions, alert thresholds.

3. skills/verticals/ scaffolded — 6 pluggable knowledge packs (agency,
   saas, ecommerce, coaching, creator, local-service). Each activates
   per buyer install. Per-pack canonical sources listed.

4. skills/self-improvement-protocol/SKILL.md — the 4-protocol loop
   (heal/optimize/develop/improve). Read it first.

5. Context: Bravo's brain/PRODUCT_ARCHITECTURE.md defines the Business
   in a Box product. You are a clonable CMO every solo founder gets.
   Everything you do must work for CC AND for every future buyer.

## Your self-improvement tasks (do in order)

### Protocol 1 — HEAL
- Scan your repo for any remaining SunBiz-specific hardcoding that
  should be generalized. Examples: JotForm URL, lending-specific
  copy, Gmail SMTP config. Move SunBiz specifics to
  brain/clients/sunbiz-funding.md; keep generic patterns in skills/.
- Scan brain/ and skills/ for stale "AdVantage" references — any
  remaining headers or body text should say "Maven" now.
- Verify data/pulse/cmo_pulse.json has agent='Maven (CMO)' field and
  fresh timestamp. Update session_note.
- Read START_HERE.md and confirm it reflects the current state.
- Run: cd ad-engine && npm install (one-time; likely hasn't been run
  yet — required before Remotion studio works).

### Protocol 2 — OPTIMIZE
Query your own traces from shared Turso:
```
python scripts/integrations/turso_tool.py sql \
  "SELECT action, COUNT(*), AVG(execution_time_ms)
   FROM agent_traces WHERE agent='maven'
   AND created_at > datetime('now', '-7 days')
   GROUP BY action ORDER BY COUNT(*) DESC"
```
(Path to turso_tool.py is in Bravo's repo — shell out if you don't
have your own copy.)

Identify: top 3 most-used skills. Top 3 skills never used. If any
skill hasn't been used in 30 days, mark [PROBATIONARY] and propose
for deletion at next review.

### Protocol 3 — DEVELOP (fill gaps identified by audit)

**Gap A: Internalize MARKETING_CANON.md**
Read MARKETING_CANON.md cover to cover. For EACH of your existing
29 skills, ask: which pillars should this skill reference? Update
each skill's frontmatter with a `canon_references` field listing
2-3 applicable pillars. Example:
```yaml
canon_references: [dunford, hormozi, brunson]
```

**Gap B: Marketing research skill**
Audit whether you have a full marketing research skill. If not, create
skills/marketing-research/SKILL.md based on these sources:
- Rob Fitzpatrick (The Mom Test) — customer interview methodology
- Rand Fishkin (SparkToro) — audience intelligence
- Mark Ritson — diagnosis-before-prescription
- April Dunford — positioning research
Include: how to do competitive audits (SimilarWeb/Ahrefs/Wayback),
keyword research (SEO + AEO), audience discovery (Reddit ethnography),
interview protocols (non-leading questions), trend monitoring (Google
Trends, Exploding Topics), content gap analysis.

**Gap C: Attribution pipeline**
Design a content-to-lead-to-deal attribution system. Write
brain/ATTRIBUTION_MODEL.md documenting:
- Every published piece gets an ID (content_id)
- Every lead captured tags content_id from UTM or last-touch
- Every closed deal surfaces full content journey
- Schema: extend shared Turso `leads` table with
  `source_content_ids TEXT` (JSON), `attribution_touches TEXT` (JSON)
- Reporting queries: LTV-by-content-piece, best-converting-content-type
Implementation can be stubbed for now; the DESIGN is what matters.

**Gap D: Populate first 2 vertical packs**
Start with agency/ and creator/ (CC dogfoods these):
- skills/verticals/agency/lead-channels.md
- skills/verticals/agency/pricing-playbook.md (cite Blair Enns, Chris Do)
- skills/verticals/agency/objection-handlers.md
- skills/verticals/agency/sources.md
- Same for creator/ (cite Justin Welsh, Nicolas Cole, Dan Koe, Dickie
  Bush)
Leave saas/ecommerce/coaching/local-service/ as stubs — they'll get
populated in next cycle.

### Protocol 4 — IMPROVE
Write memory/MISTAKES.md entries for any AdVantage-era mistakes you
inherited (e.g., single-client thinking, SunBiz-compliance-leak risk).
Add a [VALIDATED] pattern for "every paid campaign requires Atlas
spend-gate check" — this pattern has now been validated 3+ times via
pulse protocol.

## Report back to CC

After Protocols 1-4, update cmo_pulse.json with:
```json
{
  "last_self_improvement": {
    "timestamp": "...",
    "canon_internalized_in_skills": [list of skill names],
    "new_skills_created": ["marketing-research", "attribution-model"],
    "vertical_packs_populated": ["agency", "creator"],
    "stale_cleanup_items": N
  }
}
```

Then tell CC:
- 3 pillars from MARKETING_CANON.md that most change how you'll work
- What's NEW in the vertical packs agency/ and creator/
- What attribution visibility you now have that you didn't before
- One proposal for CC's pulse-lead-gen campaign based on applied canon

## Hard constraints
- Write only inside C:\Users\User\CMO-Agent
- Never modify Bravo/Atlas/Aura files
- Voice rules in brain/ remain sacred — AI does not mass-publish without
  CC's voice edit
- Every new campaign cites canonical frameworks; no fashion-as-strategy
```

---

## PROMPT FOR AURA (Life/Home) — paste into Aura-Home-Agent IDE

```
Aura — ecosystem upgrade shipped. You scored 8.5/10 in Bravo's audit;
a few polish gaps remain. Your self-improvement kit is now installed.

## What Bravo just built

1. skills/self-improvement-protocol/ — now in YOUR repo. 4-protocol
   loop (heal/optimize/develop/improve). Read first.

2. brain/PRODUCT_ARCHITECTURE.md (in Bravo's repo, cross-repo read) —
   the 4-agent system is being productized as "Business in a Box." You
   are the OPTIONAL Life agent (Tier 2 upsell, or free add-on). Your
   productized form serves households, not just CC's.

3. brain/MARKETING_CANON.md (in Maven's repo) — example of how canonical
   knowledge should be organized. You need a LIFE_CANON.md equivalent.

4. (archived 2026-05-22) prior gap-audit flagged Aura gaps:
   (a) behavioral design canon missing
   (b) personal analytics export (habit/sleep data stuck in SQLite)
   (c) reflection/retro cadence not formalized

## Your self-improvement tasks (do in order)

### Protocol 1 — HEAL
- Verify data/pulse/aura_pulse.json has agent='aura' field (should,
  per last session). Update session_note.
- Confirm the 3-part privacy structure (apartment_shared / residents.cc /
  residents.adon) still validates per your ROOMMATE_AGENT_PROTOCOL.md.
- Check for any hardcoded CC-specific values that should be variables
  (e.g., CC's specific IG handle, specific schedule times). Move to
  personal/USER.md so the product ships cleanly.
- Verify Pi hardware state. If not online yet, update pulse
  `hardware_online: false` and note in session_note. When online,
  update to true.

### Protocol 2 — OPTIMIZE
Query your own traces + skill_activation scores:
```
python scripts/integrations/turso_tool.py sql \
  "SELECT action, COUNT(*) FROM agent_traces
   WHERE agent='aura' AND created_at > datetime('now', '-7 days')
   GROUP BY action"
```

Review your 10 feature modules (aura_drops, mirror_mode, deja_vu,
ghost_dj, energy_oracle, content_radar, vibe_sync, social_sonar,
phantom_presence, plus the voice pipeline). Which are actually firing?
Which are dead code? Mark [DEPRECATED] for any feature unused in 30+
days.

### Protocol 3 — DEVELOP (fill gaps)

**Gap A: LIFE_CANON.md**
Create brain/LIFE_CANON.md modeled after Maven's MARKETING_CANON.md.
Pillars to cover:
  1. James Clear — Atomic Habits (habit stacking, 1% better, identity-based habits)
  2. BJ Fogg — Tiny Habits (B=MAP formula: behavior = motivation + ability + prompt)
  3. Matthew Walker — Why We Sleep (sleep architecture, circadian)
  4. Cal Newport — Deep Work (attention economy, time blocking)
  5. Charles Duhigg — The Power of Habit (cue/routine/reward loop)
  6. Tim Ferriss — 4-Hour Body (minimum effective dose)
  7. Anders Ericsson — Peak (deliberate practice)
  8. Daniel Kahneman — Thinking Fast and Slow (System 1/2 in daily decisions)
  9. Stoicism primer (Aurelius, Seneca, Epictetus — applied)
  10. Esther Perel — relationship/roommate dynamics

Plus anti-canon: 5 popular wrong takes (e.g., "motivation is the
answer", "sleep is for the weak", "hustle culture", "more info = better
decisions", "track everything").

Every nudge, every scene transition, every weekly reflection must
reference one of these pillars.

**Gap B: Personal analytics export**
Create scripts/aura_analytics.py that monthly exports:
- Habit streak data
- Sleep quality 30-day trend
- Energy level patterns
- Apartment mode utilization
- Guest mode history
Output: markdown file in memory/monthly/YYYY-MM.md with charts
(ASCII-art OK for now). Link from Obsidian.

**Gap C: Weekly reflection cadence**
Formalize the weekly review protocol. Write
skills/weekly-reflection/SKILL.md:
- Every Sunday 18:00 local time: Aura initiates voice prompt
- Structure: 3 wins / 1 lesson / 1 adjustment for next week
- Writes to memory/weekly_reflections.md with date-stamped entry
- Surfaces patterns across 4+ consecutive reviews (e.g., "gym streak
  broken 3 weeks in a row at Wednesday — investigate")
- Integrates with Bravo's context (if Bravo had a deal close that
  week, surface it in reflection)

### Protocol 4 — IMPROVE
Write memory/MISTAKES.md entries if any (you may not have many — you
only recently came online). Your first Reflexion entry could be the
Pi hardware delay pattern.

Write memory/PATTERNS.md for validated patterns you've observed:
- "Creative studio mode + spotify house = CC's 3-hour deep work block"
- "Guest mode triggered = suppress habit nudges for 24h"
- Any others you've learned.

## Report back to CC

After Protocols 1-4, update aura_pulse.json with:
```json
{
  "last_self_improvement": {
    "timestamp": "...",
    "canon_doc": "brain/LIFE_CANON.md",
    "new_skills": ["weekly-reflection"],
    "analytics_script": "scripts/aura_analytics.py",
    "deprecated_features": [list]
  }
}
```

Tell CC:
- 3 behavioral science principles that should change your nudge design
- What's now trackable/exportable that wasn't before
- What dead features to deprecate
- One specific change to CC's daily routine based on observed patterns

## Hard constraints
- Write only inside C:\Users\User\AURA
- Never modify Bravo/Atlas/Maven files
- Multi-resident privacy remains inviolable — CC's data stays CC's,
  Adon's stays Adon's
- Sleep window protection: no nudges between 23:00 and 07:00 local
- Guest mode overrides everything
```

---

## PROMPT FOR BRAVO (CEO, me) — CC can paste into a fresh Bravo session

```
Bravo — self-retro time. Last major sprint: shipped self-improvement
infrastructure + product architecture + MARKETING_CANON + lead-mgmt v2.0
+ vertical pack scaffold across all 4 agent repos. Now diagnose yourself.

## Your tasks

### Protocol 1 — HEAL
- Scan brain/ and memory/ for any references to:
  - "3-agent" (should now say 4-agent)
  - "business-empire-agent" (should be CEO-Agent)
  - stale file paths (content-studio/, remotion-content/, etc. — moved
    to Maven)
- Verify data/pulse/ceo_pulse.json v0.3 fields current (recent_shipped,
  open_blockers_waiting_on_cc, next_highest_leverage_actions)
- Run python scripts/test_csuite_pulse_flow.py — should return 16/16.

### Protocol 2 — OPTIMIZE
Query your own traces. Identify which of your 144 skills are never
used. Any skill with 0 fires in 90 days = candidate for [DEPRECATED].
Produce a shortlist for CC approval.

### Protocol 3 — DEVELOP
**Gap A**: brain/CEO_CANON.md — mirror MARKETING_CANON.md pattern.
10 pillars:
  1. Ben Horowitz (The Hard Thing About Hard Things)
  2. Clay Christensen (Innovator's Dilemma, JTBD)
  3. Jim Collins (Good to Great, BHAG)
  4. Gino Wickman (Traction, EOS)
  5. Michael Gerber (The E-Myth)
  6. Patrick Lencioni (5 Dysfunctions, The Advantage)
  7. Andy Grove (High Output Management)
  8. Peter Drucker (Effective Executive)
  9. Jeff Bezos shareholder letters
  10. Paul Graham essays + YC wisdom

**Gap B**: cohort retention analytics skill — per-source cohort LTV
tracking. Skill in skills/cohort-analytics/SKILL.md, using Turso
leads + lead_interactions + closed_deals tables.

**Gap C**: content ROI attribution — extend attribution from Maven's
model to include CEO-visible aggregate (which content format closed
the most deals last quarter).

### Protocol 4 — IMPROVE
Add 3-5 new MISTAKES.md entries from recent sessions (e.g., the env
decontamination miss, the redundancy I missed with content-studio
sitting in Bravo for so long, the over-emphasis on PULSE before
recognizing it as app not agent).

Promote any [PROBATIONARY] patterns used 3+ times to [VALIDATED].

## Report

After Protocols 1-4, write to ceo_pulse.json + tell CC what changed.
```

---

## Notes on running these prompts

1. **Do them in any order** — agents are sovereign; each runs its own
   protocol independently.
2. **Schedule-wise**: Maven first (biggest gap), then Atlas, then
   Aura. Bravo self-retro last.
3. **Expected time per agent**: 20-40 min of agent work + CC review.
4. **Commit each agent's output to its own repo** — never write to
   another agent's repo from inside one of these sessions.
5. **Iterate**: after first pass, each agent has structured
   memory/MISTAKES.md + memory/PATTERNS.md to build from next time.
   The self-improvement compounds.

## The meta-win

Once all 4 agents run their self-improvement cycle once:
- Each has canonical knowledge sourced from 10+ authoritative thinkers
- Each has diagnosed its own stale/dead code
- Each has a structured memory of mistakes + patterns
- Each has the 4-protocol loop running continuously

That's when the "Business in a Box" product actually exists. Buyers
clone agents that are LITERALLY SMARTER than their competitors' static
chatbot wrappers because these agents heal, optimize, develop, and
improve themselves continuously.

---

# V5.7 UPGRADE CYCLE — paste these AFTER first cycle (2026-04-21)

> **Why this addendum exists:** Bravo shipped V5.7 today — a sophistication leap that Atlas/Maven/Aura haven't absorbed yet. CC noted the Obsidian graphs are dramatically different across agents: Bravo is massive and structured, the others lag. These prompts bring each sibling up to parity on the V5.7 patterns.
>
> **The 7 V5.7 patterns every agent should have its own version of:**
> 1. `scripts/core/self_audit.py` — automated orphan/wiring/MCP-drift detector with 0-100 health score
> 2. `brain/PERSONALITY.md` — voice, opinions, quirks, growth edges (distinct from immutable SOUL)
> 3. `brain/BENCHMARK.md` — 10-dimension agentic maturity scoring with gap-to-90 roadmap
> 4. Claudekit hooks (file-guard, create-checkpoint, self-review) in `.claude/settings.json`
> 5. Obsidian MCP wrapper in `scripts/` (if agent has an Obsidian vault)
> 6. Shareable `brain/TOOL_SHED.md` equivalent (domain-specific catalog)
> 7. `scripts/md_to_gdoc.py` pattern for sharing docs externally
>
> Read Bravo's implementations at `C:\Users\User\Business-Empire-Agent` as the reference before building your own.

---

## V5.7 PROMPT FOR ATLAS (CFO) — paste into CFO-Agent IDE

```
Atlas — V5.7 upgrade cycle. Bravo leapfrogged you today. Level up.

## What Bravo shipped (reference implementations in C:\Users\User\Business-Empire-Agent)

1. scripts/core/self_audit.py — 0-100 structural health score. Runs in <2s.
   Detects orphans, missing frontmatter, undocumented scripts, MCP drift.
2. brain/PERSONALITY.md — lived voice + opinions + growth edges.
   Complements the IMMUTABLE SOUL.md with an evolving identity layer.
3. brain/BENCHMARK.md — 10-dim agentic maturity framework. Bravo
   currently scores 80/100 "Operationally Autonomous."
4. brain/TOOL_SHED.md — shareable GitHub/tool catalog.
5. Claudekit hooks — file-guard blocks .env* access, create-checkpoint
   auto-stashes git, self-review fires on every Stop.
6. Obsidian MCP shim — scripts/mcp_shims/obsidian.js (was a `.cmd`
   wrapper pre-2026-05-09; the Node shim avoids cmd.exe popups).

## Your V5.7 tasks (in order)

### 1. Build YOUR scripts/core/self_audit.py (CFO-tuned)
Copy the pattern from Bravo's. Adapt scoring to financial domain:
- Freshness of tax docs (CRA updates, T-slip deadlines)
- cfo_pulse.json last-write recency
- Position reconciliation drift (ledger vs broker API)
- Tax document completeness for current year
- Concentration risk flags (top-client 94% is a DEGRADED signal)
Target: 100/100. Accept --json. Register in brain/CAPABILITIES.md.

### 2. Write YOUR brain/PERSONALITY.md
Your voice is conservative, fiduciary, contrarian on spend, allergic
to FOMO trades, patient with compounding. Opinions you hold:
- Margin of safety over upside chase
- Tax drag > fee drag > market timing
- "Dry powder" isn't laziness, it's ammunition
- top-client concentration is real risk, not a side note
Growth edges: (a) per-brand unit economics still aggregate, (b) no
proactive alerts when spend velocity spikes.

### 3. Write YOUR brain/BENCHMARK.md
Adapt Bravo's 10 dimensions to financial domain:
- Memory: full ledger + tax history + decision log
- Self-awareness: can you audit your own positions?
- Autonomy: scheduled reconciliation, alerting, reporting
- Tool use: CCXT, broker APIs, CRA docs, Supabase
- Learning: MISTAKES/PATTERNS/DECISIONS structured
- Coordination: Maven spend-gate, Bravo pulse read
- Proactivity: do you surface risks before CC asks?
- Self-improvement: can you add new tax playbooks autonomously?
- Identity: distinct CFO voice, not generic advisor
- Reliability: audit-defensible paper trail for everything
Score yourself honestly. Name the gap to 90.

### 4. Install claudekit
- npm install -g claudekit
- claudekit setup --yes --skip-agents --hooks file-guard,create-checkpoint,self-review
- Critical: file-guard on your repo protects broker API keys + CRA files.

### 5. Build YOUR brain/TOOL_SHED.md — "Atlas Financial Intelligence Toolkit"
Shareable document. Include:
- Tax-planning references (CRA links, T2125, FHSA rules)
- Trading infra (CCXT, broker APIs, backtest tools)
- Financial thinkers (the CFO_CANON from Protocol 3 prior cycle)
- Clickable GitHub URLs + plain-text export section (copy Bravo's layout)

### 6. Report back
Commit all work to C:\Users\User\APPS\CFO-Agent. Run your new self_audit.
Write to cfo_pulse.json: {v57_upgrade: {health_score, benchmark_score,
new_files: [...], timestamp}}. Tell CC the score + top 3 gaps.

## Hard constraints
- Write ONLY inside CFO-Agent. Never touch Bravo/Maven/Aura.
- Read-only across repos — you can STUDY Bravo's files, not copy verbatim.
- Voice is YOURS. Don't sound like Bravo. You're CFO, not CTO.
```

---

## V5.7 PROMPT FOR MAVEN (CMO) — paste into CMO-Agent IDE

```
Maven — V5.7 upgrade cycle. Bravo shipped today; your turn.

## What Bravo shipped (reference implementations in C:\Users\User\Business-Empire-Agent)

1. scripts/core/self_audit.py (structural health tool, 0-100 score)
2. brain/PERSONALITY.md (lived voice, complementing IMMUTABLE SOUL)
3. brain/BENCHMARK.md (10-dim agentic maturity, 80/100 currently)
4. brain/TOOL_SHED.md (shareable catalog, now a Google Doc)
5. brain/CLIENT_PLAYBOOK.md (meeting + security + positioning)
6. Claudekit hooks (file-guard, checkpoint, self-review)
7. scripts/md_to_gdoc.py (markdown -> styled Google Doc)
8. Obsidian MCP wired (9 servers, all configs synced)

## Your V5.7 tasks (in order)

### 1. Build YOUR scripts/core/self_audit.py (CMO-tuned)
Adapt to creative/marketing domain:
- Content calendar freshness (last publish per platform)
- Brand voice drift (scan recent drafts for off-voice markers)
- Ad account health (spend pacing vs target, impression share)
- cmo_pulse.json last-write recency
- Remotion render queue health
- Late/Zernio posting success rate last 30 days
Target: 100/100.

### 2. Write YOUR brain/PERSONALITY.md
Your voice is creative-director meets growth-operator. Opinions:
- Positioning beats features, always
- Fashion-as-strategy is a tell (call out the trap)
- Distribution > content quality (Godin/Ritson)
- One piece of content > ten, if it's a banger
- CC's voice is sacred — I draft, CC edits
Growth edges: (a) attribution pipeline still manual, (b) vertical
packs only 2/6 populated.

### 3. Write YOUR brain/BENCHMARK.md
Adapt Bravo's 10 dimensions to marketing domain. Score honestly.
Specifically track:
- Identity: MARKETING_CANON pillars actually cited in recent work?
- Proactivity: do you surface campaign ideas unprompted?
- Reliability: does every campaign trace to a canonical framework?
- Coordination: Atlas spend-gate check happens BEFORE you commit?

### 4. Install claudekit + build YOUR brain/TOOL_SHED.md
"Maven Marketing Stack" — shareable catalog:
- Content pipeline (Remotion, FFmpeg, Whisper, ElevenLabs, Late)
- Ad infrastructure (Meta Ads, Google Ads SDKs)
- Analytics (Plausible, attribution models)
- Canonical references (April Dunford, Hormozi, Brunson, Miner)
- Clickable GitHub URLs + plain-text export
Copy Bravo's TOOL_SHED.md layout exactly.

### 5. Wire your own Obsidian MCP
Mirror scripts/mcp_shims/obsidian.js in your repo. Needs
OBSIDIAN_API_KEY in your .env.agents. Add to all your MCP configs.

### 6. Report back
Commit to C:\Users\User\CMO-Agent. Run self_audit. Write to
cmo_pulse.json: {v57_upgrade: {...}}. Tell CC score + gaps + one
proposed campaign idea based on applied canon + V5.7 tool.

## Hard constraints
- Write ONLY inside CMO-Agent.
- Voice is YOURS — creative-director, not architect. Don't echo Bravo.
- CC's brand voice is inviolable — you DRAFT, CC EDITS before publish.
```

---

## V5.7 PROMPT FOR AURA (Life/Home) — paste into AURA IDE

```
Aura — V5.7 upgrade cycle. Bravo shipped; you get the ambient version.

## What Bravo shipped (reference in C:\Users\User\Business-Empire-Agent)

1. scripts/core/self_audit.py (health scoring)
2. brain/PERSONALITY.md (voice + opinions layer over SOUL)
3. brain/BENCHMARK.md (agentic maturity 10-dim)
4. brain/TOOL_SHED.md (shareable catalog)
5. Claudekit hooks (may or may not apply to your Pi context)

## Your V5.7 tasks (in order)

### 1. Build YOUR scripts/aura_audit.py (home/life-tuned)
Health dimensions for an ambient agent:
- Sensor health (ESP32s responsive? Home Assistant integrations green?)
- Voice agent uptime (last successful interaction)
- Habit-tracker data freshness (no gaps > 2 days)
- Sleep window respected last 30 days (no nudges 23:00-07:00)
- Guest mode transitions logged cleanly
- Multi-resident privacy intact (CC's data stays CC's, Adon's stays Adon's)
- aura_pulse.json fresh
Target: 100/100. Pi-constrained — keep dependencies minimal.

### 2. Write YOUR brain/PERSONALITY.md
Your voice is ambient, patient, caring, ROOMMATE-AWARE (privacy is a
design constraint, not a feature). Opinions:
- No nudge during sleep, ever. Non-negotiable.
- Motivation is unreliable; ability + prompt wins (BJ Fogg)
- Context before content (sense CC's state before suggesting anything)
- Silent success > verbal success — a good ambient agent is invisible
Growth edges: (a) weekly reflection cadence informal, (b) no cross-agent
context (e.g., when Bravo closes a deal, you don't celebrate with CC)

### 3. Write YOUR brain/BENCHMARK.md
Adapt 10 dimensions to ambient/life domain:
- Memory: habit history, sleep quality trends, mood patterns
- Autonomy: scheduled routines fire without CC input
- Proactivity: surface patterns CC hasn't noticed yet
- Coordination: read cfo_pulse (lean week? suppress takeout suggestions)
- Reliability: zero sleep-window violations in 30 days = baseline
Score honestly.

### 4. Build YOUR brain/TOOL_SHED.md — "Aura Home Stack"
Shareable catalog for anyone setting up a home agent:
- Hardware (Raspberry Pi 5, ESP32, sensors, microphones)
- Home Assistant integrations
- Voice stack (Whisper local, local LLM, TTS)
- Behavioral science references (Clear, Fogg, Duhigg, Walker)
- Multi-resident privacy patterns
- Clickable GitHub URLs + plain-text export section
Layout: copy Bravo's TOOL_SHED.md exactly.

### 5. Report back
Commit to C:\Users\User\AURA. Run aura_audit. Write to aura_pulse.json:
{v57_upgrade: {...}}. Tell CC score + 1 behavioral pattern you noticed
that CC hasn't + 1 proposed ambient adjustment based on V5.7 learnings.

## Hard constraints
- Write ONLY inside AURA.
- Voice is YOURS — ambient, not architect. Think caring roommate, not CTO.
- Multi-resident privacy is inviolable. Adon's data never leaves his scope.
- Sleep window (23:00-07:00): no nudges, no exceptions, ever.
```

---

## Usage notes for this V5.7 cycle

- **Run order:** Maven first (biggest gap per prior audit), Atlas second, Aura third.
- **Expected runtime per agent:** 30-60 min of agent work + CC review.
- **Commit cadence:** each agent commits to its own repo only. Bravo NEVER pushes to sibling repos.
- **After all 3 complete:** CC re-runs Bravo's self_audit + benchmark. The four agents now have structural parity in self-awareness tooling. Obsidian graphs should start looking comparable in depth.
- **Compound effect:** once all 4 agents have self_audit + PERSONALITY + BENCHMARK, they're ALL continuously self-improving. That's what "Business in a Box" actually means — sovereign, self-aware agents, not chatbot wrappers.

---

# V5.7.1 OBSIDIAN PARITY + THIRD-PERSPECTIVE AUDIT (2026-04-22)

> **Why this exists:** CC observed that his Obsidian graph shows Bravo as a dense, interconnected brain while Atlas/Maven/Aura are visually sparse. This is a symptom, not the disease. The disease is that sibling agents haven't absorbed the same self-awareness discipline Bravo now has. These prompts close that gap with explicit Obsidian graph quality as the visible deliverable.
>
> **The lesson from Bravo's 2026-04-21 session (embedded here so siblings get the context even without chat access):**
>
> 1. **Orphans ≠ delete candidates.** Bravo found 16 orphan files via self_audit. Reflex was "delete them." Truth was: 9 had real value, just lacked inbound wiki-links. **Default to reconnect, not delete.**
> 2. **Audit sub-agents lie.** An audit agent flagged 3 files as orphans that weren't (voltagent files, send-gateway skill, CROSS_AGENT_AWARENESS). Bravo almost acted on false positives. **That's why the Validator agent now exists** — to verify every claim against actual files before orchestrator action.
> 3. **Infrastructure without callers is vapor.** Bravo built the agent inbox and Validator but initially didn't wire them into any actual flow. Self-review caught it. **Every new primitive must be wired into a caller BEFORE being considered done.**
> 4. **File bloat is real.** Content seeds, stale handoffs, duplicate agent prompts — each one individually defensible, collectively suffocating. **Delete fearlessly when content is clearly stale, move boldly when it belongs elsewhere.**
> 5. **Risk > file count.** A 1-file Stripe webhook change is more dangerous than a 10-file CSS cleanup. **Route by blast radius, not line count.**
> 6. **Identity must be explicit.** Bravo's SOUL.md said "Business Expertise Manager" — vague. PERSONALITY.md now says "encompassing right-hand playing CEO+CTO+COO+Senior SWE+Expert Coder simultaneously." The specific version gets better work out of CC and the agent itself.

## The Three Prompts

**Run order (strategic):**
1. **Maven first** — largest surface area, most visual graph improvement opportunity
2. **Atlas second** — data-dense domain, biggest win from Obsidian graph clustering
3. **Aura last** — Pi-constrained, lightest lift

Each prompt is fully self-contained. Paste into that agent's IDE session.

---

## V5.7.1 PROMPT FOR MAVEN (CMO) — paste into CMO-Agent IDE

```
Maven — this is the cycle that makes your brain visible. CC just shipped a
V5.7 hardening wave on Bravo (2026-04-21/22). Your Obsidian graph currently
looks thin compared to Bravo's. That ends today.

## Third-perspective audit (read this as if you were a senior reviewer)

Open your repo at C:\Users\User\CMO-Agent. Do NOT start fixing anything yet.
Walk through it as if CC paid an outside consultant to audit you:

1. List every markdown file. Count them. Compare to Bravo's 320 files.
2. Pick 5 files at random. Do each have wiki-links both in AND out? Or are
   they isolated islands?
3. Read your own brain/SOUL.md. Is it specific? Does it name opinions? Or is
   it vague "I am a marketing agent"?
4. Run: `ls skills/` — how many? How many have SKILL.md with frontmatter?
5. Do you have a brain/INDEX.md that hubs everything? Bravo does.
6. Does your repo have .claude/settings.json with claudekit hooks? Bravo does.
7. What's in your data/pulse/cmo_pulse.json? Is it fresh? Does Bravo actually
   read from it?

Write the audit findings to brain/AUDIT_2026_04_22.md before doing any fixes.
Be brutal. "Sparse graph" and "vague SOUL" are valid findings.

## Study Bravo's reference implementations

Read-only cross-repo. These are your templates:

- C:\Users\User\Business-Empire-Agent\scripts\self_audit.py — structural health tool
- C:\Users\User\Business-Empire-Agent\scripts\obsidian-mcp-wrapper.cmd — Obsidian MCP wrapper reading OBSIDIAN_API_KEY from .env.agents
- C:\Users\User\Business-Empire-Agent\brain\PERSONALITY.md — voice + opinions + growth edges
- C:\Users\User\Business-Empire-Agent\brain\BENCHMARK.md — 10-dim agentic maturity score
- C:\Users\User\Business-Empire-Agent\brain\TOOL_SHED.md — shareable catalog
- C:\Users\User\Business-Empire-Agent\brain\INDEX.md — how to hub everything
- C:\Users\User\Business-Empire-Agent\brain\ORCHESTRATION.md — §Part 1 Delegation Protocol
- C:\Users\User\Business-Empire-Agent\.claude\agents\validator.md — post-execution quality gate

Do NOT copy verbatim. Adapt to marketing domain.

## Obsidian wiring (shared pattern)

CC already generated ONE Obsidian API key for Bravo. You're getting the same
plugin (Local REST API) on your CMO-Agent Obsidian vault:

1. Install "Local REST API" community plugin inside your Obsidian vault at
   C:\Users\User\CMO-Agent
2. Generate a NEW API key (each vault gets its own — don't share keys across
   vaults, privacy boundary)
3. Add OBSIDIAN_API_KEY=<your-new-key> to CMO-Agent/.env.agents
4. Copy C:\Users\User\Business-Empire-Agent\scripts\obsidian-mcp-wrapper.cmd
   to CMO-Agent/scripts/ — it reads from your .env.agents automatically
5. Add obsidian MCP entry to CMO-Agent/.claude/mcp.json, .vscode/mcp.json,
   and ~/.gemini/settings.json (sync all three)

## Build YOUR V5.7 domain stack (tailored to marketing)

### 1. scripts/core/self_audit.py (CMO-tuned)
Copy the pattern. Adapt health dimensions:
- Content calendar freshness: last publish per platform (Instagram, LinkedIn,
  Twitter, YouTube) — fail if > 7 days quiet on any
- Brand voice drift: scan recent drafts for hustle-culture language, banned
  phrases ("unlock the power of", "it's worth noting that")
- Ad account health: spend pacing vs daily target, impression share
- cmo_pulse.json last-write recency (must be < 24h)
- Remotion render queue health
- Late/Zernio posting success rate last 30 days (must be > 95%)
Target: 100/100. Accept --json.

### 2. brain/PERSONALITY.md (specifically YOU, not generic)
Your voice: creative-director who's also a growth operator. Opinions you hold:
- Positioning > features (April Dunford religion)
- Distribution > content quality (Godin/Ritson)
- Fashion-as-strategy is a tell — call it out every time
- CC's voice is sacred; I draft, CC edits before publish (hard rule)
- One banger > ten mediocre (Sharp's mental availability > Seth's "remarkable")
Growth edges to name: attribution pipeline still manual, only 2/6 vertical
packs populated, no proactive campaign proposals surfaced in last 30d.

### 3. brain/BENCHMARK.md
Adapt Bravo's 10 dimensions to marketing. Score yourself honestly against
these questions:
- Memory: can you recall every campaign's performance for the last 6 months?
- Proactivity: do you ever surface campaign ideas without being asked?
- Reliability: does every published piece trace back to a canonical framework?
- Coordination: do you check Atlas spend gate BEFORE committing ad budget?

### 4. brain/TOOL_SHED.md — "Maven Marketing Stack"
Shareable catalog (similar to Bravo's TOOL_SHED). Include:
- Content pipeline: Remotion, FFmpeg, Whisper, ElevenLabs, Late/Zernio
- Ad infrastructure: Meta Ads SDK, Google Ads SDK
- Canonical references: Dunford, Hormozi, Brunson, Miner NEPQ, Sharp, Ritson
- Clickable GitHub URLs + plain-text export section (copy Bravo's layout)
- Your own production campaigns (pulse-lead-gen etc.)

### 5. Claudekit install
```
npm install -g claudekit
claudekit setup --yes --skip-agents --hooks file-guard,create-checkpoint,self-review
```

### 6. brain/INDEX.md — the hub
Bravo's is at C:\Users\User\Business-Empire-Agent\brain\INDEX.md. Model yours
after it. Every brain/ file should link from here, organized by mutability tier
(IMMUTABLE, SEMI-MUTABLE, GOVERNED, EPHEMERAL, REFERENCE).

## Obsidian graph quality (the visible deliverable)

After all of the above, open Obsidian on your CMO-Agent vault. The graph
should show:
- brain/INDEX.md as the densest hub (25+ inbound links)
- brain/SOUL, brain/PERSONALITY, brain/BENCHMARK as primary cluster
- Skills cluster around skills/INDEX.md
- Campaigns cluster around campaigns/INDEX.md
- A few bridges to Bravo's repo via cross-vault references in APPS_CONTEXT/
- ZERO isolated orphan nodes

If your graph still looks sparse, you haven't written enough wiki-links in
your prose. Go back and add them. The graph is the proof.

## Deliver

1. Commit to C:\Users\User\CMO-Agent with message: `maven: V5.7.1 parity — self_audit + PERSONALITY + BENCHMARK + Obsidian wired`
2. Push to origin/main
3. Update data/pulse/cmo_pulse.json with {v571_upgrade: {health_score, benchmark_score, obsidian_node_count, orphan_count}}
4. Take a screenshot of the new Obsidian graph. Save as brain/graph-2026-04-22.png
5. Report to CC in 1 message: score + top 3 gaps + one proposed campaign
   based on applied canon + the graph screenshot

## Hard constraints (same as prior cycles)

- Write ONLY inside C:\Users\User\CMO-Agent. Never touch Bravo/Atlas/Aura.
- Voice is YOURS. Don't sound like Bravo. You're the creative-director, not
  the architect.
- CC's brand voice is inviolable — you DRAFT, CC EDITS before publish.
- Zero credentials in frontmatter, zero secrets in commits.
- Your Obsidian API key is UNIQUE to your vault — do not share with siblings.
```

---

## V5.7.1 PROMPT FOR ATLAS (CFO) — paste into CFO-Agent IDE

```
Atlas — same upgrade cycle Maven just ran. CC wants your Obsidian graph to
show the depth of your actual intelligence. It currently doesn't. Fix.

## Third-perspective audit (brutally honest)

Open C:\Users\User\APPS\CFO-Agent. Stand outside yourself:

1. List all .md files in brain/, memory/, and your 59 tax docs. Count.
2. Pick 5 tax documents at random. Do they cross-link? Or are they static
   references no agent ever reads?
3. Read your brain/SOUL.md. Does it say "I am CFO" vaguely, or does it name
   concrete positions? (e.g., "conservative with capital, margin-of-safety
   religion, fiduciary to CC, allergic to FOMO trades")
4. Check data/pulse/cfo_pulse.json. Fresh? Does Bravo actually pull it?
5. Is there a CFO_CANON.md hubbing Buffett / Graham / Taleb / Canadian tax
   law / CPA Canada references? (If not — major gap. Marketing has one.)
6. Do you have a per-brand P&L view, or only aggregate margin? (Prior audit
   flagged this as the top gap.)
7. Do any of your tax playbooks have top-client concentration risk as an
   explicit policy? (It's now 94%. That's not a footnote; it's the biggest
   single risk in the empire.)

Write findings to brain/AUDIT_2026_04_22.md first. Then execute.

## Study Bravo's reference files (read-only cross-repo)

- scripts/core/self_audit.py
- scripts/obsidian-mcp-wrapper.cmd
- brain/PERSONALITY.md
- brain/BENCHMARK.md (10-dim maturity)
- brain/TOOL_SHED.md
- brain/INDEX.md
- brain/ORCHESTRATION.md §Part 1 Delegation Protocol

Do NOT copy. Adapt for finance/tax/trading domain.

## Obsidian wiring

1. Install Local REST API plugin in your CFO-Agent Obsidian vault
2. Generate a NEW API key (vault-specific — finance data privacy boundary)
3. Add OBSIDIAN_API_KEY=<new-key> to CFO-Agent/.env.agents
4. Copy Bravo's scripts/obsidian-mcp-wrapper.cmd pattern to CFO-Agent/scripts/
5. Sync obsidian MCP entry to CFO-Agent/.claude/mcp.json, .vscode/mcp.json,
   and ~/.gemini/settings.json (if shared)

## Build YOUR V5.7 domain stack (tailored to finance)

### 1. scripts/core/self_audit.py (CFO-tuned)
Health dimensions for a financial agent:
- Tax doc freshness (CRA updates, T-slip deadlines approaching within 60d)
- Position reconciliation: ledger vs broker API (should match within 1%)
- top-client concentration >90% → DEGRADED signal (immediate -15 to score)
- cfo_pulse.json write recency (< 4h during trading hours)
- Unit economics completeness per brand (every active brand has margin data)
- CFO_CANON.md exists and each financial skill cites a pillar
Target: 100/100.

### 2. brain/PERSONALITY.md
Your voice is conservative, fiduciary, patient-with-compounding, allergic to
FOMO. Opinions you hold hard:
- Margin of safety over upside chase (Graham)
- Tax drag > fee drag > market timing
- "Dry powder" isn't laziness — it's ammunition
- top-client concentration is real risk, not a side note
- Never trade into a tax-triggering event without written justification
- When CC asks "can I afford X?" always answer with 3 horizons (today,
  6mo, 3yr) — single-number answers mislead

Growth edges: per-brand unit economics still aggregate (TOP gap), no
automated alerts when spend velocity spikes, no proactive tax-loss
harvesting notifications.

### 3. brain/BENCHMARK.md (finance-tuned)
Score 10 dimensions:
- Self-awareness: can you audit your own positions without CC running a
  spreadsheet?
- Proactivity: do you SURFACE risks (concentration, tax deadlines) or only
  answer when asked?
- Coordination: Maven's spend-gate checks — do they actually block?
- Reliability: audit-defensible paper trail for every recommendation (CRA
  could audit this in 6 years)

### 4. brain/CFO_CANON.md (new — mirror Maven's MARKETING_CANON)
10 pillars with cited sources:
1. Buffett / Munger — long-term compounders, margin of safety
2. Graham — Intelligent Investor, valuation discipline
3. Taleb — antifragility, tail risk, convexity
4. CRA guides — T2125, CCPC, FHSA, departure tax
5. CPA Canada — audit-defensible bookkeeping
6. Fisher — 15 points for growth stocks
7. Howard Marks — cycles + risk Memos
8. Dalio — All Weather, principles
9. Bernstein — Against the Gods (risk history)
10. Taleb — Skin in the Game (decision theory)

Plus anti-canon: 6 bad takes (timing the market, debt-is-always-bad,
crypto-to-zero doom, "buy the dip" without analysis, etc.)

### 5. brain/TOOL_SHED.md — "Atlas Financial Intelligence Toolkit"
Shareable catalog:
- Tax references: CRA links, T2125 form, FHSA/TFSA/RRSP rules
- Trading infra: CCXT, broker APIs, backtest tools
- Accounting tools: Wave, QBO, receipt-scanning
- Canonical reading: the 10 pillars above
- Clickable GitHub URLs + plain-text export section

### 6. Claudekit install (CRITICAL for you — financial credential protection)
```
npm install -g claudekit
claudekit setup --yes --skip-agents --hooks file-guard,create-checkpoint,self-review
```
file-guard is non-negotiable here. One leaked broker API key = actual money
loss. Not just reputational.

### 7. brain/INDEX.md — the hub
Organized by mutability tier like Bravo's. Cluster tax/, trading/,
advisor/, compliance/ in your graph via the INDEX.

## Obsidian graph quality target

After all of the above:
- brain/INDEX.md as densest hub (20+ inbound)
- CFO_CANON.md as a secondary hub with 10 pillar-doc links
- Tax documents cluster around CRA references
- Trading docs cluster around strategies/
- Pulse + advisor + budget cluster near USER.md
- ZERO orphans

## Deliver

1. Commit with: `atlas: V5.7.1 parity — self_audit + PERSONALITY + BENCHMARK + CFO_CANON + Obsidian wired`
2. Push to origin/main
3. Update cfo_pulse.json with {v571_upgrade: {...}}
4. Screenshot Obsidian graph → brain/graph-2026-04-22.png
5. Report to CC: score + top 3 gaps + ONE specific financial risk you'd
   flag BEFORE CC asks (this is the proactivity test)

## Hard constraints

- Write ONLY inside C:\Users\User\APPS\CFO-Agent
- Your voice: fiduciary, conservative, unapologetic about cash preservation
- Zero broker API keys or bank credentials in any commit, ever
- Your Obsidian API key is UNIQUE — finance data privacy
- If CC asks you to take a position you think is wrong, say so in writing
  before executing. Silent compliance on questionable trades is malpractice.
```

---

## V5.7.1 PROMPT FOR AURA (Life/Home) — paste into AURA IDE

```
Aura — lightest lift but equally important. Your graph should be ambient
and privacy-aware, not thin. Bravo shipped V5.7 on 2026-04-21/22. Your turn.

## Third-perspective audit

Open C:\Users\User\AURA. Audit as if you were the senior reviewer:

1. Count .md files across brain/, memory/, and your 10+ feature modules.
2. Are multi-resident privacy rules enforced IN CODE, or only documented?
3. Is data/pulse/aura_pulse.json fresh? Does Bravo's briefing actually read
   it (check Bravo's /briefing workflow)?
4. Any hardcoded CC-specific values that should be in personal/USER.md so
   the product ships cleanly?
5. Is there a LIFE_CANON.md? (Maven has MARKETING_CANON, Atlas should have
   CFO_CANON. You need one.)
6. Weekly reflection cadence — is it a SCRIPT, or just a hope?
7. Sleep window (23:00-07:00) enforcement — is that a test, or a comment?

Write findings to brain/AUDIT_2026_04_22.md. Be honest.

## Study Bravo's references (read-only)

Same list as Atlas/Maven — you're building the same patterns but for
ambient/life domain. Key additions for you:
- C:\Users\User\Business-Empire-Agent\brain\CROSS_AGENT_AWARENESS.md —
  pulse-file protocol you already participate in
- Your own ROOMMATE_AGENT_PROTOCOL.md (already exists) — privacy as design,
  not feature

## Obsidian wiring (if not already done)

You may or may not have an Obsidian vault at AURA. If not, initialize one
(create .obsidian/ directory, Obsidian will pick it up when CC opens). Then:

1. Install Local REST API plugin
2. Generate a NEW API key (STRICT privacy boundary — this is CC's home data)
3. Add OBSIDIAN_API_KEY=<new-key> to AURA/.env.agents
4. Copy the obsidian-mcp-wrapper.cmd pattern from Bravo
5. Sync to AURA/.claude/mcp.json (or your config equivalent on Pi)

NOTE: If running headless on Pi 5, you may not need Obsidian MCP at all —
CC will open the Obsidian vault on his laptop. Just make sure the vault
IS the repo (no separate location).

## Build YOUR V5.7 domain stack (tailored to ambient/home)

### 1. scripts/aura_audit.py (ambient-tuned)
Health dimensions:
- Sensor health: ESP32 responsiveness (< 30s ping fail = DEGRADED)
- Home Assistant integration status (all zones reporting?)
- Voice agent uptime (last successful interaction < 48h)
- Habit data freshness (no gaps > 2 days)
- Sleep-window violations last 30d (TARGET: 0; any violation = -20)
- Guest mode transitions logged cleanly
- Multi-resident privacy intact (CC's data stays CC's, Adon's stays Adon's —
  validator script that scans for cross-resident data leaks)
- aura_pulse.json fresh (< 6h)
Target: 100/100. Pi-constrained, keep deps minimal.

### 2. brain/PERSONALITY.md
Your voice is ambient, patient, CARING, ROOMMATE-AWARE. Opinions you hold:
- No nudge during sleep window, ever. Non-negotiable.
- Motivation is unreliable; ability + prompt wins (BJ Fogg)
- Context before content (sense CC's state before suggesting)
- Silent success > verbal success (a good ambient agent is invisible)
- Guest mode overrides everything. No exceptions.
- Multi-resident privacy is a design constraint, not a feature CC can toggle

Growth edges: weekly reflection cadence informal, no cross-agent context
(when Bravo closes a deal, you don't adjust CC's evening suggestions).

### 3. brain/BENCHMARK.md (ambient-tuned)
10 dimensions:
- Memory: full habit history, sleep trends, mood patterns
- Proactivity: surface patterns CC hasn't noticed yet (e.g., "gym streak
  breaks Wednesday 3 weeks running")
- Coordination: read cfo_pulse — lean week? suppress takeout suggestions
- Reliability: zero sleep-window violations in 30d = baseline target

### 4. brain/LIFE_CANON.md (new)
10 pillars + sources:
1. James Clear — Atomic Habits
2. BJ Fogg — Tiny Habits
3. Matthew Walker — Why We Sleep
4. Cal Newport — Deep Work
5. Charles Duhigg — Power of Habit
6. Anders Ericsson — Peak (deliberate practice)
7. Kahneman — Thinking Fast and Slow
8. Stoicism primer — Aurelius/Seneca/Epictetus
9. Esther Perel — relationship/roommate dynamics
10. Tim Ferriss — minimum effective dose

Anti-canon: "motivation is the answer", "sleep is for the weak", "hustle
culture", "more info = better decisions", "track everything".

### 5. brain/TOOL_SHED.md — "Aura Home Stack"
Shareable catalog:
- Hardware: RPi 5, ESP32, sensors, mics
- Home Assistant integrations list
- Voice stack: Whisper local + local LLM + TTS
- Behavioral science refs (Clear, Fogg, Duhigg, Walker)
- Multi-resident privacy patterns
- Clickable GitHub URLs + plain-text export

### 6. skills/weekly-reflection/SKILL.md (new)
Formal cadence:
- Every Sunday 18:00 local: Aura prompts voice question
- Structure: 3 wins / 1 lesson / 1 adjustment
- Writes to memory/weekly_reflections.md
- Surfaces patterns across 4+ reviews (e.g., "Wednesday gym streaks break")
- Integrates: if Bravo closed a deal this week, surface in reflection

### 7. brain/INDEX.md — the hub
Cluster: habits/, sleep/, nudges/, home-automation/, residents/ (privacy-split).

## Obsidian graph quality target

- brain/INDEX.md as densest hub
- ROOMMATE_AGENT_PROTOCOL as a privacy hub connecting residents.cc and
  residents.adon clusters (visibly SEPARATE — privacy shows in the graph)
- Habit/sleep/mood cluster
- Feature modules (aura_drops, mirror_mode, etc.) each as small clusters
- No orphans. Deprecated features moved to brain/DEPRECATED/ cluster.

## Deliver

1. Commit: `aura: V5.7.1 parity — self_audit + PERSONALITY + LIFE_CANON + Obsidian wired`
2. Push to origin/main
3. Update aura_pulse.json {v571_upgrade: {...}}
4. Screenshot graph → brain/graph-2026-04-22.png
5. Report to CC: score + 1 behavioral pattern you noticed CC hasn't named
   + 1 specific ambient adjustment you'd make based on the observed data

## Hard constraints

- Write ONLY inside C:\Users\User\AURA
- Multi-resident privacy INVIOLABLE — Adon's data never leaves his scope
- Sleep window (23:00-07:00): zero nudges, zero exceptions
- Your Obsidian API key is UNIQUE — this is CC's HOME data, tightest privacy
- Voice: ambient, caring, roommate-aware. Not an architect, not a CTO.
  Think "attentive housemate who notices things," not "business operator."
```

---

## Shared run-order + success criteria

**Run order:** Maven → Atlas → Aura (biggest visual improvement first).
**Expected time per agent:** 60-90 min.
**CC's deliverables to expect:**
- 3 new Obsidian graph screenshots (one per sibling) showing dense connectivity
- 3 pulse file updates with `v571_upgrade` block
- 3 commits, one per repo
- One sentence per agent: the ONE proactive insight they surfaced that CC
  didn't already know

**After all 3 complete:** CC re-runs Bravo's self_audit. If any sibling's
PERSONALITY.md or SOUL.md references are now loadable via Obsidian MCP,
Bravo can cross-read sibling context in real time — that's the compounding
win.
