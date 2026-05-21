---
name: cloak-browser
description: Use CloakBrowser as the mandatory stealth tier for fresh-session browser work against bot-protected sites (Cloudflare Turnstile, reCAPTCHA v3, DataDome, ShieldSquare, FingerprintJS, BrowserScan). Drop-in Playwright replacement with C++ source-level fingerprint patches. Wraps cloakbrowser pip/npm package via scripts/browser/cloak_browser_tool.py.
tier: tool
owner: bravo
risk: low
triggers: ["cloak browser", "cloakbrowser", "stealth chromium", "bypass cloudflare", "bypass bot detection", "scrape protected site", "scrape blocked site", "site is blocking us", "403 forbidden", "1020 cloudflare", "datadome blocked", "recaptcha blocking", "fingerprintjs", "shieldsquare", "browserscan"]
tags: [tool, browser, scraping, stealth, anti-bot, cloudflare]
status: '[NEW]'
created_at: 2026-05-15
last_updated: 2026-05-15
---

# CloakBrowser — Stealth Chromium for Bot-Protected Sites

> **Mandatory tier-1** for any fresh-session browser automation that hits a site with bot defense (Cloudflare Turnstile, reCAPTCHA v3, DataDome, ShieldSquare, FingerprintJS, Akamai, Kasada, PerimeterX). Drop-in Playwright replacement — C++ source-level fingerprint patches in a compiled Chromium 146 binary, not runtime JS injection.
>
> **Does NOT replace** Browser Harness (which attaches to CC's REAL logged-in Chrome — already maximally stealthy because it IS a real human's browser). Does NOT replace Firecrawl for simple public scrapes (Firecrawl is cheaper, faster, structured-extraction-ready).

## ⚡ Preferred entry — `research_fetch` (V6.7+, 2026-05-16)

For any "give me the content at URL X" task, default to `python scripts/research_fetch.py <url>` instead of calling this skill directly. It auto-escalates Firecrawl → CloakBrowser based on actual response and remembers which tier worked per domain (so the next call skips the Firecrawl roundtrip). Skill: [[skills/research-fetch/SKILL.md]].

**Drop down to this CloakBrowser skill directly only when you need its unique features:**
- Interactive flow on a protected site (`goto <url> --eval "..."`)
- Screenshot evidence (`scrape <url> --screenshot path.png`)
- Self-test stealth signals (`check-stealth`)
- Force the stealth tier for a domain where you don't want reputation memory to apply

Source: https://github.com/CloakHQ/CloakBrowser · PyPI `cloakbrowser` 0.3.28 · npm `cloakbrowser` (MIT wrapper, separate "free to use, no redistribution" binary license).

## Decision: when does CloakBrowser fire?

```
Need a public page's text/markdown, no auth, no detection issues
  → Firecrawl (scripts/integrations/firecrawl_tool.py)

Need a public page but Firecrawl returns 403 / empty / wrong content,
or the site is documented as bot-protected (Cloudflare/Datadome/etc.)
  → CloakBrowser (scripts/browser/cloak_browser_tool.py)

Need to act AS CC inside CC's logged-in account
  → Browser Harness (CC's real Chrome on port 9222)

Need fresh-session interactive flow on an unprotected site (testing, etc.)
  → Playwright MCP (throwaway browser)
```

The "mandatory" framing: any time an agent reaches for fresh-session Playwright against a third-party site that might have bot defense, the right call is CloakBrowser instead. Playwright MCP stays for unprotected internal testing and visual verification.

## Quick reference

```bash
# Scrape a Cloudflare-protected page → text + metadata
python scripts/browser/cloak_browser_tool.py scrape https://target.com --json

# Scrape with screenshot evidence
python scripts/browser/cloak_browser_tool.py scrape https://target.com --screenshot evidence/target.png

# One-shot navigate + JS eval
python scripts/browser/cloak_browser_tool.py goto https://target.com --eval "() => document.title"

# Self-test stealth signals (run once after install, then before suspect runs)
python scripts/browser/cloak_browser_tool.py check-stealth

# Pre-fetch the ~200MB binary (run once per machine)
python scripts/browser/cloak_browser_tool.py download

# Show installed binary info
python scripts/browser/cloak_browser_tool.py binary-info
```

Common flags: `--headed` (debug, shows window), `--timeout N` (default 30s), `--proxy URL` (override), `--user-agent S`, `--json`.

## When to use

