# Bravo Playbook — How to Actually Use Your System

> **For CC, not engineers.** If you're reading this looking for SQL schemas
> or API signatures, go to [ARCHITECTURE.md](ARCHITECTURE.md) or
> [brain/CAPABILITIES.md](brain/CAPABILITIES.md) — this document is
> deliberately non-technical.
>
> **Promise:** every section here tells you what something is in plain
> English, what question it answers, and the one command (or chat
> prompt) to access it.

---

## If you only read one page: the top 5 moves

These are the five things you'll actually do 80% of days. Bookmark this section.

| What you want | Just say this | What actually happens |
|---|---|---|
| **See what the AI did today** | "show me today's activity" (Telegram or IDE) — or: `python scripts/autonomous_agent.py decisions --today` | Prints the reasoning loop's decision tape: every send, every escalation, every lead it touched, with the *why* |
| **Check if anything needs your attention right now** | "what's pending?" — or: `python scripts/autonomous_agent.py status` | Shows the agent's current state snapshot + any escalations waiting for you |
| **Trigger the reasoning loop on demand** | `python scripts/autonomous_agent.py tick` | One cycle of the brain loop. Prints plain-English summary. |
| **See your MRR / pipeline / revenue right now** | "what's my pipeline?" — or: `python scripts/ceo_dashboard.py briefing` | The CEO briefing: MRR, pipeline counts by stage, #1 priority |
| **Ask a general business question** | Just ask in Telegram or IDE — plain English | The agent routes to the right tool and answers in plain English. You don't need to know which tool. |

**Rule of thumb:** if you're typing more than one command, you're doing it the hard way. Ask in English, let Bravo route.

---

## The brain family — who does what

You have four AI agents, each with a job. They share state through the `brain/` and `memory/` directories and coordinate via `data/pulse/*.json` files. You don't have to remember this — just know who owns what:

| Agent | What it is | Lives at | Example question |
|---|---|---|---|
| **Bravo** | Lead architect + business ops + content voice. This is you, talking to Claude Code. | this repo | "draft me a proposal," "what closes this deal?" |
| **Codex** | Backend executor. Ugly implementation work, deep debugging, adversarial code review. | this repo (Codex extension / CLI) | "why is this error firing?" "find the bug in this function" |
| **Atlas** | CFO. Finance, tax, trading, budget, wealth tracking. | `C:\Users\User\APPS\CFO-Agent` | "how much runway do I have?" "what's the CRA hit on this?" |
| **Maven** | CMO. Content production, paid ads, funnels, brand. | `C:\Users\User\CMO-Agent` | "write 3 variants for this hook," "audit my ad spend" |
| **Aura** | Life/home agent. Raspberry Pi, voice, habits, smart home. | `C:\Users\User\AURA` | "what's the apartment temperature?" "remind me to hydrate" |

When you open a project folder in your IDE, the agent that loads is whichever one lives there. Bravo lives here.

---

## How to talk to Bravo — three doors

You have three entry points. Use whichever feels right. All three share the same state, so what you say in one is visible to the others within seconds.

### Door 1: Claude Code (IDE) — the deep-work door

- Best for: multi-step builds, architecture decisions, code edits, long threads
- How to use: open this repo folder in Claude Code, start chatting
- What loads automatically: `CLAUDE.md` → `brain/SOUL.md` → `brain/STATE.md` → `memory/ACTIVE_TASKS.md`
- Bravo introduces itself as "Bravo, CC's lead architect"

### Door 2: Telegram bridge — the phone-and-remote door

- Best for: asking questions on the go, approving outbounds, quick status checks
- How to use: message `@YourBot` in Telegram (already set up; runs on PM2)
- What it can do: every Python tool in `scripts/` is reachable. Natural-language requests get routed.
- What's live right now: Telegram approval buttons for outreach batches, status checks, command passthrough

### Door 3: Codex (IDE extension) — the backend door

