---
title: "SOP — Eliminating Random Terminal-Window Popups on Windows"
tags: [sop, windows, automation, cron, popup, pythonw, task-scheduler, daemon]
created: 2026-07-20
owner: bravo
applies_to: [any Windows machine running scheduled/cron automations, agent hooks, PM2 daemons]
related:
  - "[[skills/python-daemon-automation/SKILL]]"
  - "[[scripts/lib/subprocess_helpers]]"
  - "[[brain/CAPABILITIES]]"
---

# SOP — Eliminating Random Terminal-Window Popups on Windows

> **Symptom this SOP kills:** A PowerShell or CMD/console window flashes onto the
> screen at regular intervals (every minute / every 5 minutes / on a schedule) or
> on every agent action, interrupting whatever you're doing. This is the single
> most common "my automations are annoying me" complaint on Windows.

## 1. The one-sentence root cause

On Windows, `python.exe`, `cmd.exe`, `powershell.exe`, and `node.exe` are **console-subsystem** programs. When something that has **no console of its own** (a scheduled task, a `pythonw.exe`/PM2 daemon, an agent hook) launches one of them, Windows **allocates a brand-new console window** for the child — that's the popup. A job that fires every 5 minutes = a popup every 5 minutes.

Two things make the window disappear for good:

1. **Give the child no console to allocate** — run it under a windowless interpreter (`pythonw.exe`) or pass the `CREATE_NO_WINDOW` flag (`0x08000000`) when spawning it.
2. **When a real console is unavoidable, hide it** — run the task in a non-interactive session, launch it through a windowless host (VBScript `WScript.Shell.Run … 0`), or pass `STARTUPINFO` with `SW_HIDE`.

> `CREATE_NO_WINDOW` and `pythonw.exe` do **not** eat your output. The child still inherits the parent's stdout/stderr handles — logs and captured output are unaffected. It only stops a *new visible window* from being drawn.

## 2. There is no magic "one terminal"

The internal folklore is that we "consolidated everything into one System32/cmd terminal." There is **no single cmd window** doing that, and no such artifact exists in the repo. What actually eliminated the popups is the **windowless stack** in sections 4–7 below, most likely combined with the Windows system setting in section 8 (**Default terminal application → Windows Console Host**), which is the "system32" people remember. Treat the sections below as the real mechanism.

## 3. Diagnostic playbook — find *which* thing is popping

Do this **before** applying any fix. You cannot fix the popup until you know who spawns it. **The single highest-yield move is to name the culprit — do not skip to a fix.**

**Start here — catch the process at the next tick (most decisive, zero install, needs admin).** Log every process launch for one interval; the **executable + command line** tells you the fix, and the **parent process** tells you the source:
```powershell
Register-CimIndicationEvent -Query "SELECT * FROM Win32_ProcessStartTrace" -Action {
  $e = $Event.SourceEventArgs.NewEvent
  $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($e.ProcessID)" -EA SilentlyContinue).CommandLine
  "$(Get-Date -f o)  $($e.ProcessName)  PID=$($e.ProcessID)  PPID=$($e.ParentProcessID)  $cmd" |
    Add-Content $env:TEMP\popwatch.log }
# wait one full interval (~6 min), then read it:
Get-Content $env:TEMP\popwatch.log
```
Read the **parent (PPID)** to identify the source: `svchost.exe` / `taskeng.exe` → **Task Scheduler**; `wscript` / `explorer` → **Startup**; `node` → an **in-process scheduler** (node-cron / node-schedule — this leaves **no** Task Scheduler entry, which is exactly why process-capture beats enumerating tasks); `pm2` → **PM2**. For very short-lived flashes where the command line is gone before the follow-up query, use **Procmon** (Process Create filter), **Sysmon Event ID 1**, or enable **Audit Process Creation → Security event 4688** — all capture the full command line reliably. **Autoruns** (Sysinternals) lists Task Scheduler + Startup + Run/RunOnce + Services in a single view.

Then narrow by source:

1. **Time it.** Note the interval (every 1/5/15 min, on logon, on every keystroke in an agent). Interval → Task Scheduler or a cron loop. "Every agent action" → agent hooks. "On boot / always" → a Startup entry or PM2.
2. **Watch the window's title bar** the instant it appears — it usually shows the script path or interpreter (`…\python.exe`, a `.ps1` name, `node …`). That's your culprit.
3. **Task Scheduler** (most likely for a fixed interval): open `taskschd.msc` → Task Scheduler Library → sort by **Triggers**. Find the task whose trigger matches your interval. Read its **Actions** tab (what it runs) and **General** tab (is "Run whether user is logged on or not" set? is "Hidden" checked?). PowerShell equivalent:
   ```powershell
   Get-ScheduledTask | Where-Object { $_.Triggers.Repetition.Interval } |
     Select-Object TaskName, TaskPath,
       @{n='Interval';e={$_.Triggers.Repetition.Interval}},
       @{n='LogonType';e={$_.Principal.LogonType}},
       @{n='Hidden';e={$_.Settings.Hidden}} | Format-Table -Auto
   ```
