---
name: opencli
description: Turn any website into CLI commands via browser automation. Explore URLs for API discovery, run prebuilt platform commands, or synthesize new adapters.
user-invocable: true
---

# /opencli — Website-to-CLI Automation

## Three Modes

### Mode 1: Explore a URL
```bash
opencli explore <url>
```
Discovers API endpoints, forms, and interactive elements on any website.

### Mode 2: Run a Platform Command
```bash
opencli <platform> <command> [options] --json
```
46 platforms available. Examples:
- `opencli twitter search "AI automation" --json`
- `opencli reddit hot --subreddit smallbusiness --json`
- `opencli hackernews top --json`
- `opencli linkedin search "HVAC business owner" --json`

### Mode 3: List Available Commands
```bash
opencli list                    # All platforms
opencli list --platform twitter # Platform-specific
```

## When to Use
- **Research**: Search social platforms for trends, competitors, leads
- **Content**: Find trending topics before writing
- **Lead gen**: Search for potential clients by industry
- **API discovery**: Find undocumented endpoints on any website

Always use `--json` flag for structured output that agents can parse.

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
