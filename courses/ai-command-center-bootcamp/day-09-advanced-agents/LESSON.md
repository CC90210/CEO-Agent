# Day 9: Advanced Agents — Memory, Skills, and Multi-Agent Systems

> **Level:** Architect (Level 3)
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 8 complete
> **Goal:** Build an AI agent with persistent memory, custom skills, and self-improvement capabilities.

---

## Module 1: Agent Architecture (25 min)

### What Makes an Agent?

A chatbot answers questions. An **agent** takes actions, remembers context, and improves over time.

```
Chatbot:  User asks → AI responds → forgets everything

Agent:    User asks → AI checks memory → plans approach → executes actions
          → stores results → learns from outcomes → ready for next task
```

### The Agent Stack

```
┌─────────────────────────────────────┐
│           BRAIN (Identity)          │  Who am I? What are my values?
├─────────────────────────────────────┤
│           MEMORY (Knowledge)        │  What do I know? What happened?
├─────────────────────────────────────┤
│           SKILLS (Capabilities)     │  What can I do?
├─────────────────────────────────────┤
│           TOOLS (Connections)       │  What can I access? (MCPs, APIs)
├─────────────────────────────────────┤
│           STATE (Current Context)   │  What am I working on right now?
└─────────────────────────────────────┘
```

### File Structure of an Agent

```
my-agent/
├── CLAUDE.md              ← Master instructions (loaded every session)
├── brain/
│   ├── SOUL.md            ← Identity, values, personality
│   ├── STATE.md           ← Current operational state
│   └── USER.md            ← Info about the person you serve
├── memory/
│   ├── ACTIVE_TASKS.md    ← What's in progress
│   ├── SESSION_LOG.md     ← What happened each session
│   ├── MISTAKES.md        ← Things that went wrong (learn from these)
│   └── PATTERNS.md        ← Things that work well (repeat these)
├── skills/
│   └── my-skill/
│       └── SKILL.md       ← Reusable capability
├── scripts/
│   └── my_tool.py         ← CLI tools
└── .claude/
    └── mcp.json           ← MCP connections
```

---

## Module 2: Custom Skills (30 min)

### What Is a Skill?

A skill is a reusable prompt template that teaches your agent how to handle a specific type of task. Instead of re-explaining your process every time, you write it once as a skill.

### Skill Format

```markdown
# Skill Name

## Overview
What this skill does and when to use it.

## When to Use
- Trigger conditions
- Types of tasks this handles

## The Process
1. Step one
2. Step two
3. Step three

## Examples
Show input → expected output

## Rules
- Do this
- Don't do that
```

### Example: Client Onboarding Skill

```markdown
# Client Onboarding

## Overview
When a new client signs up, execute this onboarding checklist to ensure
nothing falls through the cracks.

## When to Use
- New client payment confirmed
- CC says "onboard [client name]"

## Process
1. Create client record in Supabase contacts table
2. Send welcome email using the welcome template
3. Create Stripe customer with their billing info
4. Set up their first automation workflow in n8n
5. Schedule a 30-minute kickoff call
6. Create task list for first deliverables
7. Log everything in SESSION_LOG.md

## Email Template
Subject: Welcome to OASIS AI — Let's Get Started

Body:
Hi [name],

Welcome aboard! I'm excited to start building your AI automation stack.

Here's what happens next:
1. We'll have a 30-minute kickoff call to map your workflows
2. I'll set up your first automation within 48 hours
3. You'll see results before the end of week 1

Looking forward to it,
Conaugh McKenna
OASIS AI Solutions

## Rules
- Always confirm payment before onboarding
- Never skip the kickoff call scheduling
- Log every onboarding in SESSION_LOG.md
```

### Creating Skills with Claude Code

```
Create a new skill at skills/content-review/SKILL.md that:
1. Takes a piece of content (blog post, social post, email)
2. Checks for: grammar, tone (match my brand voice), clarity, CTA
3. Suggests improvements
4. Outputs a revised version
5. Include examples of good vs bad content
```

### Slash Command Skills

Put reusable prompts in `~/.claude/commands/`:

```bash
mkdir -p ~/.claude/commands
```

Create `~/.claude/commands/morning-briefing.md`:
```markdown
Give me a morning briefing:
1. Check my active tasks (memory/ACTIVE_TASKS.md)
2. Check for any errors in recent logs
3. Summarize what was done yesterday (memory/SESSION_LOG.md)
4. List today's priorities
Keep it concise — bullet points only.
```

Now `/morning-briefing` runs this every time.

---

## Module 3: Memory Systems (25 min)

