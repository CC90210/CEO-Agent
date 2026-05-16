---
title: PM2 cold-start runbook for CC's Windows machine
date: 2026-05-16
audience: CC (operator) + anyone troubleshooting the SunBiz CRM substrate
status: ACTIVE
---

# Cold-start procedure

When CC reboots his Windows machine (CCPC), the 9 PM2 daemons that drive the SunBiz CRM substrate need to come back online before the dashboard can drive real leads end-to-end. This runbook covers the boot path + the verification checklist.

## What needs to be running

| Daemon | Owns | Auto-restart if dies? |
|---|---|---|
| `bravo-scheduler` | Empire cron (`cron_jobs` table) — Lead Follow-up Check, Stripe Revenue Sync, Funnel Fast-Poll, etc. | Yes (PM2 watchdog) |
| `bravo-telegram` | Telegram bridge to Bravo chat | Yes |
| `claude-bridge` | localhost:9100 chat HTTP server + tool proxy | Yes |
| `claude-bridge-ping` | Heartbeat + tenant cron poller | Yes |
| `event-router` | V6 cross-agent event bus tail | Yes |
| `override-consumer` | exec-override approvals → local state DB | Yes |
| `sequence-runner` | SunBiz drip-campaign engine | Yes |
| `lender-response-classifier` | Gmail thread classifier | Yes |

Plus the standalone Skool daemon (NOT in PM2 — owns its own DaemonLock; auto-started by Windows scheduled task).

## After a reboot

1. **Wait 30 seconds** after login — Windows takes a moment to settle services.
2. **Open a terminal:** `pm2 resurrect` — replays the saved process list from `~/.pm2/dump.pm2`.
3. **Verify:** `pm2 list` — every row should show `status: online`.
4. **Optional sanity ping:** open `https://agent-dashboard-cc90210.vercel.app/automations` — the Background Workers panel shows green for all 9 daemons within 60 seconds (next heartbeat tick).

If any daemon shows `errored` or `stopped`:
- `pm2 logs <name> --lines 50` — check the most recent stderr.
- `pm2 restart <name>` — most transient failures clear on restart.
- If a daemon won't stay up: file a fast hotfix; do NOT run real leads against a degraded substrate.

## Persisting state changes

After ANY PM2 reload / add / remove (`pm2 reload <name>`, `pm2 start ecosystem.config.js`, `pm2 delete <name>`):

```
pm2 save
```

This rewrites `~/.pm2/dump.pm2` with the current process list. Without `pm2 save`, the next reboot resurrects to a stale snapshot.

## Auto-start at login — ACTIVE (Phase 7.4, 2026-05-17)

The Windows Task Scheduler entry **"PM2 Resurrect"** is registered and runs `C:\Users\User\AppData\Roaming\npm\pm2.cmd resurrect` at every login. Settings:
- Trigger: at logon of `User`
- Hidden window (no terminal popup — Phase 7.4 fixed the "non-stop terminal windows" complaint)
- Restart on failure: 3 attempts, 1 minute apart
- Replays `~/.pm2/dump.pm2` so the 10 daemons (atlas-telegram, bravo-scheduler, bravo-telegram, claude-bridge, claude-bridge-ping, event-router, lender-response-classifier, maven-telegram, override-consumer, sequence-runner) come back online within 30s of login.

Verify:
```powershell
Get-ScheduledTask -TaskName "PM2 Resurrect" | Select-Object TaskName, State
```

If the task was deleted, re-register:
```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\User\AppData\Roaming\npm\pm2.cmd" -Argument "resurrect"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "PM2 Resurrect" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
```

## Verifying `dump.pm2` is fresh

```
dir %USERPROFILE%\.pm2\dump.pm2
```

The `LastWriteTime` should be recent — within minutes of the last `pm2 save`. If it's days old, the snapshot is stale and `pm2 resurrect` will spawn an outdated daemon set.

## Bridge token + .env.agents

PM2 daemons read credentials from `c:\Users\User\Business-Empire-Agent\.env.agents` via `secret_loader`. If the file is missing or unreadable, daemons fail at startup with `secret_loader: missing required env keys`. Verify with:

```
type ".env.agents" | findstr SUPABASE_URL
```

(Should print one line. If empty, the file isn't where the daemons expect it.)

## What to do if Telegram alerts say a daemon is unhealthy

The `tg_notify(severity=error)` wiring (added Saturday per Round 3 plan) sends a Telegram message when a daemon emits an error-severity event. On receipt:

1. Open `/automations` on the dashboard — confirm the daemon shows red in Background Workers.
2. `pm2 logs <name> --err --lines 100` — read the actual error.
3. Common causes:
   - Supabase auth expired → check `BRAVO_SUPABASE_SERVICE_ROLE_KEY` in `.env.agents`.
   - Anthropic API quota → check `state/anthropic_quota.log`.
   - Disk full → `dir %TEMP%` and clean if >80% full.
4. Fix the underlying issue → `pm2 restart <name>` → verify green.

## Last-known-healthy reference (2026-05-16)

When `pm2 save` was run for this runbook:
- 9 daemons online (the 8 above + atlas-telegram + maven-telegram from sister agents)
- All heartbeats fresh in `bridge_pairings.last_seen_at`
- `state/event_router.cursor` advancing every 3 seconds
- `state/sequence_runner.cursor` advancing on `agent_events` arrival

If the system ever drifts from this state, this runbook is the rollback target.