- Best for: deep backend work you want handed off while Bravo does something else
- How to use: open the Codex pane in your IDE, start chatting
- What loads: `AGENTS.md` → same brain files as Bravo
- Codex introduces itself as "Codex, backend executor in CC's empire" — if it introduces itself generically, `AGENTS.md` isn't being read; tell Bravo and we'll fix.

---

## What Bravo can do — by the question you'd actually ask

Organized by the question, not the tool. The tool names are in italics so you can ignore them if you want.

### Revenue & finance

| Question | Answer |
|---|---|
| "What's my MRR?" | *`revenue_engine.py mrr`* |
| "Show me all revenue events this month" | *`revenue_engine.py dashboard`* |
| "Sync Stripe to my DB" | *`revenue_engine.py sync-stripe`* |
| "What's my Stripe balance?" | *`stripe_tool.py balance`* |
| "Can I afford [thing]?" / "runway?" | ask Atlas (`C:\Users\User\APPS\CFO-Agent`) |

### Leads, pipeline, CRM

| Question | Answer |
|---|---|
| "Who do I need to follow up with?" | *`lead_engine.py followups`* |
| "Show me my pipeline" | *`lead_engine.py pipeline`* |
| "Add a new lead" | *`lead_engine.py add "Name" --email ... --company ...`* |
| "What's my relationship with Jane at Acme?" | *`context_builder.py show --email jane@acme.com`* — gives you relationship stage, sentiment, last touch |
| "Import leads from CSV" | *`lead_engine.py bulk-import`* |

### Outbound (emails, DMs, calls)

| Question | Answer |
|---|---|
| "Send a cold email to this new lead" | *`outreach_engine.py send --lead-id ...`* — drafts + sends through the gateway, CASL-compliant |
| "Start a batch of cold emails for me to approve" | *`outreach_batch.py --limit 5`* — you approve each via Telegram |
| "Send this one-off email" | *`email_engine.py send --to ... --subject ... --body ...`* |
| "Is it safe to email this lead right now?" | *`send_gateway.py can-act --lead-id ... --channel email`* |
| "How many outbounds today?" | *`send_gateway.py stats`* |

### The reasoning loop (the always-on brain)

| Question | Answer |
|---|---|
| "Run one thinking cycle" | *`autonomous_agent.py tick`* |
| "What did the agent decide today?" | *`autonomous_agent.py decisions --today`* |
| "Show me the last tick's state" | *`autonomous_agent.py status`* |
| "Run it in shadow mode" (no real sends) | *`autonomous_agent.py tick --shadow`* |
| "Run it every 15 min in background" | *`autonomous_agent.py daemon --interval 900`* |

### Content, scheduling, social

| Question | Answer |
|---|---|
| "Schedule a post" | *`late_tool.py create`* (will reroute to a paid plan when you upgrade) |
| "Run the content pipeline on this video" | *`content_pipeline.py process`* |
| "Plan next week's content" | *`content_engine.py week-plan`* |
| "Check my Instagram DMs" | *`instagram_engine.py check-dms`* |
| "Manage the Skool community" | *`skool_engine.py`* (runs as daemon) |

### Calendar, email inbox, Google Workspace

| Question | Answer |
|---|---|
| "What's on my calendar today?" | *`google_tool.py calendar list`* |
| "Book a meeting" | *`google_tool.py calendar create --title ... --start ... --end ... --meet`* |
| "Check my inbox" | *`google_tool.py gmail list`* — or *`email_engine.py check-inbox`* if you want IMAP + logging |
| "Create a Google Doc" | *`google_tool.py docs create`* |

### Database & infrastructure (rarely direct)

| Question | Answer |
|---|---|
| "Query my Supabase" | *`supabase_tool.py select <table>`* |
| "Run a SQL migration" | *`apply_migration.py database/NNN_...sql`* |
| "List all my n8n workflows" | *`n8n_tool.py list`* |
| "Scrape this URL" | Firecrawl MCP (ask in IDE) |

