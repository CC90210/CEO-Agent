---
name: self-improvement-protocol
version: 1.0.0
description: "The 4-protocol loop every C-Suite agent runs to stay sharp: self-heal (detect+fix broken state), self-optimize (track+tune own performance), self-develop (fill capability gaps), self-improve (learn from outcomes). Installs in Bravo / Atlas / Maven / Aura with per-agent scoping."
metadata:
  category: cross-cutting
  universal: true
  installs_in: [bravo, atlas, maven, aura]
  tier: full
triggers: [self-heal, self-optimize, self-develop, self-improve, retrospective, reflexion, review-self, heal, optimize, evolve]
---

# SELF-IMPROVEMENT PROTOCOL — The 4-Loop

The skill every agent runs to stay production-grade. Four protocols, one unified loop.

```
┌─── OBSERVE ───────────────────────────────────────┐
│  Session outcomes, pulse drift, broken refs,      │
│  skill activation scores, mistakes, validated     │
│  patterns, external signal changes                │
└────────────────┬──────────────────────────────────┘
                 │
      ┌──────────┼──────────┬────────────┬──────────┐
      ▼          ▼          ▼            ▼          ▼
   HEAL     OPTIMIZE    DEVELOP       IMPROVE    (escalate to CC)
  (fix)    (tune perf) (add skill)  (learn)
```

Trigger: **every session end**, **on failure**, **on "retro" / "reflexion" / "self-heal"**, **weekly auto-review** (cron).

---

## Protocol 1 — SELF-HEAL (detect + fix broken state)

Run on session start and after any major file operation.

### Checklist
1. **Pulse freshness**: is your own `data/pulse/*.json` < 24h stale? If not, update `updated_at`.
2. **Pulse sovereignty**: did any external process write to YOUR pulse? Check git history.
3. **Stale file references**: scan your docs for paths that don't exist.
   - Bash: `grep -rIEl "scripts/[a-z_]+\.py" brain/ skills/ memory/ | xargs -I{} sh -c 'grep -oE "scripts/[a-z_]+\.py" {} | while read p; do [ -f "$p" ] || echo "BROKEN: $p in {}"; done'`
4. **Broken wikilinks**: if Obsidian vault, scan for `[[target]]` where target file doesn't exist.
5. **Git drift**: any unpushed commits? any uncommitted work older than session age? `git status --short`, `git log @{u}..HEAD`.
6. **Env health**: required env vars present + unexpired? See agent-specific `ENV_STRUCTURE.md` if exists.
7. **Integration tokens**: test at least one call per live integration. If 401/403, mark `needs_rotation: true` in pulse.
8. **Schema alignment**: if you have migrations, are they all applied? (check with Supabase/Turso CLI).

### Fix actions
- Renamed files → rewrite references to new path
- Broken wikilinks → resolve to closest match OR remove
- Stale pulse → write fresh timestamp + session_note
- Uncommitted work → stage + commit with honest message
- Expired tokens → surface to CC, don't silently retry

### Auto-fix vs surface rule
- **Auto-fix**: mechanical problems (broken refs, stale timestamps, missing wikilinks, formatting)
- **Surface to CC**: anything touching credentials, external state, or reversible-but-destructive operations

---

## Protocol 2 — SELF-OPTIMIZE (track + tune own performance)

### Metrics every agent tracks in Supabase (`agent_traces` + `skill_activation`)

| Metric | How to compute |
|--------|----------------|
| Task success rate | % of traces with `outcome='success'` in last 7d |
| Avg tokens per task | `SUM(input_tokens + output_tokens) / COUNT(*)` per task_type |
| Skill firing frequency | `skill_activation.frequency` sorted desc |
| Skill outcome quality | Cross-join `agent_traces.outcome` with invoked `skill_id` |
| Time-to-first-reply | per conversation turn (Bravo/Maven mostly) |
| User override rate | % of drafts CC edits/rewrites before sending |

