# AI Command Center Bootcamp — Full Curriculum

> **"Claude Code + SecureClaw = Agent Command Centers"**
> 10 days from zero to operating your own AI employee.

## Who This Is For

- Business owners who want AI to handle operations (non-technical)
- Aspiring developers who want to build with AI
- Anyone who sees AI as the future and wants hands-on skills
- No prior coding experience required — we start from absolute zero

## What You'll Walk Away With

By Day 10, every student will have:
- A fully configured AI coding environment (Claude Code + IDE)
- Connected integrations (database, payments, social media, automation)
- Their own Agent Command Center (light version)
- A portfolio project proving they can operate AI tools
- Confidence to sell AI services or use them in their own business

## Bootcamp Structure

Each day = ~2-4 hours of guided work + exercises

---

### DAY 0: Foundation — What Is AI and Why It Matters
**Level Required:** Explorer (Level 0)
**Goal:** Understand the landscape before touching any tools

| Topic | Duration | Description |
|-------|----------|-------------|
| The AI Landscape | 30 min | LLMs, agents, what's real vs hype |
| How AI "Thinks" | 20 min | Tokens, context windows, prompts, temperature |
| The Tool Stack | 20 min | IDEs vs CLIs vs APIs vs MCPs — what each does |
| Business Case Studies | 30 min | Real examples of AI saving businesses 10+ hours/week |
| Mindset | 15 min | Why most people fail at AI adoption (fear, not skill) |

**Key Concepts:**
- LLM = Large Language Model (ChatGPT, Claude, Gemini — these are the brains)
- IDE = Integrated Development Environment (where you write code — Cursor, Anti-Gravity, VS Code)
- CLI = Command Line Interface (text-based terminal — Claude Code, Gemini CLI, OpenCode)
- API = Application Programming Interface (how software talks to other software)
- MCP = Model Context Protocol (how AI connects to external tools — databases, APIs, browsers)
- Agent = AI that can take actions, not just chat

**Exercise:** Write down 5 tasks in your business/life that are repetitive and could be automated.

**Deliverable:** Students understand the vocabulary and aren't intimidated by any term.

[Full lesson plan](day-00-foundation/LESSON.md)

---

### DAY 1: Environment Setup — Your AI Workstation
**Level Required:** Builder (Level 1)
**Goal:** Every student has a working AI coding environment by end of day

| Topic | Duration | Description |
|-------|----------|-------------|
| Terminal Basics | 30 min | What is a terminal, basic commands (cd, ls, mkdir, etc.) |
| Node.js & npm | 20 min | Install Node.js, understand package managers |
| Git & GitHub | 30 min | Install Git, create GitHub account, clone first repo |
| Claude Code Install | 20 min | `npm install -g @anthropic-ai/claude-code`, API key setup |
| First Conversation | 20 min | Talk to Claude Code, ask it to build something simple |
| IDE Setup | 30 min | Install VS Code + Anti-Gravity extension (or Cursor) |

**Tools Installed:**
- Node.js (LTS)
- Git
- Claude Code CLI
- VS Code or Cursor
- Anti-Gravity extension (optional)
- GitHub account

**Exercise:** Use Claude Code to create a "Hello World" webpage. Push it to GitHub.

**Deliverable:** Working terminal + Claude Code + IDE. First GitHub commit.

[Full lesson plan](day-01-environment-setup/LESSON.md)

---

### DAY 2: Claude Code Deep Dive — Your AI Employee
**Level Required:** Builder (Level 1)
**Goal:** Master Claude Code as your primary AI tool

| Topic | Duration | Description |
|-------|----------|-------------|
| Claude Code Architecture | 20 min | How it works: context window, tools, permissions |
| Effective Prompting | 30 min | How to give Claude Code clear instructions |
| CLAUDE.md Files | 20 min | Project instructions — teaching your AI about your codebase |
| Skills & Slash Commands | 30 min | /commit, /review, custom skills — extending capabilities |
| Working with Files | 30 min | Read, Edit, Write, Glob, Grep — the core toolset |
| Multi-file Operations | 20 min | Refactoring across files, subagents for parallel work |
| Settings & Configuration | 15 min | .claude/ directory, permissions, model selection |

**Key Concepts:**
- CLAUDE.md = Your AI's instruction manual (project-level rules)
- Skills = Reusable prompt templates that extend Claude Code's abilities
- Subagents = Claude Code spawning helper agents for parallel tasks
- Context window = How much the AI can "see" at once (~200K tokens)
- Permission modes = plan, autoaccept, default — how much autonomy you give

