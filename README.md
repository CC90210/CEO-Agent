# Business Empire Agent — BRAVO V5.5

> Autonomous AI operations hub for CC's business empire. Manages codebases, deployments, content pipelines, and business operations across OASIS AI Solutions, PropFlow, and Nostalgic Requests.

---

## What This Is

A self-evolving AI agent system that runs across 3 interfaces (Claude Code, Gemini CLI, Antigravity IDE) with shared intelligence, 55 skills, 16 agents, 15 workflows, and 8 MCP servers. Every interface sees the same brain, memory, and capabilities.

**North Star:** $1,000 Net MRR by March 31, 2026 (Goal Exceeded — ~$2,691 MRR)

---

## Agent Entry Points

| Agent / Environment | Entry File | Role |
|---|---|---|
| **Claude Code CLI** | `CLAUDE.md` | Lead Architect — complex refactoring, debugging, system evolution |
| **Antigravity IDE** (VS Code) | `ANTIGRAVITY.md` | Infantry/Architect Hybrid — broadest MCP tool access |
| **Gemini CLI** | `GEMINI.md` | Inference Engine — fast queries, diagnostics, content |

All entry files share the same `brain/`, `memory/`, and `skills/` system.

---

## Architecture

```
Business-Empire-Agent/
│
├── CLAUDE.md / GEMINI.md / ANTIGRAVITY.md   ← Agent entry points (one per interface)
│
├── brain/                      ← Agent intelligence (shared, always loaded)
│   ├── SOUL.md                 ← Identity & values (IMMUTABLE)
│   ├── STATE.md                ← Live operational state
│   ├── AGENTS.md               ← 16 subagents + orchestration matrix
│   ├── USER.md                 ← CC's profile & preferences
│   ├── APP_REGISTRY.md         ← 8 external app repos with routing
│   ├── CAPABILITIES.md         ← Full tool & integration inventory
│   ├── BRAIN_LOOP.md           ← 10-step reasoning protocol (multi-hypothesis + Reflexion)
│   ├── INTERACTION_PROTOCOL.md ← Logging tiers & session governance
│   ├── HEARTBEAT.md            ← Proactive health monitoring
│   ├── GROWTH.md               ← Voyager-style skill evolution
│   └── CHANGELOG.md            ← Self-modification audit trail
│
├── memory/                     ← Persistent memory across all sessions & agents
│   ├── SESSION_LOG.md          ← What happened (all agents write here)
│   ├── ACTIVE_TASKS.md         ← Current work in progress
│   ├── PATTERNS.md             ← Proven approaches ([PROBATIONARY] → [VALIDATED])
│   ├── MISTAKES.md             ← Root cause analysis & prevention
│   ├── DECISIONS.md            ← Architectural decision log
│   ├── LONG_TERM.md            ← Verified persistent knowledge
│   ├── SELF_REFLECTIONS.md     ← Structured failure analysis (Reflexion framework)
│   ├── SOP_LIBRARY.md          ← Standard Operating Procedures
│   └── content-strategy.md     ← Content Bible (3 daily pillars, hook bank)
│
├── agents/                     ← 16 subagent role definitions
│   ├── architect.md            ← System design (Opus tier)
│   ├── meta-agent.md           ← Generates new agents from descriptions [PROBATIONARY]
│   ├── writer.md               ← Code implementation (TDD)
│   ├── debugger.md             ← Root cause analysis
│   ├── reviewer.md             ← Code quality & security audit
│   ├── researcher.md           ← Market & documentation intel (Playwright)
│   ├── content-creator.md      ← Brand voice & copywriting
│   ├── chief-of-staff.md       ← Communication & mission control
│   ├── revenue-hunter.md       ← Sales strategy & lead nurturing
│   ├── workflow-builder.md     ← n8n automation creation
│   ├── video-editor.md         ← FFmpeg + Whisper + ElevenLabs pipeline
│   ├── social-publisher.md     ← Late API multi-platform posting
│   ├── git-ops.md              ← Version control & PR management
│   ├── documenter.md           ← Documentation maintenance
│   └── explorer.md             ← Codebase navigation (read-only)
│
├── skills/                     ← 55 skills (progressive 3-tier loading)
│   ├── SKILL_LOADING.md        ← Loading protocol (frontmatter → instructions → references)
│   ├── systematic-debugging/   ← 4-phase root cause debugging
│   ├── self-healing/           ← 5-dimension auto-recovery
│   ├── test-driven-development/← RED → GREEN → REFACTOR
│   ├── browser-automation/     ← Playwright MCP reference
│   ├── e2e-testing/            ← Parallel 3-agent E2E with DB validation
│   ├── code-review/            ← Quality & security audit
│   ├── ship/                   ← Production deployment checklist
│   ├── retro/                  ← Post-session retrospective + insights-to-rules pipeline
│   ├── cli-anything/           ← Generate CLI wrappers for any software/API
│   ├── skool-automation/       ← Skool course editing via Playwright
│   ├── memory-management/      ← Five-Gate Knowledge Filter + confidence scoring
│   ├── writing-plans/          ← Implementation plan generation
│   ├── executing-plans/        ← Batch execution with review checkpoints
│   └── [41 more skills]        ← See skills/ directory for full list
│
├── .agents/                    ← Antigravity IDE workflows
│   ├── workflows/              ← 15 slash commands (/commit, /post, /evolve, etc.)
│   └── plans/                  ← Implementation plans
│
├── scripts/                    ← MCP wrappers & utilities
│   ├── *-mcp-wrapper.cmd       ← 4 credential-injecting MCP launchers
│   ├── supabase_tool.py        ← Supabase SDK CLI (full CRUD, 3 projects)
│   ├── stripe_tool.py          ← Stripe SDK CLI (balance, customers, invoices)
│   ├── edit_content.py         ← Video pipeline (FFmpeg 8.0.1, Whisper, ElevenLabs)
│   └── cli_templates/          ← Reusable CLI-Anything templates
│
├── courses/                    ← Skool course registry (16 courses, 62 lessons)
│   └── SKOOL_REGISTRY.md       ← Full URL mapping for Skool automation
│
├── database/                   ← SQL schemas (14 tables across 3 Supabase projects)
│   ├── 001_bravo_agent_schema.sql
│   └── 002_interaction_traces_schema.sql
│
├── docs/                       ← Guides & documentation
│   └── MOBILE_TERMINAL.md      ← Claude Code from phone (Tailscale + SSH)
│
├── media/                      ← Media assets (raw/ and exports/ gitignored)
├── telegram_agent.js           ← Telegram bridge (V8.0 — user ID firewall, PM2)
├── .env.agents                 ← All credentials (gitignored — NEVER commit)
└── .env.agents.template        ← Required env vars template
```

