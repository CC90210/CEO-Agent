---
title: PM2 cold-start runbook for CC's Windows machine
date: 2026-05-16
audience: CC (operator) + anyone troubleshooting the SunBiz CRM substrate
status: ACTIVE
tags: [docs]
last_updated: 2026-07-19
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
| `sequence-runner` | SunBiz drip-campaign engine | Yes |
| `lender-response-classifier` | Gmail thread classifier | Yes |

## After a reboot

1. **Wait 30 seconds** after login — Windows takes a moment to settle services.
2. **Auto-start should run:** the `PM2 Resurrect` scheduled task replays the saved process list from `~/.pm2/dump.pm2`.
3. **Verify manually if needed:** `pm2 list` — every row should show `status: online`.
4. **Optional sanity ping:** open `https://oasisai.work/automations` — the Background Workers panel shows green for all 9 daemons within 60 seconds (next heartbeat tick).

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

## Auto-start at login - ACTIVE (popup fix, 2026-05-18)

Two scheduled tasks keep the substrate alive across reboots. There must be
exactly one PM2 resurrection entry point and exactly one Skool manager entry
point. Do not also keep `start-bravo.vbs` or `OASIS-Bravo-Bridge.vbs` in the
Windows Startup folder; those duplicate PM2's ownership and can reintroduce
visible terminal popups.

### Task 1: "PM2 Resurrect"
The Windows Task Scheduler entry **"PM2 Resurrect"** is registered and runs
`wscript.exe //B //Nologo C:\Users\User\Business-Empire-Agent\scripts\pm2_resurrect_hidden.vbs`
at every login. The VBS wrapper calls `pm2.cmd resurrect` with
`WshShell.Run(..., 0, False)`, so the PM2 restore happens without a visible
`cmd.exe` console. Settings:
- Trigger: at logon of `User`
- Hidden task
- Restart on failure: 3 attempts, 1 minute apart
- Replays `~/.pm2/dump.pm2` so the 10 daemons (atlas-telegram, bravo-scheduler, bravo-telegram, claude-bridge, claude-bridge-ping, dashboard-email-consumer, event-router, lender-response-classifier, maven-telegram, sequence-runner) come back online within 30s of login.

Verify:
```powershell
Get-ScheduledTask -TaskName "PM2 Resurrect" | Select-Object TaskName, State
```

If the task was deleted, re-register:
```powershell
$repo = "C:\Users\User\Business-Empire-Agent"
$vbs = "$repo\scripts\pm2_resurrect_hidden.vbs"
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\wscript.exe" -Argument "//B //Nologo `"$vbs`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "PM2 Resurrect" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
```

The old duplicate task **"PM2 Resurrect on Login"** must stay disabled. It used
`cmd.exe /c pm2.cmd resurrect ...` directly and was the popup-prone path.

### Task 2: "SkoolWatchdog" [ARCHIVED 2026-05-18 — do not re-register; see scripts/_archive/skool/README.md]
The Skool daemon is standalone (NOT in PM2 - owns its own DaemonLock). It is
managed by **"SkoolWatchdog"**, which runs every 5 minutes through
`pythonw.exe` and starts/restarts `skool_engine.py` with the no-console
triple guard (`pythonw.exe`, `CREATE_NO_WINDOW`, `SW_HIDE`).

- Execute: `C:\Users\User\AppData\Local\Programs\Python\Python312\pythonw.exe`
- Args: `C:\Users\User\Business-Empire-Agent\scripts\skool_watchdog_silent.pyw`
- Working dir: `C:\Users\User\Business-Empire-Agent`
- Trigger: every 5 minutes
- Console-free: yes (`pythonw.exe`)

If the task was deleted, re-register:
```powershell
$py = "C:\Users\User\AppData\Local\Programs\Python\Python312\pythonw.exe"
$script = "C:\Users\User\Business-Empire-Agent\scripts\skool_watchdog_silent.pyw"
$cwd = "C:\Users\User\Business-Empire-Agent"
$action = New-ScheduledTaskAction -Execute $py -Argument $script -WorkingDirectory $cwd
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date
$trigger.Repetition.Interval = "PT5M"
$trigger.Repetition.Duration = "P1D"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "SkoolWatchdog" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
```

Verify the daemon is alive:
```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "pythonw.exe" -and $_.CommandLine -match "skool_engine.py daemon" }
```

The old **"Skool Daemon"** task must stay disabled. It used `python.exe`
directly at login, which is console-capable on Windows.

The daemon also self-reports to `integrations_health` (`service = "skool_engine"`) every 5-minute cycle since Phase 7.4, so the Operations dashboard's Background Workers panel shows it green within one cycle of startup.

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

## Authorized auto-start entries (anything else = bug)

CC's reboot UX requirement: **exactly one minimized terminal in the taskbar after login. Nothing else visible. No pop-ups.** The whitelist below is what must be running. Anything pointing into this repo outside this list is a regression — disable it and file a fix.

### Whitelisted auto-start surfaces

| Surface | Entry | Visibility | Purpose |
|---|---|---|---|
| Task Scheduler | `PM2 Resurrect` | Hidden (wscript //B //Nologo) | Replays `~/.pm2/dump.pm2` so all 10 daemons come back online |
| Startup folder | `Bravo Console.lnk` → `bravo_console_launcher.vbs` | Minimized in taskbar (WindowStyle=7) | THE cockpit — `wt.exe` tailing `pm2 logs --raw` |
| Startup folder | `Chrome-RemoteDebug.lnk` | Visible Chrome window (its own GUI, not a terminal) | Chrome with `--remote-debugging-port=9222` for Browser Harness |

### Things that must NOT be in either surface

- `PM2 Resurrect on Login` (the `cmd.exe /c pm2.cmd resurrect …` variant) — keep disabled. It pops a cmd window.
- `start-bravo.vbs` / `OASIS-Bravo-Bridge.vbs` in the Startup folder — moved to `tmp/windows-startup-disabled/` 2026-05-18.
- Any direct `python.exe scripts\foo.py` in Startup or Task Scheduler — console-subsystem, always pops.

### Quick audit

```powershell
# Task Scheduler entries pointing into this repo
Get-ScheduledTask | Where-Object { $_.TaskName -match 'Bravo|Skool|Empire|PM2|Claude' -or $_.Actions.Execute -match 'Business-Empire' } | Select-Object TaskName, State, @{Name='Action';Expression={$_.Actions.Execute + ' ' + $_.Actions.Arguments}}