**Exercise:** Create a CLAUDE.md for a personal project. Add 3 custom rules. Use Claude Code to build a simple tool following those rules.

**Deliverable:** Students can instruct Claude Code, use skills, and manage projects.

[Full lesson plan](day-02-claude-code/LESSON.md)

---

### DAY 3: MCPs & Integrations — Connecting AI to the World
**Level Required:** Integrator (Level 2)
**Goal:** Understand and configure MCP servers to give AI superpowers

| Topic | Duration | Description |
|-------|----------|-------------|
| What Are MCPs? | 20 min | Model Context Protocol — AI's USB ports for external tools |
| MCP Architecture | 20 min | Servers, tools, resources — how they connect |
| Installing MCPs | 30 min | .claude/mcp.json, npx servers, configuration |
| Playwright MCP | 30 min | Browser automation — navigate, click, scrape, screenshot |
| Memory MCP | 20 min | Persistent knowledge graph across sessions |
| Context7 MCP | 15 min | Library documentation lookup |
| Building Custom MCPs | 30 min | When to build vs when to use existing ones |

**MCPs Covered:**
- Playwright (browser automation)
- Memory (knowledge persistence)
- Context7 (documentation lookup)
- Sequential Thinking (structured reasoning)

**Key Concept — MCP vs API:**
- API = You write code to call it
- MCP = AI calls it automatically when relevant
- MCPs turn APIs into AI-native tools

**Exercise:** Install 2 MCPs. Use Playwright to scrape a website. Use Memory to store and recall information across conversations.

**Deliverable:** Students have working MCPs and understand when/why to use them.

[Full lesson plan](day-03-mcps-and-integrations/LESSON.md)

---

### DAY 4: APIs & Scripting — JSON to Python
**Level Required:** Integrator (Level 2)
**Goal:** Read APIs, write Python scripts, automate data flows

| Topic | Duration | Description |
|-------|----------|-------------|
| What Is an API? | 20 min | REST, endpoints, authentication, JSON |
| Reading JSON | 20 min | Structure, parsing, nested data |
| Python Basics | 30 min | Variables, functions, pip, virtual environments |
| API Calls in Python | 30 min | requests library, headers, auth, error handling |
| JSON to Python Scripts | 30 min | Turning API responses into useful tools |
| CLI Wrappers | 30 min | Building command-line tools from APIs (CLI-Anything pattern) |
| Environment Variables | 15 min | .env files, secrets management, never hardcode keys |

**Key Pattern — CLI-Anything:**
- Any API can become a command-line tool
- `python my_tool.py list` → clean output
- `python my_tool.py list --json` → machine-readable output
- Never reimplement core logic — always wrap the official SDK/API

**Exercise:** Pick a public API (weather, quotes, news). Build a Python CLI tool that fetches and displays data. Add --json flag for machine output.

**Deliverable:** Students can read API docs, write Python scripts, and build CLI tools.

[Full lesson plan](day-04-apis-and-scripting/LESSON.md)

---

### DAY 5: Database & Backend — Supabase
**Level Required:** Integrator (Level 2)
**Goal:** Set up a database, write queries, understand data persistence

| Topic | Duration | Description |
|-------|----------|-------------|
| Why Databases? | 15 min | Storing data persistently — when files aren't enough |
| Supabase Setup | 20 min | Create project, dashboard tour, connection strings |
| SQL Basics | 30 min | SELECT, INSERT, UPDATE, DELETE — the 4 operations |
| Tables & Schema | 25 min | Designing tables, columns, types, relationships |
| Row Level Security | 20 min | Protecting data — who can see/edit what |
| Supabase + Claude Code | 20 min | MCP integration, querying from your AI agent |
| Real-Time Features | 15 min | Subscriptions, live data updates |

**Tools:**
- Supabase (PostgreSQL database + auth + storage + realtime)
- Supabase MCP for Claude Code
- SQL basics

**Exercise:** Create a Supabase project. Build a "contacts" table. Write SQL to add, query, update, and delete contacts. Connect it to Claude Code via MCP.

**Deliverable:** Working database that their AI agent can read/write to.

[Full lesson plan](day-05-database-and-backend/LESSON.md)

---

### DAY 6: Automation & Workflows — n8n and Cron Jobs
**Level Required:** Integrator (Level 2)
**Goal:** Automate repetitive tasks with visual workflows and scheduled jobs

