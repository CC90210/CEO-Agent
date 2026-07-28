---
name: Install / setup help
about: The installer failed, the wizard crashed, or bravo doctor is showing errors
title: "[INSTALL] "
labels: install, help wanted
assignees: CC90210
tags: [root]
last_updated: 2026-05-11
---

## What failed?

Describe what happened. Paste the exact error message.

```
paste error here
```

## Which step failed?

- [ ] `curl ... | bash` — the one-liner itself
- [ ] `irm ... | iex` — the PowerShell one-liner
- [ ] Prerequisite check (missing Python / Node / Git)
- [ ] `git clone` step
- [ ] `pip install -r requirements.txt`
- [ ] `npm install`
- [ ] `bravo setup` wizard
- [ ] `bravo doctor` — one or more checks failing
- [ ] A specific credential validation (name it below)

**Credential / step that failed:**

## Environment

- OS + version: [e.g. macOS 14.5, Ubuntu 22.04, Windows 11 22H2]
- Shell: [bash / zsh / PowerShell 7 / Windows PowerShell 5.1]
- Python: `python3 --version` (paste output)
- Node: `node --version` (paste output)
- Git: `git --version` (paste output)
- Are you behind a corporate proxy or VPN? [yes / no]

## Full terminal output

Paste everything from the terminal — the full install log, not just the last line.

```
paste full output here
```

## What you already tried

List what you tried before opening this issue.

## Which credentials do you have ready?

Check all that apply — this helps narrow down which parts of the wizard will work.

- [ ] Anthropic API key
- [ ] Supabase project URL + service role key
- [ ] Telegram bot token
- [ ] Stripe secret key
- [ ] Other (list below)

## Additional context

Screenshots, network logs, corporate firewall rules — anything that helps.

## Related

- [[.github/ISSUE_TEMPLATE/INDEX]]
- [[.github/ISSUE_TEMPLATE/bug_report]]
- [[.github/ISSUE_TEMPLATE/feature_request]]
