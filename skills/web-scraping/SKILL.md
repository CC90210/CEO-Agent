---
name: web-scraping
description: Web scraping and structured data extraction. Activate when CC needs to pull content from competitor sites, extract pricing/contacts/listings, harvest data for research, scrape pages that don't have an API, or operate a site under CC's logged-in account.
tags: [skill, scraping, data-extraction, research, browser-harness, cloak-browser]
triggers: ["web scraping", "use web scraping", "run web scraping", "web scraping and structured data extraction"]
last_updated: 2026-05-15
---

# Web Scraping — Firecrawl, CloakBrowser, Playwright, and Browser Harness

> Four tools, four jobs. **Firecrawl** extracts public data fast and cheap.
> **CloakBrowser** is the mandatory stealth tier when fresh-session targets
> are bot-protected (Cloudflare, DataDome, etc.). **Playwright** automates
> throwaway-browser interactions on unprotected sites. **Browser Harness**
> drives CC's real, logged-in Chrome for actions that require authenticated
> sessions.

## 🟢 PREFERRED ENTRY POINT (V6.7+, 2026-05-16): `research_fetch`

**For any "give me the content at URL X" task, default to:**

```bash
python scripts/research_fetch.py <url> --json
```

It auto-escalates Firecrawl → CloakBrowser based on actual response and remembers which tier worked per domain (SQLite at `state/site_reputation.db`). The four-tool matrix below is still the authoritative mental model — but `research_fetch` lets agents stop choosing tiers manually for the Firecrawl/CloakBrowser hand-off. Full skill: [[skills/research-fetch/SKILL]]. Drop down to a specific tool only when you need:

- structured extraction with a schema → `firecrawl_tool.py extract`
- batch site crawling → `firecrawl_tool.py crawl`
- site mapping → `firecrawl_tool.py map`
- search-and-scrape in one call → `firecrawl_tool.py search`
- interactive flow / form submission on a protected site → `cloak_browser_tool.py goto`
- screenshot evidence → `cloak_browser_tool.py scrape --screenshot`
- act AS CC in CC's logged-in account → Browser Harness

## Tool Decision Matrix

| Scenario | Tool | Why |
|----------|------|-----|
| Extract text/pricing/contacts from a **public, unprotected** page | **Firecrawl** | Returns clean markdown, handles JS-rendered pages, no browser overhead |
| Crawl an entire site for content harvesting | **Firecrawl `crawl`** | Follows links automatically up to the limit |
| Extract structured data (pricing tables, job listings, profiles) | **Firecrawl `extract`** | LLM-powered schema extraction — gets exactly the fields you specify |
| Get all URLs on a domain for analysis | **Firecrawl `map`** | Purpose-built for site mapping |
| Search for pages and extract their content in one step | **Firecrawl `search`** | Search + scrape in a single call |
| **Firecrawl returned 403/429/empty content, OR target is documented as bot-protected (Cloudflare Turnstile, reCAPTCHA v3, DataDome, ShieldSquare, FingerprintJS, Akamai, Kasada, PerimeterX)** | **CloakBrowser** | Stealth Chromium with C++ source-level fingerprint patches. reCAPTCHA v3 ~0.9 score. Drop-in Playwright API. Use a residential proxy via `CLOAK_PROXY_URL` for the hardest tier. |
| Automate a generic web workflow on an unprotected site you don't need to be logged into | **Playwright MCP** | Throwaway browser, deterministic. Cheap visual snapshots/screenshots. |
| Take screenshots for visual reference / E2E test | **Playwright MCP** | Firecrawl doesn't capture visuals; Playwright is purpose-built for it. (For protected sites, CloakBrowser also screenshots via `--screenshot`.) |
| **Act inside CC's logged-in account** — Skool community, Stripe dashboard, Supabase, Vercel, LinkedIn profile views, anywhere "log in fresh" isn't an option | **Browser Harness** | Attaches to CC's already-running Chrome at port 9222. The session, cookies, MFA, and reputation are all already there. |
| Read a protected page AS CC (when CC already has the session) | **Browser Harness** | A real human's browser is the gold standard — even better than CloakBrowser. Use Cloak only when CC has no session on the target. |
| Read pages that ONLY render under a specific extension/persona Chrome has installed | **Browser Harness** | Inherits whatever extensions and prefs CC's Chrome has |

