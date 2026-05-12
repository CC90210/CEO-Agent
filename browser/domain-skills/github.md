# GitHub

## Site

- URL patterns: `https://github.com/<owner>/<repo>`, `/pull/<number>`, `/issues/<number>`, `/actions`, `/settings`
- Auth assumptions: CC may be logged in locally. Treat settings, secrets, deploy keys, branch protection, and billing as approval-gated.
- Agent owner: Bravo/Codex
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect README, files, PRs, issues, Actions checks, releases, commit history.
- Draft-only: prepare PR comments or issue text in local files.
- Approval required: merge, close, delete branch, change settings, add secrets, invite users, publish releases.

## Stable Navigation

- Repo file view: `https://github.com/<owner>/<repo>`
- Pull request: `https://github.com/<owner>/<repo>/pull/<number>`
- Actions: `https://github.com/<owner>/<repo>/actions`
- Settings are high-risk: do not modify without approval.

## Selectors And Structure

- Prefer visible text and ARIA labels for buttons.
- GitHub uses dynamic React areas; verify after every click with screenshot and URL.
- Diff pages can virtualize content. Use GitHub connector or CLI for exact diffs when possible.

## Preferred Tools

- Use GitHub app/connector for PR metadata and comments when available.
- Use `git` and local clone for code inspection.
- Use Browser Harness for visual repo inspection, Actions UI, and settings verification.

## Approval Gates

Approval required before merge, close, delete, rerun costly workflows, alter repo settings, alter collaborators, edit secrets, or publish releases.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]


## Related (graph)

- [[browser/domain-skills/README]]
- [[browser/domain-skills/browser-use-cloud]]
- [[browser/domain-skills/canva]]
- [[browser/domain-skills/client-portal-template]]
