# Lesson 1: Command Center Architecture — The Control Room for Your AI Empire

> **Course:** Agent Command Centers
> **XP Reward: +300 XP** | Running Total: 300 XP
> **Level: Architect (L3)** — You're designing systems now, not just using them.

---

## What Is an Agent Command Center?

A command center is the control room for all your AI agents. It is not one agent — it is the system that governs, monitors, and coordinates all of them.

Without a command center, you have a collection of AI tools that don't know about each other. With one, you have an autonomous business operations system.

```
Without command center:
  Claude Code (knows about this session only)
  Gemini CLI (knows about this session only)
  n8n workflows (know about their triggers only)
  → No coordination, no persistent memory, no shared ground truth

With command center:
  All agents read from the same brain/ files
  All agents write to the same memory/ files
  State persists across sessions, devices, AI switches
  → Coordinated execution, shared knowledge, compounding intelligence
```

The Business-Empire-Agent repository you've been building in this course is a command center. This lesson explains the architecture that makes it work.

---

## The Four Architecture Layers

A command center has four distinct layers. Understanding each layer and its responsibility prevents the confusion that comes from mixing concerns.

```
┌───────────────────────────────────────────────┐
│         PRESENTATION LAYER                    │
│   Dashboard UI · Telegram Bridge · CLI        │
│   "How does a human interact with the system" │
├───────────────────────────────────────────────┤
│         ORCHESTRATION LAYER                   │
│   CLAUDE.md · AGENTS.md · Task Router         │
│   "Which agent handles which type of task"    │
├───────────────────────────────────────────────┤
│         INTELLIGENCE LAYER                    │
│   brain/ · memory/ · skills/                  │
│   "What the system knows and how it thinks"   │
├───────────────────────────────────────────────┤
│         INFRASTRUCTURE LAYER                  │
│   MCP servers · APIs · Supabase · n8n         │
│   "What the system can connect to"            │
└───────────────────────────────────────────────┘
```

### Layer 1: Presentation

Where humans interact with the system.

| Interface | Use Case |
|-----------|----------|
| Claude Code CLI | Deep work — code, architecture, multi-file changes |
| Gemini CLI | Quick queries, research, fast iteration |
| Telegram bridge | On-the-go commands, notifications, status checks |
| Web dashboard | Visual monitoring, client-facing reporting |
| Anti-Gravity IDE | Paired development, inline AI assistance |

The key principle: each interface is interchangeable. A task started in Claude Code can be picked up in Gemini because they read from the same brain and memory files. The interface is thin; the intelligence is in the layers below.

### Layer 2: Orchestration

The rules that govern how the system behaves.

**CLAUDE.md** is the master control file. It is not documentation — it is the operating system for your agents. It defines:
- What the project is (WHAT section)
- Why it exists (WHY section)
- How agents should behave (HOW section — rules, routing, workflows)

**AGENTS.md** defines the roster of specialized agents and the decision matrix that routes tasks to the right one.

**Task routing** is the mechanism that matches an incoming task to the right specialist:

```
Signal: "Fix the checkout bug in PropFlow"
  → Routing: code keyword + app name
  → Agent: Debugger
  → App registry lookup: C:\Users\User\realestate-App
  → Execute in the correct directory
```

### Layer 3: Intelligence

The knowledge that persists across sessions and accumulates over time.

```
brain/
  SOUL.md        ← Who the agent is (immutable — never changes)
  USER.md        ← Who CC is, preferences, context
  STATE.md       ← What's happening right now (ephemeral, updated constantly)
  CAPABILITIES.md ← What the system can do (updated as tools are added)

memory/
  ACTIVE_TASKS.md   ← What's in progress
  SESSION_LOG.md    ← What happened (written every session)
  MISTAKES.md       ← What went wrong and why
  PATTERNS.md       ← What works (promoted to SOPs after 3 validations)
  LONG_TERM.md      ← Persistent facts (clients, pricing, decisions)

skills/
  [skill-name]/
    SKILL.md      ← Reusable capability definition
```