---

## MCP Servers (8 Active)

| Server | Purpose | Status |
|--------|---------|--------|
| **Supabase** | Database queries, migrations, schema management (3 projects) | ✅ Active |
| **Stripe** | Payments, subscriptions, invoices (SDK fallback for broken MCP) | ✅ Active |
| **n8n-mcp** | Workflow automation (44+ workflows via REST API) | ✅ Active |
| **Late** | Social media posting (8 connected accounts) | ✅ Active |
| **Playwright** | Browser automation, web research, E2E testing | ✅ Active |
| **Context7** | Live library documentation lookup | ✅ Active |
| **Memory** | Persistent knowledge graph across sessions | ✅ Active |
| **Sequential Thinking** | Structured multi-step reasoning | ✅ Active |

**Security:** All credential-sensitive servers use `cmd /c scripts/*-mcp-wrapper.cmd` wrappers that read from `.env.agents` at runtime. Zero hardcoded keys in any config file.

### MCP Config Locations

| File | Used By |
|------|---------|
| `.claude/mcp.json` | Claude Code CLI |
| `.vscode/mcp.json` | Antigravity IDE |
| `~/.gemini/settings.json` | Gemini CLI |
| `.env.agents` | Credentials only (all wrappers read from here) |

---

## Key Features

### 10 Advanced Patterns
1. **Five-Gate Knowledge Filter** — VALUE → ALIGNMENT → REDUNDANCY → FRESHNESS → PLACEMENT
2. **Exponential Confidence Decay** — C(t) = C0 x e^(-lambda x t), category-specific rates
3. **Meta-Agent** — Generates new subagent definitions from natural language
4. **`/evolve` Command** — Extracts session patterns → promotes to skills/SOPs/rules
5. **Progressive Skill Loading** — 3-tier: frontmatter (always) → instructions (activation) → references (on-demand)
6. **Surgical Changes** — Every edit touches ONLY what was requested
7. **Insights-to-Rules Pipeline** — Pattern extraction → rule drafting → hook consideration → integration
8. **Boil the Lake** — Always recommend the COMPLETE implementation when AI makes cost near-zero
9. **Fix-First** — Auto-fix mechanical issues, ASK for judgment calls
10. **Dual Effort Estimation** — Show human-team time vs CC+Bravo time for every task

### Cross-AI Sync (Rule 0)
All 3 agents write to the same `brain/STATE.md`, `memory/SESSION_LOG.md`, and `memory/ACTIVE_TASKS.md`. Switch between Claude, Gemini, or Antigravity mid-task with zero context loss.

### Self-Improvement Loop
```
Every Session:
  ├── Mistakes → memory/MISTAKES.md (root cause + prevention)
  ├── Patterns → memory/PATTERNS.md ([PROBATIONARY] → [VALIDATED] after 3 sessions)
  ├── Decisions → memory/DECISIONS.md (date + rationale)
  └── Reflections → memory/SELF_REFLECTIONS.md (Reflexion framework)
```

### Mobile Access
Claude Code from your phone via Tailscale + SSH. See `docs/MOBILE_TERMINAL.md`.

---

## App Registry (8 External Repos)

Code for each app lives in its own repo. Business-Empire-Agent is ONLY for agent intelligence.

| App | Stack | Status |
|-----|-------|--------|
| **TIKTIK** | Next.js 14, Supabase, face-api.js | ✅ Live (facial recognition + IP camera ready) |
| **OASIS AI Platform** | React 18, Vite, Supabase | ✅ Active |
| **PropFlow** | Next.js 14, Supabase, Stripe | ✅ Active |
| **Nostalgic Requests** | Next.js, Supabase, Stripe Connect | ✅ Active |
| **Grape Vine Cottage** | Vite, React 18 | ✅ Active |
| **Mindset Companion** | Next.js 16, React 19 | ✅ Active |
| **On The Hill** | Vite, React 19 | ✅ Active |
| **Atlas Trading Agent** | Python 3.11+, CCXT, Claude API | ✅ Active |

Full routing table with local paths: `brain/APP_REGISTRY.md`

---

## Quick Start

1. Copy `.env.agents.template` → `.env.agents` and fill in credentials
2. Agent reads its entry file (`CLAUDE.md` / `GEMINI.md` / `ANTIGRAVITY.md`)
3. Brain loads silently (`brain/SOUL.md` + `brain/STATE.md`)
4. CC gives a task → agent routes to MCP tools or delegates to subagents
5. Session end → state files updated, learnings captured, git committed

---

## Credentials

All secrets live in `.env.agents` (gitignored). **NEVER hardcode API keys in scripts or config files.**

---

*Bravo V5.5 — "Only good things from now on."*
