---
name: web-scraping
description: Web scraping and structured data extraction. Activate when CC needs to pull content from competitor sites, extract pricing/contacts/listings, harvest data for research, or scrape pages that don't have an API.
tags: [skill, scraping, data-extraction, research]
---

# Web Scraping — Firecrawl + Playwright Decision Guide

> Two tools, two jobs. Firecrawl extracts data. Playwright automates interactions.
> Pick the right one — never use both for the same task.

## Tool Decision: Firecrawl vs Playwright

| Scenario | Tool | Why |
|----------|------|-----|
| Extract text/pricing/contacts from a public page | **Firecrawl** | Returns clean markdown, handles JS-rendered pages, no browser overhead |
| Crawl an entire site for content harvesting | **Firecrawl `crawl`** | Follows links automatically up to the limit |
| Extract structured data (pricing tables, job listings, profiles) | **Firecrawl `extract`** | LLM-powered schema extraction — gets exactly the fields you specify |
| Get all URLs on a domain for analysis | **Firecrawl `map`** | Purpose-built for site mapping |
| Search for pages and extract their content in one step | **Firecrawl `search`** | Search + scrape in a single call |
| Log into a site, click buttons, fill forms | **Playwright MCP** | Requires session state and user interaction |
| Automate a multi-step web workflow (booking, posting) | **Playwright MCP** | Stateful browser session needed |
| Take screenshots for visual reference | **Playwright MCP** | Firecrawl doesn't capture visuals |
| Bypass heavy anti-bot protection on a site you must interact with | **Playwright MCP** | More human-like interaction pattern |

**Rule of thumb:** If you only need the content — use Firecrawl. If you need to DO something on the page — use Playwright.

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

## Firecrawl vs Playwright — Full Comparison

| Feature | Firecrawl | Playwright MCP |
|---------|-----------|----------------|
| JS-rendered pages | Yes (cloud browser) | Yes (local browser) |
| Clean markdown output | Yes (built-in) | No (raw HTML/snapshot) |
| Login/auth sessions | No | Yes |
| Form submission | No | Yes |
| Rate limiting / anti-bot | Cloud-side (handled) | Manual strategy needed |
| Structured extraction | Yes (LLM schema) | No (manual parsing) |
| Batch crawling | Yes (`crawl`) | No (manual loop) |
| Site mapping | Yes (`map`) | No |
| Screenshots | No | Yes |
| Works without API key | No | Yes |

## Integration with Other Tools

- **Competitive Intel:** Feed `scrape` output into `scripts/competitive_intel.py add`
- **Lead Research:** Feed `crawl` output into `scripts/lead_engine.py add`
- **Content Pipeline:** Feed `search` results into content ideation
- **Knowledge Wiki:** `/ingest` scraped content into `knowledge/raw/`

## Obsidian Links
- [[skills/browser-automation/SKILL]] | [[brain/CAPABILITIES]]
- `scripts/firecrawl_tool.py` | [[memory/ACTIVE_TASKS]]
