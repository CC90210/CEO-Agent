---
name: browser-harness
description: Use Browser Harness for direct authenticated browser control, diagnostics, and domain-skill learning with Bravo safety gates.
---

# /browser-harness

Use this workflow when CC asks for browser automation, authenticated web app inspection, UI testing, Browser Harness setup, or a reusable site map.

## Steps

1. Read `skills/browser-harness/SKILL.md`.
2. Run `python scripts/browser/browser_harness_doctor.py`.
3. If attach is pending, run `& (Get-Command browser-harness).Source --setup` and ask CC for the Chrome one-time approval only if required.
4. Search `browser/domain-skills/` for the site.
5. Use `new_tab(url)`, then `wait_for_load()`, then `page_info()` or screenshots.
6. Stop for approval before any write, publish, send, billing, finance, admin, destructive, or production action.
7. Add durable findings to `browser/domain-skills/<site>.md`.
8. Re-run diagnostics if browser infrastructure changed.

## Default Smoke Test

```powershell
@'
new_tab("https://github.com/browser-use/browser-harness")
wait_for_load()
print(page_info())
'@ | & (Get-Command browser-harness).Source
```

## Never

- Do not store secrets, cookies, tokens, private account screenshots, or raw coordinates.
- Do not bypass `scripts/integrations/send_gateway.py` for outbound communication.
- Do not click irreversible UI actions without explicit CC approval.

## Related

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
- [[.agents/workflows/client-health-report]]
