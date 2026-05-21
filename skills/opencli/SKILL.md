---
name: opencli
description: Turn any website into a CLI command via browser automation. Use for web scraping, social media automation, API discovery, and platform integration without building custom scrapers.
triggers: [opencli, website CLI, web automation, API discovery, browser CLI, explore website, synthesize adapter]
tier: specialized
dependencies: [browser-automation, cli-anything]
---

# OpenCLI — Website-to-CLI Automation

## Overview

OpenCLI transforms websites into structured CLI commands via browser automation. While `cli-anything` wraps **local software and APIs** into CLIs, OpenCLI wraps **websites** — reusing browser sessions (cookies, auth) to interact with platforms like Twitter, YouTube, Discord, and any other website through the terminal.

**Core Principle:** Any website with a browser interface can become a CLI command. Browser sessions handle auth, JavaScript rendering, and dynamic content automatically.

**Installed:** `npm install -g @jackwener/opencli` (v1.1.1)

## When to Use

- Need to interact with a website that has no API or broken API
- Want to automate social media actions beyond what Zernio (formerly Late) MCP supports
- Need to discover a website's hidden API endpoints
- Want to scrape structured data from JavaScript-heavy websites
- Building a new platform integration and need to reverse-engineer the API first
- Need to interact with a platform using existing browser login (cookie-based auth)

## When NOT to Use

- Platform has a working MCP server (use MCP first)
- Platform has a well-documented REST API (use `cli-anything` to wrap it)
- Simple static page scraping (use Playwright MCP directly)
- One-off browser interactions (use Playwright MCP directly)

## Relationship to Other Tools

| Tool | Wraps | Best For |
|------|-------|----------|
| **OpenCLI** | Websites (via browser) | Repeatable web interactions, API discovery, multi-platform commands |
| **cli-anything** | Local software/APIs (via subprocess) | SDK wrappers, GUI apps, local tools |
| **Playwright MCP** | Browser (direct control) | One-off browsing, testing, screenshots |
| **Zernio (fmr. Late) MCP** | Social media (via API) | Posting, scheduling (8 platforms) |

## Core Commands

### Discovery & Exploration

```bash
# List all available CLI commands (50+ prebuilt adapters)
opencli list

# Explore a website's API endpoints (AI-driven discovery)
opencli explore https://example.com

# Synthesize CLI adapters from exploration results
opencli synthesize

# System health check
opencli doctor

# Initial setup (browser bridge)
opencli setup
```

### Using Prebuilt Adapters

```bash
# Social Media
opencli twitter trending --limit 10
opencli twitter search --keyword "AI automation"
opencli discord channels --server "my-server"
opencli linkedin feed --limit 5

# Content Platforms
opencli youtube trending --limit 10
opencli youtube search --keyword "AI agents"
opencli medium trending --limit 5
opencli reddit hot --subreddit technology --limit 10
opencli hackernews top --limit 20

# Developer Tools
opencli github trending --language typescript
opencli chatgpt models

# Research
opencli arxiv search --keyword "large language models"
opencli wikipedia search --keyword "AI"

# All commands support --json for agent consumption
opencli twitter trending --limit 5 --json
```

### Plugin System

```bash
# Install community plugins from GitHub
opencli plugin install github:user/repo

# List installed plugins
opencli plugin list

# Remove a plugin
opencli plugin uninstall myplugin
```

### External CLI Passthrough

```bash
# OpenCLI can route to local CLIs too
opencli gh status          # → GitHub CLI
opencli docker ps          # → Docker CLI
```

## API Discovery Workflow (Agent-Driven)

This is the most powerful feature for Bravo. When CC needs to integrate a new platform:

### Step 1: Explore
```bash
opencli explore https://target-website.com
```
This launches a browser session that:
1. Navigates to the target website
2. Auto-scrolls and clicks to trigger lazy-loaded APIs
3. Captures all network requests and responses
4. Analyzes response structures and field types
5. Deduces API patterns from URLs
6. Infers capabilities based on URL semantics

**Output:** Exploration bundle with endpoint catalog, inferred capabilities, confidence scores, and auth strategy recommendations.

### Step 2: Synthesize
```bash
opencli synthesize
```
Takes the exploration bundle and:
1. Ranks discovered capabilities by confidence score
2. Generates YAML adapter templates
3. Produces candidate CLI commands ready for refinement

