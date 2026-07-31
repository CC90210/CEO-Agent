---
name: auto-generated
description: Container for skills synthesized at runtime by skill_synthesizer.py. Each child directory is a [NEW] skill with its own SKILL.md + metrics.json. Promoted to skills/<slug>/ after 3 successful uses (skill_metrics.py promote).
tier: meta
owner: bravo
risk: low
status: '[VALIDATED]'
disable-model-invocation: true
triggers: [synthesize, new auto-generated skill]
tags: [skill, auto-generated]
last_updated: 2026-05-06
---

# Auto-Generated Skills Container

This is the parent skill directory for runtime-synthesized skills. Children appear when `scripts/skill_synthesizer.py synthesize --decision-id X` extracts a successful pattern from `agent_decisions` and renders it as a SKILL.md.

## Lifecycle

1. **`[NEW]`** — child directory created here, frontmatter status set to `[NEW]`
2. **`[VALIDATED]`** — after 3 successful uses tracked in `metrics.json`, `skill_metrics.py promote --skill <name>` moves the child up to `skills/<name>/`
3. **Pruned** — if a `[NEW]` skill goes unused for 30 days, `skill_metrics.py` recommends removal

## Safety

`skill_synthesizer.py validate` rejects auto-generated skills containing destructive triggers (rm, drop, delete, force, send, post, publish, pay) unless the `disable-model-invocation: true` flag is set. CC reviews promotions; auto-promotion is blocked for any skill that touches send_gateway, Stripe, Supabase migrations, or git push.

## Reference

- `scripts/skill_synthesizer.py` — the extractor
- `scripts/skill_metrics.py` — the promoter
- `skills/auto-generated/README.md` — operator-facing lifecycle docs

## Obsidian Links
- [[skills/auto-generated/README]] | `scripts/skill_synthesizer.py` | `scripts/skill_metrics.py`
