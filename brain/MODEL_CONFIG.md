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
    model: claude-sonnet-4-6
    fallbacks: *id001
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
- [[brain/AGENT_GAP_AUDIT]]
- [[brain/AGENT_INDEX]]
