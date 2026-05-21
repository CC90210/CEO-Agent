---
name: close-review
description: Analyze a sales call transcript against NEPQ + LAER + sales-closing frameworks. Scores the call, flags missed closes, and writes the lesson back into memory so the sales-closing skill compounds over real reps.
triggers: [close review, call review, transcript review, analyze my call, /close-review]
inputs: [transcript_path OR pasted_transcript, optional deal_name, optional outcome]
outputs: [scored_analysis, pattern_entry_in_memory, update_to_ACTIVE_TASKS]
tier: strategic
dependencies: [sales-methodology, sales-closing, client-success]
---

# /close-review — Sales Call Transcript Analysis

> CC records the call → exports transcript (Fireflies, Otter, Granola, Zoom auto-transcribe, or raw copy-paste) → hands it to Bravo → Bravo runs the breakdown → logs the pattern → updates the sales-closing skill if a new pattern emerges.

## When to Fire This

- After every sales call, discovery call, or closing conversation — won, lost, or pending
- After a prospect goes silent post-proposal (analyze the last call to find the objection that wasn't surfaced)
- Weekly retro: run it on 3 calls at once to find patterns

## Input Formats Bravo Accepts

1. **File path:** `"Run /close-review on tmp/calls/2026-04-15-hvac-jim.txt"` — Bravo reads the file
2. **Pasted transcript:** CC dumps the transcript directly in chat, tagged with the deal name and outcome
3. **Meeting notes:** Even rough bullet notes work — Bravo will extract what it can and flag gaps
4. **Multiple calls:** CC can pass 3-5 transcripts in one request for pattern analysis across deals

## What Bravo Produces (Deterministic Output Format)

```
CALL REVIEW — [deal name, date, outcome]
═══════════════════════════════════════

1. DISCOVERY QUALITY (NEPQ scoring — 0 to 10)
   ├─ Pattern interrupt at open:          [present / missing / weak]
   ├─ Connection questions (pain mapping): [count + quality]
   ├─ Situation questions:                 [count + quality]
   ├─ Problem awareness questions:         [count + quality]
   ├─ Solution awareness questions:        [count + quality]
   ├─ Consequence questions:               [count + quality]
   ├─ Qualifying questions (budget/auth):  [count + quality]
   └─ Overall NEPQ grade:                  [letter grade + 1-sentence why]

2. TRIAL CLOSES (did CC test temperature?)
   - Trial close 1: [quote from transcript + timestamp/position]
   - Trial close 2: [quote]
   - ...
   - Missed opportunities: [moments where a trial close would have surfaced the real objection]

3. OBJECTIONS RAISED (what they said → what it actually meant)
   For each objection:
   ├─ Literal: "[exact words]"
   ├─ Real meaning: [price / timing / authority / trust / fit]
   ├─ How CC handled it: [LAER phase hit: Listen / Acknowledge / Explore / Respond]
   ├─ LAER grade: [A/B/C/D/F]
   └─ Better response (if applicable): [specific rewrite]

4. CLOSE ATTEMPT
   - Technique used: [assumptive / alternative / summary / scarcity / takeaway / question / none]
   - Timing: [too early / right moment / too late / never attempted]
   - Next step secured: [yes/no — what was the next concrete action?]
   - Grade: [A/B/C/D/F]

5. MATH-FOR-THEM CHECK
   - Did CC do the unit economics for the prospect? [yes/no]
   - Was price defended or reframed as ROI? [defended = bad / reframed = good]
   - Specific missed reframe: [if applicable, the sentence CC should have said]

6. CONAUGH VS CC NAMING
   - Did CC introduce himself correctly? [Conaugh McKenna for B2B, CC for DJ/entertainment]

7. ONE-SENTENCE LESSON
   [The single takeaway CC should internalize before the next call]

8. PATTERN LOGGED
   - File: memory/sales_patterns.md
   - Entry: [what was added]
   - If this objection appeared 3+ times → escalate to skills/sales-closing/SKILL.md update
```

## Execution Protocol (Bravo's Actual Steps)

When this workflow fires, Bravo:

1. **Load the transcript** (read file or accept pasted text)
2. **Read** `skills/sales-methodology/SKILL.md` and `skills/sales-closing/SKILL.md` for the current frameworks
3. **Score each section** above — quote the transcript literally, never paraphrase the prospect
4. **Write analysis** directly in chat using the output format (above)
5. **Append pattern** to `memory/sales_patterns.md` (create file if missing) with:
   - Deal name, date, outcome
   - Objection(s) raised
   - Handling grade
   - Lesson learned
6. **Check for repeat patterns** — grep `memory/sales_patterns.md` for the same objection. If seen 3+ times, propose an update to `skills/sales-closing/SKILL.md` with the new handling pattern.
7. **Update** `memory/ACTIVE_TASKS.md` if the call moved a deal's stage
8. **If lost:** Set 90-day follow-up reminder via `python scripts/core/cron_engine.py add --task "followup: [deal]" --when "+90d"`
9. **If won:** Log the winning technique to `memory/PATTERNS.md` as a validated pattern with `[V]` tag after 3 wins

## The Compound Effect

Every real deal feeds back into the skill. After 10 calls, the sales-closing SKILL.md will contain:
- CC's actual objections from his actual market (not generic ones)
- CC's voice in rebuttals (extracted from wins)
- Specific patterns for HVAC, wellness, real estate verticals
- The exact moment most calls died (pattern across losses)

**That's how Bravo becomes CC's embodiment for sales, not just a generic closer.**

## Example Invocation

```
CC: "Ran a discovery with Jim from Collingwood HVAC today. Attached the transcript.
     He said yes to everything but wants to 'talk to his wife'. /close-review"

Bravo: [reads transcript, produces full analysis, logs pattern, proposes a
        specific follow-up message for the spouse objection, adds 'Jim HVAC
        spouse-call Thursday' to ACTIVE_TASKS.md]
```

## Anti-Patterns

- Analyzing a call without reading the actual transcript (zero bullshit scoring)
- Grading too generously (false signal wastes CC's time)
- Extracting lessons without logging them (lesson decays in 48 hours)
- Rewriting the skill based on one data point (need 3 occurrences)
- Skipping the "next step secured" check — this is the single best predictor of deal velocity

## Obsidian Links
- [[skills/sales-methodology/SKILL]]
- [[skills/sales-closing/SKILL]]
- [[memory/PATTERNS]]
- [[memory/PATTERNS]]
- [[brain/USER]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
