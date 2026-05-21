# Progressive Skill Loading Protocol

## Overview

Skills consume context window tokens. Loading all 151 skills at session start would burn most of the context budget before work begins. Progressive loading ensures only relevant content is in context.

As of 2026-04-28, `skills_registry` in Supabase is the runtime catalog. `scripts/register_skill.py sync-all --deactivate-missing --json` syncs every `skills/*/SKILL.md` into the database with triggers, tier, owner agent, risk level, dependencies, and a source hash. `scripts/register_skill.py route "<task>" --json` is the fastest way for any AI interface to decide which skills to load.

## Three-Tier Loading

### Tier 1: Runtime Metadata (Always Available)
Every skill has YAML frontmatter with name, description, and trigger keywords. Supabase stores that metadata plus inferred routing fields, so agents can route by trigger/category/owner/risk without loading the full skill.

When the Brain Loop reaches Step 2 (RECALL), call `python scripts/register_skill.py route "<task>" --json` to identify relevant skills. Only load Tier 2 for matched skills.

Example frontmatter:
```yaml
---
name: Systematic Debugging
description: Root cause investigation before attempting fixes
triggers: [bug, error, failure, crash, broken, not working, debug]
tier: core
dependencies: []
---
```

### Tier 2: Instructions (Activation-Triggered)
The main body of the SKILL.md — the actual methodology, steps, checklists, and rules. Loaded when:
- CC explicitly invokes the skill (e.g., `/review`)
- Brain Loop matches task signals to skill triggers
- Another skill references this one as a dependency

### Tier 3: References (On-Demand)
Supporting files within the skill directory — templates, checklists, examples, taxonomy files. Only loaded when the skill's instructions explicitly reference them.

Example: `skills/code-review/SKILL.md` (Tier 2) references `review/checklist.md` (Tier 3). The checklist is only loaded when the review skill is actively running and reaches the checklist step.

## Loading Rules

1. **Never pre-load Tier 2 or 3** — always scan Tier 1 first
2. **Maximum 3 skills active simultaneously** — if a 4th is needed, evaluate if one can be unloaded
3. **Dependencies load automatically** — if skill A lists skill B as a dependency, loading A triggers loading B
4. **Unload after completion** — when a skill's task is done, its Tier 2/3 content can be released from active consideration
5. **Core skills are pre-warmed** — systematic-debugging, memory-management, and self-healing have their Tier 1 always in context because they apply to every session

## Frontmatter Standard

Every SKILL.md should have this frontmatter (add to existing skills over time):

```yaml
---
name: [Skill Name]
description: [One-line description for Tier 1 scanning]
triggers: [keyword1, keyword2, keyword3]
tier: [core|standard|specialized]
dependencies: [skill-name-1, skill-name-2]
---
```

Tier classification:
- **core**: Always pre-warmed (debugging, memory, self-healing)
- **standard**: Common skills loaded frequently (TDD, browser automation, code review)
- **specialized**: Domain-specific, loaded only on explicit trigger (skool-automation, retro, ship)

## Trigger Keyword Reference

All 151 skills are synced to Supabase with trigger metadata. The folder frontmatter remains the source of truth; `skills_registry` is the runtime cache used for fast routing and drift detection.

To scan triggers manually, read the frontmatter of each skill:
```
skills/[skill-name]/SKILL.md → triggers: [keyword1, keyword2, ...]
```

**Current runtime state:** 151 active skills, 14 core, 45 standard, 92 specialized, 0 invalid; one inactive legacy row (`content-creation`) remains in Supabase for history.

**Core examples** — always pre-warmed or route-boosted: task-routing, send-gateway, email-safety, systematic-debugging, memory-management, self-healing, security-protocol, verification-before-completion, context-optimization, codex-delegation, agent-permissions, anti-drift.

Use `route` for the live list instead of maintaining static trigger tables here.

## Integration with Brain Loop Step 2 (RECALL)

During RECALL, the agent should:

1. Identify task type from CC's request (1-2 words: "bug fix", "new feature", "content post")
2. Match task type with `python scripts/register_skill.py route "<task>" --json`
3. Load matched skills' Tier 2 content (SKILL.md body)
4. Load their declared dependencies if any
5. Proceed with execution using loaded skills as methodology guides

This replaces the previous pattern of loading all skills speculatively. Supabase routing metadata covers 100% of active skills and remains drift-checked against the folder library.

## Obsidian Links
- [[skills/SKILL_LOADING.md]] | [[skills/INDEX.md]]


## Related (graph)

- [[skills/INDEX.md]]
