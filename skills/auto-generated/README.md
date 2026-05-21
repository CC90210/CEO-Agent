---
tags: [skills, auto-generated, lifecycle]
---

# Auto-Generated Skills

> Skills in this directory were created by `scripts/skill_synthesizer.py` from
> successful patterns observed in `agent_decisions`. They are NOT hand-authored.

## Lifecycle

Every auto-generated skill moves through three states:

```
[NEW]  ->  [VALIDATED]  ->  promoted to skills/<slug>/
```

| State | Meaning | How to move forward |
|-------|---------|---------------------|
| `[NEW]` | Just generated, not yet proven | Use the skill; `skill_metrics.py track` each time |
| `[VALIDATED]` | 3+ successes with >85% success rate | Automatic at threshold, or manual promote |
| `[PROMOTED]` | Copied to `skills/<slug>/` (main tree) | Final state in auto-generated; canonical lives in `skills/` |

## Promotion conditions

A skill is eligible for promotion when **both** are true:
- `success_count >= 3`
- `success_rate > 0.85`

The `skill_metrics.py track` command auto-sets status to `[VALIDATED]` when
these conditions are met. Run `skill_metrics.py promote` to copy the skill to
the main tree and log it to `memory/PATTERNS.md`.

## How to inspect a generated skill

Every skill folder contains:
- `SKILL.md` — the auto-generated skill documentation (YAML frontmatter + body)
- `metrics.json` — usage tracking (auto-created on first `track` call)

Read `SKILL.md` to understand what the skill does and whether the extraction
was accurate. The `source_decision_id` field in the frontmatter points to the
`agent_decisions` row this was generated from.

## How to manually approve or reject

**To approve early** (before 3 tracked uses):

```bash
# 1. Edit the metrics.json to set success_count >= 3 and success_rate > 0.85
# 2. Run:
python scripts/skill_metrics.py promote --skill <skill-slug>
```

**To reject** (skill should not exist):

```bash
# Simply delete the folder — no registry entry exists yet at [NEW] status.
rm -rf skills/auto-generated/<slug>/
```

If the skill was already registered (passed validate + register stages),
deactivate it in the skills_registry table:

```bash
python scripts/register_skill.py audit  # find the registry row
# Then manually set is_active=false in Supabase
```

## Safety guarantees

The `skill_synthesizer.py validate` step **blocks** any auto-generated skill
whose steps or triggers contain these terms:

```
rm, drop, delete, truncate, force-push, force, send, post, publish, pay, charge, deploy, migrate
```

Skills containing these terms will fail at the validate stage and NEVER be
auto-registered. They can only reach the main tree through manual author.

This means auto-generated skills are safe to run in read-only or analysis
contexts. Any skill that would mutate external state must be authored by hand.

## Required frontmatter fields

Every `SKILL.md` in this directory must have these YAML frontmatter fields:

```yaml
---
name: <kebab-case-slug>
description: <one sentence>
tier: specialized
owner: bravo
risk: low
triggers: ["<phrase 1>", "<phrase 2>"]
status: '[NEW]'
generated_at: <ISO 8601>
confidence: <float 0.0-1.0>
source_decision_id: <agent_decisions row id>
---
```

## Related scripts

| Script | Purpose |
|--------|---------|
| `scripts/skill_synthesizer.py` | Extract -> generate -> validate -> register pipeline |
| `scripts/skill_metrics.py` | Track uses, promote to main tree |
| `scripts/register_skill.py` | Wire skill into `skills_registry` Supabase table |

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]] | [[memory/PATTERNS]]
