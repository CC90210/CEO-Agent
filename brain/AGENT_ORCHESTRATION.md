---
description: "Fleet coordination contract: defines agent roles, responsibilities, pulse-protocol state hand-offs, approval authority, and veto boundaries"
tags: [orchestration, contract, multi-agent, autonomy]
last_updated: 2026-08-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# AGENT ORCHESTRATION — Master Multi-Agent Contract

> Canonical contract for how Bravo, Atlas, Maven, AURA, Hermes, and Codex coordinate. **Read this before designing any cross-agent flow.** Atlas's `brain/AGENT_ORCHESTRATION.md` and Maven's `brain/RESPONSIBILITY_BOUNDARIES.md` are the per-agent views; this is the single source of truth.

## The fleet (as of 2026-05-03)

| Agent | Repo | Role | Primary persona | Always-on cron? |
|-------|------|------|-----------------|-----------------|
| **Bravo** | `Business-Empire-Agent/` | CEO/COO/CTO — strategy, orchestration, operations, clients, revenue, code | Right hand · second brain | ✅ 14 jobs (8 active) |
| **Atlas** | `APPS/CFO-Agent/` | CFO — tax, accounting, research, wealth aggregation | Senior PM + CPA | ⚠️ 0 jobs registered |
| **Maven** | `CMO-Agent/` | CMO — content, ads, brand, distribution | Marketing strategist | ⚠️ 0 jobs registered |
| **AURA** | `AURA/` | Smart-home + voice — apartment ambient intelligence | Calm, brief, ambient | n/a (Home Assistant handles its own automations) |
| **Hermes** | `hermes/` | Commerce agent — Emmanuel Lowinger's back-office | Laconic, audit-trail | Per-client (Emmanuel's machine) |
| **Codex** | external (OpenAI) | Backend executor — delegated by Bravo | Backend specialist | n/a (invoked on demand) |

Atlas and Maven cron emptiness is a **known gap**, not a feature — see `## Known gaps` below.

---

## The pulse protocol — one-way state hand-off

Each operating agent writes one canonical state file. Other agents read it, **never write to it**. This is the core data contract; every other coordination mechanism builds on it.

| File | Owner | Readers | Purpose |
|------|-------|---------|---------|
| `Business-Empire-Agent/data/pulse/ceo_pulse.json` | Bravo | Atlas, Maven | CEO directive: revenue priority, client focus, current week's #1 |
| `APPS/CFO-Agent/data/pulse/cfo_pulse.json` | Atlas | Bravo, Maven | CFO directive: spend gate, ad budget cap, runway, tax windows |
| `CMO-Agent/data/pulse/cmo_pulse.json` | Maven | Bravo, Atlas | CMO directive: content backlog, campaign state, attribution |

**Schema invariants (machine-checkable):**
- Every pulse has `agent`, `schema_version`, `updated_at` (ISO 8601 with timezone)
- Every pulse declares which fields readers can rely on as authoritative
- `updated_at` older than each agent's freshness threshold = staleness escalation (see Atlas's `bravo_pulse_age_days` field — if > 7, Atlas alerts CC)

**Write discipline:**
- Only the owning agent's `pulse_publish.py` (or equivalent) writes the file. Direct edits forbidden.
- Atomic writes only (write to `.tmp`, then rename). Readers must never see a partial file.
- A pulse write triggers an `agent_inbox` notification to readers when material fields change.

---

## Veto and approval authority

