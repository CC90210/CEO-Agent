---
name: opencli
description: Explore websites and create CLI adapters using OpenCLI
trigger: /opencli
---

# /opencli — Website-to-CLI Automation

## Trigger
`/opencli <url-or-command>`

## Behavior

### Mode 1: Explore a Website
When CC provides a URL: `/opencli https://example.com`

1. Run `opencli explore <url>` to discover API endpoints
2. Present findings: endpoints found, auth strategy, confidence scores
3. Ask CC if they want to synthesize adapters
4. If yes: run `opencli synthesize` and present generated adapters
5. Test the adapters and report results

### Mode 2: Run an Existing Command
When CC provides a platform command: `/opencli twitter trending`

1. Run the command: `opencli twitter trending --json`
2. Parse and present results in a readable format
3. If the command fails, suggest alternatives or re-explore

### Mode 3: List Available Commands
When CC asks what's available: `/opencli list`

1. Run `opencli list`
2. Present categorized command list

## Skill Reference
Load `skills/opencli/SKILL.md` for full documentation.

## Post-Action
- Log results to `memory/SESSION_LOG.md`
- If a new adapter was created, update `brain/CAPABILITIES.md`

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
