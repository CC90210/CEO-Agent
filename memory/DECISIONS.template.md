---
description: "Template for recording tactical decisions (decision/reasoning/revisit criteria); agent appends to per-operator live version (gitignored)"
tags: [memory, decisions, template]
last_updated: 2026-06-09
freshness_threshold_days: 90
---
# DECISIONS — {{ preferred_name }}

> Tactical / business decisions and the reasoning behind them ("We decided X
> because Y"). Distinct from `docs/adr/` (architectural, persistent). Live version
> is gitignored (per-operator); this template ships the schema so inbound
> `[[memory/DECISIONS]]` links resolve in a fresh clone.

## Format

```
### <decision title> — YYYY-MM-DD
**Decision:** what was decided.
**Why:** the reasoning / trade-off accepted.
**Revisit when:** the condition that would reopen it (or "stable").
```

## Example (illustrative — not real data)

### Defer the money-path refactor to a fresh session — 2026-06-09
**Decision:** do the large send-path decomposition on its own, a day after the other changes land.
**Why:** refactoring the outbound money path alongside nine other changes multiplies outage risk; isolation makes the diff reviewable and the blast radius small.
**Revisit when:** the surrounding changes are stable in production for 24h.

## Live entries below

<!-- Bravo appends decisions here. -->

## Related
- [[memory/INDEX]]
- [[docs/adr/0001-skill-dependency-classification]]
