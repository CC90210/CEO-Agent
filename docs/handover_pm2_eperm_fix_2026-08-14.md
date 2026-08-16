# Handover — PM2 EPERM Startup Incident & Bridge Token Repair (2026-08-14)

**Author:** Kimi Code CLI session (Bravo chassis), operator CC
**Status:** COMPLETE — all verification passed 2026-08-14 ~21:49 UTC (only the trading-vbs intent question remains for CC, §6.5)
**Review contract for the next AI:** verify each claim against live state before acting (AGENTS.md RULE 9.5 — inherited claims are archived context, not verified state). Every section lists its own verification command.

---

## 1. Incident summary

After a workstation reboot, multiple terminal windows popped up with:

```
Error: connect EPERM //./pipe/rpc_User.sock  (errno -4048)
[PM2] Spawning PM2 daemon with pm2_home=C:\Users\User\.pm2
```

### Root cause (verified, not assumed)

The Task Scheduler task **"PM2 Resurrect"** was registered with `LogonType=S4U` + `RunLevel=Highest`. At boot it spawned an **elevated** PM2 daemon. On Windows, named pipes created by a high-integrity process reject connections from medium-integrity (normal user) clients — every interactive `pm2` command then failed with EPERM.

The trap that made it unrecoverable: **`pm2 kill` must connect to the same wedged pipe before it can kill anything**, so the existing recovery script (`scripts/pm2_resurrect_hidden.cmd`, which already pinned PM2_HOME after the 2026-08-07 incident) died with the same EPERM and the stale daemon survived every boot.

### Kill-chain evidence

- `pm2.pid` pointed at a dead PID (stale).
- Three+ stale `Daemon.js` node processes visible to the user session; one more elevated daemon (PID 16072, invisible command line from medium integrity) owned the pipes, with 4 elevated `ProcessContainerFork` children.
- Pipes `\\.\pipe\{rpc,pub}_User.sock` persisted after ALL user-visible PM2 processes were killed → proved an elevated process owned them.
- `(Get-ScheduledTask 'PM2 Resurrect').Principal` → `S4U / Highest`.
- Generic named-pipe create+connect probe succeeded (AVG was NOT blocking pipes) — integrity-level ACL was the differentiator.

## 2. Changes made (all verified live)

### Business-Empire-Agent repo

| File | Change |
|---|---|
| `scripts/pm2_resurrect_hidden.cmd` | Added PID-based stale-daemon sweep (PowerShell `Get-CimInstance` match on `pm2/lib/Daemon.js` + `ProcessContainerFork` → `Stop-Process`) and stale pid-file cleanup **before** `pm2 kill`. Header comments document why `pm2 kill` alone can't recover from EPERM, and that the sweep only reaches daemons in the caller's own security context. |
| `scripts/bravo_console_tail.cmd` | Replaced `cmd /k` failure fallback with: retry `pm2 logs` 4× @ 15s gaps (covers logon race vs the resurrect task) → append to `.pm2\startup-log\bravo-console-fail.log` → best-effort `python scripts\notify.py` Telegram alert → `exit /b`. No more orphaned error windows. The visible log window on success is intentional (CC wants it at logon — see launcher vbs comments). |
| `brain/APP_REGISTRY.md` | Added the missing hub row for this repo (remote verified: `CC90210/CEO-Agent`). |
| `memory/SESSION_LOG.md` | Incident entry appended. |
| `tmp/pm2_elevated_reset.ps1` | One-shot elevated cleanup script (kept for reuse): kills PM2 daemons by PID from an admin context, clears pid files, verifies pipes freed, sets the scheduled task to `RunLevel=Limited`. |
| `tmp/startup-quarantine/` | Receives dead/disabled startup items instead of deletion (reversible). Currently holds `atlas_live_trading.vbs` + `atlas_paper_trade.vbs` — both pointed at `C:\Users\User\APPS\trading-agent`, **which does not exist anywhere on the machine**. **Open question for CC: were these retired intentionally, or should they be repointed to a new home?** |

### Machine state (not in git)

- Scheduled task **"PM2 Resurrect"**: `RunLevel` Highest → **Limited** (still S4U, still Ready). This is the permanent fix for the recurrence vector.
- Killed elevated orphan **PID 15988** (python, `atlas-telegram` bot, child of the dead elevated daemon) — it was holding the `~/.oasis/bridge_locks/atlas.json` bridge lock with fresh heartbeats, keeping PM2's managed `atlas-telegram` in a `waiting restart` conflict loop. After the kill, PM2's copy acquired the lock and is stable (`pm2 reset atlas-telegram` cleared the cosmetic restart counter).
- Startup folder now contains only live entries: `Bravo Console.lnk`, `Chrome-RemoteDebug.lnk`, `OASIS-PowerShell-Flash-Suppressor.vbs`, `Wispr Flow.lnk`.

### oasis-command-center repo (`C:\Users\User\APPS\oasis-command-center`)

**Commit `971484a` on local `main` — PUSHED BY CC (confirm: `git log origin/main -1`).**

- `lib/api-helpers.ts`: new `isUniqueViolationError(err)` — accepts Postgres `23505` AND SQLite/libSQL `UNIQUE constraint failed` / `duplicate key` message forms. Follows the `isMissingTableError` consolidation precedent; same pattern was already inlined in `/api/cron/tps-enroll`.
- `app/api/auth/pair/route.ts`: the bridge-pairing insert-then-rotate conflict branch now uses `isUniqueViolationError(ins.error)` instead of `ins.error?.code === "23505"`.

