---
tags: [runtime]
last_updated: 2026-05-11
---

# Skill Lifecycle

Bravo's skill system should become a managed lifecycle, not a folder full of disconnected instructions.

## States

| State | Meaning | Required Evidence |
|---|---|---|
| `draft` | Created but not trusted | SKILL.md exists |
| `registered` | Discoverable by agents | linked in `skills/INDEX.md` and docs |
| `validated` | Used successfully | structural validation and at least one successful use |
| `promoted` | Included in default agent pack | default docs mention it |
| `deprecated` | Replaced or unsafe | replacement documented |

## Required Fields

Every `SKILL.md` needs:

- `name`
- `description`
- trigger conditions
- safety constraints
- exact commands or files used
- verification path

## Browser Domain Skills

Browser domain skills live outside `skills/` because they are site memory, not agent behavior packages.

Use:

```text
browser/domain-skills/<site>.md
```

They should be promoted when the same site is used repeatedly by Bravo, Atlas, Maven, Aura, Hermes, or a client agent.

## Future Commands

```text
bravo skills list
bravo skills validate <name>
bravo skills audit
bravo skills promote <name>
bravo skills deprecate <name>
bravo browser learn <site>
```

## Related
- [[brain/INDEX]]
- [[skills/INDEX]]


## Related (graph)

- [[runtime/README]]