This is the differentiating layer. Most AI setups have Layers 1 and 4 (an interface and some tools). Layers 2 and 3 are what make a system an agent rather than a chatbot.

### Layer 4: Infrastructure

The external services the system can touch.

```
MCP Servers (real-time tools):
  Playwright    → web browsing, screenshots, UI automation
  Supabase      → database read/write/query
  n8n           → workflow management
  Late          → social media publishing
  Memory        → cross-session knowledge graph

CLI Tools (reliable alternatives):
  stripe_tool.py     → Stripe API (billing, customers, subscriptions)
  supabase_tool.py   → Supabase (CRUD, SQL, project management)

External APIs:
  Anthropic     → Claude models
  Stripe        → payments
  Vercel        → deployments
  GitHub        → version control
```

---

## The brain/ Directory Pattern in Detail

The `brain/` directory is where your agent's identity and operational state live. These files are loaded at the start of every session — they are what make the agent consistent across thousands of interactions.

### SOUL.md — The Identity Contract

SOUL.md defines who the agent is. It answers:
- What is my name and role?
- What are my core values?
- How do I communicate?
- What is my primary objective?
- What will I never do?

This file is immutable. An agent that changes its own identity based on user input is dangerous — it can be manipulated. The soul is the one constant.

```markdown
# Agent Name — Role

## Identity
Name, version, role, who I serve.

## Personality
How I communicate. Tone, style, energy.

## Core Values
3-5 non-negotiables that govern every decision.

## Prime Directive
One sentence. What is the ultimate goal?

## Communication Rules
How I address the operator. What I never say.
```

### STATE.md — The Operational Snapshot

STATE.md is the opposite of SOUL.md — it changes constantly. It captures what is true right now:
- What is the current focus?
- What MCPs are working and which are broken?
- What was the most recent significant action?
- What's blocked?

Any agent picking up mid-session reads STATE.md first to understand where things stand.

```markdown
## Current State — [DATE]

**Focus:** [Active project or task]
**Status:** [What's in flight]
**MCP Health:** [Which servers are working]
**Blocked On:** [If anything is waiting on CC]
**Last Action:** [Most recent meaningful event]
**Next Action:** [What should happen next]
```

### CAPABILITIES.md — The Inventory

CAPABILITIES.md is the complete inventory of what the system can do. When a new tool is added or a skill is created, this file is updated. When debugging why an agent didn't use a tool, this is the first place to look.

---

## Memory Architecture: Five Tiers

The memory system is designed around a simple principle: **the most frequently accessed information must load fastest.** Tier 1 is always in context. Tier 5 is never loaded unless specifically requested.

| Tier | Files | Load Strategy | Budget |
|------|-------|--------------|--------|
| **1 — Always loaded** | `brain/SOUL.md`, `brain/USER.md`, `brain/STATE.md` | Every session | <500 lines combined |
| **2 — On demand** | `memory/ACTIVE_TASKS.md`, `memory/LONG_TERM.md`, `memory/SOP_LIBRARY.md` | Brain Loop Step 2 | <300 lines each |
| **3 — When relevant** | `memory/PATTERNS.md`, `memory/MISTAKES.md`, `memory/DECISIONS.md` | Debugging, planning | <200 lines each |
| **4 — Write-mostly** | `memory/SESSION_LOG.md`, `memory/SELF_REFLECTIONS.md` | Written constantly, rarely read | Unlimited |
| **5 — Cold storage** | `memory/ARCHIVES/` | Monthly audits only | Unlimited |

This tiered architecture keeps the context window clean. Every file you load costs context tokens. Load only what you need.

---

## State Management: How Agents Know What's Happening

The fundamental challenge of multi-session, multi-agent systems is: how does an agent picking up mid-task know what's already been done?

The answer is disciplined state writing at the end of every session.

### The State Sync Protocol

After every session — whether the work is complete or not — the agent must:

1. **Update STATE.md** with current focus, MCP health, last action, next action
2. **Update ACTIVE_TASKS.md** with current task statuses
3. **Append to SESSION_LOG.md** with a summary of what happened
4. **Git commit** with a sync message: `bravo: sync — session YYYY-MM-DD`

