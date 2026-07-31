---
name: self-evolution
description: Promote a validated memory pattern into permanent, routable capability — a skill or an SOP. Use when CC says evolve, when a retro produces a lesson worth keeping, or when a pattern has been applied enough times that the next agent should not have to re-derive it.
triggers: ["evolve", "promote this pattern", "make this a skill", "turn this into an sop", "what should be promoted", "scan for promotion candidates"]
tier: meta
mutability: EVOLVING
tags: [skill, self-improvement, evolution, memory, promotion]
last_updated: 2026-07-29
---

# /evolve — Promote Memory Into Capability

> **The gap this closes.** The fleet already *records* lessons — `bravo_sleep.py` writes
> `memory/MISTAKES.md` and `memory/PATTERNS.md`, `agent_self_improvement.py` rebuilds the
> capability graph and flags staleness, `skills/retro` runs a session retrospective. Nothing
> **promotes**. A pattern could be marked `[V]` (validated, applied 3+ times per Rule 9) and
> still live only as a memory line: not a skill, not an SOP, not routable, invisible to
> `capability_query.py resolve`. The next agent re-derives it from scratch. That is a
> learning loop with no output stage.

## Where this sits

```
outcome ──▶ bravo_sleep ──▶ memory/PATTERNS.md  [P] ──3 uses──▶ [V]
                                                                 │
                                          ▶ /evolve scan ────────┘   ← THIS SKILL
                                                 │
                                                 ▼
                                    skills/<name>/SKILL.md   or   docs/sop/<NAME>.md
                                                 │
                                                 ▼
                                    build_capability_graph.py  → routable by every agent
```

### How this relates to what already existed

- **`.agents/workflows/evolve.md`** — the `/evolve` *procedure*: retrieval queries, candidate
  classification, the Five-Gate filter, the report. It predates this skill and remains the
  authority on **judgement**. It called for "create a new skill in skills/" but had no tool to
  do it, and no way to measure gate 3 (REDUNDANCY) beyond reading. `evolve.py scan` is that
  measurement; the workflow now opens with it as Step 0.
- **`skills/self-improvement-protocol`** — the four *behavioural* loops (heal / optimise /
  develop / improve). Broader, and not artifact-producing.
- **This skill** — the single mechanical step: which validated patterns have no owner, and
  scaffolding one when they don't.

Three layers, not three copies: procedure (workflow) → measurement (this) → behaviour (protocol).

## Commands

```bash
python scripts/core/evolve.py scan                    # validated patterns with no owner
python scripts/core/evolve.py scan --json --limit 30
python scripts/core/evolve.py promote "<title>" --kind skill          # dry run
python scripts/core/evolve.py promote "<title>" --kind skill --apply  # writes the scaffold
python scripts/core/evolve.py promote "<title>" --kind sop --apply
```

`scan` compares each `[V]` entry's vocabulary against every existing skill and SOP. Overlap
≥ 0.5 counts as already-owned; below that it is a candidate, listed weakest-match first.

## It scaffolds — it does not author

`promote --apply` writes a stub carrying the pattern text, the provenance line, and a TODO
block. **It deliberately does not write the body.** A skill authored by token-overlap
heuristics is mock data wearing documentation's clothes — Anti-Slop #3 applied to knowledge,
and worse than no skill because it *looks* authoritative. A human or an agent with real
context fills it in.

Before the stub counts as a skill:

1. **When to use — and when not.** Calibration is what stops a skill from firing on everything.
2. **The procedure.** Exact commands, paths verified against source (Anti-Slop #7).
3. **The incident.** What actually went wrong. A rule without its incident does not survive
   contact with a deadline.
4. **`triggers:` — narrow.** The resolver scores triggers at 2.0 per overlapping word, so a
   broad trigger steals routes from other skills. Verify both directions:
   ```bash
   python scripts/capability_query.py resolve "<the intent this should own>"
   python -m pytest scripts/tests/test_routing_accuracy.py -q   # golden set must stay green
   ```
5. **Register it:**
   ```bash
   python scripts/build_capability_graph.py && python scripts/build_capability_graph.py --emit-docs
   ```

## Choosing skill vs SOP

- **Skill** — the agent performs it. Has triggers, gets routed, invoked mid-task.
- **SOP** — a human (CC, Adon, a client) follows it, or it is a multi-session runbook.
  Lives in `docs/sop/`, linked from the relevant skill.

When both fit, write the skill and link the SOP from it. Never duplicate the content.

## Cadence

Run `scan` at the end of any session that produced a lesson, and during `skills/retro`.
It is read-only and takes under a second — there is no reason to batch it.

## Related

[[skills/self-improvement-protocol/SKILL]] · [[skills/retro/SKILL]] ·
[[skills/writing-skills/SKILL]] · [[memory/PATTERNS]] · [[memory/MISTAKES]] ·
[[brain/EXECUTION_RULES]] (§ 19 Anti-Slop Matrix)
