# Day 10: Capstone — Build Your Agent Command Center

> **Level:** Operator (Level 4) -- LEVEL UP!
> **Duration:** ~3.5 hours
> **Prerequisites:** Days 0-9 complete
> **Goal:** Combine everything into a working Agent Command Center. Prove you can operate AI tools independently.

---

## Capstone Briefing (15 min)

### What You're Building

Your own **Agent Command Center** — a complete AI operations setup that includes:
1. An AI agent with custom instructions and personality
2. Connected integrations (database, at minimum)
3. Automated workflows
4. A way to accept payments OR distribute content
5. Evidence that it all works together

### Requirements

| # | Requirement | Day Learned | Points |
|---|------------|-------------|--------|
| 1 | Working Claude Code environment with custom CLAUDE.md | Day 2 | Required |
| 2 | At least 2 MCP integrations connected and working | Day 3 | Required |
| 3 | A Supabase database with at least 2 tables | Day 5 | Required |
| 4 | One automation (n8n workflow OR cron job) | Day 6 | Required |
| 5 | Either: deployed app OR business tool (Stripe/social) | Day 7-8 | Required |
| 6 | A custom skill or agent specialization | Day 9 | Required |

### Bonus Points

| Bonus | Points | Description |
|-------|--------|-------------|
| Docker | +10 | Containerized any part of your stack |
| Multi-agent | +10 | Agent delegates to sub-agents |
| Bot integration | +15 | WhatsApp, Telegram, or Discord bot |
| Client-ready demo | +15 | Could show this to a real client |
| Custom CLI tool | +10 | Built a CLI wrapper for an API |
| Full CRUD app | +10 | Frontend + backend + database with all 4 operations |

---

## Build Phase (120 min)

### Approach Options

**Option A: Business Tool Stack (Best for non-technical)**
Build an agent that manages a business:
- Supabase: clients, invoices, tasks tables
- Stripe: accept payments for a service
- Late API: schedule social media content
- n8n: new client → auto-invoice → welcome email
- Skill: client onboarding checklist

**Option B: Personal Productivity Hub (Best for personal use)**
Build an agent that manages your life:
- Supabase: tasks, habits, journal entries
- Playwright: daily news/research briefing
- n8n: morning briefing cron job
- Memory MCP: persistent preferences
- Skill: daily review and planning

**Option C: Content Machine (Best for creators)**
Build an agent that automates content:
- Supabase: content calendar, ideas database
- Late API: cross-platform posting
- n8n: scheduled content pipeline
- Playwright: competitor research
- Skill: content generation with brand voice

**Option D: Custom (Your Idea)**
Build whatever you want. Must meet the 6 requirements above.

### Getting Started

```bash
mkdir ~/ai-bootcamp/capstone
cd ~/ai-bootcamp/capstone
git init
claude
```

Tell Claude Code your plan:
```
I'm building my capstone project for the AI Command Center Bootcamp.

Here's my plan:
[Describe what you're building — which option or your own idea]

Requirements I need to hit:
1. Custom CLAUDE.md with project rules
2. 2+ MCPs (I want [list which])
3. Supabase with [describe your tables]
4. Automation: [describe your workflow]
5. Business tool: [Stripe/social media/deployed app]
6. Custom skill: [describe what it does]

Let's start with the CLAUDE.md and project structure.
```

### Build Tips

1. **Start with CLAUDE.md** — This guides everything else
2. **Set up Supabase tables early** — Data is the foundation
3. **Connect MCPs before building features** — Verify connections work
4. **Build the simplest version first** — Add complexity after it works
5. **Test each component individually** — Don't build everything then test
6. **Commit frequently** — `git commit -m "capstone: add [component]"`

---

## Integration Check (30 min)

### Verify Everything Works

Run through this checklist with Claude Code:

```
Run my capstone integration check:

1. CLAUDE.md: Read it and confirm it has project rules, tool routing, and don'ts
2. MCPs: List connected MCPs and test each with a simple query
3. Database: List my Supabase tables and run a SELECT on each
4. Automation: Show my n8n workflow(s) or cron job configuration
5. Business tool: Verify Stripe products exist OR show scheduled social posts
6. Skill: Load my custom skill and demonstrate it

Report: Pass/Fail for each requirement.
```

