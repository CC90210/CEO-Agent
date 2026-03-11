# Business Empire Agent — BRAVO V5.5

> Autonomous AI operations hub for CC's business empire. Manages codebases, deployments, content pipelines, and business operations across OASIS AI Solutions, PropFlow, and Nostalgic Requests.

---

## Agent Entry Points

Any AI agent landing in this repo should read **one** of these files first based on its environment:

| Agent / Environment | Entry File | Purpose |
|---|---|---|
| **Antigravity IDE** (VS Code) | `ANTIGRAVITY.md` | Primary IDE agent — broadest tool access |
| **Claude Code CLI** | `CLAUDE.md` | Lead Architect — complex refactoring & debugging |
| **Gemini CLI** | `GEMINI.md` | Speed layer — fast queries, diagnostics, content |
| **BlackBox AI** | `BLACKBOX.md` | Rapid infantry — boilerplate, simple edits |

All entry files reference the same shared brain (`brain/`) and memory (`memory/`) system.

---

## Directory Structure

```
Business-Empire-Agent/
│
├── ANTIGRAVITY.md              ← Antigravity IDE agent rules
├── CLAUDE.md                   ← Claude Code CLI rules
├── GEMINI.md                   ← Gemini CLI rules
├── BLACKBOX.md                 ← BlackBox AI rules
├── README.md                   ← This file
├── .gitignore
│
├── brain/                      ← Agent intelligence (shared across all agents)
│   ├── SOUL.md                 ← Identity, values, philosophy (IMMUTABLE)
│   ├── STATE.md                ← Current operational state (updated each session)
│   ├── AGENTS.md               ← Subagent registry & orchestration (14 agents)
│   ├── USER.md                 ← CC's profile and preferences
│   ├── CAPABILITIES.md         ← Full tool & capability inventory
│   ├── BRAIN_LOOP.md           ← Multi-hypothesis reasoning protocol
│   ├── INTERACTION_PROTOCOL.md ← Tiered logging & session protocol
│   ├── HEARTBEAT.md            ← Health check procedures
│   ├── GROWTH.md               ← Growth strategy & milestones
│   └── CHANGELOG.md            ← Version history
│
├── memory/                     ← Persistent memory across sessions
│   ├── ACTIVE_TASKS.md         ← Current work in progress
│   ├── SESSION_LOG.md          ← Session-end summaries
│   ├── PATTERNS.md             ← Proven approaches & anti-patterns
│   ├── MISTAKES.md             ← Bug root cause analysis
│   ├── DECISIONS.md            ← Architectural decisions log
│   ├── LONG_TERM.md            ← Verified long-term knowledge
│   ├── SELF_REFLECTIONS.md     ← Reflexion framework learnings
│   ├── PROPOSED_CHANGES.md     ← Pending changes for CC approval
│   ├── SOP_LIBRARY.md          ← Standard Operating Procedures
│   ├── PROMPT_LIBRARY.md       ← Reusable prompt templates
│   └── LEAD_TRACKER.csv        ← Sales lead tracking
│
├── .agents/                    ← Antigravity IDE workflows
│   ├── workflows/              ← /command workflows (11 workflows)
│   │   ├── client-onboard.md   ← /client-onboard — new client setup
│   │   ├── commit.md           ← /commit — smart git commit
│   │   ├── content.md          ← /content — brand content creation
│   │   ├── debug.md            ← /debug — systematic debugging
│   │   ├── health.md           ← /health — full system diagnostic
│   │   ├── n8n.md              ← /n8n — workflow management
│   │   ├── post.md             ← /post — social media posting
│   │   ├── prime.md            ← /prime — load full context
│   │   ├── research.md         ← /research — web research
│   │   ├── status.md           ← /status — project status
│   │   └── sync.md             ← /sync — end-of-session sync
│   └── plans/                  ← Implementation plans
│
├── commands/                   ← Claude Code slash commands (21 commands)
│
├── agents/                     ← Sub-agent role definitions (14 agents)
│   ├── architect.md            ← System design (Opus)
│   ├── chief-of-staff.md       ← Communication & mission control
│   ├── content-creator.md      ← Content & copywriting
│   ├── debugger.md             ← Bug investigation
│   ├── documenter.md           ← Documentation maintenance
│   ├── explorer.md             ← Codebase navigation
│   ├── git-ops.md              ← Version control
│   ├── researcher.md           ← Market & doc intel
│   ├── revenue-hunter.md       ← Sales & growth strategy
│   ├── reviewer.md             ← Code quality & security
│   ├── social-publisher.md     ← Late API posting
│   ├── video-editor.md         ← Media production pipeline
│   ├── workflow-builder.md     ← n8n automation
│   └── writer.md               ← Code implementation (TDD)
│
├── scripts/                    ← MCP wrapper scripts & utilities
│   ├── n8n-mcp-wrapper.cmd     ← n8n MCP launcher (reads .env.agents)
│   ├── late-mcp-wrapper.cmd    ← Late MCP launcher (reads .env.agents)
│   ├── late_mcp_patched.py     ← Patched Late SDK server (fixes Pydantic bugs)
│   ├── edit_content.py         ← Video pipeline (FFmpeg, Whisper, ElevenLabs)
│   └── [other utilities]       ← Email, outreach, calendar scripts
│
├── skills/                     ← 49 skills library (READ-ONLY)
│   ├── systematic-debugging/   ← 4-phase root cause debugging
│   ├── self-healing/           ← Auto-recovery patterns
│   ├── test-driven-development/← TDD workflow (RED → GREEN → REFACTOR)
│   ├── browser-automation/     ← Playwright web automation
│   ├── e2e-testing/            ← End-to-end testing
│   ├── writing-plans/          ← Implementation planning
│   ├── executing-plans/        ← Batch execution with checkpoints
│   ├── security-protocol/      ← Credential management rules
│   ├── mcp-operations/         ← MCP server management
│   ├── memory-management/      ← Knowledge graph operations
│   └── [31 more]               ← See skills/ directory
│
├── APPS_CONTEXT/               ← Per-business context files
│   ├── OASIS_AI_CLAUDE.md      ← OASIS AI Solutions
│   ├── PROPFLOW_CLAUDE.md      ← PropFlow SaaS
│   ├── NOSTALGIC_REQUESTS_CLAUDE.md ← Nostalgic Requests
│   ├── CONTENT_BRAND_CLAUDE.md ← CC's personal brand
│   ├── AI_TRAINING_CLAUDE.md   ← AI Training business
│   └── OASIS_WORKFLOWS.md      ← OASIS n8n workflow docs
│
├── database/                   ← SQL schemas
│   ├── 001_bravo_agent_schema.sql  ← Agent intelligence tables
│   └── 002_interaction_traces_schema.sql ← Interaction logging
│
├── media/                      ← Media assets
│   ├── assets/                 ← Logos, branding (tracked)
│   ├── raw/                    ← Input media (gitignored)
│   └── exports/                ← Output media (gitignored)
│
├── telegram_agent.js           ← Telegram bridge (V6.0) — routes to Gemini/Claude CLI
├── .gemini/settings.json       ← Gemini CLI MCP config (uses wrappers)
├── .claude/mcp.json            ← Claude Code MCP config (gitignored — has keys)
├── .vscode/mcp.json            ← Antigravity IDE MCP config
├── .env.agents                 ← All credentials (gitignored — NEVER commit)
└── .env.agents.template        ← Template showing required env vars (safe to commit)
```

