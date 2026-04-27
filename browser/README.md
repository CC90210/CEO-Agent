# Bravo Browser Intelligence Layer

This directory is Bravo's durable browser memory and safety layer.

Browser Harness gives direct Chrome/Edge control. Bravo adds the business rules: use safer APIs first, capture reusable site knowledge, and require approval before real account actions.

## Layout

```text
browser/
  README.md
  SAFETY.md
  DOMAIN_SKILL_TEMPLATE.md
  interaction-skills/
  domain-skills/
  evidence/
```

## Layer Hubs
- [[browser/SAFETY]] — fail-closed rules for sends, deletes, money moves
- [[browser/DOMAIN_SKILL_TEMPLATE]] — empty-state template for new site memory
- [[browser/WINDOWS_PATCH]] — Windows-specific fixes for the harness
- [[browser/domain-skills/README|domain-skills hub]] — site-specific browser memory
- [[browser/interaction-skills/INDEX|interaction-skills hub]] — cross-site interaction primitives
- [[browser/evidence/README|evidence hub]] — screenshots / network captures saved during runs

## Obsidian Links
- [[brain/STATE]] | [[brain/CAPABILITIES]] | [[skills/browser-harness/SKILL]] | [[skills/browser-automation/SKILL]] | [[skills/e2e-testing/SKILL]]

## Operating Model

1. Diagnose the harness: `python scripts/browser_harness_doctor.py`.
2. Search `browser/domain-skills/` before exploring a site.
3. Use Browser Harness for authenticated UI tasks and screenshots.
4. Prefer official CLIs/APIs for logged business operations.
5. Add durable site findings back to `browser/domain-skills/`.

## Installed Tool

- Checkout: `C:\Users\User\APPS\browser-harness`
- CLI: `C:\Users\User\.local\bin\browser-harness.exe`
- Global Codex skill: `C:\Users\User\.codex\skills\browser-harness`
- Bravo skill: `skills/browser-harness/SKILL.md`

## Current Attach State

The harness is installed. Chrome/Edge attach requires one-time remote-debugging approval in the browser profile.

Run:

```powershell
& (Get-Command browser-harness).Source --setup
```

If Chrome opens `chrome://inspect/#remote-debugging`, choose the normal profile, enable the remote debugging/discovery option if shown, and click `Allow` if prompted.

## Rule

Browser Harness is allowed to observe, inspect, test, and draft. It is not allowed to send, publish, delete, buy, move money, change billing, or change production configuration without explicit CC approval.