### Weekly optimization pass
1. Query own traces for last 7 days
2. Identify: top 3 most-used skills, top 3 least-used skills, lowest success rate skill
3. For each low performer, run Reflexion (see Protocol 4)
4. For each high performer never needing CC override, promote to `[VALIDATED]`
5. Write summary to own `memory/SELF_REFLECTIONS.md` + pulse's `recent_optimization` field

### Skill activation score formula
`score = 0.3*recency + 0.4*frequency + 0.3*confidence`
- Recency: days-since-last-use, normalized 0-1 (< 1 day = 1.0, > 30 days = 0.0)
- Frequency: invocations last 30 days, normalized to max
- Confidence: success rate × CC-override-inverse

Supabase RPC: `refresh_activation_scores()` updates these weekly.

---

## Protocol 3 — SELF-DEVELOP (fill capability gaps)

### Gap detection triggers
1. CC asks for X → no existing skill matches → **LOG THE GAP**
2. A skill fires but success rate < 50% over N=5 attempts → **LOG THE GAP**
3. Manual pattern repeats 3+ times without a skill → **PROMOTE TO SKILL**
4. External best-practice identified (new framework, new tool) → **EVALUATE FOR INTEGRATION**

### Gap log format (in `memory/CAPABILITY_GAPS.md`)
```markdown
## Gap: [short name]
- **Identified**: 2026-04-19
- **Trigger**: CC asked "draft a white paper for PropFlow" but no white-paper skill exists
- **Frequency**: 1 ask so far
- **Priority**: low (wait for 2nd ask before building)
- **Proposed skill**: `skills/white-paper-drafting/`
- **Sources to seed**: [HBR Ideacast on B2B content], [First Round: The New Content Marketing]
- **Status**: PROBATIONARY / VALIDATED / DROPPED
```

### Skill creation protocol
1. Use template: `skills/SKILL_TEMPLATE.md` (each agent keeps a local copy)
2. Required sections: name/version, triggers, description, when-to-use, rules, examples, authoritative sources, metrics for success
3. Tag as `[PROBATIONARY]` on creation
4. After 3 successful uses (tracked in `skill_activation.confidence > 0.7`), promote to `[VALIDATED]`
5. After 10 uses with < 50% success, mark `[DEPRECATED]` + propose deletion

### Authoritative source sourcing
When building a new skill, seed it with 2-5 canonical references. Don't invent frameworks. Examples:
- **Marketing**: April Dunford, Alex Hormozi, Byron Sharp, Mark Ritson, Seth Godin, Rory Sutherland
- **Finance**: Buffett/Munger letters, Graham, Taleb, Canadian CRA tax guides, CPA Canada
- **Strategy**: Ben Horowitz, Clay Christensen, Jim Collins, Gino Wickman (Traction), The E-Myth
- **Sales**: Jeremy Miner (NEPQ), Chet Holmes, Cialdini (Influence)
- **Habits**: James Clear, BJ Fogg, Matthew Walker, Cal Newport

Cite sources in the skill's frontmatter + examples section.

---

## Protocol 4 — SELF-IMPROVE (learn from outcomes)

### Mistake logging (required)
On every failure or CC correction:
1. Write to `memory/MISTAKES.md` with structured entry:
```markdown
## 2026-04-19 — [short name]
**What happened**: [facts]
**Root cause (5 Whys)**:
  1. Why did X happen? ...
  2. Why did that happen? ...
  3. ... (continue to bedrock)
**Prevention (specific rule for next time)**: ...
**Pattern**: [one-liner to search for later]
```
2. Also append to Supabase `memories` table with `category='mistake'`
3. Update any skill that was involved — add rule to its "rules" section

### Pattern logging (validated patterns)
When a non-obvious approach works:
1. Write to `memory/PATTERNS.md` with:
```markdown
## [PROBATIONARY] 2026-04-19 — [short name]
**Situation**: ...
**Approach**: ...
**Outcome**: ...
**Why it worked**: ...
**When to apply**: ...
**Counter-indications**: ...
```
2. After 3 successful re-uses → promote to `[VALIDATED]`
3. Consider promoting to a skill if recurring