When a new agent (or a new session of the same agent) starts:

1. Reads STATE.md — knows where things stand immediately
2. Reads ACTIVE_TASKS.md — knows what's in progress
3. Reads SESSION_LOG.md — knows the recent history
4. Picks up exactly where the previous session left off

This is the mechanism that makes your three AI agents (Claude, Gemini, Anti-Gravity) interchangeable. They share state, not sessions.

---

## The CLAUDE.md as Operating System

CLAUDE.md is the file loaded at the start of every Claude Code session. It is the single most important file in your entire command center because it governs all agent behavior.

### The 100-Line Discipline

Claude Code's system prompt consumes approximately 50 instruction units. You have approximately 100 more before instruction-following reliability drops. This means every line in CLAUDE.md must be essential.

The test for every line: "Would removing this cause the agent to make a mistake?"

If the answer is no, remove it.

### Structure That Works

```markdown
# [Agent Name] — [Version]

## Principles
[3-5 universal principles that apply to everything. Not rules — worldview.]

## WHAT — Project & Stack
[What is this? Stack, owner, brands. 5-10 lines.]

## WHY — Purpose
[North star goal. One sentence.]

## HOW — Workflows & Rules

### RULE 0: [Most critical rule — state sync, security, etc.]
### RULE 1: [Second most critical...]
### RULE N: ...

## Workflow Commands
[Table of /slash commands and what they do]

## Skills
[References to skills/, loaded on demand]
```

---

## Real Example: Business-Empire-Agent Walkthrough

The system you've been building in this course implements this architecture exactly.

| File | Layer | Purpose |
|------|-------|---------|
| `CLAUDE.md` | Orchestration | Master control — rules, routing, commands |
| `brain/SOUL.md` | Intelligence | Bravo's identity — immutable |
| `brain/USER.md` | Intelligence | CC's profile — preferences, brands, goals |
| `brain/STATE.md` | Intelligence | Current operational state — ephemeral |
| `brain/CAPABILITIES.md` | Intelligence | Complete tool inventory |
| `memory/ACTIVE_TASKS.md` | Intelligence | In-progress work |
| `memory/SESSION_LOG.md` | Intelligence | Complete history — all agents |
| `skills/*/SKILL.md` | Intelligence | Reusable capabilities |
| `.claude/mcp.json` | Infrastructure | MCP server connections |
| `scripts/*.py` | Infrastructure | CLI tools |

Every component in its layer. Every layer with a clear responsibility. No overlap.

---

## 🔥 EXERCISE: Design Your Command Center Architecture

Before writing a single file, design your architecture on paper (or in a markdown document).

**Step 1:** Define your four layers.

For each layer, answer:
- **Presentation:** What interfaces will you support? (Claude Code only? + Telegram? + Web dashboard?)
- **Orchestration:** What are the 5-10 rules that govern your agent's behavior? What agent types do you need?
- **Intelligence:** What does your agent need to know? Map out your brain/ and memory/ files.
- **Infrastructure:** What external services does your agent connect to? List every MCP and CLI tool.

**Step 2:** Draw the architecture diagram.

Create a text-based diagram (like the one in this lesson) showing your four layers and what lives in each.

**Step 3:** Create the directory structure.

```bash
mkdir -p my-command-center/brain
mkdir -p my-command-center/memory
mkdir -p my-command-center/skills
mkdir -p my-command-center/scripts
mkdir -p my-command-center/.claude
```

Create placeholder files for each brain and memory file you identified in Step 1.

**Deliverable:** A complete architecture diagram and directory structure for your personal or client-facing command center.

---

## 🧠 KEY TAKEAWAY

The four-layer architecture — Presentation, Orchestration, Intelligence, Infrastructure — is the blueprint that separates a real command center from a collection of AI tools. The intelligence layer (brain/, memory/, skills/) is what makes the system accumulate capability over time instead of starting fresh every session. Design it before you build it. The architecture decisions you make now determine whether you're maintaining a system or fighting one six months later.

---

**Next:** [Lesson 2 — Multi-Agent Orchestration](../lesson-02-multi-agent/LESSON.md)
