# LinkedIn

## Site

- URL patterns: `https://www.linkedin.com/`
- Auth assumptions: CC may be logged in locally. Messages and connection requests are outbound.
- Agent owner: Maven/Bravo
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect profiles, company pages, posts, search results.
- Draft-only: prepare connection/message copy locally.
- Approval required: connect, follow, message, comment, post, endorse, react, scrape at scale.

## Preferred Tools

- Use existing CRM/outreach tools where possible.
- Browser Harness can inspect profiles and verify page state.

## Traps

- LinkedIn aggressively rate-limits and flags automation.
- UI labels and modals shift often.
- Do not scrape private data at scale without explicit approval.

## Approval Gates

Approval required before any connection request, message, comment, reaction, follow, profile edit, or post.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]


## Related (graph)

- [[browser/domain-skills/README]]
- [[browser/domain-skills/browser-use-cloud]]
- [[browser/domain-skills/canva]]
- [[browser/domain-skills/client-portal-template]]