4. **Startup folder / logon:** `shell:startup` (per-user) and `shell:common startup` (all users); also `Get-CimInstance Win32_StartupCommand`.
5. **Agent hooks** (Claude Code, or any agent that runs shell commands on events): open its settings (`.claude/settings.local.json` / `settings.json`) and look at every hook `command`. Any that starts with **`python `** (not `pythonw`) pops a window on every event.
6. **PM2 / node daemons:** `pm2 list`, then `pm2 describe <name>` — check the interpreter.
7. **What you don't own:** some popups come from third-party apps (RGB/fan control, dictation tools, driver "repair" scripts). You can't edit those — use the belt-and-suspenders hider in section 7.

## 4. Fix by source — the decision table

| Culprit | Fix | Section |
|---|---|---|
| Windows **Scheduled Task** | Run windowless interpreter + "Run whether user is logged on or not" **or** Hidden **or** VBS launcher | 4a |
| **Agent hook** (`python …` on every event) | Change hook command to `pythonw …` | 4b |
| **PM2** daemon | `interpreter: pythonw.exe` + `windowsHide: true` | 4c |
| **In your own code** (`subprocess.run/Popen`) | Add `creationflags=CREATE_NO_WINDOW`; `.cmd`/`.bat`/`shell=True` also needs `STARTUPINFO`+`SW_HIDE` | 4d |
| **npm/node `.cmd` shim** | Invoke `node.exe` on the underlying JS, bypass the `.cmd` | 4d |
| **App you don't control** | Runtime window-hider daemon | 7 |

### 4a. Scheduled Task (the every-5-minutes case)

Strongest lever first. **Any one of these** kills the popup; combine for belt-and-suspenders.

**Option 1 — run it in session 0 (recommended, invisible by construction).** Set the task to **"Run whether user is logged on or not."** A task in this mode runs in a non-interactive session and *cannot draw a window on your desktop*, period.
```powershell
# Requires admin. Replace <TaskName>.
$p = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType S4U -RunLevel Highest
Set-ScheduledTask -TaskName "<TaskName>" -Principal $p
```

**Option 2 — mark the task Hidden + run a no-console interpreter.** `schtasks /Create` has **no** Hidden switch; you must set it via the cmdlet:
```powershell
$t = Get-ScheduledTask -TaskName "<TaskName>"
$t.Settings.Hidden = $true
Set-ScheduledTask -InputObject $t
```
And make the **Action** run the windowless interpreter with a **full path** (Task Scheduler does not inherit `PATH` — a bare `python`/`pythonw` fails with `0x80070002`):
```
Program/script:  C:\Users\<you>\AppData\Local\Programs\Python\Python312\pythonw.exe
Add arguments:   C:\path\to\your\script.py
Start in:        C:\path\to
```
(For a Node task, there is no windowless node — use Option 1, or the VBS launcher in Option 3, or start it via a `.py`/`.ps1 -WindowStyle Hidden` wrapper.)

**Option 3 — launch through a windowless VBScript host.** VBScript's `WScript.Shell.Run(cmd, 0, False)` — the `0` is window style **hidden**. The `.vbs` host itself has no console, so nothing flashes. Point the task's Action at `wscript.exe your-launcher.vbs`:
```vbscript
' run-hidden.vbs  — runs the command with a hidden window
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\job.ps1", 0, False
```

### 4b. Agent hooks (Claude Code and similar)

The agent harness spawns each hook `command` through `cmd /c …`, so the console is allocated **before your script even runs** — `CREATE_NO_WINDOW` inside the script is too late and cannot help. **Fix at the config level:** change the interpreter in the hook command from `python` to `pythonw`.

```jsonc
// .claude/settings.local.json — BEFORE (pops a window on every hook fire)
"command": "python C:/path/to/hook.py"
// AFTER (windowless)
"command": "pythonw C:/path/to/hook.py"
```
Hooks fire on *every* prompt and *every* tool call, so this is the highest-frequency popup source on an agent workstation. `pythonw` still receives stdin and returns exit codes identically.

### 4c. PM2 daemons

On Windows, `windowsHide: true` alone is **unreliable across PM2 versions**. The guarantee is to run the daemon under `pythonw.exe`:
```js
// ecosystem.config.js
const PYTHONW = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'pythonw.exe');
{
  name: 'my-daemon',
  script: 'scripts/my_daemon.py',
  interpreter: PYTHONW,   // no-console interpreter — popup-suppressed even on crash-loop restart
  windowsHide: true,      // belt-and-suspenders
}
```

### 4d. In your own code (`subprocess`)

Every recurring popup that originates in code is the same bug: a `subprocess.run/Popen` inside a background process, missing the flag.

```python
import subprocess, sys, os

CREATE_NO_WINDOW = 0x08000000          # child gets no console window
DETACHED_PROCESS = 0x00000008          # + this for daemons that outlive the parent

# Plain child:
subprocess.run(cmd, creationflags=CREATE_NO_WINDOW)

# .cmd/.bat/powershell/shell=True can still flash a conhost before handoff —
# also pass a hidden STARTUPINFO:
si = subprocess.STARTUPINFO()
si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
si.wShowWindow = subprocess.SW_HIDE
subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, startupinfo=si)

# Long-lived Python child → run it under pythonw, which physically cannot
# allocate a console:
pythonw = sys.executable.replace("python.exe", "pythonw.exe")
subprocess.Popen([pythonw, "daemon.py"], creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS)
```

