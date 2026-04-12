---
tags: [sync, multi-machine, protocol, non-negotiable]
purpose: Single canonical protocol for how Claude Code on Windows and Claude Code on Mac stay in perfect sync without stepping on each other's work.
owner: CC (Conaugh McKenna)
created: 2026-04-11
---

# CROSS-MACHINE SYNC PROTOCOL

> CC uses two machines interchangeably: the Windows production box (where all daemons run) and a MacBook (read/edit/analyze). Claude Code runs on both. This file is the protocol for staying coherent.

## The Three Rules (Non-Negotiable)

1. **Boot with `git pull`, end with `git push`.** Every Claude Code session on either machine opens with a pull and closes with a commit + push. No exceptions. If you skip the pull, you're guaranteed to fight the other machine eventually.

2. **Only ONE machine runs production daemons.** That's Windows. The Mac can read, analyze, edit, and run ad-hoc commands, but it never starts the scheduler, skool daemon, telegram-bot, or any cron worker. Two schedulers against the same Supabase `cron_jobs` table = every job runs twice.

3. **Declare your session in `memory/ACTIVE_SESSION.json` before you start real work.** This tells the other machine "I'm live, don't stomp on these files." Claimed sessions auto-expire after 30 minutes of no heartbeat so a crashed session doesn't lock the repo forever.

## File Ownership Map

| File/Directory | Owner | Notes |
|---|---|---|
| `.env.agents` | **LOCAL to each machine** | NEVER committed. Each box has its own copy with machine-specific overrides (GWS_PATH, paths, etc). |
| `tmp/` | **LOCAL to each machine** | Gitignored. Daemon state, browser profiles, heartbeats. Never shared. |
| `brain/` | **shared, read-mostly** | Both machines read. Edits go through normal commit flow. |
| `memory/SESSION_LOG.md` | **append-only shared** | Both machines append to the top. Git merges cleanly because every entry is a new section. |
| `memory/ACTIVE_TASKS.md` | **shared, mutation-prone** | Both machines may update P0 items. Use the handoff protocol to avoid conflicts. |
| `memory/ACTIVE_SESSION.json` | **shared, machine-claimed** | Declares which machine holds the "live" slot right now. |
| `memory/HANDOFF.md` | **shared** | Outgoing session writes here; incoming session reads first. |
| `scripts/` | **shared** | Both machines can edit. Surgical changes only — no full-file rewrites on Mac if Windows is also editing. |
| `skills/` | **shared** | Safe to edit on either. |
| Daemons (skool, scheduler, telegram-bot) | **Windows only** | Mac never starts these. |

## The Session Lifecycle

### On session START (every Claude Code boot, either machine)

```bash
bash scripts/bravo-session-start.sh
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
bash scripts/bravo-session-end.sh "one-line summary of what I did"
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

## The Skool Daemon Exclusivity Lock

The skool daemon uses a **file-based lock** at `tmp/skool_daemon.lock` (Windows `msvcrt.locking`). Only one process can hold it. But `tmp/` is gitignored and machine-local, so Mac has no knowledge of the Windows lock. That means:

**Never run `python scripts/skool_engine.py daemon` on Mac.** The Mac daemon would try to open a fresh Chromium profile at `tmp/skool-browser/`, Skool would see a second device logging into the same account, and you'd get double-replies in the live community.

Enforcement: the session script checks which machine you're on and refuses to start skool daemon if `machine != "windows"`.

## Telegram as the Cross-Machine Control Plane

Your existing `telegram_agent.js` already acts as a bridge between your phone and either machine. Two enhancements make it a true multi-machine control plane:

1. **Machine routing prefix** — commands starting with `@mac` or `@win` target that specific machine. Unprefixed commands go to whichever machine last registered as active.
2. **Session heartbeat** — each machine's telegram-bot worker updates `memory/ACTIVE_SESSION.json` every 60 seconds while running, so the bot knows which machine is actually online and can route accordingly.

This is future work — the protocol supports it, the implementation is ~60 lines in `telegram_agent.js`.

## Obsidian Links
- [[brain/MAC_SYNC_PROMPT]]
- [[brain/CREDENTIALS_SCAFFOLD]]
- [[memory/SESSION_LOG]]
- [[memory/ACTIVE_TASKS]]
- [[memory/HANDOFF]]
- [[memory/ACTIVE_SESSION]]
