---
tags: [docs]
last_updated: 2026-05-21
---

# Getting Started

Welcome. Your AI agent is now installed and watching its own back via the V6.0 guardrail layer. This page is the 30-second orientation; the next three pages cover safety, escalation, and pause.

## What you actually have

You installed an autonomous AI agent that:

- **Reads and writes a local SQLite database** (`state/empire_state.db`) for every action it takes — heartbeat, session log, tasks. This is the single source of truth.
- **Searches its own memory** via FTS5 (`scripts/core/memory_retriever.py`) so it answers "what did we do last week?" in milliseconds without re-reading your entire knowledge base.
- **Runs every command through three guards** (exec, secret, state) that block destructive actions, refuse to read your credentials, and protect auto-generated state files.

You did not install a chatbot. You installed an operator. It will do work; the guardrails make sure it does the *right* work.

## How to read the dashboard

The sidebar is split into **Operations** (your daily plan, pipeline, reasoning trace, this playbook) and **System** (agents, runs, system health, settings).

Two pages worth visiting weekly:

- **System Health** — a one-glance check on the V6.0 engine. Are the guards in `enforce` or `report` mode? When did the agent last tick? How many bypass attempts have been logged? If anything looks off, it shows up here first.
- **Runs** — the chronological log of agent actions. Most of what the agent does is invisible (background ticks, cron jobs, webhook responses). This is where you scrub the tape.

## Where things live on disk

```
state/empire_state.db        ← agent state (heartbeat, session_log, tasks)
state/memory_index.db        ← FTS5 retrieval index
state/{guard}.log            ← jsonl audit logs (one per guard)
state/secret_access.log      ← every script that loaded .env.agents
.env.agents                  ← your API keys (not LLM-readable)
memory/SESSION_LOG.md        ← human-readable mirror of session_log
brain/STATE.md               ← human-readable mirror of agent_state
```

Everything in `state/` is local-only and gitignored. Only the migration SQL files are tracked.

## What "V6.0 mode" means in the header

In the System Health page header you'll see one of:

- **off** — V5.5 mode. Old flat-file behavior; the database mirrors but doesn't drive.
- **shadow** — Both run. New writes go to flat files AND the database. Used during the 14-day soak before cutover.
- **on** — Database is authoritative. Markdown mirrors are auto-generated. This is the production target.

Default for fresh installs is **shadow** on cloud, **off** on local-dev.

## What to do today

1. Open the System Health page and confirm the agent has ticked recently.
2. Skim the next three playbook pages — Safe Interaction, When to Call, Pause & Rollback.
3. Send your agent a low-stakes ask ("summarize my pipeline", "draft a follow-up email") and watch the Reasoning page render the trace.

## Related

- [[docs/playbooks/INDEX]]
- [[docs/playbooks/02-safe-interaction]]
- [[docs/playbooks/03-when-to-call-cc]]
