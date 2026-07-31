---
description: "Failures log template with root-cause and prevention rules; ships as schema so inbound memory links resolve in fresh clones"
tags: [memory, mistakes, template]
last_updated: 2026-06-09
freshness_threshold_days: 30
---
# MISTAKES — {{ preferred_name }}

> Failures + corrections, with root cause and a one-line prevention. The iron law:
> the operator never teaches the same lesson twice. Live version is gitignored
> (per-operator); this template ships the schema so inbound `[[memory/MISTAKES]]`
> links resolve in a fresh clone.

## Format

```
### <short title> — YYYY-MM-DD
**What happened:** the failure / correction.
**Root cause:** the real why (not the symptom).
**Prevention:** one line — the rule that stops a repeat.
```

## Example (illustrative — not real data)

### Assumed a config change took effect mid-session — 2026-06-09
**What happened:** edited a hook's mode in settings, assumed it applied immediately.
**Root cause:** settings `env` is read at session start; mid-session edits don't reload.
**Prevention:** verify behavior with a live smoke-test rather than assuming a settings edit is active.

## Live entries below

<!-- Bravo appends mistakes here. -->

## Related
- [[memory/INDEX]]
- [[memory/PATTERNS.template.md]]
