# {{AGENT_NAME}} — Skills Index

| Skill | Description | Status |
|---|---|---|
| [[silver-platter/SKILL]] | Per-agent data-readiness audit (V6.7 default) | ✓ scaffolded |
| [[integrations-sync/SKILL]] | Idempotent refresh patterns for external sources (V6.7 default) | ✓ scaffolded |
| [[memory-journaling/SKILL]] | Structured DECISIONS / PATTERNS / MISTAKES logging (V6.7 default) | ✓ scaffolded |
| _domain skills_ | Add first domain skill to `skills/<name>/SKILL.md` | — |

## Adding a Skill

Create `skills/<slug>/SKILL.md` with YAML frontmatter:

```yaml
---
name: skill-slug
description: One-line trigger statement. When should this skill fire?
---
```

Then add a row to this index.

## Related
- [[../AGENTS]] · [[../CLAUDE]]
- [[brain/INDEX]]
