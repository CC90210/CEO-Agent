---
description: "Template for logging validated patterns (working approaches proven through re-use); agents reference to recall when/why to apply them"
tags: [memory, patterns, template]
last_updated: 2026-06-09
freshness_threshold_days: 30
---
# PATTERNS — {{ preferred_name }}

> Validated ways of working that paid off. Bravo logs here when a new/non-obvious
> approach succeeds. Live version is gitignored (per-operator); this template ships
> the schema so a fresh clone has the structure and inbound `[[memory/PATTERNS]]`
> links resolve.

## Lifecycle
`[P]` Probationary (first use) → promote to `[V]` Validated after 3 successful re-uses.

## Format

```
### [P] <short pattern name> — YYYY-MM-DD
**Pattern:** what to do.
**Why it works:** the mechanism / root benefit.
**When to apply:** the trigger conditions.
**Uses:** 1 (increment on each re-use; [P]→[V] at 3)
```

## Example (illustrative — not real data)

### [V] Verify in a throwaway mirror before any irreversible push — 2026-06-09
**Pattern:** Run destructive git history rewrites in a `--mirror` clone and verify the result before force-pushing the real remote.
**Why it works:** the mirror is discardable, so a wrong assumption costs nothing; the real remote only changes once the outcome is proven.
**When to apply:** any history rewrite, mass migration, or one-way data operation.
**Uses:** 3

## Live entries below

<!-- Bravo appends validated patterns here. -->

## Related
- [[memory/INDEX]]
- [[memory/MISTAKES.template.md]]