**Rule of thumb (in priority order):**

1. Need the content from a public unprotected page? → **Firecrawl** (cheapest, fastest).
2. Firecrawl blocked or page sits behind bot defense? → **CloakBrowser** (mandatory stealth tier for fresh-session protected scraping).
3. Need to DO something on a public unprotected page? → **Playwright** (deterministic).
4. Need to do it AS CC under CC's login? → **Browser Harness** (real human's Chrome).

Never use Browser Harness for what Firecrawl can do — it's heavier and depends
on Chrome being open. Never use Playwright for what CloakBrowser can do —
raw Playwright fingerprints are obvious and Cloudflare/DataDome will block
within a few requests. Never use CloakBrowser for what Browser Harness can do
on a CC-authenticated target — a real human's browser beats any stealth fork.

## Command Reference

### CloakBrowser (stealth tier)

```bash
# Scrape a Cloudflare/DataDome-protected page → text + metadata
python scripts/cloak_browser_tool.py scrape https://protected-target.com --json

# With screenshot evidence
python scripts/cloak_browser_tool.py scrape https://target.com --screenshot evidence/target.png

# One-shot navigate + JS eval
python scripts/cloak_browser_tool.py goto https://target.com --eval "() => document.title"

# Self-test stealth signals (run after install + when blocking starts unexpectedly)
python scripts/cloak_browser_tool.py check-stealth --json

# Pre-fetch the ~200MB binary (run once per machine)
python scripts/cloak_browser_tool.py download
```

Full reference: [[skills/cloak-browser/SKILL]].

#### Known bot-protected targets — ALWAYS cloak, never raw

