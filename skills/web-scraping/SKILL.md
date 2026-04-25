---
name: web-scraping
description: Web scraping and structured data extraction. Activate when CC needs to pull content from competitor sites, extract pricing/contacts/listings, harvest data for research, scrape pages that don't have an API, or operate a site under CC's logged-in account.
tags: [skill, scraping, data-extraction, research, browser-harness]
---

# Web Scraping — Firecrawl, Playwright, and Browser Harness

> Three tools, three jobs. **Firecrawl** extracts public data. **Playwright**
> automates throwaway-browser interactions. **Browser Harness** drives CC's
> real, logged-in Chrome for actions that require authenticated sessions.

## Tool Decision Matrix

| Scenario | Tool | Why |
|----------|------|-----|
| Extract text/pricing/contacts from a **public** page | **Firecrawl** | Returns clean markdown, handles JS-rendered pages, no browser overhead |
| Crawl an entire site for content harvesting | **Firecrawl `crawl`** | Follows links automatically up to the limit |
| Extract structured data (pricing tables, job listings, profiles) | **Firecrawl `extract`** | LLM-powered schema extraction — gets exactly the fields you specify |
| Get all URLs on a domain for analysis | **Firecrawl `map`** | Purpose-built for site mapping |
| Search for pages and extract their content in one step | **Firecrawl `search`** | Search + scrape in a single call |
| Automate a generic web workflow on a site you don't need to be logged into | **Playwright MCP** | Throwaway browser, deterministic, doesn't require user sessions |
| Take screenshots for visual reference / E2E test | **Playwright MCP** | Firecrawl doesn't capture visuals; Playwright is purpose-built for it |
| **Act inside CC's logged-in account** — Skool community, Stripe dashboard, Supabase, Vercel, LinkedIn profile views, anywhere "log in fresh" isn't an option | **Browser Harness** | Attaches to CC's already-running Chrome at port 9222. The session, cookies, MFA, and reputation are all already there. |
| Scrape a site that aggressively blocks bot browsers (Cloudflare, PerimeterX, Datadome) when you must read it as CC | **Browser Harness** | Anti-bot systems can't easily distinguish it from a real human's browser — because it IS one |
| Read pages that ONLY render under a specific extension/persona Chrome has installed | **Browser Harness** | Inherits whatever extensions and prefs CC's Chrome has |

**Rule of thumb (in priority order):**

1. Need the content from a public page? → **Firecrawl** (cheapest, fastest).
2. Need to DO something on a public page? → **Playwright** (deterministic).
3. Need to do it AS CC under CC's login? → **Browser Harness**.

Never use Browser Harness for what Firecrawl can do — it's heavier and depends
on Chrome being open. Never use Playwright for what Browser Harness can do —
fresh-session bot detection will block you on protected sites.

## Command Reference

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

## Three-way Comparison

| Feature | Firecrawl | Playwright MCP | Browser Harness |
|---------|-----------|----------------|-----------------|
| JS-rendered pages | Yes (cloud browser) | Yes (local browser) | Yes (CC's real Chrome) |
| Clean markdown output | Yes (built-in) | No (raw HTML/snapshot) | No (raw page state) |
| Login/auth sessions | No | Throwaway only — fresh login each run | **Yes — CC's real Chrome session** |
| Form submission | No | Yes | Yes |
| Anti-bot detection risk | Cloud-side (handled) | High on protected sites (Cloudflare etc.) | **Lowest — it IS a real browser** |
| Structured extraction | Yes (LLM schema) | No (manual parsing) | No (manual parsing) |
| Batch crawling | Yes (`crawl`) | No (manual loop) | No (manual loop) |
| Site mapping | Yes (`map`) | No | No |
| Screenshots | No | Yes | Yes |
| Works without API key | No | Yes | Yes (but needs Chrome already running) |
| Survives `bravo doctor`-quality automation | Yes — stateless | Yes — stateless | Requires the harness daemon up + Chrome attached |
| Setup overhead per session | None | None | One-time `bravo browser setup` per machine, then leave Chrome open |

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
