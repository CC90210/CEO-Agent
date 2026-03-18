# Progressive Skill Loading Protocol

## Overview

Skills consume context window tokens. Loading all 53+ skills at session start would burn most of the context budget before work begins. Progressive loading ensures only relevant content is in context.

## Three-Tier Loading

### Tier 1: Frontmatter (Always Available)
Every skill has YAML frontmatter with name, description, and trigger keywords. This metadata is lightweight (~50 tokens per skill) and can be scanned without loading the full skill.

When the Brain Loop reaches Step 2 (RECALL), scan skill frontmatter to identify relevant skills for the current task. Only load Tier 2 for matched skills.

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

| Skill | Key Triggers |
|-------|-------------|
| systematic-debugging | bug, error, failure, crash, broken, not working, debug |
| memory-management | memory, bloat, archive, compress, session log, confidence |
| self-healing | heal, broken config, drift, inconsistent, stale |
| test-driven-development | test, TDD, failing test, unit test, red green |
| browser-automation | playwright, browser, navigate, screenshot, click, snapshot |
| e2e-testing | end-to-end, E2E, user journey, integration test |
| code-review | review, PR, quality, security audit, checklist |
| mcp-operations | MCP, tool routing, Late, n8n, Supabase MCP |
| skool-automation | Skool, lesson, classroom, community, Tiptap |
| writing-plans | plan, implementation plan, feature plan |
| executing-plans | execute plan, run plan, implement plan |
| security-protocol | secret, credential, API key, exposed, rotation |
| n8n-patterns | n8n, workflow, automation, trigger, node |
| supabase-patterns | Supabase, SQL, migration, RLS, schema |
| sop-breakdown | SOP, standard operating procedure, process |
| content-engine | content, post, copy, brand voice, pillar |
| linkedin-outreach | LinkedIn, outreach, lead, prospect, DM |
| growth-engine | MRR, revenue, growth, sales, pipeline |
| frontend-design | UI, design, Tailwind, component, responsive |
| cli-anything | CLI, wrapper, SDK, subprocess |

## Integration with Brain Loop Step 2 (RECALL)

During RECALL, the agent should:

1. Identify task type from CC's request (1-2 words: "bug fix", "new feature", "content post")
2. Match task type against trigger keywords in this table
3. Load matched skills' Tier 2 content (SKILL.md body)
4. Load their declared dependencies if any
5. Proceed with execution using loaded skills as methodology guides

This replaces the previous pattern of loading all skills speculatively. The trigger table above covers ~90% of common task types with zero ambiguity.