### Reflexion protocol (after any material failure)
```
PHASE 1 — ACKNOWLEDGE
  State failure in one sentence, no excuses.

PHASE 2 — DECOMPOSE
  What was the goal? What was the plan? Where did plan diverge from reality?

PHASE 3 — HYPOTHESIZE (generate 2-3 root cause candidates)
  H1: [guess 1]
  H2: [guess 2]
  H3: [guess 3]

PHASE 4 — TEST (rank by evidence)
  Which hypothesis has strongest support?

PHASE 5 — CORRECT
  Specific rule / new skill / new check to prevent re-occurrence

PHASE 6 — SHARE
  Write to memory/SELF_REFLECTIONS.md. If insight is cross-agent-relevant,
  flag for CC to promote to shared Supabase `memories` table.
```

### Cross-agent pattern sharing
Via Supabase `memories` table with `agent` + `category` + `content` + `embedding`.
- Maven logs "ad hook that converted 12%" → other agents can `search_memories('what ad hooks convert')` and surface it
- Bravo logs "client negotiation move" → Maven can reference for sales-adjacent content
- Patterns cross-pollinate without copying files

---

## Integration with existing infrastructure

| Existing | How this skill uses it |
|----------|------------------------|
| `memory/MISTAKES.md` | Protocol 4 writes here |
| `memory/PATTERNS.md` | Protocol 4 writes here |
| `memory/SELF_REFLECTIONS.md` | Protocol 4 Phase 6 writes here |
| `memory/CAPABILITY_GAPS.md` | Protocol 3 writes here (NEW — create on first use) |
| Supabase `agent_traces` | Protocol 2 queries for metrics |
| Supabase `skill_activation` | Protocol 2 reads, Protocol 3 updates on new skill |
| Supabase `memories` | Protocol 4 writes + cross-agent lookup |
| `data/pulse/*.json` | Protocol 1 heals; Protocol 2 writes `recent_optimization` |
| `brain/CHANGELOG.md` | Protocol 3 logs new skills created |

## Scheduling

**Per-session automatic triggers**:
- Session start → run Protocol 1 (Heal) checklist
- Session end → run Protocol 4 logging (at minimum: any mistakes + patterns)
- On failure/CC correction → run Reflexion (Phase 1-6) inline before continuing

**Weekly cron** (each agent's own cron):
- Sunday 09:00 UTC → run Protocol 2 (Optimize) full pass + write summary
- Sunday 10:00 UTC → run Protocol 3 (Develop) gap review

## Guardrails

1. **Never auto-create a new skill without CC approval** — log to CAPABILITY_GAPS.md and surface
2. **Never auto-rotate credentials** — surface to CC
3. **Never delete existing skills** — mark `[DEPRECATED]` only, CC confirms removal
4. **Never modify other agents' files** — respect sovereignty; surface cross-agent suggestions via your own pulse
5. **Preserve human-readable memory** — structured data goes to Supabase, but the markdown record stays

## When to use

**Automatic (every session):**
- Session-start heal check (Protocol 1)
- Session-end reflection (Protocol 4)

**Trigger-phrases:**
- "run a retro" → full Protocol 2 + 4 pass
- "self-heal" → Protocol 1 explicit run
- "what are my gaps" → Protocol 3 gap review
- "did we already solve this" → Supabase `memories` search + MISTAKES.md scan

**Weekly (cron):**
- Full 4-protocol pass with written report

## Output artifacts

After each run, produce:
- A one-paragraph summary to CC (surface any CC-needed actions)
- Structured updates to the markdown memory files
- Supabase row inserts for `agent_traces` (the meta-action of running this protocol)
- Pulse `updated_at` + `recent_optimization` field refresh

---

**The iron rule**: CC never teaches the same lesson twice. If Protocol 4 caught it, it's in MISTAKES.md. If it's in MISTAKES.md, Protocol 1 checks against it next time.
