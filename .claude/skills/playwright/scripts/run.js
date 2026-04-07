#!/usr/bin/env node
/**
 * Playwright CLI Runner — headless browser automation that returns clean JSON.
 *
 * Usage:
 *   node .claude/skills/playwright/scripts/run.js <url>                    # Scrape page content
 *   node .claude/skills/playwright/scripts/run.js <url> --links            # Include all links
 *   node .claude/skills/playwright/scripts/run.js <url> --selector ".product-card"  # Extract specific elements
 *   node .claude/skills/playwright/scripts/run.js <url> --table "table.pricing"     # Extract table as JSON
 *   node .claude/skills/playwright/scripts/run.js <url> --wait networkidle          # Wait strategy
 *   node .claude/skills/playwright/scripts/run.js <url> --timeout 15000             # Custom timeout (ms)
 *   node .claude/skills/playwright/scripts/run.js <url> --delay 3000                 # Wait for SPA rendering (ms)
 *   node .claude/skills/playwright/scripts/run.js <url> --full                      # Full page text (no stripping)
 *   node .claude/skills/playwright/scripts/run.js <url> --js "document.title"       # Run arbitrary JS, return result
 *   node .claude/skills/playwright/scripts/run.js <url> --screenshot out.png        # Save screenshot (rare fallback)
 *
 * Returns JSON to stdout. Errors go to stderr.
 */

const { chromium } = require("playwright");

const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36";

function parseArgs(argv) {
  const args = {
    url: null,
    links: false,
    selector: null,
    table: null,
    wait: "domcontentloaded",
    timeout: 10000,
    delay: 0,
    full: false,
    js: null,
    screenshot: null,
  };

  let i = 2; // skip node + script path
  while (i < argv.length) {
    const arg = argv[i];
    if (arg === "--links") {
      args.links = true;
    } else if (arg === "--full") {
      args.full = true;
    } else if (arg === "--selector" && argv[i + 1]) {
      args.selector = argv[++i];
    } else if (arg === "--table" && argv[i + 1]) {
      args.table = argv[++i];
    } else if (arg === "--wait" && argv[i + 1]) {
      args.wait = argv[++i];
    } else if (arg === "--timeout" && argv[i + 1]) {
      args.timeout = parseInt(argv[++i], 10);
    } else if (arg === "--delay" && argv[i + 1]) {
      args.delay = parseInt(argv[++i], 10);
    } else if (arg === "--js" && argv[i + 1]) {
      args.js = argv[++i];
    } else if (arg === "--screenshot" && argv[i + 1]) {
      args.screenshot = argv[++i];
    } else if (!arg.startsWith("--") && !args.url) {
      args.url = arg;
    }
    i++;
  }
  return args;
}

async function stripNoise(page) {
  await page.evaluate(() => {
    const selectors = [
      "nav",
      "header",
      "footer",
      "[role='banner']",
      "[role='navigation']",
      "[role='contentinfo']",
      ".cookie-banner",
      ".cookie-consent",
      "#cookie-notice",
      "[class*='cookie']",
      "[id*='cookie']",
      "[class*='gdpr']",
      "[class*='consent']",
      ".popup",
      ".modal-overlay",
      "[class*='newsletter']",
      "[class*='subscribe-popup']",
    ];
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => el.remove());
    }
  });
}

async function extractContent(page, args) {
  if (!args.full) {
    await stripNoise(page);
  }

  // Custom JS execution
  if (args.js) {
    const result = await page.evaluate(args.js);
    return { url: args.url, jsResult: result };
  }

  // Table extraction
  if (args.table) {
    const tableData = await page.evaluate((sel) => {
      const table = document.querySelector(sel);
      if (!table) return null;
      const rows = [];
      const headers = [];
      table.querySelectorAll("thead th, thead td").forEach((th) => {
        headers.push(th.textContent.trim());
      });
      table.querySelectorAll("tbody tr").forEach((tr) => {
        const row = {};
        tr.querySelectorAll("td").forEach((td, j) => {
          const key = headers[j] || `col_${j}`;
          row[key] = td.textContent.trim();
        });
        rows.push(row);
      });
      return { headers, rows, rowCount: rows.length };
    }, args.table);
    return { url: args.url, table: tableData };
  }

  // Selector extraction
  if (args.selector) {
    const elements = await page.evaluate((sel) => {
      return Array.from(document.querySelectorAll(sel)).map((el) => ({
        tag: el.tagName.toLowerCase(),
        text: el.textContent.trim().slice(0, 500),
        href: el.href || null,
        src: el.src || null,
      }));
    }, args.selector);
    return { url: args.url, selector: args.selector, count: elements.length, elements };
  }

  // Default: page content
  const title = await page.title();
  const text = await page.evaluate(() => {
    const main =
      document.querySelector("main") ||
      document.querySelector("[role='main']") ||
      document.querySelector("article") ||
      document.body;
    return main.innerText.trim().slice(0, 8000);
  });

  const result = { url: args.url, title, text, charCount: text.length };

  if (args.links) {
    result.links = await page.evaluate(() => {
      return Array.from(document.querySelectorAll("a[href]"))
        .map((a) => ({ text: a.textContent.trim().slice(0, 100), href: a.href }))
        .filter((l) => l.href.startsWith("http"));
    });
    result.linkCount = result.links.length;
  }

  return result;
}

async function main() {
  const args = parseArgs(process.argv);

  if (!args.url) {
    console.error("Usage: node run.js <url> [--links] [--selector css] [--table css] [--js expr] [--wait strategy] [--timeout ms] [--full] [--screenshot path]");
    process.exit(1);
  }

  let browser = null;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      userAgent: USER_AGENT,
      viewport: { width: 1280, height: 900 },
      locale: "en-US",
    });
    const page = await context.newPage();

    await page.goto(args.url, {
      waitUntil: args.wait,
      timeout: args.timeout,
    });

    // Extra delay for SPAs that render client-side after load
    if (args.delay > 0) {
      await page.waitForTimeout(args.delay);
    }

    // Optional screenshot (fallback for visual-only pages)
    if (args.screenshot) {
      await page.screenshot({ path: args.screenshot, fullPage: true });
    }

    const result = await extractContent(page, args);
    console.log(JSON.stringify(result, null, 2));
  } catch (err) {
    console.error(`Error: ${err.message}`);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
}

main();
