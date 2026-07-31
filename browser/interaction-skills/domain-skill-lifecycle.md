---
tags: [browser, automation]
last_updated: 2026-05-11
---

# Domain Skill Lifecycle

Use this after discovering site-specific knowledge.

## When To Create Or Update

Update a domain skill when you learn:

- a stable selector
- a private API route
- a load/wait condition
- a login/auth trap
- a modal/dialog trap
- a site-specific workflow
- a route that skips unnecessary UI
- an action that needs approval

## File Location

Use:

```text
browser/domain-skills/<site>.md
```

If the site is a client portal, start from:

```text
browser/domain-skills/client-portal-template.md
```

## Quality Bar

A useful domain skill lets the next agent save time without exposing private data.

Do not include run narration, raw coordinates, secrets, cookies, tokens, or screenshots with sensitive data.

## Related
- [[browser/README]]
- [[browser/interaction-skills/INDEX]]
- [[skills/browser-automation/SKILL]]


## Related (graph)

- [[browser/interaction-skills/INDEX]]
- [[browser/interaction-skills/approval-gates]]
- [[browser/interaction-skills/connection]]
- [[browser/interaction-skills/evidence]]