### Step 3: Refine
Review generated adapters, test them, and commit working ones.

## Adapter Format (YAML)

OpenCLI adapters are defined in YAML — simple, declarative, no code needed for basic cases:

```yaml
site: example.com
name: example
commands:
  trending:
    description: Get trending items
    args:
      - name: limit
        type: number
        default: 10
    pipeline:
      - navigate: https://example.com/trending
      - wait: ".trending-list"
      - evaluate: |
          () => {
            return [...document.querySelectorAll('.item')]
              .map(el => ({
                title: el.querySelector('.title')?.textContent,
                url: el.querySelector('a')?.href
              }));
          }
    columns: [title, url]
```

For complex cases, TypeScript modules provide full programmatic control.

## Authentication Strategies

OpenCLI supports three auth strategies per adapter:

| Strategy | How It Works | Best For |
|----------|-------------|----------|
| **Cookie-based** | Reuses browser login session | Social media, logged-in dashboards |
| **Header-based** | Bearer tokens, CSRF protection | APIs with token auth |
| **Public API** | Direct fetch, no auth | Public data endpoints |

**Cookie-based auth** is the killer feature — it means the agent can interact with any platform CC is logged into, without needing API keys or OAuth flows.

## Integration with Bravo's Ecosystem

### With Playwright MCP
OpenCLI uses Playwright under the hood. When `opencli explore` needs browser access, it leverages the same browser automation stack. For one-off tasks, use Playwright MCP directly. For repeatable tasks, create an OpenCLI adapter.

### With cli-anything
These are complementary:
- **cli-anything**: Wrap local software → Python CLI with Click + subprocess
- **OpenCLI**: Wrap websites → YAML/TS adapter with browser automation

When a website also has a local SDK, prefer cli-anything (more reliable, no browser needed).

### With Zernio (formerly Late) MCP
Zernio handles posting and scheduling to 8 platforms. OpenCLI can handle **reading** from those same platforms (trending content, analytics, DMs) — filling the gap that Zernio's API doesn't cover.

### With n8n
OpenCLI commands can be triggered from n8n workflows via Execute Command nodes, enabling automated web data collection pipelines.

## Prebuilt Adapters (50+)

| Category | Platforms |
|----------|-----------|
| **Social** | Twitter/X, Facebook, Instagram, LinkedIn, Discord, TikTok, Weibo, Xiaohongshu |
| **Content** | YouTube, Medium, Substack, Reddit, HackerNews, Arxiv, Wikipedia |
| **Developer** | ChatGPT, Cursor, Grok, GitHub Copilot, Hugging Face |
| **Finance** | Yahoo Finance, Coupang |
| **Regional** | Bilibili, Douban, Zhihu, Weread, V2ex, Codeforces |
| **Tools** | Notion, Steam, Discord (desktop app), Google |

## Creating Custom Adapters

When CC needs a platform not in the prebuilt list:

1. Run `opencli explore <url>` to discover APIs
2. Run `opencli synthesize` to generate adapter template
3. Refine the YAML adapter
4. Test with `opencli <adapter-name> <command>`
5. Optionally publish as a plugin: `opencli plugin install github:CC90210/<repo>`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Browser not connected" | Run `opencli setup` to configure browser bridge |
| "No cookies found" | Log into the target site in the browser first |
| Adapter returns empty data | Website may have changed — re-run `opencli explore` to update |
| Command not found | Run `opencli list` to see available commands |
| Plugin install fails | Check Node.js ≥ 20.0.0: `node --version` |

## Quick Reference

```bash
# Discovery
opencli list                              # All available commands
opencli explore <url>                     # Discover website APIs
opencli synthesize                        # Generate adapters from exploration
opencli doctor                            # Health check

# Usage (any adapter)
opencli <platform> <command> [--options]  # Run a command
opencli <platform> <command> --json       # Machine-readable output

# Plugins
opencli plugin install github:user/repo   # Install from GitHub
opencli plugin list                       # Show installed
opencli plugin uninstall <name>           # Remove

# System
opencli setup                             # Configure browser bridge
opencli --version                         # Show version
```

## Obsidian Links
- [[skills/cli-anything/SKILL.md]] | [[skills/browser-automation/SKILL.md]]
- [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[skills/mcp-operations/SKILL.md]]