### Three Tiers of Memory

| Tier | Duration | Where | Example |
|------|----------|-------|---------|
| **Session** | One conversation | Context window | "The user asked about pricing" |
| **File-based** | Across sessions | Markdown files | ACTIVE_TASKS.md, SESSION_LOG.md |
| **Database** | Permanent | Supabase | Customer records, analytics |

### Session Memory (Automatic)

Claude Code remembers everything in the current conversation. When the conversation ends, it's gone — unless you save it.

**Extending session memory:**
- `/compact` — summarizes conversation to save space
- Claude Code auto-compresses when context window fills up

### File-Based Memory (Manual + Automated)

**ACTIVE_TASKS.md** — What's in progress:
```markdown
## In Progress
- [ ] Build client dashboard — started 2026-03-15
- [ ] Fix email automation — blocked on API key

## Completed Recently
- [x] Deploy landing page — completed 2026-03-14
```

**SESSION_LOG.md** — What happened:
```markdown
### 2026-03-15 — Morning Session
**Focus:** Client dashboard build
**Done:** Set up React app, connected to Supabase, built 3 components
**Next:** Add authentication, deploy to Vercel
```

**MISTAKES.md** — Learn from failures:
```markdown
### 2026-03-14 — API Key Exposed in Git
**What happened:** Committed .env file to GitHub
**Root cause:** .gitignore wasn't set up before first commit
**Prevention:** ALWAYS create .gitignore before git init
```

**PATTERNS.md** — Repeat what works:
```markdown
### CLI-Anything Pattern [VALIDATED]
When building a CLI tool: wrap the official SDK, support --json flag,
load credentials from .env. Works every time. Used 10+ times.
```

### Database Memory (Persistent)

For cross-session, cross-device, cross-agent memory:
```sql
CREATE TABLE memories (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    category    TEXT NOT NULL,  -- 'fact', 'pattern', 'mistake', 'preference'
    content     TEXT NOT NULL,
    confidence  NUMERIC DEFAULT 0.5,
    created_at  TIMESTAMPTZ DEFAULT now(),
    last_used   TIMESTAMPTZ DEFAULT now()
);
```

### Memory MCP

The Memory MCP (installed Day 3) provides a knowledge graph:
```
Store this in memory: Client ABC prefers morning meetings
and communicates via Slack, not email.
```

---

## Module 4: Multi-Agent Orchestration (25 min)

### Why Multiple Agents?

One agent doing everything = bottleneck. Multiple specialists = parallel execution.

```
You: "Build a landing page with database and payment processing"

Single Agent:
  → Build frontend (30 min)
  → Set up database (15 min)
  → Add Stripe (20 min)
  Total: 65 minutes (sequential)

Multi-Agent:
  Agent 1: Build frontend    → 30 min
  Agent 2: Set up database   → 15 min  } Running in parallel
  Agent 3: Add Stripe        → 20 min
  Total: 30 minutes (parallel)
```

### Claude Code Subagents

Claude Code can spawn sub-agents automatically:
```
Search the entire codebase for security vulnerabilities.
Check for: hardcoded secrets, SQL injection, XSS, missing auth checks.
Report findings with file paths and line numbers.
```

Claude Code may spawn multiple search agents to scan different directories in parallel.

### Agent Specialization Pattern

Define specialists in your CLAUDE.md:
```markdown
## Agent Roles

When delegating complex tasks, use these specializations:

- **Researcher:** Deep investigation, web browsing, documentation lookup
- **Coder:** Implementation, bug fixes, testing
- **Reviewer:** Code review, security audit, quality check
- **Writer:** Content creation, documentation, communications
```

### Agent Communication

Agents share context through files:
```
Agent 1 writes → plan.md
Agent 2 reads → plan.md → implements
Agent 3 reads → implementation → reviews → writes feedback.md
Agent 1 reads → feedback.md → revises
```

---

## Module 5: Self-Healing Patterns (15 min)

### What Is Self-Healing?

An agent that detects and fixes its own problems:

| Dimension | Detects | Fixes |
|-----------|---------|-------|
| **Memory** | Contradictions, stale data | Removes conflicts, updates facts |
| **Infrastructure** | MCP failures, broken tools | Reports errors, suggests fixes |
| **Context** | Outdated references | Flags for review |
| **Performance** | Slow responses, errors | Adjusts approach |

### Basic Self-Healing Checklist

Add to your CLAUDE.md:
```markdown
## Before Ending Session
1. Check for uncommitted changes (git status)
2. Update ACTIVE_TASKS.md with current status
3. Log session summary to SESSION_LOG.md
4. Flag any errors encountered in MISTAKES.md
5. Clean up temp files
```