- **True People Search (truepeoplesearch.com)** — Cloudflare + DataDome layered. Raw Playwright is blocked within a few requests; Firecrawl returns empty. Must route through `cloak_browser_tool.py scrape <url>`. If even Cloak gets a hard block (rare), set `CLOAK_PROXY_URL` in `.env.agents` to a residential proxy (Bright Data, Smartproxy, etc.) and retry. The 2026-05-15 SunBiz meeting flagged a prior TPS attempt that failed without cloak — that's the failure mode this entry exists to prevent.
- **LinkedIn (any logged-out page)** — use Browser Harness (CC's authenticated session) instead. Cloak gets you past the bot wall but you'll hit the un-authed paywall on most profile pages.
- **State business registries** (FL SunBiz, NY Dept State, etc.) — usually Firecrawl-friendly; only fall through to Cloak on 403 / 429.

### Firecrawl (default tier — cheapest, fastest)

```bash
# Scrape a single page → clean markdown
python scripts/firecrawl_tool.py scrape https://example.com

# Crawl a site (follows links, max 10 pages)
python scripts/firecrawl_tool.py crawl https://example.com --limit 10

# Search query → scrape top results
python scripts/firecrawl_tool.py search "AI automation agencies Ontario"

# Extract structured data with a schema
python scripts/firecrawl_tool.py extract https://example.com/pricing \
  --schema '{"type":"object","properties":{"plans":{"type":"array"}}}'

# Get all URLs on a domain
python scripts/firecrawl_tool.py map https://example.com

# Machine-readable JSON (for agent pipelines)
python scripts/firecrawl_tool.py scrape https://example.com --json
```

## Common Use Cases

### Competitor Research
```bash
# Get their full pricing page
python scripts/firecrawl_tool.py scrape https://competitor.com/pricing

# Map what pages exist on their site
python scripts/firecrawl_tool.py map https://competitor.com

# Extract pricing structured data
python scripts/firecrawl_tool.py extract https://competitor.com/pricing \
  --schema '{"type":"object","properties":{"plans":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"price":{"type":"string"},"features":{"type":"array","items":{"type":"string"}}}}}}}'
```

### Lead Website Analysis (OASIS client research)
```bash
# Understand what a prospect's business does before the call
python scripts/firecrawl_tool.py scrape https://prospect.com

# Crawl their full site for comprehensive understanding
python scripts/firecrawl_tool.py crawl https://prospect.com --limit 15
```

### Content Harvesting
```bash
# Search for industry articles to inform content strategy
python scripts/firecrawl_tool.py search "AI automation for HVAC businesses 2025"

# Crawl a resource site for research
python scripts/firecrawl_tool.py crawl https://industry-blog.com --limit 25
```

### Market Research
```bash
# Extract job listing data for hiring research
python scripts/firecrawl_tool.py extract https://jobs.example.com \
  --schema '{"type":"object","properties":{"jobs":{"type":"array","items":{"type":"object","properties":{"title":{"type":"string"},"salary":{"type":"string"},"location":{"type":"string"}}}}}}'

# Search for competitor pricing intelligence
python scripts/firecrawl_tool.py search "HVAC AI software pricing 2025" --json
```

## Credentials

Set in `.env.agents`:
```
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxx
```

Get your key at [firecrawl.dev](https://firecrawl.dev). The free tier covers most agent research tasks.

## Four-way Comparison

| Feature | Firecrawl | CloakBrowser | Playwright MCP | Browser Harness |
|---------|-----------|--------------|----------------|-----------------|
| JS-rendered pages | Yes (cloud browser) | Yes (stealth Chromium 146) | Yes (local browser) | Yes (CC's real Chrome) |
| Clean markdown output | Yes (built-in) | Text only (HTML→text) | No (raw HTML/snapshot) | No (raw page state) |
| Login/auth sessions | No | Persistent context optional | Throwaway only | **Yes — CC's real Chrome session** |
| Form submission | No | Yes (Playwright API) | Yes | Yes |
| Anti-bot detection risk | Cloud-side (handled) | **Very low** — C++ fingerprint patches, reCAPTCHA v3 ~0.9 | High on protected sites | **Lowest — it IS a real browser** |
| Structured extraction | Yes (LLM schema) | No (manual parsing) | No (manual parsing) | No (manual parsing) |
| Batch crawling | Yes (`crawl`) | Manual loop (write your own) | No (manual loop) | No (manual loop) |
| Site mapping | Yes (`map`) | No | No | No |
| Screenshots | No | Yes (`--screenshot`) | Yes | Yes |
| Works without API key | No (FIRECRAWL_API_KEY) | Yes | Yes | Yes (but needs Chrome already running) |
| Setup overhead per session | None | One-time ~200MB binary download per machine | None | One-time `bravo browser setup` per machine |
| Recurring cost | Per-scrape (Firecrawl) | Free (proxy optional, ~$50-200/mo if used) | Free | Free |

## When to use Browser Harness specifically

Browser Harness shines when the URL you need fails on the other two:

- **Skool community** — replies, post views, mod actions all require an
  authenticated coach session.
- **Stripe dashboard** — pulling MRR breakdowns, dispute details, and
  customer history that the Stripe API doesn't expose.
- **Supabase / Vercel / Cloudflare web UIs** — viewing logs, RLS
  policies, deployment pages.
- **LinkedIn profile reads** (research, NOT outreach — there is no
  LinkedIn outreach automation in this system by design).
- **Internal SaaS tools** that have no API and require SSO.

Run `bravo browser doctor` to confirm the daemon is attached to Chrome
before you start. If it isn't, run `bravo browser setup` once.

## Integration with Other Tools

- **Competitive Intel:** Feed `scrape` output into `scripts/competitive_intel.py add`
- **Lead Research:** Feed `crawl` output into `scripts/lead_engine.py add`
- **Content Pipeline:** Feed `search` results into content ideation
- **Knowledge Wiki:** `/ingest` scraped content into `knowledge/raw/`

## Obsidian Links
- [[skills/browser-automation/SKILL]] | [[skills/browser-harness/SKILL]] | [[brain/CAPABILITIES]]
- `scripts/firecrawl_tool.py` | `scripts/browser_harness_doctor.py` | [[browser/README]] | [[browser/SAFETY]]
- [[memory/ACTIVE_TASKS]]