---

## MCP Servers (6 Active)

| Server | Tools | Purpose | Status |
|--------|-------|---------|--------|
| **n8n-mcp** | 15+ | Workflow automation (44+ workflows) | ✅ Active |
| **Late** | 19 | Social media posting (8 platforms) | ✅ Active |
| **Playwright** | 22 | Browser automation, web research | ✅ Active |
| **Context7** | 2 | Live library documentation | ✅ Active |
| **Memory** | 8 | Knowledge graph persistence | ✅ Active |
| **Sequential Thinking** | 1 | Structured reasoning | ✅ Active |

**Offline (reconfigure later):** Supabase, Stripe

### MCP Config Locations

| File | Used By | Contains Keys? |
|------|---------|----------------|
| `.gemini/settings.json` | Gemini CLI | ❌ Uses wrapper scripts |
| `.claude/mcp.json` | Claude Code | ⚠️ Yes — gitignored |
| `.vscode/mcp.json` | Antigravity IDE | ⚠️ Yes — gitignored |
| `scripts/n8n-mcp-wrapper.cmd` | Gemini CLI, Antigravity | ❌ Reads from .env.agents |
| `scripts/late-mcp-wrapper.cmd` | Gemini CLI, Antigravity | ❌ Reads from .env.agents |

### Windows MCP Note

On Windows, MCP hosts don't always pass `env` block variables to subprocesses. The wrapper `.cmd` scripts fix this by reading `.env.agents` and setting vars before launching the MCP server.

---

## Cross-Agent Compatibility

All four agent environments (Antigravity, Claude Code, Gemini CLI, BlackBox) share:

1. **Same brain** → `brain/SOUL.md`, `brain/STATE.md`, `brain/CAPABILITIES.md`, `brain/AGENTS.md`
2. **Same memory** → `memory/ACTIVE_TASKS.md`, `memory/SESSION_LOG.md`, `memory/PATTERNS.md`
3. **Same skills** → `skills/` directory (49 skills)
4. **Same credentials** → `.env.agents` (never committed)
5. **Same MCP servers** → n8n, Late, Playwright, Context7, Memory, Sequential Thinking

Each agent entry file contains the same rules tailored to that environment's capabilities.

---

## Quick Start

1. Agent reads its entry file (`ANTIGRAVITY.md` / `CLAUDE.md` / `GEMINI.md` / `BLACKBOX.md`)
2. Silently loads `brain/SOUL.md` + `brain/STATE.md`
3. CC gives a task → agent routes to MCP tools via entry point routing table
4. Complex tasks → consults `brain/AGENTS.md` for subagent delegation
5. For business-specific context → reads `APPS_CONTEXT/` and `skills/`
6. Session end → updates `brain/STATE.md`, `memory/ACTIVE_TASKS.md`, `memory/SESSION_LOG.md`

---

## Self-Improvement Loop

```
Every Session:
  ├── Mistakes → memory/MISTAKES.md (root cause + prevention)
  ├── Patterns → memory/PATTERNS.md (tag [PROBATIONARY])
  ├── Decisions → memory/DECISIONS.md (date + rationale)
  └── Reflections → memory/SELF_REFLECTIONS.md (Reflexion framework)

Every 3+ Sessions:
  └── [PROBATIONARY] patterns promoted to [VERIFIED] if consistently useful
```

---

## Credentials

All secrets live in `.env.agents` (gitignored). Copy `.env.agents.template` to get started.

**NEVER hardcode API keys in scripts or config files that get committed.**

---

*Bravo V5.5 — "Only good things from now on."*
