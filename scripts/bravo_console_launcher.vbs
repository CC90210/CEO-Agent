' Bravo Console launcher — opens ONE persistent console at logon tailing all
' pm2 process logs as a unified stream. Replaces the "dedicated terminal CC
' used to have at the bottom of the screen" that got closed and didn't reopen.
' wscript runs this with no console of its own, so the window below is the only
' one that appears.
'
' Routing: pm2 logs --lines 100 --raw streams stdout+stderr from every pm2
' process (bravo-scheduler, telegram bridges, event-router, etc.) into one
' merged feed. CC has a single place to glance at activity.
'
' ── Why this does NOT use Windows Terminal (measured 2026-08-13) ─────────────
' It used to, and it had been silently broken. Three separate faults stacked:
'
'   1. `wt.exe -w new new-window ...` — there is no `new-window` SUBCOMMAND
'      (the set is new-tab / split-pane / focus-tab / move-focus / move-pane),
'      so the command line failed to parse and nothing opened at all.
'   2. `cmd /k "pm2 logs --lines 100 --raw"` — wt strips those quotes while
'      parsing its own command line and hands cmd a mangled string; unquoted,
'      wt instead eats `--lines` / `--raw` as ITS OWN options. Marker-file
'      proof: `cmd /k echo X> f` ran, `cmd /k "echo X> f"` did not.
'   3. Even with both fixed and the command moved into a flagless .cmd file,
'      wt.exe launched from Shell.Run opened an EMPTY window every time — a new
'      WindowsTerminal process appeared, Shell.Run returned 0 with no error,
'      and the tab process was never created. The identical string run from a
'      shell worked. Four variants were tried (direct / via-cmd, PATH alias /
'      full path, hidden / visible); none spawned the tail from wscript.
'
' A plain console has none of that surface: no argument parser to fight, no
' WindowsApps execution alias to resolve. Verified working — cmd.exe -> node.exe
' streaming pm2 logs. If the Terminal chrome is ever wanted back, do it as a wt
' PROFILE (point the profile's commandline at bravo_console_tail.cmd), not with
' another round of command-line escaping.
Option Explicit

Dim Shell, Script, Cmd
Set Shell = CreateObject("WScript.Shell")

' The tail lives in a sibling .cmd so this launcher passes ONE quoted path and
' nothing can be reinterpreted. Derived from this script's own location so a
' moved or cloned repo still resolves.
Script = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\")) & "bravo_console_tail.cmd"
Cmd = "cmd /k """ & Script & """"

' WindowStyle codes: 0 hidden, 1 normal (visible), 2 minimized+active,
' 7 minimized+inactive. 1 so the log window is actually on screen at logon —
' the old minimized-and-inactive setting meant CC had to dig it out of the
' taskbar every boot, which defeated the point.
Shell.Run Cmd, 1, False
