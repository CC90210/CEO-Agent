# Playwright CLI Skill — Headless Browser Automation (JSON-First)

## When to Use

Use this skill **instead of MCP screenshot tools** for:
- Scraping page content (text, links, tables)
- Extracting structured data from websites
- Filling forms and capturing results
- Batch scraping multiple pages
- Any task where you need DATA, not a picture

**Still use Playwright MCP** (`browser_navigate`, `browser_snapshot`, etc.) for:
- Interactive multi-step browser sessions (login flows, Skool editing, multi-page wizards)
- Visual verification that requires seeing the page layout
- Tasks requiring persistent browser state across many actions

## Why This Exists

| Approach | 10 pages scraped | Data format | Context cost |
|----------|-----------------|-------------|-------------|
| MCP screenshots | 20,000-30,000 tokens | Claude interprets image | Massive |
| **CLI script (this)** | **200-500 tokens** | **Clean JSON** | **Minimal** |

Screenshots burn context. JSON is surgical.

## Usage

All commands return JSON to stdout. Run from project root.

### Scrape page content
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com"
```
Returns: `{ url, title, text, charCount }`

### Include all links
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --links
```
Returns: `{ url, title, text, links: [{ text, href }], linkCount }`

### Extract specific elements
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --selector ".product-card"
```
Returns: `{ url, selector, count, elements: [{ tag, text, href, src }] }`

### Extract a table
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com/pricing" --table "table.pricing"
```
Returns: `{ url, table: { headers, rows, rowCount } }`

### Run arbitrary JavaScript
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --js "document.querySelectorAll('.item').length"
```
Returns: `{ url, jsResult: <value> }`

### Full page text (skip noise stripping)
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --full
```

### SPA delay (React/Next.js sites like Skool)
```bash
node .claude/skills/playwright/scripts/run.js "https://www.skool.com" --delay 3000
```
Waits extra ms after page load for client-side rendering. Essential for SPAs.

### Custom wait strategy
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --wait networkidle
```
Options: `domcontentloaded` (default, fast), `networkidle` (slow pages), `load`

### Custom timeout
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --timeout 15000
```

### Screenshot fallback (rare)
```bash
node .claude/skills/playwright/scripts/run.js "https://example.com" --screenshot tmp/page.png
```

## Decision Matrix: CLI vs MCP

| Task | Use CLI | Use MCP |
|------|---------|---------|
| Scrape text/data from a URL | YES | NO |
| Extract table/list from page | YES | NO |
| Fill a form, get result | YES (with --js) | YES (if multi-step) |
| Login flow with cookies | NO | YES |
| Skool lesson editing | NO | YES |
| Visual layout verification | NO | YES |
| Batch scrape 10+ pages | YES | NO |
| Interactive multi-step wizard | NO | YES |

**Rule of thumb:** If you need DATA, use CLI. If you need to INTERACT with a stateful session, use MCP.

## Noise Stripping

By default, the script removes:
- `<nav>`, `<header>`, `<footer>`
- Cookie banners, GDPR popups, newsletter modals
- Any element with role="banner", role="navigation", role="contentinfo"

Use `--full` to disable stripping.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Empty text returned | Add `--wait networkidle` (page needs JS to render) |
| Browser binary not found | Run `npx playwright install chromium` |
| Site blocks script (Cloudflare) | Use MCP for that site (stealth not built-in) |
| Script times out | Increase with `--timeout 15000` |
| Need to scrape behind login | Use MCP for auth, then CLI for data extraction |

## Integration with Existing Skills

- **`skills/browser-automation/SKILL.md`** — MCP reference (interactive sessions)
- **`skills/e2e-testing/SKILL.md`** — E2E testing (uses MCP for interactions)
- **`skills/skool-automation/SKILL.md`** — Skool editing (uses MCP for stateful editing)
- **This skill** — Data extraction (JSON-first, minimal tokens)