- **Fresh competitor scrape that returned 403/429 from Firecrawl** — escalate to CloakBrowser before giving up.
- **Lead enrichment** against directories that block raw Playwright (LinkedIn search, Apollo-protected pages, ZoomInfo previews).
- **Pricing / SKU monitoring** on Cloudflare-shielded SaaS marketing sites.
- **Compliance/regulator pages** that gate access behind Turnstile (CRA, Florida SunBiz when reading non-public sections).
- **Whenever the V6 lineage skill is "give me HTML/text from URL X" and we don't already have CC's session.**

Do NOT use CloakBrowser when:
- Firecrawl works for the page (waste of 200MB binary + slower).
- The task is "do something as CC inside a logged-in app" — that's Browser Harness.
- Posting/sending/clicking irreversible buttons — even on protected sites, CASL + send_gateway rules in `browser/SAFETY.md` still apply.

## Stealth quality

Documented passes (per CloakHQ):
- reCAPTCHA v3 → 0.9 score (human-level)
- Cloudflare Turnstile (non-interactive + managed)
- ShieldSquare, FingerprintJS, BrowserScan, 30+ detection sites

Built-in C++ patches (not runtime JS shims): `navigator.webdriver`, Chrome runtime/plugins, WebGL vendor strings, Canvas/Audio fingerprints, font enumeration, timezone/locale GeoIP. Survives Chromium rebases (CloakHQ actively rebases the patched fork).

**Without a residential proxy**, stealth is degraded against the hardest tier (Akamai, Kasada). Datacenter IPs get flagged on reputation alone regardless of fingerprint quality. Configure a proxy when needed:

```bash
# In .env.agents
CLOAK_PROXY_URL=http://user:pass@gw.brightdata.com:22225
# Or split:
CLOAK_PROXY_URL=http://gw.brightdata.com:22225
CLOAK_PROXY_USERNAME=username
CLOAK_PROXY_PASSWORD=password
# Optional GeoIP overrides (else CloakBrowser GeoIPs automatically):
CLOAK_TIMEZONE_ID=America/Toronto
CLOAK_LOCALE=en-US
```

Recommended residential proxy providers when a use case demands it: Bright Data, Oxylabs, IPRoyal, Smartproxy. Rough budget: $50-200/mo for ~1-5GB of residential traffic. Don't sign up until a real use case justifies it — most of CC's lead/competitor work is fine with the bare CloakBrowser binary.

## Self-test: `check-stealth`

Run after install and any time a target site starts blocking unexpectedly:

```bash
python scripts/browser/cloak_browser_tool.py check-stealth --json
```

Verifies five core fingerprint signals: `navigator.webdriver` hidden, `chrome.runtime` present, plugins populated, languages populated, WebGL vendor not SwiftShader. Exit 0 = all green; exit 1 = a stealth signal regressed and we should investigate before relying on the tool.

## Tools used

- `scripts/browser/cloak_browser_tool.py` — canonical CLI wrapper (subcommands: `scrape`, `goto`, `check-stealth`, `binary-info`, `download`, `clear-cache`)
- `scripts/lib/secret_loader.py` — env loading (CLOAK_PROXY_URL etc., audit-logged to `state/secret_access.log`)
- `cloakbrowser` Python package (Playwright drop-in) — installed in `.venv`
- `cloakbrowser` npm package (Playwright/Puppeteer drop-in for Node-based agents)

## Constraints

- **License caveat:** wrapper is MIT, but the compiled Chromium binary has a "free to use, no redistribution" clause. Safe for agent consumption (we use, we don't redistribute), but **do not bundle the binary into client agent forks** packaged via `skills/agent-forge` / `skills/agent-runtime-packaging`. Forked client agents must `pip install cloakbrowser` themselves on first run.
- **Cold-start cost:** ~200MB binary download on first launch. Pre-fetch with `download` subcommand during machine bootstrap; the V6 setup wizard should call this in `step_environment` for any client tier that includes web research.
- **Linux fonts:** for the hardest tier (Kasada, Akamai), Linux hosts need `fonts-noto-color-emoji`, `fonts-liberation`, `fonts-dejavu`. Windows/Mac are fine out-of-box.
- **macOS Gatekeeper:** first run on macOS triggers quarantine; one-time `xattr -cr ~/.cache/cloakbrowser` workaround.

## Related skills

- [[skills/web-scraping/SKILL.md]] — full 4-tool decision matrix (Firecrawl / CloakBrowser / Playwright / Browser Harness)
- [[skills/browser-automation/SKILL.md]] — Playwright MCP reference (used for non-protected sites)
- [[skills/browser-harness/SKILL.md]] — CC's real-Chrome layer for authenticated work
- [[browser/SAFETY]] — applies regardless of which browser layer; sends/posts/money still need CC approval
