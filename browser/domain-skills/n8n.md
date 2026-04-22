# n8n

## Site

- URL patterns: n8n cloud or Hostinger-hosted editor URLs
- Auth assumptions: CC may be logged in locally. Active workflows can affect production communication.
- Agent owner: Bravo
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect workflow nodes, execution history, errors, schedules, credentials names.
- Draft-only: prepare node changes and paste-in prompts for CC.
- Approval required: activate/deactivate workflows, edit credentials, run production workflows, delete nodes, change schedules.

## Preferred Tools

- Use `python scripts/n8n_tool.py list`, `search`, `get`, `executions`, and `stats` before browser work.
- Browser Harness is for visual workflow editing where the API is awkward.

## Traps

- Credentials are sensitive. Do not reveal, copy, or store them.
- A manual "execute workflow" can send real messages.
- Active workflow changes can take effect immediately.

## Approval Gates

Approval required before activating, deactivating, executing production workflows, saving major node changes, editing credentials, changing schedules, or deleting nodes.
