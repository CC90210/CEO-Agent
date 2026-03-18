# Day 3: MCPs & Integrations — Connecting AI to the World

> **Level:** Integrator (Level 2) -- LEVEL UP!
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 2 complete, comfortable with Claude Code
> **Goal:** Install and use MCPs to give your AI agent superpowers beyond text generation.

---

## Module 1: What Are MCPs? (20 min)

### The USB Analogy

Your computer alone can't print, scan, or connect to a monitor. But plug in a USB device and suddenly it can.

**MCPs work the same way for AI:**
- Claude Code alone → reads files, writes code, runs commands
- Claude Code + Playwright MCP → can browse the web, fill forms, take screenshots
- Claude Code + Supabase MCP → can query databases, create tables, manage data
- Claude Code + Memory MCP → can remember things across conversations

**MCP = Model Context Protocol** — a standard way for AI to connect to external tools.

### Why MCPs > Raw APIs

| Approach | How It Works | Effort |
|----------|-------------|--------|
| Raw API | You write Python/JS code to call each API manually | High |
| MCP | AI calls the tool automatically when relevant | Zero (after setup) |

With MCPs, you don't write integration code. You tell Claude Code "check my database" and it knows to use the Supabase MCP.

---

## Module 2: MCP Architecture (20 min)

### How an MCP Server Works

```
Claude Code sends request → MCP Server processes it → Returns result to Claude Code
```

Each MCP server exposes **tools** that Claude Code can call:

```
Playwright MCP:
├── browser_navigate    → Go to a URL
├── browser_snapshot    → Get page content
├── browser_click       → Click an element
├── browser_type        → Type text into a field
└── browser_screenshot  → Take a screenshot

Supabase MCP:
├── execute_sql         → Run SQL queries
├── list_tables         → See all tables
├── apply_migration     → Create/alter tables
└── get_project         → Project info
```

### Configuration File

MCPs are configured in `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--headless"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

Each server entry tells Claude Code:
- **command:** What program to run (usually `npx`)
- **args:** What package to install and any flags

---

## Module 3: Installing Your First MCPs (30 min)

### Step 1: Create the Config

In your project root:
```bash
mkdir -p .claude
```

Create `.claude/mcp.json`:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--headless"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    }
  }
}
```

### Step 2: Restart Claude Code

MCPs load when Claude Code starts. Exit and re-enter:
```bash
# Exit
Ctrl+D

# Re-enter
claude
```

### Step 3: Verify

Ask Claude Code:
```
What MCP servers are connected? List the tools available from each.
```

It should list Playwright, Memory, and Context7 with their tools.

---

## Module 4: Playwright MCP — Browser Automation (30 min)

### What It Does
Playwright MCP gives Claude Code a web browser. It can:
- Navigate to any URL
- Read page content
- Click buttons and links
- Fill out forms
- Take screenshots
- Run JavaScript on pages

### Core Workflow

```
1. Navigate to a page
2. Snapshot to see what's there (gets accessibility tree with element refs)
3. Interact with elements using refs
4. Re-snapshot after any change (refs become stale)
```

### Hands-On Exercise: Web Research

Start Claude Code and try:

```
Use Playwright to go to https://news.ycombinator.com and tell me the top 5 stories right now.
```

Claude Code will:
1. Navigate to the URL
2. Snapshot the page
3. Read the accessibility tree
4. Extract the titles
5. Return them to you

### Hands-On Exercise: Screenshot Evidence

```
Navigate to my GitHub profile at https://github.com/YOUR-USERNAME
Take a screenshot and save it as github-profile.png
```

### Important Rules

1. **Always re-snapshot after navigation** — element references change when the page changes
2. **Use snapshot for data, screenshot for visuals** — snapshots give you text, screenshots give you images
3. **Don't hardcode selectors** — always use refs from the snapshot

---

## Module 5: Memory MCP — Persistent Knowledge (20 min)