**npm/node `.cmd` shims** (`playwright.cmd`, `npm.cmd`, etc.) can flash a `cmd.exe` window before handing off to `node.exe`, even with `CREATE_NO_WINDOW`. Bypass the shim by invoking `node.exe` directly on the real JS entrypoint that the `.cmd` wraps.

**A plain Node scheduled task** (running `node.exe` directly) is still console-subsystem — Node has no windowless build like `pythonw`. Hide it via session 0 (§4a Option 1), a VBS launcher (§4a Option 3), or, if you control the code, `child_process.spawn(cmd, args, { windowsHide: true, detached: true })`. On **Windows 11 22H2+**, `conhost.exe --headless <command>` runs any console command with no visible window and is a clean wrapper to put in a task's Action for node/cmd/anything.

**Make it impossible to forget:** wrap `subprocess` once in a `safe_run` / `safe_popen` helper that injects `CREATE_NO_WINDOW` (and the hidden `STARTUPINFO` for shells) by default, and route every call through it. See `scripts/lib/subprocess_helpers.py` for the canonical implementation.

## 5. Keep it from regressing (enforcement)

A fix that isn't enforced drifts back within weeks (this repo re-accumulated 9 unflagged calls between audits). Three guards keep it green:

1. **AST audit in CI/pre-commit** — walk every `.py` file, fail the build on any `subprocess.{run,Popen,call,check_output}` that lacks a windowless flag and isn't in a POSIX-only branch. See `scripts/audit_no_visible_subprocess.py`. Run it: `python scripts/audit_no_visible_subprocess.py`.
2. **A pre-write guard hook** that blocks the agent from *adding* a new un-flagged subprocess call in the first place (`scripts/hooks/subprocess_guard.py`).
3. **Central helpers** (`safe_run`/`safe_popen`/`safe_daemon_popen`) so the correct behavior is the default and call sites can't silently omit the flag.

## 6. Verify the fix

```powershell
# 1. Watch for one full interval (e.g. 5 min) — no window should appear.
# 2. Confirm the task now runs hidden / in session 0:
Get-ScheduledTask -TaskName "<TaskName>" |
  Select-Object @{n='Hidden';e={$_.Settings.Hidden}},
                @{n='LogonType';e={$_.Principal.LogonType}}
# 3. Confirm it still actually runs (check its last result + your job's log):
Get-ScheduledTaskInfo -TaskName "<TaskName>" | Select LastRunTime, LastTaskResult
```
"No window" is only half the proof — always confirm the job **still executed** (last result `0`, log advanced). Hiding a task that silently stopped running is a worse outcome than the popup.

## 7. Belt-and-suspenders: hide windows you don't own

For popups from third-party apps you cannot edit (RGB/fan utilities, dictation tools, vendor "repair" scripts), run a tiny background daemon that instantly hides any throwaway console the instant it appears:

- Register a `SetWinEventHook(EVENT_OBJECT_SHOW)` callback.
- On each show event, check the process (name in `{powershell.exe, pwsh.exe, conhost.exe}`, or window class `ConsoleWindowClass`), and if it matches a known-noisy source, call `ShowWindow(hwnd, SW_HIDE)`.
- Run the hider itself windowless — a Startup `.vbs` (`WScript.Shell.Run …, 0`) or a Hidden `ONLOGON` scheduled task under `pythonw`.
- Protect the windows that were already open when it started, so you never hide a real terminal you're using.

Reference implementation: `scripts/state/powershell_flash_suppressor.py` (`install` / `start` / `status` / `once`).

## 8. The system-level knob ("the System32 setting")

Windows 11 → **Settings → System → For developers → Terminal**, or **Windows Terminal → Settings → Startup → Default terminal application**. Set **"Default terminal application" to "Windows Console Host"** (`conhost.exe`, which lives in `System32`) rather than "Windows Terminal." Windows Terminal always opens a full tabbed window and ignores `SW_HIDE` for its host in some versions; the classic Console Host honors hidden/minimized window styles, so `SW_HIDE`/VBS-hidden launches behave. This setting is almost certainly the "system32/cmd" people remember consolidating onto.

## 9. Anti-patterns (don't)

- **Bare `python`/`pythonw` in a Task Scheduler action** → `0x80070002` (no PATH). Always full path.
- **Relying on `windowsHide: true` alone** in PM2 → unreliable across versions. Use `pythonw`.
- **`CREATE_NO_WINDOW` inside an agent-hook script** → too late; the harness already allocated the console via `cmd /c`. Fix the hook command's interpreter instead.
- **Disabling / deleting the annoying task** without checking what it does → you may kill a real automation. Hide it or run it in session 0 instead.
- **Hiding a task without verifying it still runs** → silent failure is worse than a visible popup.
