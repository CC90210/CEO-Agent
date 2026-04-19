---
tags: [prompts, self-improvement, agents, delegation]
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

3. brain/AGENT_GAP_AUDIT.md (in Bravo's repo) — your completeness scored
   8.5/10. Gaps flagged: (a) unit-economics validator, (b) per-brand
   breakdown, (c) SOUL/STATE stale pre-pivot references.

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
  CFO state: $7K liquid, primary retainer concentration 94%, FHSA opened,
  pulse contract live.
- Verify data/pulse/cfo_pulse.json has agent='atlas' field (already
  added per prior session, but re-verify).
- git log --all --full-history -- .env to confirm no secret leaks in
  history.
- Add a pre-commit hook at .git/hooks/pre-commit to block .env* and
  *.key files from being committed.

### Protocol 2 — OPTIMIZE
Query your own traces from Supabase:
```
python scripts/supabase_tool.py query \
  "SELECT action, COUNT(*), AVG(execution_time_ms)
   FROM agent_traces WHERE agent='atlas'
   AND created_at > now() - interval '7 days'
   GROUP BY action ORDER BY COUNT(*) DESC" --project bravo
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
aggregate margin. Extend to per-brand: OASIS margin, primary retainer margin,
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
Query your own traces from shared Supabase:
```
python scripts/supabase_tool.py query \
  "SELECT action, COUNT(*), AVG(execution_time_ms)
   FROM agent_traces WHERE agent='maven'
   AND created_at > now() - interval '7 days'
   GROUP BY action ORDER BY COUNT(*) DESC" --project bravo
```
(Path to supabase_tool.py is in Bravo's repo — shell out if you don't
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
- Schema: extend shared Supabase `leads` table with
  `source_content_ids JSONB`, `attribution_touches JSONB`
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

4. brain/AGENT_GAP_AUDIT.md (in Bravo's repo) — your gaps:
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
python scripts/supabase_tool.py query \
  "SELECT action, COUNT(*) FROM agent_traces
   WHERE agent='aura' AND created_at > now() - interval '7 days'
   GROUP BY action" --project bravo
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
tracking. Skill in skills/cohort-analytics/SKILL.md, using Supabase
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