---

## V6 Apex background daemons — what must be running 24/7

After V6 Apex (2026-05-10) + OASIS Town Phase 3 (2026-05-11) shipped, three daemons need to be alive on your machine. PM2 keeps them up across reboots.

| Daemon | What it does | Without it |
|---|---|---|
| **event-router** | Reads every new `agent_events` row, projects it to `state/event_router.log`. Powers the `/feed` page on the Vercel dashboard. | Dashboard feed shows stale data. No on-host event-bus audit log. |
| **override-consumer** | Polls Supabase for dashboard Approve/Deny clicks on blocked commands. Applies them locally with HMAC. | Dashboard `/overrides` page can record decisions but the agent never sees them — you'd have to fall back to CLI `python scripts/exec_override.py approve <req-id>` (TTY-only). |
| **oasis-embed** | FastAPI on `localhost:8767` that exposes Bravo's FTS5+LanceDB retrieval to the OASIS Town Convex backend. Provides `/embed` (384-dim fastembed MiniLM) and `/query` (hybrid RRF retrieval over `memory/`, `skills/`, `brain/`). | OASIS Town's agent memory falls back to zero-vector stubs — agents still talk but lose live empire-state context (no more "Archive has three validated cases in memory/X.md" style references). |

### One-time setup

Run these once. They register the daemons with PM2 and persist across reboot:

```bash
cd /c/Users/User/Business-Empire-Agent

pm2 start scripts/event_router.py \
  --name event-router \
  --interpreter python \
  -- loop --interval 3

pm2 start scripts/exec_override_consumer.py \
  --name override-consumer \
  --interpreter python \
  -- loop --interval 5

pm2 start scripts/oasis_embed_server.py \
  --name oasis-embed \
  --interpreter python

pm2 save                # persist the process list to disk
# If PM2 startup isn't already registered for boot:
pm2 startup             # follow the printed instructions (one elevated command)
```

### Day-to-day operations

```bash
pm2 status              # list all PM2 processes; both should show "online"
pm2 logs event-router         --lines 50
pm2 logs override-consumer    --lines 50
pm2 restart event-router      # after editing scripts/event_router.py
pm2 restart override-consumer # after editing scripts/exec_override_consumer.py
pm2 stop  event-router        # temporary halt; pm2 start brings it back
pm2 delete event-router       # remove from PM2 entirely (rarely needed)
```

### Sanity checks

If something feels off:

```bash
# event-router heartbeat — last line of the log should be recent (<5s)
python scripts/event_router.py tail --count 5

# override-consumer — apply any pending dashboard intent in one shot
python scripts/exec_override_consumer.py once --verbose

# Are the daemons actually polling? Check PM2 uptime + restart count
pm2 status
```

If `pm2 status` shows either daemon `errored` or stuck restarting:

```bash
pm2 logs <name> --lines 100   # find the stack trace
pm2 restart <name>            # often a transient Supabase blip; this is enough
```

Both daemons are designed to fail open — if Supabase is unreachable, they log and retry; they never crash the local state DB.

## When things feel stuck — troubleshooting

Three things that will happen and how to unstick each.

### "Fresh Claude Code chat doesn't know what I'm working on"

**Why**: Claude reads `CLAUDE.md` → `brain/STATE.md` → `memory/ACTIVE_TASKS.md` at session start. If any of those are stale, context is stale.

**Fix**: ask "read the brain — what's our current state?" — forces a re-read. If that doesn't help, run `python scripts/state_sync.py --heartbeat` to refresh the timestamp, then restart the chat.

### "Codex introduces itself as generic 'Codex', not Bravo-aware"

**Why**: `AGENTS.md` at the repo root isn't being read by the Codex config. This file was added 2026-04-20.

**Fix**: tell Bravo "Codex isn't reading AGENTS.md." We'll add a `CODEX.md` pointer or `.codex/config.toml` (2-minute fix).

