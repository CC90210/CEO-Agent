---
name: browser-harness
description: Use Browser Harness for direct Chrome/Edge browser control, browser diagnostics, and durable domain-skill learning while preserving Bravo's business safety gates.
triggers: ["browser harness", "use browser harness", "run browser harness", "use browser harness for direct chrome/edge browser control"]
tier: standard
---

# Browser Harness

Browser Harness is Bravo's direct browser-control layer. Use it when a task needs a real logged-in browser, authenticated web app navigation, UI inspection, screenshots, form testing, or repeatable site-specific automation.

Bravo now treats browser work as compounding procedural memory: every time a site reveals a durable pattern, selector, wait, API route, auth wall, or trap, capture it in `browser/domain-skills/` so the next agent starts smarter.

## Install State

- CLI script: `scripts/browser/browser_harness_cli.py` (replaces broken uv shim)
- Wrapper script: `C:\Users\User\.local\bin\browser-harness.cmd`
- CloakBrowser: `scripts/browser/cloak_browser_tool.py` (stealth Chromium v146)
- Bravo wrapper skill: this file
- Bravo domain memory: `browser/domain-skills/`
- Bravo interaction memory: `browser/interaction-skills/`

Run diagnostics before using it:

```powershell
python scripts/browser/browser_harness_doctor.py
```

If invoking the CLI directly:

```powershell
python scripts/browser/browser_harness_cli.py --doctor
python scripts/browser/browser_harness_cli.py --setup
```

## Required Context

Before doing browser work:

1. Read this file.
2. Read `browser/SAFETY.md`.
3. Search `browser/domain-skills/` for the site.
4. Search `browser/interaction-skills/` only when the browser mechanic itself is the hard part.
5. If using upstream helpers directly, read `C:\Users\User\APPS\browser-harness\helpers.py`.

## Default Invocation

**Browser Harness (browser_use):**
```powershell
python scripts/browser/browser_harness_cli.py --setup
```

**CloakBrowser (stealth, for bot-protected sites):**
```powershell
python scripts/browser/cloak_browser_tool.py scrape <url> --json
python scripts/browser/cloak_browser_tool.py check-stealth --json
python scripts/browser/cloak_browser_tool.py goto <url> --eval "<js>"
```

Use CloakBrowser for fresh-session scrapes against bot-protected sites.
Use Browser Harness for authenticated CC session work.

## Safety Gates

Browser Harness is high-trust. It can click real account UIs. That means Bravo's business safety rules override upstream convenience.

Always require explicit CC approval before:

- sending email, DMs, posts, comments, proposals, invoices, contracts, or calendar invites
- publishing content
- changing ad budgets, billing, subscriptions, users, permissions, DNS, domains, workflows, or production settings
- moving money, issuing refunds, filing taxes, buying software, upgrading plans, or changing payment methods
- deleting, archiving, suppressing, importing, exporting, or bulk-modifying production business data
- clicking any irreversible confirmation button

When an official CLI/API exists, prefer it over browser clicks:

- outbound communication: `scripts/integrations/send_gateway.py`
- Supabase: `scripts/integrations/supabase_tool.py`
- Stripe: `scripts/integrations/stripe_tool.py`
- Google Workspace: `scripts/integrations/google_tool.py`
- n8n: `scripts/integrations/n8n_tool.py`
- scraping/extraction: `scripts/integrations/firecrawl_tool.py`

Browser Harness is the authenticated UI layer, not a bypass around logged, safer tools.

## Domain-Skill Lifecycle

When a site teaches us something reusable:

1. Add or update `browser/domain-skills/<site>.md`.
2. Capture stable selectors, URL patterns, private API shapes, waits, traps, and approval gates.
3. Do not store secrets, cookies, tokens, screenshots containing private data, raw coordinates, or run narration.
4. Link evidence paths only if the files are safe to keep.
5. Re-run `python scripts/browser/browser_harness_doctor.py` after editing browser infrastructure.

Good domain skills are maps, not diaries.

## Current Windows Note

Upstream Browser Harness assumed Unix sockets. The editable checkout at `C:\Users\User\APPS\browser-harness` has a local Windows compatibility patch that falls back to localhost TCP when `socket.AF_UNIX` is unavailable. Keep that patch unless upstream ships native Windows support.

Chrome/Edge still needs one-time remote-debugging profile approval before attach works. Run:

```powershell
& (Get-Command browser-harness).Source --setup
```

If setup opens `chrome://inspect/#remote-debugging`, pick the normal Chrome profile, tick the remote debugging/discover targets option if shown, and click `Allow` if Chrome prompts.

## Agent Routing

- Bravo: use for business dashboards, GitHub, Supabase UI, Vercel, n8n, Stripe read-only inspection, Google admin UI, and client portals.
- Atlas: use for finance dashboards only with explicit approval before money movement or tax submissions.
- Maven: use for content platforms and ad dashboards only with approval before publishing or budget changes.
- Aura: use for Home Assistant/router dashboards only with approval before locks, cameras, resets, or privacy-sensitive views.
- Hermes/client agents: use per-client profiles and write domain skills for every portal.

## Verification

Minimum verification for browser work:
```powershell
python scripts/browser/browser_harness_doctor.py
python scripts/browser/cloak_browser_tool.py check-stealth --json
```

For a live attach smoke test:
```powershell
python scripts/browser/cloak_browser_tool.py scrape https://example.com --json
```

For a live attach smoke test after CC enables Chrome remote debugging:

```powershell
@'
new_tab("https://github.com/browser-use/browser-harness")
wait_for_load()
print(page_info())
'@ | & (Get-Command browser-harness).Source
```
