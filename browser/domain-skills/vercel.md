# Vercel

## Site

- URL patterns: `https://vercel.com/<team>/<project>`, `/settings`, `/deployments`
- Auth assumptions: CC may be logged in locally. Env vars and production deploy settings are high risk.
- Agent owner: Bravo/Codex
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect deployments, build logs, project settings, domains, env var names.
- Draft-only: prepare env var checklist or deployment notes.
- Approval required: redeploy, rollback, delete project, change env vars, change domains, disable protection.

## Preferred Tools

- Use CLI for deploys when available and approved.
- Browser Harness is good for reading failed build logs and confirming project settings.

## Traps

- Team scope matters. Confirm the visible account/team before taking action.
- Env var values may be hidden. Do not try to reveal or store secrets.
- Rollback/redeploy buttons affect production.

## Approval Gates

Approval required before redeploy, rollback, domain changes, env var edits, access changes, project deletion, or deployment protection changes.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]


## Related (graph)

- [[browser/domain-skills/README]]
- [[browser/domain-skills/browser-use-cloud]]
- [[browser/domain-skills/canva]]
- [[browser/domain-skills/client-portal-template]]
