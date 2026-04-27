# Progressive Skill Loading Protocol

## Overview

Skills consume context window tokens. Loading all 55 skills at session start would burn most of the context budget before work begins. Progressive loading ensures only relevant content is in context.

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

All 55 skills now have `triggers:` in their YAML frontmatter. The frontmatter IS the authoritative trigger source -- no separate table needed.

To scan triggers, read the frontmatter of each skill:
```
skills/[skill-name]/SKILL.md → triggers: [keyword1, keyword2, ...]
```

**Core skills (8)** — always pre-warmed: systematic-debugging, memory-management, self-healing, mcp-operations, security-protocol, using-superpowers, heartbeat, growth-engine

**Standard skills (22)** — loaded on trigger match: browser-automation, code-review, content-engine, dispatching-parallel-agents, e2e-testing, executing-plans, finishing-a-development-branch, frontend-design, n8n-patterns, receiving-code-review, requesting-code-review, sequential-reasoning, ship, sop-breakdown, subagent-driven-development, supabase-patterns, test-driven-development, using-git-worktrees, verification-before-completion, webapp-testing, writing-plans, brainstorming

**Specialized skills (25)** — loaded only on explicit trigger: ai-integration, algorithmic-art, brand-guidelines, canvas-design, cli-anything, doc-coauthoring, docx, internal-comms, investor-materials, linkedin-outreach, market-research, mcp-builder, n8n-mcp-integration, notebooklm, pdf, pptx, retro, skill-creator, skool-automation, slack-gif-creator, strategic-compact, theme-factory, web-artifacts-builder, writing-skills, xlsx

## Integration with Brain Loop Step 2 (RECALL)

During RECALL, the agent should:

1. Identify task type from CC's request (1-2 words: "bug fix", "new feature", "content post")
2. Match task type against `triggers:` keywords in skill frontmatter
3. Load matched skills' Tier 2 content (SKILL.md body)
4. Load their declared dependencies if any
5. Proceed with execution using loaded skills as methodology guides

This replaces the previous pattern of loading all skills speculatively. The frontmatter triggers cover 100% of skills with zero ambiguity.

## Obsidian Links
- [[skills/SKILL_LOADING]] | [[skills/INDEX]]
