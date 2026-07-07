---
tags: [operational-state, ephemeral]
last_updated: 2026-07-07
freshness_threshold_days: 7
---

# OPERATIONAL STATE — Live Infrastructure & Known Issues

> Ephemeral half of `brain/STATE.md` (split 2026-05-07 per Architecture Certification C5). PIDs, deploy state, the daily-shifting issue queue, and last-heartbeat live here under a 7-day freshness gate. Stable identity / mission / capability architecture stays in `brain/STATE.md`.
>
> ⚠ **Read the freshness gate first.** If `last_updated` above is older than 7 days, treat every claim below as archived — re-verify with `pm2 list`, `python scripts/core/self_audit.py --json`, and `git log --since="7 days ago"` before quoting it.
>
> ⚠ **Never state the day of the week** without computing it: `python -c "from datetime import date; print(date.today().strftime('%A'))"`.

---

## Machine

- **Primary:** Windows 11 desktop "CCPC", **Montreal QC**, runs **24/7** (relocated 2026-07). Python 3.12, `.venv` at repo root, Node + PM2 global.
- **Cold-standby:** Mac (Conaughs-MacBook-Air) via `ssh cc-mac`. LAN IPs changed with the move — refresh `brain/CROSS_MACHINE_SYNC.md` before relying on the handoff.

## PM2 Fleet — verified live 2026-07-07

Reboot-persistent via `pm2 save` (dump.pm2) + the **`PM2 Resurrect` scheduled task** (Task Scheduler, at-logon) → `scripts/pm2_resurrect_hidden.vbs` → `pm2 resurrect`. This is the single canonical resurrection entry point per `docs/RUNBOOK_PM2_COLD_START.md`. Re-registered 2026-07-07 — the task was missing after the Montreal move, which is why persistence was broken.

| Process | Role | Status |
|---------|------|--------|
| **bravo-scheduler** | Cron engine (`scripts/scheduler.py`) — polls Supabase `cron_jobs` every 60s | ✅ executing jobs; now writes an `agent_state` heartbeat (fixed 2026-07-07) |
| **bravo-telegram** | DM bridge (`telegram_agent.js`) — full computer control, subscription-first auth | ✅ V15.8 ready, polling |
| **bravo-coord** | OASIS group bridge (`coordination_agent.js`) — Bravo↔APEX | ✅ online |
| **claude-bridge** | Dashboard chat server (`bravo_cli.bridge_chat_server`) :9100, 19 tools | ✅ `/health` 200 |
| **claude-bridge-ping** | Bridge heartbeat + tenant cron poller | ✅ online |
| **event-router** | Cross-agent event-bus tail (`event_router.py loop`) | ✅ routing |
| _atlas-telegram, maven-telegram_ | Sibling agents' bridges (Atlas CFO, Maven CMO) | ✅ online |
| _pm2-logrotate_ | PM2 module — rotates PM2 logs | ✅ online |

**VPS (Linux, `/srv/sunbiz/...`) — NOT run locally:** `dashboard-email-consumer`, `extraction-consumer`, SunBiz `sequence-runner` + `lender-response-classifier`. Started from the VPS `ecosystem.config.js`.

## Core substrate (intact)

- **Send Gateway** — `scripts/integrations/send_gateway.py`, single outbound chokepoint (CASL + cooldown + caps + draft critic + DNS doctor). All business engines route through it.
- **State DB** — `state/empire_state.db` (SQLite/WAL). Heartbeats, session_log, active_task. Nightly backup cron.
- **Guards (enforce)** — secret_guard · exec_guard · state_guard · anti_pattern · subprocess_guard (`.claude/settings.local.json`).
- **Retrieval** — FTS5 `memory_retriever.py` + 3-layer memory + Obsidian Knowledge Graph MCP.
- **Command Center** — `oasis-command-center` (Vercel, Next.js) — the Agent Command Centre dashboard. Chat widget talks to `claude-bridge`.
- **Sibling agents** — Atlas (CFO, `~/APPS/CFO-Agent`, owns all finance/revenue), Maven (CMO, `~/CMO-Agent`, owns content/ads).

## Known Issues (triaged 2026-07-07)

| Issue | Severity | Action |
|-------|----------|--------|
| `dashboard-email-consumer` also running on **Windows** though it's designated VPS-only | HIGH | Double-send risk on lead-email queue. Verify the VPS consumer is up, then `pm2 delete dashboard-email-consumer` on Windows + `pm2 save`. **Needs CC confirmation of VPS state first.** |
| CFO finance module still lives in Bravo repo | MEDIUM | Revenue skills (ceo-dashboard, financial-modeling, revenue-operations, ceo-briefing), `revenue_engine.py`/`financial_model.py`/`sync_mrr.py`, and the 3 revenue crons (Stripe Revenue Sync, Daily MRR Auto-Sync, Weekly MRR Report) should migrate to Atlas (CFO). Flagged 2026-07-07 finance purge — do NOT deactivate revenue tracking before Atlas has equivalents. |
| Cross-machine LAN IPs stale after Montreal move | LOW | Refresh in `brain/CROSS_MACHINE_SYNC.md`. |

## Recently Fixed (2026-07-07 Montreal turnkey reset)

- **Fleet reboot-persistence** — was none; installed Startup VBS + `pm2 save`.
- **`agent_state` heartbeat gap** — scheduler is "the heartbeat" but never wrote `agent_state` (frozen 46 days, made a live fleet look dead). Wired `state_manager.heartbeat` into the loop.
- **Scheduler busy-spin** — the 60s sleep lived only in the error branch, so the healthy loop re-queried Supabase ~8×/sec. Added normal-path pacing.

## Update Protocol

Update when infra status changes, an issue is added/resolved, or at end-of-session (bump `last_updated:` if the body changed). Run `python scripts/state/state_sync.py --note "<summary>"` after edits. 7-day freshness gate enforced by `memory_aging.py`.

## Obsidian Links
- [[brain/STATE]] (stable identity / mission / capability arch)
- [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]] | [[memory/MISTAKES]]
- [[brain/CHANGELOG]] | [[brain/ORCHESTRATION]] | [[memory/INDEX]]
