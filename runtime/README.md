---
tags: [runtime]
last_updated: 2026-04-27
---

# Bravo Runtime Layer

This directory is the future home for the shared runtime that sits under Bravo, Atlas, Maven, Aura, and Hermes.

## Why It Exists

Bravo already has deep business intelligence. The missing layer is product infrastructure:

- one installer
- one setup wizard
- one doctor
- one tool registry
- one skill lifecycle
- one browser intelligence layer
- one session/search substrate
- one agent scaffold

## Current First Step

The Browser Harness integration added:

- a real installed browser tool
- a Bravo wrapper skill
- browser domain skills
- interaction skills
- onboarding diagnostics

## Planned Modules

```text
runtime/
  README.md
  tool_manifest.py
  session_store.py
  skill_lifecycle.py
  profile_home.py
  gateway/
    router.py
    adapters/
```

## Boundary

Runtime code should orchestrate existing scripts. It should not duplicate business logic that already works in `scripts/`.

Critical rule: runtime messaging must preserve the V5.6 outbound chokepoint.

## Related
- [[brain/INDEX]]
- [[skills/INDEX]]
