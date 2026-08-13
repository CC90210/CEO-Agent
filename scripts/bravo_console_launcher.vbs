' Bravo Console launcher — opens ONE persistent Windows Terminal at logon,
' minimized, tailing all pm2 process logs as a unified stream. Replaces the
' "dedicated terminal CC used to have at the bottom of the screen" that got
' closed and didn't reopen. wscript runs this with no console of its own.
' wt.exe is started VISIBLE (WindowStyle = 1) so the log window is actually
' on screen at logon — the earlier minimized-and-inactive setting (7) meant CC
' had to go find it in the taskbar every boot, which defeated the point.
'
' Title is fixed to "Bravo Console" so CC can find it on the taskbar.
'
' Routing: pm2 logs --lines 100 --raw streams stdout+stderr from every pm2
' process (bravo-scheduler, telegram bridges, event-router, etc.) into one
' merged feed. CC has a single place to glance at activity.
Option Explicit

Dim Shell
Set Shell = CreateObject("WScript.Shell")

' Use Windows Terminal if available; fall back to plain cmd otherwise.
'
' Argument shape matters: `-w new` is the WINDOW SELECTOR (open a new window),
' and it must be followed by a real wt SUBCOMMAND. The valid set is
' new-tab / split-pane / focus-tab / move-focus / move-pane — there is NO
' `new-window` subcommand, so `-w new new-window ...` fails to parse and the
' launcher dies silently at logon with no console ever appearing.
Dim Cmd
Cmd = "wt.exe -w new new-tab --title ""Bravo Console"" cmd /k ""pm2 logs --lines 100 --raw"""

' WindowStyle codes: 0 hidden, 1 normal (visible, pops up), 2 minimized+active, 7 minimized+inactive.
Shell.Run Cmd, 1, False
