---
tags: [browser, automation]
last_updated: 2026-05-11
---

# Browser Use Cloud

## Site

- URL patterns: Browser Use dashboard and cloud browser live URLs
- Auth assumptions: BROWSER_USE_API_KEY may be configured later.
- Agent owner: Bravo/Codex
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect cloud browser sessions and profiles.
- Remote browser: run isolated browsers for parallel agents with distinct `BU_NAME`.
- Approval required: paid usage if it increases cost, profile sync with personal login state.

## Preferred Tooling

Use upstream Browser Harness helpers:

- `start_remote_daemon("work")`
- `list_cloud_profiles()`
- `list_local_profiles()`
- `sync_local_profile()`

## Traps

- Remote browsers can bill until timeout.
- Profile sync can upload login state. Treat as sensitive.
- Distinct `BU_NAME` values prevent parallel agents from fighting over the same session.

## Approval Gates

Approval required before uploading/syncing a local profile, using paid cloud browsers for long sessions, or sharing live URLs externally.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]


## Related (graph)

- [[browser/domain-skills/README]]
- [[browser/domain-skills/canva]]
- [[browser/domain-skills/client-portal-template]]
- [[browser/domain-skills/github]]
