---
tags: [brain]
last_updated: 2026-07-02
freshness_threshold_days: 90
verified: 2026-07-02
---

version: 1
defaults:
  provider: claude
  model: claude-sonnet-4-6
  fallbacks: &id001
  - provider: claude
    model: claude-haiku-4-5
agents:
  bravo:
    provider: claude
    model: claude-fable-5
    fallbacks:
    - provider: claude
      model: claude-opus-4-8
    - provider: claude
      model: claude-sonnet-4-6
  atlas:
    provider: claude
    model: claude-sonnet-4-6
    fallbacks: *id001
  maven:
    provider: claude
    model: claude-sonnet-4-6
    fallbacks: *id001
  aura:
    provider: claude
    model: claude-sonnet-4-6
    fallbacks: *id001
task_types: {}

## Related

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
