# Regression: Leaked Bash Background Tasks Spammed Console Popups Every 8s (2026-05-09)

## What went wrong
CC saw a terminal window "continuously popping up" on screen for hours. Two prior sessions had failed to identify the source. Popup-watcher diagnostic ran for 24 minutes and captured 168 spawn events — 108 of them were `cmd /d /s /c vc ls --yes` at ~10s intervals. Root cause: **three orphan Bash polling loops** (`until [ "$(npx vercel ls --yes ...)" = "Ready" ]; do sleep 8; done`) and one `until grep "Ready in" /tmp/cc-dev2.log` loop, all spawned earlier in the session via `Bash(run_in_background: true)` and never cleaned up. Each was a leftover from "wait for deploy" / "start dev server" tasks in earlier turns where `KillShell` was never called when the loop terminated semantically (the deploy went Ready hours ago) but the bash process kept polling forever.
- Each `npx vercel ls --yes` sh

## The behavior that must NOT recur
1. **Always emit a sentinel** — long-polling background bash loops must write a file when their condition is met (`touch /tmp/build-ready` after `until grep "Ready in"…`) AND the agent must check for that sentinel before moving on, then call `KillShell` on the background task. Without the explicit kill, the loop polls until the user reboots.
2. **Audit running bash on session boundary** — `Get-CimInstance Win32_Process -Filter "Name='bash.exe'" | Where-Object { $_.ParentProcessId -eq <claude.exe pid> }` enumerates all background-task children of the current Claude Code instance. Should be a one-liner the agent runs before declaring a task complete.
3. **Patched defensive subprocess gaps in scripts run periodically** — `scripts/core/system_health_check.py:_run` and `scripts/core/cron_dispat