### Confidence Scoring

Rate how sure you are about stored facts:

| Score | Meaning | Action |
|-------|---------|--------|
| 0.9-1.0 | Verified fact | Trust fully |
| 0.7-0.89 | High confidence | Trust, verify quarterly |
| 0.5-0.69 | Medium | Verify before relying on |
| Below 0.5 | Low confidence | Don't trust without verification |

---

## Module 6: Prompt Engineering for Agents (20 min)

### CLAUDE.md Best Practices

**The 100-Line Rule:** Claude Code's system prompt uses ~50 instructions. You have ~100 more before reliability drops. Make every line count.

**Every line must pass:** "Would removing this cause Claude to make mistakes?"

### Structure Template

```markdown
# [Agent Name]

## What — Project & Context
[2-3 sentences: what is this project?]

## Rules
[Numbered list of behavioral rules]

## Tools
[What MCPs/tools are available]

## Don't
[Explicit anti-patterns]
```

### The WAT Framework

Structure instructions as:
- **W**orkflows — How to handle specific task types
- **A**gents — Who does what (if multi-agent)
- **T**ools — What tools are available and when to use each

### Common Mistakes

| Mistake | Fix |
|---------|-----|
| Too many rules | Keep under 100 lines. Quality > quantity. |
| Vague instructions | "Be good at coding" → "Use TypeScript. Run tests before committing." |
| No negative rules | Include "Don't" section. AI needs to know boundaries. |
| Over-engineering | Start simple. Add rules only when AI makes mistakes. |

---

## Module 7: GitHub Repos & Community Tools (15 min)

### Useful Open-Source Agent Repos

| Repo | Purpose |
|------|---------|
| **anthropics/claude-code** | Claude Code itself (reference implementation) |
| **community skills** | Pre-built skills for Claude Code |
| **n8n-io/n8n** | Workflow automation (self-hosted) |
| **supabase/supabase** | Database platform |
| **anthropics/courses** | Anthropic's AI courses |

### Finding and Using Community Skills

Ask Claude Code:
```
Search for community skills related to [your need].
Show me what's available and how to install them.
```

### Contributing Back

As you build useful skills and tools, consider:
1. Open-sourcing your CLI tools
2. Publishing your skills
3. Sharing workflow templates
4. Writing about your setup (blog posts, social media)

This builds your reputation and helps the community.

---

## Exercise: Build Your Own Agent

**Step 1:** Create your agent project
```bash
mkdir ~/ai-bootcamp/day-09-my-agent
cd ~/ai-bootcamp/day-09-my-agent
mkdir -p brain memory skills scripts .claude
```

**Step 2:** Start Claude Code and build out your agent:
```bash
claude
```

```
Help me build a personal AI agent. Create:

1. CLAUDE.md — Master instructions with:
   - Project description (my personal business assistant)
   - 5-10 rules for how it should behave
   - Tool routing (what MCP to use when)
   - A "Don't" section

2. brain/SOUL.md — Agent identity:
   - Name: [pick a name for your agent]
   - Role: Personal business assistant
   - Personality: Professional but friendly
   - Core values (3-5)

3. brain/STATE.md — Current state template

4. memory/ACTIVE_TASKS.md — Task tracking template

5. memory/SESSION_LOG.md — Session log template

6. skills/daily-review/SKILL.md — A skill that:
   - Reviews what was done today
   - Identifies what's pending
   - Suggests priorities for tomorrow
   - Outputs a clean summary

7. .claude/mcp.json — With Playwright and Memory MCPs
```

**Step 3:** Test your agent by starting a new Claude Code session in the project:
```bash
cd ~/ai-bootcamp/day-09-my-agent
claude
```

Ask it:
```
Who are you? What can you do?
```

It should respond based on your SOUL.md and CLAUDE.md.

**Step 4:** Push to GitHub.

---

## Checklist Before Moving On

- [ ] Understand agent architecture (brain, memory, skills, tools, state)
- [ ] Can create custom skills with proper structure
- [ ] Understand three tiers of memory (session, file, database)
- [ ] Know how multi-agent orchestration works
- [ ] Understand self-healing patterns
- [ ] Know CLAUDE.md best practices (100-line rule, WAT framework)
- [ ] Built your own agent with custom personality and skills
- [ ] Pushed to GitHub

**All boxes checked?** You've built an AI agent from scratch. Tomorrow, you put it all together.

---

**Next:** [Day 10 — Capstone](../day-10-capstone/LESSON.md)
