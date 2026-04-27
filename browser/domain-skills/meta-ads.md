# Meta Ads

## Site

- URL patterns: `https://adsmanager.facebook.com/`, `https://business.facebook.com/`
- Auth assumptions: CC or Maven may be logged in locally. Budgets and campaigns are high risk.
- Agent owner: Maven
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect campaign structure, spend, learning status, errors, audiences, creatives.
- Draft-only: prepare campaign notes and screenshots.
- Approval required: budget changes, publishing ads, pausing/enabling campaigns, audience edits, billing changes.

## Traps

- Meta UI is iframe-heavy and dynamic.
- Account/ad account selector matters. Confirm visible account before interpreting data.
- Draft changes can persist in the UI.

## Approval Gates

Approval required before publish, pause, enable, budget edits, audience edits, creative edits, billing changes, or business manager permission changes.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]
