---
name: Bug report
about: Something is broken or behaving unexpectedly
title: "[BUG] "
labels: bug
assignees: CC90210
---

## What happened?

A clear description of the bug. What did you see? What did you expect?

## Steps to reproduce

1. 
2. 
3. 

## Error output

Paste the exact error message or stack trace here. Wrap in a code block.

```
paste error here
```

## Environment

- OS: [e.g. macOS 14.4, Ubuntu 22.04, Windows 11 + WSL2]
- Python version: `python3 --version`
- Node version: `node --version`
- Bravo version / git commit: `git -C ~/.bravo/repo rev-parse --short HEAD`

## Which component?

- [ ] `install.sh` / `install.ps1`
- [ ] `bravo setup` wizard
- [ ] A specific script in `scripts/` (name it below)
- [ ] Telegram bridge
- [ ] Scheduler / cron jobs
- [ ] Skool automation engine
- [ ] MCP server
- [ ] Other (describe below)

**Component name / file path:**

## Did `bravo doctor` show any failures?

Paste the relevant section of the output.

```
bravo doctor output here
```

## Additional context

Anything else — screenshots, log files, what you tried before opening this issue.