### "The AI did something weird and I don't trust it right now"

**Reset switches, in order of severity:**

1. **Shadow mode** — `python scripts/autonomous_agent.py tick --shadow` — runs the reasoning loop but logs decisions instead of acting
2. **Dry-run** — `--dry-run` — zero DB writes, zero sends
3. **Pause the daemon** — `pm2 stop bravo-scheduler` (Windows) — halts cron-triggered automation
4. **Kill switch** — `pm2 kill` — stops every PM2-managed process. Nothing auto-sends after this until you restart.

The send gateway itself has hard caps (50 emails/day) that no amount of agent enthusiasm can override.

### "Telegram bot is silent / dead"

**Fix**: `pm2 status` → look for `bravo-telegram` → if stopped, `pm2 start bravo-telegram`. If running but not responding, `pm2 restart bravo-telegram`. Full restart in 5 seconds.

### "I changed my .env.agents and something broke"

**Fix**: the three MCP configs (`.claude/mcp.json`, `.vscode/mcp.json`, `~/.gemini/settings.json`) all use wrapper scripts that read `.env.agents` at runtime. No cross-file sync needed. If something still broke, it's probably a bad edit in `.env.agents` — check for missing quotes or equal signs.

---

## Onboarding a new capability (skill)

You'll want to add new things to Bravo over time. The pattern has 3 steps today (Build #6 will shrink it to one command). Here's the manual version:

### Step 1: Drop a folder

```
skills/my-new-skill/
├── SKILL.md       ← one page, plain English, what it does + when to use
├── spec.yaml      ← inputs, outputs, preconditions (structured)
└── run.py         ← the actual implementation (if it's code)
```

The `SKILL.md` file follows the format every skill uses — look at `skills/send-gateway/SKILL.md` as a template.

### Step 2: Register it in three places

