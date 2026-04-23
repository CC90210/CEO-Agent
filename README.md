# CEO Agent — Bravo

> **Bravo (CEO)** — strategy, clients, revenue, partnerships, vision. One third of a three-agent AI C-Suite running CC's business empire. Paired with **Atlas (CFO)** for finance + tax + wealth, and **Maven (CMO)** for brand + content + ads + funnels. Not a framework. Not a demo. A production system managing real revenue, real clients, and real automations across two machines, three AI interfaces, and 56 CLI tools.

Built by one person with AI. Running 24/7 since March 2026.

**The C-Suite:**
- 🏛️ **Bravo (CEO)** — this repo: [CC90210/CEO-Agent](https://github.com/CC90210/CEO-Agent)
- 💰 **Atlas (CFO)** — [CC90210/CFO-Agent](https://github.com/CC90210/CFO-Agent)
- 🎨 **Maven (CMO)** — [CC90210/CMO-Agent](https://github.com/CC90210/CMO-Agent)

See [`brain/C_SUITE_ARCHITECTURE.md`](brain/C_SUITE_ARCHITECTURE.md) for the governance, pulse protocol, and decision rights matrix.

---

## Quick Install (One Line)

**macOS / Linux / WSL:**
```bash
curl -sSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 | iex
```

That single line:
1. Checks for Python + Node + Git (prints the `winget` / `brew` / `apt` command if anything's missing)
2. Clones the repo to `~/bravo-repo`
3. Creates your `~/.bravo/` home directory
4. Puts a `bravo` command on your PATH
5. Launches the interactive setup wizard — it walks you through:
   - Which agent profile you want (Bravo, Atlas, Maven, Aura, Hermes, or custom)
   - Your Anthropic API key (required) and OpenAI key (optional)
   - Telegram bridge setup — paste your BotFather token, it validates live, auto-detects your chat_id, and sends you a test message
   - Optional: Stripe, Supabase, n8n
6. Runs `bravo doctor` to confirm everything works

After install:

```bash
bravo doctor            # full health check
bravo status            # live operational summary
bravo agent list        # see the 20 sub-agents
bravo sessions recent   # rewind past sessions
```

## What You Get

What you get after install:
- `bravo` on your PATH (launches from `bin/bravo` or `bin/bravo.cmd`)
- `~/.bravo/` home directory (config, profiles, sessions, logs, skills, cache)
- A populated `.env.template` (never reads or copies secrets)
- 73 CLI tools discoverable via `bravo tools`
- 148 skills discoverable via `bravo skills`
- 20 sub-agents discoverable via `bravo agent list`
- Full-text search over session history via `bravo sessions search <query>`
- Browser Harness integration with Chrome / Edge

## First Five Commands

```bash
bravo                    # Branded launch — status + quick help
bravo doctor             # Full health check (100-point audit)
bravo status             # One-screen operational summary
bravo agent list         # See the 20 sub-agents available
bravo sessions recent    # Rewind recent work across all sessions
```

## Forge a New Agent

Bravo's moat: it can scaffold a new agent in seconds, with identity, memory, safety, and a doctor command on day one.

```bash
bravo agent create Hermes --role "client commerce operations"
bravo agent doctor Hermes
```

See [`skills/agent-forge/SKILL.md`](skills/agent-forge/SKILL.md) for the full template contract.

## Browser Automation That Learns

Real logged-in browser control with a two-layer memory system (interaction skills + site-specific domain skills), CC-approval gates on writes, and the V5.6 outbound chokepoint preserved end-to-end.

```bash
bravo browser doctor           # Is Chrome attached?
bravo browser setup            # One-time Chrome remote-debug approval
bravo browser learn linkedin   # Scaffold a new domain skill
```

See [`browser/SAFETY.md`](browser/SAFETY.md) for the approval policy.

---

## What This Actually Does

This system replaced a team. It handles:

- **Lead capture and nurturing** -- funnel form submissions trigger instant Telegram alerts, automated welcome emails, and a Day 2 / Day 5 follow-up sequence. All fail-closed with 40 unit tests.
- **Community management** -- a Skool automation engine that replies to posts AND comments, detects when a member needs the founder's personal attention (crisis, hot leads, direct mentions), and escalates via Telegram instead of auto-replying. Crash-safe state persistence so a Playwright failure never causes a public double-reply.
- **Revenue tracking** -- Stripe sync, MRR calculation, client health scoring, pipeline reviews, and CEO briefings. All on scheduled cron jobs.
- **Inbound email triage** -- N8N workflow classifies every inbound Gmail into 4 categories (Client Tech Support / Business Opportunities / Financial & Legal / Low Priority) and hands off to the matching sub-agent for reply, labeling, or Telegram escalation.
- **Cross-machine orchestration** -- Windows desktop is the production server. MacBook is a cold-standby node. SSH passwordless control, PM2 process management, git-based session handoff protocol. One machine runs daemons, the other reads and edits. Never both.
- **Self-improvement** -- every session generates patterns, mistakes, and reflections. Patterns get tagged [PROBATIONARY] and promoted to [VALIDATED] after 3 successful uses. The system literally gets smarter over time.

Current MRR: $3,322. Goal: $5,000 by May 15, 2026.

---

## Architecture

```
Business-Empire-Agent/
|
|-- CLAUDE.md                    # Claude Code entry point (120 lines, 9 rules)
|-- GEMINI.md                    # Gemini CLI entry point
|-- ANTIGRAVITY.md               # VS Code / Antigravity IDE entry point
|-- ecosystem.config.js          # PM2 process management (platform-gated)
|
|-- brain/                       # Shared intelligence (read by all AI interfaces)
|   |-- SOUL.md                  # Identity and values (IMMUTABLE -- never self-edits)
|   |-- STATE.md                 # Live operational state (EPHEMERAL -- updates every session)
|   |-- AGENTS.md                # 17 agent definitions + routing matrix
|   |-- BRAIN_LOOP.md            # 10-step reasoning with multi-hypothesis + Reflexion
|   |-- CAPABILITIES.md          # Full tool inventory (56 scripts, 8 MCPs, 35 workflows)
|   |-- QUICK_REFERENCE.md       # Intent-to-tool routing table
|   |-- DAILY_SCHEDULE.md        # Founder's optimized daily structure + accountability
|   |-- CLIENT_READY.md          # Honest productization scorecard (15/100 currently)
|   |-- CROSS_MACHINE_SYNC.md    # Windows/Mac coordination protocol
|   +-- CREDENTIALS_SCAFFOLD.md  # Every env var documented (no secrets, safe to commit)
|
|-- memory/                      # Persistent memory across all sessions
|   |-- SESSION_LOG.md           # Cross-agent activity log (append-only)
|   |-- ACTIVE_TASKS.md          # Current sprint + 5-week roadmap
|   |-- ACTIVE_SESSION.json      # Which machine is live right now
|   |-- HANDOFF.md               # Session handoff notes for cross-machine continuity
|   |-- PATTERNS.md              # Proven approaches
|   |-- MISTAKES.md              # Root cause analysis
|   +-- SELF_REFLECTIONS.md      # Structured failure analysis (Reflexion framework)
|
|-- skills/                      # 152 skills (progressive 3-tier loading)
|   |-- hyperthink/              # Maximum-depth multi-hypothesis reasoning protocol
|   |-- sales-closing/           # LAER objection loop + 6 close techniques
|   |-- ethical-hacking/         # Authorized pentest methodology + secure-by-default coding
|   |-- skool-automation/        # Community management (V2.1 comment-tier + escalation)
|   +-- [147 more]
|
|-- scripts/                     # 56 Python CLI tools (all read .env.agents, never hardcode secrets)
|   |-- scheduler.py             # Cron job orchestrator (fail-closed, retry-on-error)
|   |-- skool_engine.py          # Skool community daemon (V2.1, 2500+ lines)
|   |-- revenue_engine.py        # MRR tracking, Stripe sync, forecasting
|   |-- funnel_sync.py           # CRM bridge with fast-poll mode (60s alert latency)
|   |-- funnel_nurture.py        # Day 2 / Day 5 email sequences with CASL compliance
|   |-- notify.py                # Human-readable Telegram alerts (V3 format)
|   |-- email_engine.py          # Gmail SMTP + IMAP with poison UID quarantine
|   |-- lead_engine.py           # CRM: scoring, pipeline, follow-ups
|   |-- stripe_tool.py           # Multi-account Stripe management
|   |-- supabase_tool.py         # Multi-project Supabase CRUD
|   |-- google_tool.py           # 7 Google Workspace services, 30+ commands
|   +-- [44 more]
|
|-- .agents/
|   |-- workflows/               # 35 slash commands (/commit, /ship, /close-review, etc.)
|   +-- plans/                   # Implementation plans
|
+-- .claude/
    +-- agents/                  # 6 native Claude Code subagents (architect, debugger, etc.)
```

---

## The Notification Pipeline

Every automation reports to the founder via Telegram. The notification system went through 3 major versions to get here:

**V1** (March 2026): Bracket-prefixed system dumps. `[REVENUE] Stripe sync complete. Inserted: 0. Skipped: 4.` Founder stopped reading them.

**V2** (April 2026): Fail-closed parsing. If a handler can't parse its output as JSON, it surfaces ERROR instead of silently succeeding. Prefix-based skip matching replaced dangerous substring matching (the word "ok" was matching inside "booking" and silencing real notifications). 40 unit tests.

**V3** (April 2026): Human-readable format. No brackets, no JSON, no military time. Clean category labels and 12-hour timestamps. Every notification passes the "3-second phone glance test."

```
Revenue
$800 payment from Bennett Agency

5:34 PM
```

Fail-closed means: if Stripe goes down, the founder knows immediately. If the email engine fails to send a nurture email, it surfaces as an error, not silence. Silent failures are treated as worse than loud failures.

---

## Cross-Machine Orchestration

Two machines, one brain, zero conflicts.

**Windows desktop** (always on): runs the scheduler, Skool daemon, Telegram bridge, and all cron jobs. This is the production server.

**MacBook** (portable): reads, edits, analyzes. Has the Telegram bridge registered in PM2 but stopped. Can take over Telegram when the founder is away from the desktop.

Coordination protocol:
- Every session starts with `bash scripts/bravo-session-start.sh` (pulls latest, claims session slot, reads handoff notes)
- Every session ends with `bash scripts/bravo-session-end.sh "what I did"` (commits, pushes, writes handoff for the next machine)
- `memory/ACTIVE_SESSION.json` declares which machine is live. Stale claims auto-expire after 30 minutes.
- SSH passwordless control: Windows can execute commands on Mac directly via `ssh cc-mac "command"`
- Platform-gated PM2: the scheduler literally cannot start on Mac (ecosystem.config.js checks `process.platform`)

---

## Skool Community Engine (V2.1)

An autonomous community manager for Skool that:

1. Scans the community feed every 5 minutes
2. Reads each post's full content + images (Claude vision)
3. Web-searches specific tools and products mentioned before replying (no generic advice)
4. Generates a reply in the founder's coaching voice
5. Detects 38 escalation signals (crisis, hot leads, direct mentions, refund requests) and pings Telegram instead of auto-replying
6. Scans comments on every post and replies to other members
7. When the founder has already top-level commented, Bravo's comment replies are forced brief (max 180 chars, "supportive second voice" mode)
8. Persists state after every public action (crash-safe, no double-replies)
9. Prunes stale state entries older than 30 days

2,600 lines of Python. Runs as a standalone daemon with its own file-based exclusive lock.

---

## CLI Tools (56 Scripts)

Every script follows the same pattern: read `.env.agents` for credentials, accept `--json` for machine consumption, support `--help` for discovery. No hardcoded secrets, ever.

| Category | Scripts | Purpose |
|----------|---------|---------|
| Revenue and Finance | `revenue_engine.py`, `stripe_tool.py`, `financial_model.py`, `ceo_dashboard.py` | MRR tracking, Stripe sync, forecasting, CEO briefings |
| Sales and CRM | `lead_engine.py`, `client_health.py`, `proposal_generator.py`, `competitive_intel.py` | Lead scoring, pipeline, health reports, battlecards |
| Email and Outreach | `email_engine.py`, `funnel_nurture.py`, `funnel_sync.py`, `outreach_engine.py` | Gmail SMTP/IMAP, nurture sequences, CRM bridge |
| Community Management | `skool_engine.py` | Skool community daemon (2,600 lines, V2.1) |
| Infrastructure | `supabase_tool.py`, `n8n_tool.py`, `google_tool.py`, `firecrawl_tool.py` | Database, workflows, Google Workspace, web scraping |
| System | `scheduler.py`, `notify.py`, `cron_engine.py`, `cost_tracker.py`, `mem0_tool.py` | Cron orchestration, alerts, cost tracking, semantic memory |

---

## Browser Harness Layer

Bravo now has Browser Harness installed as the direct logged-in browser layer:

- Checkout: `C:\Users\User\APPS\browser-harness`
- Skill: `skills/browser-harness/SKILL.md`
- Domain memory: `browser/domain-skills/`
- Interaction memory: `browser/interaction-skills/`
- Diagnostics: `python scripts/browser_harness_doctor.py`
- Full onboarding doctor: `python scripts/onboarding_diagnostics.py`

Use this when a task needs authenticated UI control, screenshots, browser-only workflows, or reusable site knowledge. Business actions remain gated: outbound goes through `scripts/send_gateway.py`, and any send/publish/delete/billing/finance/admin/production click requires explicit approval.

---

## Scheduler (Fail-Closed Architecture)

10 active cron jobs, all verified against real services with 9/9 handler tests passing.

| Schedule | Job | What the Founder Sees |
|----------|-----|----------------------|
| Every 1 min | Funnel Fast-Poll | Telegram alert within 60 seconds of a new form submission |
| Every 5 min | Funnel Lead Sync | Backstop sync (silent unless new leads) |
| Every 5 min | Email Inbox Monitor | Telegram alert for real emails (spam auto-filtered) |
| 6:00 AM | Stripe Revenue Sync | Silent unless new revenue events |
| 8:00 AM | Lead Follow-up Check | Telegram if follow-ups are overdue |
| 10:00 AM | Nurture Sequence | Silent unless Day-2 or Day-5 email sent |
| 6:00 PM | Booking Reminders | Telegram if meetings scheduled tomorrow |
| Monday 9 AM | Weekly MRR Report | Revenue dashboard summary |
| Monday 10 AM | Pipeline Review | Lead scoring and pipeline status |
| 1st of month | Monthly Snapshot | MRR trend and client metrics |

Every handler uses fail-closed parsing: non-JSON output, subprocess errors, and top-level error fields all surface as ERROR with Telegram notification. Zero silent failures. If Stripe is down, the founder knows. If email SMTP fails, the founder knows. Jobs that error retry in 5 minutes instead of waiting 24 hours for the next scheduled slot.

---

## Self-Improvement Loop

```
Session completes
  |
  +-- Did anything fail or get corrected?
  |     YES --> memory/MISTAKES.md (root cause + 1-line prevention)
  |
  +-- Was this approach new or non-obvious?
  |     YES --> memory/PATTERNS.md [PROBATIONARY]
  |               |
  |               +-- Used successfully 3 more times?
  |                     YES --> Promote to [VALIDATED]
  |
  +-- Did the user express a preference or correction?
        YES --> Save WHY, not just WHAT (highest-value signal)
```

The iron law: the user never teaches the same lesson twice.

---

## MCP Servers (8 Active)

| Server | Purpose |
|--------|---------|
| Playwright | Browser automation, web testing, screenshot evidence |
| Context7 | Live library documentation for any framework |
| Memory | Persistent knowledge graph across sessions |
| Sequential Thinking | Multi-step structured reasoning |
| GitHub | PR/issue/repo management |
| Firecrawl | Web scraping and structured data extraction |
| Filesystem | Cross-directory file access |
| Knowledge Graph | Obsidian vault queries (PageRank, communities, paths) |

CLI-first architecture: services requiring API credentials use Python CLI tools that read `.env.agents` at runtime. No credentials in config files. Wrapper scripts (`.cmd`) inject env vars for MCP servers that need them.

---

## Quick Start

```bash
# Clone
git clone https://github.com/CC90210/CEO-Agent.git
cd business-empire-agent

# Set up credentials (see brain/CREDENTIALS_SCAFFOLD.md for the full list)
cp brain/CREDENTIALS_SCAFFOLD.md .env.agents  # Use as reference, fill in real values
# At minimum: ANTHROPIC_API_KEY, BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY,
# TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS

# Install Python dependencies
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Install Node dependencies (for telegram bridge + MCP servers)
npm install

# Check next-gen onboarding + browser infrastructure
python scripts/onboarding_diagnostics.py
python scripts/browser_harness_doctor.py

# Start with any AI interface
# Claude Code reads CLAUDE.md automatically
# Gemini CLI reads GEMINI.md
# VS Code / Antigravity reads ANTIGRAVITY.md
```

The agent loads silently, routes your task to the right specialist, and starts working. Session state saves automatically so any AI interface can pick up where the last one left off.

---

## Numbers

| Metric | Value |
|--------|-------|
| Skills | 152 |
| CLI scripts | 56 |
| Workflows | 35 |
| Agents | 17 (+ 6 native Claude Code subagents) |
| MCP servers | 8 |
| Cron jobs | 10 active |
| Unit tests (notification pipeline) | 40/40 passing |
| Handler tests (scheduler) | 9/9 passing |
| Lines of Python (skool_engine alone) | 2,600+ |
| Supabase tables | 28 |
| Cross-machine sync | 2 machines, passwordless SSH, PM2-managed |

---

## Contributing

The architecture is modular. Fork it and make it yours.

- **Add an agent:** create `.claude/agents/your-agent.md` with a system prompt
- **Add a skill:** create `skills/your-skill/SKILL.md` with YAML frontmatter (name, description, triggers)
- **Add a workflow:** create `.agents/workflows/your-command.md`
- **Add a CLI tool:** create `scripts/your_tool.py` following the pattern in `scripts/cli_templates/`
- **Tune behavior:** edit `.agents/config.toml` (all thresholds are configurable)

---

## License

MIT

---

*Built by one person with Claude Code, Gemini CLI, and the belief that AI should multiply human ambition, not replace it.*