**Why:** the dashboard backend moved to Turso. libSQL reports unique violations as `SQLITE_CONSTRAINT` with no code mapping, so the rotate branch never fired and re-pairing a known machine 500'd with `UNIQUE constraint failed: bridge_pairings.tenant_id, bridge_pairings.machine_fingerprint`. This is what kept `claude-bridge-ping` dead (it self-pairs on boot to get `~/.oasis/bridge_token`).

## 3. Verification already performed

| Check | Result |
|---|---|
| `pm2 ping` | `pong` |
| `pm2 list` | 10/10 services + logrotate; 9 stable online, `claude-bridge-ping` pending token (§6) |
| Daemon count | exactly one `Daemon.js` (user context) |
| `pm2 resurrect` after clean | full fleet restored from `dump.pm2` |
| Scheduled task | `Ready`, `RunLevel=Limited` |
| `npx tsc --noEmit` (oasis-command-center) | exit 0 |
| Sweep regex dry-run (Select, not Stop) | matches only PM2 daemon/fork processes |
| atlas-telegram | online, 0 restarts after orphan kill + lock release |

Not verified: the failure path of `bravo_console_tail.cmd` (requires a wedged PM2 to trigger naturally; logic reviewed, retry/fail branches exercised by reading, notify.py existence confirmed at `scripts/notify.py`).

## 4. PM2 fleet inventory (dump.pm2, all restored)

`bravo-telegram`, `maven-telegram`, `atlas-telegram`, `claude-bridge`, `claude-bridge-ping`, `event-router`, `bravo-coord`, `bravo-scheduler`, `breeze-live-watch`, `atlas-scheduler` + `pm2-logrotate` module.

Cron: `python scripts/core/cron_engine.py list` → 29 jobs, 21 active — all driven by `bravo-scheduler`. DB/cron layer was healthy throughout; only the PM2 daemon layer was wedged.

Task Scheduler: `PM2 Resurrect` (Ready, now Limited), `PM2 Resurrect on Login` (Disabled — redundant, left as-is), `BravoSystemHealth` (Disabled), `MavenSchedulePosts` (Ready), `OASIS Chrome Audio Guard` (Ready).

## 5. Latent issues found (NOT fixed — candidates for follow-up)

1. **Same 23505-only pattern in ~12 other routes** in oasis-command-center (`grep -n "23505" app/ lib/`). Any of them breaks silently the same way IF its table lives on Turso. Each has its own dedup semantics, so they were deliberately not mass-edited. Recommended: adopt `isUniqueViolationError` per-route as each surface gets touched, or audit which tables are actually on Turso vs Supabase.
2. `claude-bridge-ping` had been crash-looping since ~2026-08-12 (rotated logs prove pre-existing) — the Turso migration likely broke self-pair days before the reboot made it visible.
3. `gh auth` token on this machine is **expired** (`gh auth status` → "token in default is invalid"). Git Credential Manager has no stored GitHub credential for non-interactive shells. Agent-driven pushes are blocked until CC re-auths (`gh auth login`) or pushes manually.

## 6. Resolution record (completed 2026-08-14)

1. ~~CC: push the fix~~ — **DONE.** CC pushed; commit `971484a` confirmed on `origin/main` (`git merge-base --is-ancestor 971484a origin/main` → true). Vercel deployed.
2. ~~Self-pair~~ — **DONE.** `_self_pair_if_needed()` returned `paired: True`; `~/.oasis/bridge_token` written (68 bytes, `oab_` + 64 hex). The fixed rotate branch fired against the pre-existing live pairing row — end-to-end proof of the code fix in production.
3. ~~Restart claude-bridge-ping~~ — **DONE.** `pm2 restart` + `pm2 reset`; status `online`, 0 restarts, error log stopped growing (last entry predates the restart).
4. ~~bridge.last_ping~~ — **DONE.** Advanced from stale 2026-08-11 to live (verified advancing at 21:49 UTC).
5. **STILL OPEN — CC decision:** retired vs repoint for the two quarantined Atlas trading vbs files (`tmp/startup-quarantine/`).
6. Optional hardening: re-auth `gh` so agents can push non-interactively; consider adopting `isUniqueViolationError` in the other routes listed in §5.1.

Final fleet state: 10/10 services + pm2-logrotate **online, 0 restarts across the board** (`pm2 jlist` verified).

## 7. Lessons / patterns worth keeping

- **Windows PM2 + Task Scheduler: never `RunLevel=Highest` for a user daemon.** The pipes it creates become unreachable from the interactive session and `pm2 kill` self-destructs on EPERM. Recovery must be PID-based, not pipe-based.
- **EPERM on `\\.\pipe\` ≠ AV interference.** Probe generic pipe create/connect first (script preserved in `tmp/pipe_probe.ps1`); if generic pipes work, suspect integrity-level mismatch from an elevated owner.
- **Postgres→Turso migrations break every `err.code === "23505"` check.** SQLite surfaces constraint violations by message, not code. Classify errors cross-DB (`isUniqueViolationError`, `isMissingTableError`) instead of matching one backend's codes.
- **Quarantine, don't delete** startup items and migrated files — `tmp/startup-quarantine/` keeps the change reversible until CC confirms intent.
- Bridge-lock arbitration (`scripts/core/bridge_lock.py` in CFO-Agent) worked exactly as designed — the PM2 copy correctly refused to clobber a live same-host lock. The fix was removing the orphaned holder, not weakening the lock.