Until `register_skill.py` exists (Build #6), you manually add the skill name to:

- `brain/CAPABILITIES.md` (routing table)
- `brain/QUICK_REFERENCE.md` (if it's user-facing)
- `brain/AGENTS.md` or the relevant agent's skill list (if a specific agent owns it)

### Step 3: Test it

If it's code, write a test file at `scripts/test_<skill>.py`. If it's a doc-only skill, no test needed.

### Step 4 (coming in Build #6): Automate the above

`python scripts/register_skill.py my-new-skill` will handle steps 2 + 3 automatically.

---

## What you should NOT try to do through Bravo

Hard boundaries. Bravo will push back if you ask for any of these — good. Know the list so you understand why:

| Don't ask Bravo to… | Why | Do this instead |
|---|---|---|
| **Move real money** (transfer Stripe balance, initiate ACH, wire, pay invoices) | Irreversible. One prompt-injection or bug = financial incident. | Open Stripe dashboard manually. Bravo can draft the transaction for you to execute. |
| **Sign / accept legal documents** | Your signature is your signature. | Bravo can *draft* contracts and proposals. You sign. |
| **Email a specific person without relationship context** | Without running `context_builder`, tone will miss the relationship stage. | Ask: "check context for X first, then draft." |
| **Push to `main` without review** | Breaks production. | Bravo pushes to feature branches. You merge. |
| **Run `DROP TABLE` / `TRUNCATE` / `git reset --hard` on production** | The exec_sql RPC server-side guard already refuses this, but the principle applies to any destructive op. | Use Supabase Dashboard / manual git for anything destructive. |
| **Log in as you** to a service (bank, tax, brokerage) | Your session cookies are your session cookies. Never share. | Bravo can automate *after* you're logged in (Playwright against an open session). |

---

## Glossary — every technical term in plain English

In alphabetical order. Skip this unless you're unsure about a specific word.

- **Agent** — An AI (Bravo, Codex, Atlas, Maven, Aura). Each one has a job and its own personality.
- **Brain** — the `brain/` directory. Where each agent's identity, state, and rules live. Shared across agents.
- **CASL** — Canada's Anti-Spam Legislation. Requires every cold email to include your name, business address, and an unsubscribe link. Fines up to $10M per incident. The send gateway enforces this automatically.
- **Chokepoint** — a single point every action must pass through. The send gateway is a chokepoint for outbound mail — nothing sends without going through it.
- **Cooldown** — the minimum time between outbound messages to the same lead on the same channel. Default: 72h for email. Prevents duplicate-email embarrassment.
- **Cron** — a scheduler that runs scripts at fixed times (e.g. "every 15 min"). Your scheduler.py daemon is a cron runner.
- **Daemon** — a long-running background process. Your Telegram bot is a daemon. The reasoning loop can run as a daemon.
- **Decision tape** — the `agent_decisions` table. Every choice the reasoning loop makes is logged here with reasoning + confidence.
- **Gateway** — the send gateway. `scripts/send_gateway.py`. Every outbound email/DM/call passes through it.
- **Intent** — what the AI thinks the inbound message is about: booking, pricing, objection, unsubscribe, etc. Assigned by the inbound classifier.
- **Ledger** — the `lead_interactions` table. Every interaction (outbound + inbound) with every lead, across every channel.
- **MCP** — Model Context Protocol. How Claude connects to external tools (Playwright, Context7, GitHub, etc.). You have 8 active MCP servers.
- **Policy** — rules for when the AI can auto-act vs when it must ask you. Currently hard-coded; Build #5+ will move to a YAML policy file.
- **Pulse** — `.json` files in `data/pulse/` where Atlas/Bravo/Maven write their current status. How agents see each other.
- **Relationship stage** — where a lead sits in the pipeline from the AI's view: cold → contacted → warm → engaged → active_client → dormant → lost. Computed automatically by `context_builder`.
- **RPC** — a function running on Supabase (Postgres) that your code can call. The `exec_sql` RPC is how you run migrations without a Supabase token.
- **Shadow mode** — run the agent, log what it WOULD have done, don't actually do it. Safety net for new behavior.
- **Skill** — a reusable capability at `skills/<name>/SKILL.md`. Example: `skills/send-gateway/SKILL.md` documents the gateway's contract.
- **State** — "what's true right now." Lives in `brain/STATE.md`. Every agent reads it on session start.
- **Tick** — one cycle of the reasoning loop. Each tick goes through 7 phases (orient → recall → assess → plan → verify → execute → reflect).
- **Traces** — `agent_traces` table. Every meaningful action the agent takes is traced here for observability.

---

## Files you'll want to know by name

Only the ones you might open directly. The rest you access through commands or chat.

| File | What's in it | When you'd open it |
|---|---|---|
| `brain/STATE.md` | Current operational state | Quick "what's live right now" check |
| `memory/ACTIVE_TASKS.md` | Current task queue | When you want to know what's pending |
| `memory/SESSION_LOG.md` | What every agent did, day by day | When auditing / recalling recent work |
| `brain/USER.md` | CC's profile — your goals, brands, preferences | Update this when priorities shift |
| `.env.agents` | All credentials | Rotate keys, add new services |
| `docs/N8N_INBOUND_INTEGRATION.md` | How to wire the inbound node in your N8N workflow | Before wiring (on your task list) |
| `ARCHITECTURE.md` | How the whole system is designed and why | When an engineer asks or you're building a new subsystem |
| `PLAYBOOK.md` | This file | Right now. |

---

## Final principle

Bravo's job is to multiply your time. Every thing in this playbook should save you more minutes than it costs you to learn. If something here doesn't feel like a net positive, tell Bravo and we'll kill it. The goal is a system you use without thinking — not a system you spend time managing.

*Last updated: 2026-04-20 (V5.6 — outbound chokepoint + reasoning loop live).*

## Related
- [[CLAUDE]]
- [[brain/INDEX]]
- [[brain/CAPABILITIES]]