# Startup-folder shortcuts
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
```

If the result lists anything beyond the whitelist above, disable it (`schtasks /Change /TN "<name>" /DISABLE` or move the Startup shortcut to `tmp/windows-startup-disabled/`).

### The subprocess-popup root cause + safety net (2026-05-18)

Most "terminal pop-up" reports are NOT Task Scheduler or Startup-folder bugs — by 2026-05-18 those surfaces were already clean. The recurring cause was `subprocess.{Popen,run,...}` calls inside background daemons (PM2-managed, bridge-spawned, scheduler-managed) without `creationflags=CREATE_NO_WINDOW`. The parent daemon runs under `pythonw.exe` (no console). When it spawns a console-subsystem child (`python.exe`, `cmd.exe`, anything via `shell=True`), Windows allocates a fresh console for the child — the pop-up.

The fix is layered:

1. **Canonical wrappers** — `scripts/_subprocess_helpers.py` and `bravo_cli/_subprocess_helpers.py` export `safe_run`, `safe_popen`, `safe_daemon_popen` (CREATE_NO_WINDOW forced; STARTUPINFO+SW_HIDE auto-applied on `shell=True` / `.cmd` / `.bat` shims). Every daemon-spawned subprocess MUST go through these.

2. **Audit script** — `python scripts/audit_no_visible_subprocess.py` AST-walks the repo for any unflagged `subprocess.*` call. Exits 1 on any violation. Wire into CI / pre-push hooks.

3. **PreToolUse guard** — `scripts/hooks/subprocess_guard.py` blocks Edit/Write/MultiEdit on `.py` files that introduce a new unflagged call. Wired in `.claude/settings.local.json`. Default mode `report` for 7-day soak; flip `EMPIRE_HOOK_SUBPROCESS_GUARD=enforce` once stable.

To deliberately ALLOW a console-visible subprocess (an operator-facing CLI CC runs interactively), annotate the line with `# noqa: SUBPROCESS`. Don't strip the flag.

## Last-known-healthy reference (2026-05-16)

When `pm2 save` was run for this runbook:
- 9 daemons online (the 8 above + atlas-telegram + maven-telegram from sister agents)
- All heartbeats fresh in `bridge_pairings.last_seen_at`
- `state/event_router.cursor` advancing every 3 seconds
- `state/sequence_runner.cursor` advancing on `agent_events` arrival

If the system ever drifts from this state, this runbook is the rollback target.