### What It Does
Memory MCP creates a knowledge graph that persists across conversations. Claude Code can:
- Create entities (people, projects, concepts)
- Add observations (facts about entities)
- Create relationships (link entities together)
- Search and recall information later

### Hands-On Exercise

```
Create an entity for me in your memory:
- Name: [Your Name]
- Type: Student
- Observations:
  - Started AI Bootcamp on [today's date]
  - Interested in [your interest]
  - Business/project: [your business or project idea]
```

Now exit Claude Code (`Ctrl+D`) and start a new session:
```bash
claude
```

Ask:
```
What do you remember about me from our memory?
```

It should recall everything you stored. That's persistence across sessions.

### Why This Matters
- AI normally forgets everything when you close the chat
- Memory MCP = your AI remembers your preferences, projects, and context
- Like training a new employee who never forgets their training

---

## Module 6: Context7 MCP — Library Documentation (15 min)

### What It Does
Context7 looks up current documentation for any library or framework. Instead of AI guessing how a library works (which can be outdated), it checks the real docs.

### How to Use It

```
Using Context7, look up how to create a new project in Next.js 14.
Show me the recommended file structure.
```

Claude Code will:
1. Resolve the library ID for Next.js
2. Query the documentation
3. Return current, accurate information

### When to Use It
- Learning a new framework
- Checking if an API has changed
- Getting code examples from official docs
- Verifying syntax before writing code

---

## Module 7: Sequential Thinking MCP (Optional, 15 min)

### What It Does
Helps Claude Code reason through complex problems step-by-step.

### Configuration
Add to your `.claude/mcp.json`:
```json
"sequential-thinking": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
}
```

### When to Use
- Multi-step business decisions
- Complex debugging
- Architecture planning
- Any problem that benefits from structured reasoning

---

## Exercise: MCP Integration Project

**Build a "Daily Briefing" tool using MCPs:**

**Step 1:** Create project
```bash
mkdir ~/ai-bootcamp/day-03-briefing
cd ~/ai-bootcamp/day-03-briefing
claude
```

**Step 2:** Set up MCPs (copy the .claude/mcp.json from Module 3)

**Step 3:** Ask Claude Code to:
```
Use Playwright to:
1. Go to https://news.ycombinator.com and get the top 3 tech stories
2. Go to a weather site and get today's weather for [your city]

Then use Memory to:
3. Store today's briefing as an entity with the stories and weather as observations

Finally:
4. Create an HTML page called "briefing.html" that displays all this information
   in a clean, dark-themed dashboard format with today's date as the header
```

**Step 4:** Push to GitHub
```bash
git add .
git commit -m "day 3: daily briefing with MCP integrations"
git push
```

---

## MCP Cheat Sheet

| MCP | Best For | Key Tools |
|-----|----------|-----------|
| **Playwright** | Web browsing, screenshots, form filling | navigate, snapshot, click, type |
| **Memory** | Cross-session knowledge | create_entities, search_nodes |
| **Context7** | Library documentation | resolve-library-id, query-docs |
| **Sequential Thinking** | Complex reasoning | sequentialthinking |
| **Supabase** | Database operations | execute_sql, list_tables |
| **n8n** | Workflow automation | search_workflows, execute_workflow |
| **Late** | Social media posting | posts_create, posts_cross_post |

---

## Checklist Before Moving On

- [ ] Understand what MCPs are and why they matter
- [ ] Can configure MCPs in .claude/mcp.json
- [ ] Installed and tested Playwright MCP
- [ ] Installed and tested Memory MCP
- [ ] Installed and tested Context7 MCP
- [ ] Completed the Daily Briefing exercise
- [ ] Pushed exercise to GitHub

**All boxes checked?** You're an Integrator. The AI isn't just chatting — it's connected to the world.

---

**Next:** [Day 4 — APIs & Scripting](../day-04-apis-and-scripting/LESSON.md)