| Authority | Owner | Bound by |
|-----------|-------|----------|
| Ad spend cap (monthly, paid campaigns) | **Atlas** via `cfo_pulse.approved_ad_spend_monthly_cap_cad` | Maven MUST honor before launching paid creatives |
| CEO priority of the week | **Bravo** via `ceo_pulse.priority_focus` | Atlas + Maven align their cron + content to it |
| Content publish approval (CC-facing brand) | **CC** | Maven drafts, CC approves before publish |
| Trade execution / withdrawal / CRA filing | **CC** | Atlas prepares, never executes |
| New external integration / API key | **CC** | Any agent surfaces via `agent_inbox`; CC adds to `.env.agents` |
| Client-facing email / DM send | **Bravo** (after `send_gateway` validation) | Goes through cooldown + CASL + draft_critic |
| Pi production deploy | **CC** | AURA confirms before flashing live |
| Customer-facing commerce action (Emmanuel's clients) | **Emmanuel** | Hermes prepares, Emmanuel approves |

When in doubt: escalate to CC via `agent_inbox` (priority `HIGH` or `URGENT`). Don't act on ambiguous authority.

---

## The agent inbox — async cross-agent messaging

`scripts/core/agent_inbox.py` is the cross-repo message queue. Different from pulse files: pulses are state, inbox is messages.

**Protocol:**
- Sender posts: `python scripts/core/agent_inbox.py post --from <self> --to <recipient> --subject "..." --body "..." [--priority normal|high|urgent]`
- Recipient lists at session start: `python scripts/core/agent_inbox.py list --to <self>`
- Recipient reads: `python scripts/core/agent_inbox.py read <message_id>`
- Storage: `tmp/agent_inbox/<recipient>/<unread|read>/<id>.json`

**When to use inbox vs pulse:**
- **Pulse:** "Here's my current state; act on it accordingly" (passive, polled)
- **Inbox:** "Something happened that needs your attention" (active, push)

**Examples of correct inbox use:**
- Atlas → Bravo: "MRR crossed $4k — your concentration risk just dropped, FYI"
- Maven → Bravo: "Today's video posted, 3 platforms, 14 minute backlog cleared"
- Maven → Atlas: "Paid campaign launching tomorrow — confirming I'm under your $X cap"
- Codex → Bravo: "Background task XYZ completed, here's the diff"

**Examples of wrong inbox use:**
- Anything CC needs to see (use Telegram bridge or direct CC notification)
- Routine "I did the daily thing" status (cron's success log is enough)

---

## Boot ritual — every agent, every session

When ANY agent starts a session (Claude Code / Gemini / Antigravity / OpenCode / Codex / cron tick):

1. **Read your own SOUL/CLAUDE.md silently** — load identity
2. **Check the staleness report** — SessionStart hook surfaces stale memory files
3. **Read your inbox** — `agent_inbox.py list --to <self>`
4. **Read your pulse + sibling pulses you depend on** — confirm they're fresh enough to trust
5. **Read `memory/SESSION_LOG.md` last 5 entries** — what every other runtime did recently
6. **Then answer CC** — informed, current, contractually compliant

If any of those steps reveal a contract violation (stale pulse, blocked cap, urgent inbox), surface it BEFORE answering the question.

---

## Headless / autonomous mode

Bravo's `scripts/autonomous_agent.py` is the always-on reasoning loop. Cron-friendly entry points:

```bash
# Single tick — read, reason, act once, exit. Used by cron.
python scripts/autonomous_agent.py tick [--dry-run] [--shadow]

# Long-running daemon — tick every N seconds forever. Used by systemd / pm2.
python scripts/autonomous_agent.py daemon --interval 900

# Inspect — read-only state of last tick.
python scripts/autonomous_agent.py status --json

# Audit — recent decisions tape (DB-backed).
python scripts/autonomous_agent.py decisions --today --limit 50
```

**Cron orchestration today:** `scripts/core/cron_engine.py` is the source-of-truth registry of scheduled jobs (delegates actual scheduling to n8n at `https://n8n.srv993801.hstgr.cloud`). Currently 14 jobs registered, 8 active — all owned by Bravo. Atlas and Maven have **zero registered jobs** as of 2026-05-03.

**For full fleet autonomy, every agent needs its own scheduled work:**
- Atlas: nightly `wealth_tracker` refresh + receipt ingestion sweep + tax-window deadline check
- Maven: nightly content backlog audit + ad-platform token expiry check + cmo_pulse refresh
- Bravo: already covered (Stripe sync, MRR report, lead follow-up, funnel sync, etc.)
- AURA: covered by Home Assistant's own automation engine (no n8n needed)
- Hermes: per-client (Emmanuel's machine handles its own scheduling)

See `## Known gaps` for what's not yet wired.

---

## Bridge arbitration — multi-machine safety

When Bravo runs on multiple machines (laptop + desktop + future VPS), `scripts/bridge_lock.py` prevents duplicate Telegram bridges from racing.

- Lockfile: `~/.oasis/bridge_locks/<agent>.json` (host + pid + heartbeat)
- Acquire on bridge startup; exit cleanly if another host has fresh heartbeat (<60s old)
- Heartbeat every 15s while running
- Release on graceful shutdown
- CLI: `python scripts/bridge_lock.py {acquire|heartbeat|release|status} --agent bravo`

This is what prevented the V6.5 "two bridges echoing each other forever" failure mode. Same pattern extends to future Discord/Slack bridges.

---

## Per-client API key isolation (deployment pattern, not yet wired)

When OASIS deploys a sibling agent for a client (e.g., Hermes for Emmanuel), credentials must isolate from CC's `.env.agents`:

**Recommended pattern (not yet implemented — see `## Known gaps`):**
- Per-client env: `.env.client-<id>` (e.g., `.env.client-emmanuel`)
- Wrapper script loads correct env based on `CLIENT_ID` environment variable
- Each client's agent runs with its own keys; cross-client data isolation enforced architecturally (separate DBs, separate stores)
- Audit trail per client (Hermes already does this — local SQLite, customer data never leaves the machine)

This is the pattern Hermes already enforces (`brain/SOUL.md` immutable: "Local-first. Customer data never leaves this machine."). Just needs to be documented and templatized for future client agents.

---

## Known gaps (autonomy-readiness scorecard, 2026-05-03)

| # | Gap | Impact | Effort to close |
|---|-----|--------|----------------|
| 1 | Atlas + Maven have 0 cron jobs registered | They only run when CC manually invokes them. Atlas's wealth_tracker doesn't refresh nightly; Maven's content backlog doesn't audit nightly. | 30 min: register baseline jobs in each repo's `cron_engine` (or n8n equivalent) |
| 2 | No `.env.agents.example` template | New machine / new client deployment requires reverse-engineering which keys exist. | 20 min: extract from current `.env.agents` (sanitized, with comments) |
| 3 | SessionStart staleness hook only in Bravo | Atlas/Maven/Aura/Hermes can still treat stale memory as truth. | 15 min: copy `.claude/settings.local.json` SessionStart hook to siblings |
| 4 | No `scripts/fleet_health.py` rollup | No single command shows: which pulses are fresh, which inboxes have unread urgent, which crons last ran successfully. | 45 min |
| 5 | No `prompts/` directory extraction | Agent identities live in CLAUDE.md/AGENTS.md/etc. — not pullable by n8n / Telegram / future API clients without parsing markdown. | 90 min (multi-file refactor, schedule for own session) |
| 6 | Per-client API key isolation undocumented | Future client agent deployments would require re-figuring out the pattern each time. | 60 min (docs + wrapper script) |
| 7 | Bravo's `ceo_pulse.json` is 16 days stale (verified 2026-05-03 via `fleet_health.py`) | Atlas is making CFO decisions against stale CEO directive. | CC must refresh manually — auto-refresh re-introduces the staleness failure mode. |
| 8 | **Atlas + Maven autonomous scripts missing** (discovered 2026-05-03) | Cron entries can't fire — these scripts don't exist yet: `../APPS/CFO-Agent/scripts/pulse_publish.py` (Atlas pulse refresh), `../CMO-Agent/scripts/token_expiry_check.py` (Meta/Google/Late token watch). Wealth tracker exists but at `finance/wealth_tracker.py`, not `scripts/`. | 30 min Atlas (build pulse_publish.py); 30 min Maven (build token_expiry_check.py). Cron entries deactivated until built. |

**Tonight's ship list (status):** #1 (Atlas wealth tracker registered, path corrected). #2 (env template shipped). #3 (SessionStart hooks propagated). #4 (fleet_health shipped). #7 (surfaced — needs CC). #8 (3 cron entries deactivated; deferred to Atlas + Maven sessions).

---

## Inviolable rules — cross-agent

- **No agent writes to another agent's pulse file.** Ever.
- **No agent writes to another agent's repo.** Reads are fine; writes go through `agent_inbox` or pulse contracts.
- **No agent ignores Atlas's spend cap.** Maven launches over the cap = contract violation, escalate to CC.
- **No agent treats stale pulse as truth.** Each pulse declares its freshness; readers check it.
- **No agent introduces itself as a generic AI.** Each agent has a non-negotiable identity.
- **No agent skips the inbox at session start.** Cross-agent messages must be acknowledged.
- **No agent silently drops a CC instruction.** Every directive logged in `memory/SESSION_LOG.md`.
- **No agent posts internal operational noise to the OASIS partner group.** Blocked sending numbers, scraper logs, cron failures, tracebacks and daemon crashes go to CC's private DM. See below.
- **No agent treats Apex and Knut as two peers.** They are one system — Adon's agent.

---

## External peer: APEX / Knut (Adon's agent)

**APEX == Knut == Adon's agent.** One system, two names: "Apex" is the persona, "Knut" is the bot (`@KnutRPEbot`). `PEER_KEYS` defaults to `apex,knut` in BOTH `scripts/integrations/agent_activity.py` and `coordination_agent.js`. Watching only one key makes rows written under the other invisible — including **file claims**, so Bravo could edit a file Knut had open.

### Channel isolation — what may reach the partner group

`OASIS 🏝️💸` (`COORD_GROUP_CHAT_ID` = `-5165125484`) contains **Adon**, who is a 50/50 partner on **PropFlow only**. Everything in that room is partner-scoped by definition.

| Traffic | Destination | Enforced by |
|---|---|---|
| Operational / outreach / scraper / cron / crash | **CC private DM** (`TELEGRAM_ALLOWED_USERS`) | `_GROUP_BLOCKED_TERMS_RE` reroutes `group=True` → DM |
| Financial receipts & invoices | Atlas bridge (`ATLAS_TELEGRAM_*`) | `notify(..., agent="atlas")` |
| Content & marketing | Maven bridge (`MAVEN_TELEGRAM_*`) | `CATEGORY_TO_AGENT` |
| Partner broadcast / deliverable handover | **OASIS group** | explicit `group=True`, or `agent_activity.py --mirror` |

Enforced by CONTENT in two live places, not just by lane:
- `scripts/notify.py` — reroutes to CC's DM rather than dropping. A dropped alert trades a noise problem for a silence problem, which is worse.
- `scripts/integrations/agent_activity.py` — refuses the `--mirror` broadcast. **The `agent_activity` row is still written**, so the agent↔agent channel loses nothing; only the human-facing echo is withheld.
- `coordination_agent.js` — same denylist, **automated posts only**.

**Reply exemption.** A message answering a human who spoke in the group is exempt. If CC asks "why is the cron failing?" in that room, gagging Bravo's answer would defeat the bridge. Consent is the line: unprompted broadcast = noise; answer to a question asked there = not.

**Known gap (2026-08-03):** `notify.py`'s `group=True` lane reads `GROUP_TELEGRAM_CHAT_ID`, which resolves to nothing — `telegram_identity_audit.py` reports `FAIL notify-group-broadcast … sends on this lane are refused`. The lane fails closed, so it leaks nothing, but it also cannot deliver a deliberate broadcast. Repointing it at `COORD_GROUP_CHAT_ID` would ACTIVATE a currently-dead path into the partner group — do that only deliberately, with the filter above already in place.

---

## Obsidian Links
- [[CLAUDE]] · [[brain/SOUL]] · [[brain/AGENTS]] · [[brain/CAPABILITIES]] · [[brain/QUICK_REFERENCE]]
- [[../APPS/CFO-Agent/brain/AGENT_ORCHESTRATION]] · `../CMO-Agent/brain/RESPONSIBILITY_BOUNDARIES`
- [[memory/ACTIVE_TASKS]] · [[memory/SESSION_LOG]]