### Common Issues and Fixes

| Issue | Fix |
|-------|-----|
| MCP not connecting | Restart Claude Code. Check .claude/mcp.json syntax. |
| Supabase query fails | Check API key in .env. Verify RLS policies. |
| n8n workflow not triggering | Check if workflow is activated. Test webhook URL. |
| Stripe in live mode | Switch to test mode. Use test API keys. |
| Skill not loading | Check file path and YAML frontmatter format. |

---

## Demo & Review (30 min)

### Prepare Your Demo

Create a `DEMO.md` in your project:

```markdown
# Capstone Demo — [Your Project Name]

## What I Built
[2-3 sentences describing your Agent Command Center]

## Architecture
[Simple diagram or description of how components connect]

## Components
1. **Agent:** [Name, personality, purpose]
2. **Database:** [Tables and their purpose]
3. **Integrations:** [MCPs connected]
4. **Automation:** [Workflow description]
5. **Business Tool:** [What it does]
6. **Custom Skill:** [What it does]

## Demo Flow
1. [Step 1: Show the agent responding to a command]
2. [Step 2: Show data flowing into the database]
3. [Step 3: Show the automation triggering]
4. [Step 4: Show the business tool in action]
5. [Step 5: Show the custom skill executing]

## What I'd Build Next
[3 ideas for extending this project]
```

### Present to the Cohort

If in a group setting:
- 5-minute demo per person
- Show the live system working
- Explain your architecture
- Take questions

### Self-Review

Rate yourself honestly:

| Criteria | 1-5 | Notes |
|----------|-----|-------|
| Does it work end-to-end? | | |
| Is the CLAUDE.md well-structured? | | |
| Are integrations reliable? | | |
| Would a client be impressed? | | |
| Could someone else set this up from your docs? | | |

---

## What's Next (15 min)

### You Are Now an AI Operator

Over 10 days, you went from zero to:
- **Environment:** Terminal, Git, Node.js, Python, Docker
- **AI Tools:** Claude Code, MCPs, custom skills, agent architecture
- **Infrastructure:** Supabase, Vercel, n8n, webhooks, cron
- **Business:** Stripe, social media automation, content pipelines
- **Architecture:** Multi-agent systems, memory, self-healing

### Paths Forward

**Path 1: Sell AI Services**
- Offer what you've learned to businesses
- Package as: "AI Automation Setup" ($500-$2000)
- Use your capstone as a portfolio piece
- Key pitch: "I'll set up AI tools that save you 10+ hours per week"

**Path 2: Build AI Products**
- Turn your capstone into a SaaS product
- Add user authentication (Supabase Auth)
- Add payment processing (Stripe)
- Deploy to Vercel
- Charge monthly subscriptions

**Path 3: Join AI Teams**
- These skills are in massive demand
- "AI Engineer" and "AI Operations" are real job titles
- Your GitHub portfolio proves you can build
- Freelance on Upwork, Fiverr, or direct outreach

**Path 4: Keep Learning**
- Advanced topics: RAG (Retrieval-Augmented Generation), vector databases, fine-tuning
- Infrastructure: Kubernetes, Terraform, monitoring
- AI frameworks: LangChain, CrewAI, AutoGen
- Stay in the community — AI changes weekly

### Staying Connected

- **Community:** Bennett's WhatsApp group (announcements + support)
- **Dashboard:** Agent Command Center for monitoring your setup
- **Updates:** Curriculum will be updated as new tools emerge
- **Support:** Ask questions in the group. Help others. That's how you solidify knowledge.

### The Mindset

```
Day 0:  "What even is an API?"
Day 10: "I built an AI agent that automates my business."
```

That's 10 days. Most people take months to get here. You did it because you showed up, followed the structure, and built real things.

**Now go build something that matters.**

---

## Final Checklist

- [ ] Capstone project meets all 6 requirements
- [ ] Integration check passes
- [ ] DEMO.md created
- [ ] Project pushed to GitHub
- [ ] You can explain what you built to a non-technical person
- [ ] You have ideas for what to build next

**All boxes checked?** You're an Operator. Welcome to Level 4.

---

*Congratulations. You're now part of the future.*

*Built by CC & Bennett — OASIS AI Solutions x Agent Command Center*
