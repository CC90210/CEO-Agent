---
tags: [sync, multi-machine, protocol, non-negotiable]
purpose: Single canonical protocol for how Claude Code on Windows and Claude Code on Mac stay in perfect sync without stepping on each other's work.
owner: CC (Conaugh McKenna)
created: 2026-04-11
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# CROSS-MACHINE SYNC PROTOCOL

> CC uses two machines interchangeably: the Windows production box (where all daemons run) and a MacBook (read/edit/analyze). Claude Code runs on both. This file is the protocol for staying coherent.

## The Three Rules (Non-Negotiable)

1. **Boot with `git pull`, end with `git push`.** Every Claude Code session on either machine opens with a pull and closes with a commit + push. No exceptions. If you skip the pull, you're guaranteed to fight the other machine eventually.

2. **Only ONE machine runs state-mutating daemons. That's WINDOWS. Mac runs only the operator-side chat-server.**

   ❌ Mac must NOT run any of these (they mutate shared state — running two = corruption):
   - `scheduler.py` (Supabase `cron_jobs` table)
   - `telegram_agent.js` (single Telegram poll connection)
   - any PM2 processes under the `bravo-*` namespace
   - `local_bridge.py _loop` (heartbeat ping daemon — single bridge per machine is fine, but redundant heartbeats waste rows)

   ✅ Mac IS allowed to run (operator-side, no shared state):
   - `bravo bridge serve` (the chat-server on `localhost:9100`) — each machine
     pairs independently via `_machine_fingerprint`, the `bridge_pairings`
     table holds N rows per profile by design. When CC opens the dashboard
     from the Mac, the chat widget connects to the Mac's local chat-server
     and gets file-system access to the Mac's clone. When CC opens from
     Windows, same thing on the Windows clone. Both can be paired and online
     simultaneously — no conflict.
   - `bravo bridge install` to set up launchd auto-start on login.

   **Skool daemon:** archived 2026-05-18 → `scripts/_archive/skool/` (revival steps in its README).

   **Telegram bridge specifically:** Only one bridge can exist globally. Both
   bridges use the same `TELEGRAM_BOT_TOKEN`, which means Telegram's
   long-poll `getUpdates` API will randomly route messages to whichever
   bridge grabs them first — effectively both bridges get random half the
   messages, neither sees the full picture. **Windows runs the single
   telegram bridge. Mac never starts one.**

   **Incident 2026-04-11:** Mac had rogue scheduler + telegram_agent running
   under PM2 for ~40 hours (started Tuesday 6PM from hand-launch, then
   PM2-managed with restart counter 2188 for scheduler, 9 for telegram).
   Net damage was minimal only because the shared Supabase `cron_jobs`
   table acted as an accidental mutex. Both daemons deleted from Mac PM2 on
   2026-04-11 with `pm2 delete bravo-scheduler` and `pm2 delete bravo-telegram`.
   **If you ever see `bravo-*` in `pm2 list` on Mac, delete it immediately.**

3. **Declare your session in `memory/ACTIVE_SESSION.json` before you start real work.** This tells the other machine "I'm live, don't stomp on these files." Claimed sessions auto-expire after 30 minutes of no heartbeat so a crashed session doesn't lock the repo forever.

## File Ownership Map

| File/Directory | Owner | Notes |
|---|---|---|
| `.env.agents` | **LOCAL to each machine** | NEVER committed. Each box has its own copy with machine-specific overrides (GWS_PATH, paths, etc). Both machines use the SAME `TELEGRAM_BOT_TOKEN` and SAME `BRAVO_SUPABASE_*` — that's intentional (single source of truth for state), but it also means both machines must NEVER run the telegram bridge or scheduler simultaneously. |
| `tmp/` | **LOCAL to each machine** | Gitignored. Daemon state, browser profiles, heartbeats. Never shared. |
| `brain/` | **shared, read-mostly** | Both machines read. Edits go through normal commit flow. |
| `memory/SESSION_LOG.md` | **append-only shared** | Both machines append to the top. Git merges cleanly because every entry is a new section. |
| `memory/ACTIVE_TASKS.md` | **shared, mutation-prone** | Both machines may update P0 items. Use the handoff protocol to avoid conflicts. |
| `memory/ACTIVE_SESSION.json` | **shared, machine-claimed** | Declares which machine holds the "live" slot right now. |
| `memory/HANDOFF.md` | **shared** | Outgoing session writes here; incoming session reads first. |
| `scripts/` | **shared** | Both machines can edit. Surgical changes only — no full-file rewrites on Mac if Windows is also editing. |
| `skills/` | **shared** | Safe to edit on either. |
| Daemons (scheduler, telegram-bot) | **Windows only** | Mac never starts these. |

## The Session Lifecycle

### On session START (every Claude Code boot, either machine)

```bash
bash scripts/hooks/bravo-session-start.sh
```

What it does:
1. `git fetch origin main && git pull --ff-only origin main`
2. Reads `memory/ACTIVE_SESSION.json` — if another machine is live (<30 min since last heartbeat), prints a warning with the other machine's current task
3. Writes a fresh ACTIVE_SESSION claim: `{machine, hostname, started_at, last_heartbeat, claude_session_id}`
4. Reads `memory/HANDOFF.md` and prints the last handoff note
5. Reports status: commit hash, P0 task count, current MRR from live DB

### During a session (each significant action)