| Topic | Duration | Description |
|-------|----------|-------------|
| What Is Automation? | 15 min | Triggers, actions, workflows — the automation mindset |
| n8n Setup | 25 min | Self-hosted vs cloud, dashboard tour |
| First Workflow | 30 min | Webhook trigger → process data → send notification |
| Common Patterns | 30 min | Form submissions, email parsing, data sync |
| Cron Jobs | 20 min | Scheduled tasks — run things at specific times |
| n8n + Claude Code | 20 min | MCP integration, triggering workflows from AI |
| Webhooks | 20 min | Event-driven automation — when X happens, do Y |

**Tools:**
- n8n (visual workflow automation)
- Cron (scheduled jobs)
- Webhooks (event triggers)

**Key Concept — Event-Driven vs Scheduled:**
- Cron = "Run this every day at 9am" (time-based)
- Webhook = "Run this when a form is submitted" (event-based)
- Best practice: prefer webhooks over polling

**Exercise:** Build an n8n workflow: when a webhook receives data, format it and send a Slack/email notification. Add a cron job that runs a daily summary.

**Deliverable:** Working automation pipeline. Students understand triggers, actions, and scheduling.

[Full lesson plan](day-06-automation-and-workflows/LESSON.md)

---

### DAY 7: Deployment & Hosting — Going Live
**Level Required:** Architect (Level 3)
**Goal:** Deploy a real application to the internet

| Topic | Duration | Description |
|-------|----------|-------------|
| What Is Deployment? | 15 min | Local vs production, domains, DNS |
| Vercel | 30 min | Deploy a Next.js/React app in 5 minutes |
| Environment Variables | 15 min | Production secrets, .env.production |
| Docker Basics | 30 min | Containers, images, Dockerfiles — what and why |
| VPS Hosting | 25 min | When you need a server (n8n, bots, custom backends) |
| Domains & DNS | 15 min | Buying domains, pointing to your app |
| CI/CD Basics | 20 min | Auto-deploy on git push (GitHub Actions) |

**Tools:**
- Vercel (frontend hosting)
- Docker (containerization)
- Hostinger/DigitalOcean (VPS for backends)
- GitHub Actions (CI/CD)
- Cloudflare (DNS, optional)

**Exercise:** Deploy the webpage from Day 1 to Vercel with a custom domain (or Vercel subdomain). Dockerize a simple Python script.

**Deliverable:** A live app on the internet. Understanding of when to use Vercel vs VPS vs Docker.

[Full lesson plan](day-07-deployment-and-hosting/LESSON.md)

---

### DAY 8: Business Tools — Stripe, Social Media, and the Money Stack
**Level Required:** Architect (Level 3)
**Goal:** Connect payment processing and social media to your AI stack

