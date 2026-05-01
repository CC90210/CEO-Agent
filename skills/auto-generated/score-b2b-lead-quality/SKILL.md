---
name: score-b2b-lead-quality
description: Evaluate inbound B2B SaaS leads using weighted signal analysis to prioritize routing and outreach strategy.
tier: specialized
owner: bravo
risk: low
triggers: ["evaluate lead quality", "should we reach out to this prospect", "rate this inbound lead", "what's the lead score"]
status: '[NEW]'
generated_at: 2026-05-01T23:14:33.463288+00:00
confidence: 0.78
source_decision_id: 34008c17-4efa-422b-99e0-01f1196f437f
---

# Score B2b Lead Quality

> Evaluate inbound B2B SaaS leads using weighted signal analysis to prioritize routing and outreach strategy.

## Why this skill exists

Auto-generated from a successful agent decision (confidence 0.78).
The agent completed this workflow with high reliability — encoding it as a
skill makes it discoverable and reusable without re-discovering the pattern.

## Trigger phrases

- evaluate lead quality
- should we reach out to this prospect
- rate this inbound lead
- what's the lead score

## Steps

1. Identify hiring activity signals (open roles, job postings) and assign a weight of 2.5x
2. Extract funding recency data (stage, announcement date) and apply decay function, weight 1.8x
3. Measure inbound engagement signals (page visits, downloads, content interactions) and weight 3.0x
4. Calculate composite score: (hiring_signal × 2.5) + (funding_recency × 1.8) + (inbound_engagement × 3.0)
5. Normalize composite score to 0-100 scale
6. If final score falls between 49-51, use Claude Haiku to break tie and finalize categorization
7. Bucket lead into tier: hot (>80), warm (50-80), or cold (<50)
8. Return scored lead with tier assignment and routing recommendation

## Tools used

- `claude-haiku`
- `lead-scoring-engine`

## Success signals

- Lead assigned to correct tier (hot/warm/cold) based on composite signals
- Score falls within 0-100 range
- Tie-breaking resolved for borderline cases
- Lead ready for routing into appropriate pipeline

## Preconditions

- Lead profile contains hiring activity data
- Lead profile contains funding information with dates
- Lead profile contains engagement event history
- Lead is B2B SaaS company in target market segment

## Safety note

This skill was auto-generated and carries status `[NEW]`. It has been
validated to contain no destructive operations. After 3 successful tracked
uses via `python scripts/skill_metrics.py track`, it will be promoted to
`[VALIDATED]` and moved to `skills/score-b2b-lead-quality/SKILL.md`.

To manually approve earlier: edit `skills/auto-generated/score-b2b-lead-quality/metrics.json`
and run `python scripts/skill_metrics.py promote --skill score-b2b-lead-quality`.

## Related files

- `skills/auto-generated/score-b2b-lead-quality/metrics.json` — usage tracking
- `scripts/skill_metrics.py` — promotion tool
- `scripts/skill_synthesizer.py` — generation pipeline

## Obsidian Links
- [[skills/auto-generated/README]]