The session script runs in the background and bumps the heartbeat every 5 minutes so the claim doesn't expire. If you're about to touch a file that the other machine also touched in the last 10 minutes (detected via `git log`), the protocol says: pull again, re-check, and either proceed or write to HANDOFF.md first.

### On session END

```bash
bash scripts/hooks/bravo-session-end.sh "one-line summary of what I did"
```

What it does:
1. Appends to `memory/SESSION_LOG.md` with the summary + machine tag
2. Writes `memory/HANDOFF.md` with: status, files touched, blocker if any, recommended next steps
3. Releases the ACTIVE_SESSION claim
4. `git add <tracked files> && git commit -m "bravo(<machine>): <summary>"`
5. `git push origin main`
6. Prints the commit hash so the other machine can verify it when it pulls

## Conflict Resolution

If two machines edit the same file at the same time (rare but possible):

1. Session end push fails with a merge conflict
2. The session script does NOT auto-merge destructively — it saves your work to a stash and prints the conflict file list
3. You resolve manually, re-run session-end, push clean

**Never force-push main.** Ever. If you hit a divergence you can't resolve, leave it alone and come back from the other machine.

## Repo Location Per Machine

Different machines, different clone paths. When SSH-ing across machines, use the absolute path:

| Machine | Repo path |
|---|---|
| Windows (CCPC) | `C:\Users\User\Business-Empire-Agent` (bash: `/c/Users/User/Business-Empire-Agent`) |
| Mac (Conaughs-MacBook-Air) | `/Users/conaugh/CEO-Agent` |

Mac moved from `~/Downloads/business-empire-agent` to `~/CEO-Agent` on 2026-05-19 — the stale Downloads clone was 8 days behind a force-pushed remote and ~1.0 GB of redundant disk. Mac is now CC's on-the-go workstation only; all daemons + cron run on Windows.

## Machine Identification

Every session declares its identity in `ACTIVE_SESSION.json`:

```json
{
  "machine": "windows",
  "hostname": "CC-DESKTOP",
  "started_at": "2026-04-11T20:30:00Z",
  "last_heartbeat": "2026-04-11T20:35:00Z",
  "current_task": "Fixing notification pipeline",
  "claude_session_id": "...",
  "commit_at_start": "f7ddfd1"
}
```

Any Claude Code session that reads this file knows instantly: who's live, what they're doing, how stale the claim is, and whether to defer or proceed.

## Telegram Bridge Handoff Protocol (Windows ↔ Mac)

**Default state:**
- Windows runs `telegram-bot` (PID 13556, 5d stable uptime) — **LIVE**
- Mac has `bravo-telegram` registered in PM2 — **STOPPED**

Both declared in `ecosystem.config.js`. Single-instance invariant: same `TELEGRAM_BOT_TOKEN` on both machines means only ONE bridge should ever be running. Two bridges = random message routing between them.

### Hand off FROM Windows TO Mac (CC wants to control Telegram from MacBook)

```bash
# On Windows (or via SSH from wherever):
ssh cc-mac "cd /Users/conaugh/CEO-Agent && pm2 start bravo-telegram"
# Wait ~5 seconds, verify Mac is online:
ssh cc-mac "pm2 list"
# Then stop Windows:
pm2 stop telegram-bot
pm2 save
```

### Hand off FROM Mac TO Windows (return control to desktop)

```bash
# On Windows (first):
pm2 start telegram-bot
pm2 save
# Then stop Mac:
ssh cc-mac "pm2 stop bravo-telegram && pm2 save"
```

### Hard rules

- **NEVER both running.** Two bridges sharing `TELEGRAM_BOT_TOKEN` → Telegram routes each message to whichever grabs it first, alternating randomly. Your phone commands will feel broken.
- **Scheduler stays Windows-only regardless of telegram location.** Never run two schedulers against one Supabase `cron_jobs` table.
- **Only telegram bridge is handoff-capable.** Everything else (scheduler, content automation) is Windows-pinned.

## Telegram as the Cross-Machine Control Plane

Your existing `telegram_agent.js` already acts as a bridge between your phone and either machine. Two enhancements make it a true multi-machine control plane:

1. **Machine routing prefix** — commands starting with `@mac` or `@win` target that specific machine. Unprefixed commands go to whichever machine last registered as active.
2. **Session heartbeat** — each machine's telegram-bot worker updates `memory/ACTIVE_SESSION.json` every 60 seconds while running, so the bot knows which machine is actually online and can route accordingly.

This is future work — the protocol supports it, the implementation is ~60 lines in `telegram_agent.js`.

## Obsidian Links
- [[docs/deploy/MAC_SYNC_PROMPT]]
- [[docs/deploy/MULTI_MACHINE_PAIRING_PROMPT]] — paste-ready prompt for pairing any secondary machine (Mac/Linux/Windows) to the Agent Command Center
- [[docs/deploy/MAC_COMMAND_CENTER_PROMPT]] — backward-compat pointer at MULTI_MACHINE_PAIRING_PROMPT (Mac body moved there)
- [[brain/SECURITY_MODEL]] — how tenant isolation, encryption, and bridge auth work end-to-end
- [[brain/CREDENTIALS_SCAFFOLD]]
- [[memory/SESSION_LOG]]
- [[memory/ACTIVE_TASKS]]
- [[memory/HANDOFF]]
- [[memory/SESSION_LOG]]
