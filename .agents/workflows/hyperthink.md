---
description: Fire the Hyperthink maximum-depth reasoning protocol — structured 7-phase loop for architectural, irreversible, or multi-hypothesis problems.
---

# /hyperthink — Maximum-Depth Reasoning

## What This Command Does

Engages the **Hyperthink protocol** — a structured multi-hypothesis reasoning loop for CC's highest-stakes problems. Wraps Claude Code's native `ultrathink` (31,999 thinking tokens) with a 7-phase framework that forces real divergence, adversarial stress testing, and documented reversibility.

> **IMPORTANT:** This command does NOT by itself allocate more thinking tokens unless the underlying Claude Code runtime recognizes one of the trigger words. To guarantee extended thinking, CC should also include the literal word `ultrathink` in the message. The protocol below runs either way and produces the same structured output.

## When to Use

Fire `/hyperthink` when ANY of these are true:

- **Architectural change** — touches 5+ files, changes a system invariant, or rewrites a contract
- **Irreversible / expensive to undo** — destructive migrations, schema changes, deployment topology
- **Multi-hypothesis debugging** — 3+ plausible root causes and picking wrong is expensive
- **Strategic business call** — pricing, partnerships, client concentration decisions
- **Cross-cutting refactor** — spans multiple directories or services

**Do NOT fire for:**
- Simple edits (<3 files, reversible)
- Lookups / status queries
- Tasks where the obvious answer is correct
- Any task you'd finish faster than you'd spend thinking

## How It Works / Steps

Load `skills/hyperthink/SKILL.md` and run the full 7-phase loop. Output must start with `HYPERTHINK ENGAGED` and include every phase, even if a phase is short.

### Phase 1 — REFRAME
Restate the problem. Identify goal, constraints, explicit assumptions, reversibility level.

### Phase 2 — MAP
List every moving piece: files, agents, services, upstream triggers, downstream consequences, blast radius.

### Phase 3 — GENERATE (force 3 real alternatives)
Produce 3 genuinely distinct approaches. Score each: completeness (0-10), human-team time, CC+Bravo time, risk profile, reversibility.

### Phase 4 — STRESS TEST (top candidate only)
Ask: double-click, network drop mid-request, scale (10k → 10M rows), malicious input, concurrent modification, dependency misconfigured.

### Phase 5 — COORDINATE
Check `~/.claude/AGENT_COORDINATION.md` for overlap with sibling Claude agents. Check existing skills/utils for reuse. Never fork silently.

### Phase 6 — DECIDE
Pick winner in one sentence. Document killers (abort conditions) and rollback path.

### Phase 7 — EXECUTE
Run the plan with Reflexion on failure. On any error: stop, reflect (1-3 sentences), branch (adjust or fall back to Plan B), log to `memory/SELF_REFLECTIONS.md` if the lesson is generalizable.

## Output Format

Always start with:

```
HYPERTHINK ENGAGED
════════════════════
```

Then include all 7 phase blocks inline. See [[skills/hyperthink/SKILL]] for the full template.

## Anti-Patterns

- Firing on trivial tasks (dilutes signal, burns tokens)
- Phase 3 producing 3 variations of the same idea instead of real alternatives
- Picking the winner before Phase 4
- Skipping Phase 5 coordination check — causes collisions with sibling Claude agents
- Silent failures — always surface what broke
- Forgetting to log Reflexion on failure

## Related

- [[skills/hyperthink/SKILL]] — full protocol definition
- [[skills/sequential-reasoning/SKILL]] — standard-tier reasoning (use for moderate complexity)
- [[skills/systematic-debugging/SKILL]] — specialized root-cause analysis
- [[skills/codex-delegation/SKILL]] — Codex as a second-mind participant in Phase 3 or Phase 4
- [[brain/BRAIN_LOOP]] — the baseline 10-step loop hyperthink amplifies
- `~/.claude/AGENT_COORDINATION.md` — cross-agent coordination ledger (Phase 5 check)


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