| Topic | Duration | Description |
|-------|----------|-------------|
| Stripe Setup | 25 min | Create account, API keys, test mode |
| Payments & Subscriptions | 30 min | Products, prices, checkout sessions, webhooks |
| Social Media APIs | 20 min | Late API — schedule and cross-post content |
| Content Automation | 25 min | AI-generated content → scheduled posting pipeline |
| Platform Limits | 10 min | X=280, Threads=500, IG=2200, LinkedIn=3000, TikTok=4000 |
| NotebookLM | 20 min | Google's research tool — turn documents into podcasts/summaries |
| Business Dashboard | 15 min | Agent Command Center overview (Bennett's light version) |

**Tools:**
- Stripe (payments)
- Late API (social media scheduling)
- NotebookLM (research & content)
- Agent Command Center (dashboard)

**Exercise:** Set up Stripe test mode. Create a product with a price. Build a checkout link. Schedule a social media post using Late API.

**Deliverable:** Students can accept payments and automate social media.

[Full lesson plan](day-08-business-tools/LESSON.md)

---

### DAY 9: Advanced Agents — Memory, Skills, and Multi-Agent Systems
**Level Required:** Architect (Level 3)
**Goal:** Build an AI agent with persistent memory, custom skills, and self-improvement

| Topic | Duration | Description |
|-------|----------|-------------|
| Agent Architecture | 25 min | Brain files, memory tiers, state management |
| Custom Skills | 30 min | Writing SKILL.md files, YAML frontmatter, skill loading |
| Memory Systems | 25 min | Short-term (session) vs long-term (files) vs persistent (database) |
| Multi-Agent Orchestration | 25 min | Subagents, delegation, parallel work |
| Self-Healing Patterns | 15 min | Error recovery, state sync, confidence scoring |
| Prompt Engineering | 20 min | CLAUDE.md best practices, WAT framework, instruction limits |
| GitHub Repos & Community | 15 min | Finding and using open-source agent tools |

**Key Concepts:**
- Brain files = Your agent's personality, knowledge, and state
- Skills = Modular capabilities your agent can load on demand
- Memory tiers = What to remember always vs sometimes vs archive
- WAT Framework = Workflows / Agents / Tools structure for instructions
- Self-healing = Agent detects and fixes its own problems

**Exercise:** Create a mini agent with: CLAUDE.md (instructions), 2 custom skills, a memory file, and a brain/STATE.md. Make it do something useful for your business.

**Deliverable:** Students have built their own specialized AI agent.

[Full lesson plan](day-09-advanced-agents/LESSON.md)

---

### DAY 10: Capstone — Build Your Agent Command Center
**Level Required:** Operator (Level 4)
**Goal:** Combine everything into a working Agent Command Center

| Topic | Duration | Description |
|-------|----------|-------------|
| Capstone Briefing | 15 min | Requirements, judging criteria, support available |
| Build Time | 120 min | Students build their own agent command center |
| Integration Check | 30 min | Verify all connections work (DB, payments, social, automation) |
| Demo & Review | 30 min | Present to the cohort, get feedback |
| What's Next | 15 min | Advanced topics, ongoing community, selling AI services |

**Capstone Requirements:**
1. Working Claude Code environment with custom CLAUDE.md
2. At least 2 MCP integrations connected
3. A database with real data
4. One automation workflow (n8n or cron)
5. Either: a deployed app OR a business tool (Stripe/social media)
6. A custom skill or agent specialization

**Bonus Points:**
- Docker containerization
- Multi-agent setup
- WhatsApp/Telegram bot integration
- Client-ready demo

**Deliverable:** A complete Agent Command Center they own and operate.

[Full lesson plan](day-10-capstone/LESSON.md)

---

## Tools & Resources Master List

### AI Coding Tools (Core)
| Tool | Type | Purpose | Install |
|------|------|---------|---------|
| Claude Code | CLI | Primary AI agent | `npm i -g @anthropic-ai/claude-code` |
| Anti-Gravity | IDE Extension | AI-native IDE | VS Code extension |
| Cursor | IDE | AI-first code editor | cursor.com |
| Gemini CLI | CLI | Google's AI agent | `npm i -g @anthropic-ai/gemini-cli` |
| OpenCode | CLI | Open-source AI CLI | GitHub |

### Infrastructure
| Tool | Type | Purpose |
|------|------|---------|
| Supabase | BaaS | Database, auth, storage, realtime |
| Vercel | Hosting | Frontend deployment |
| Docker | Containerization | Package apps for any environment |
| n8n | Automation | Visual workflow builder |
| GitHub | Version Control | Code hosting, collaboration |

### Business Tools
| Tool | Type | Purpose |
|------|------|---------|
| Stripe | Payments | Accept payments, subscriptions |
| Late API | Social Media | Schedule/cross-post content |
| NotebookLM | Research | Document analysis, podcast generation |
| WhatsApp Business API | Communication | Group chat automation |

### MCP Servers
| Server | Purpose | Package |
|--------|---------|---------|
| Playwright | Browser automation | `@playwright/mcp@latest` |
| Supabase | Database operations | `@supabase/mcp-server-supabase@latest` |
| Memory | Knowledge persistence | `@modelcontextprotocol/server-memory` |
| Context7 | Library docs | `@upstash/context7-mcp@latest` |
| Sequential Thinking | Structured reasoning | `@modelcontextprotocol/server-sequential-thinking` |
| n8n | Workflow automation | `n8n-mcp` |
| Late | Social media | `late-sdk[mcp]` |

---

## Progression Map

```
Day 0  [Explorer]     Foundation — vocabulary, mindset, landscape
Day 1  [Builder]      Environment — terminal, Git, Claude Code install
Day 2  [Builder]      Claude Code — deep dive, skills, CLAUDE.md
  |
  v  LEVEL UP: Builder → Integrator
  |
Day 3  [Integrator]   MCPs — connecting AI to external tools
Day 4  [Integrator]   APIs — JSON, Python scripting, CLI tools
Day 5  [Integrator]   Database — Supabase, SQL, data persistence
Day 6  [Integrator]   Automation — n8n, cron jobs, webhooks
  |
  v  LEVEL UP: Integrator → Architect
  |
Day 7  [Architect]    Deployment — Vercel, Docker, going live
Day 8  [Architect]    Business — Stripe, social media, money stack
Day 9  [Architect]    Advanced — multi-agent, memory, self-healing
  |
  v  LEVEL UP: Architect → Operator
  |
Day 10 [Operator]     Capstone — build your Agent Command Center
```

---

*Built by CC & Bennett — OASIS AI Solutions x Agent Command Center*
*Curriculum version 1.0 — March 2026*
