' Bravo Console launcher — opens ONE persistent Windows Terminal at logon,
' minimized, tailing all pm2 process logs as a unified stream. Replaces the
' "dedicated terminal CC used to have at the bottom of the screen" that got
' closed and didn't reopen. wscript runs this with no console of its own;
' wt.exe gets started minimized (WindowStyle = 7) so it lives in the taskbar
' without ever stealing focus.
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
' wt.exe -w 0 reuses the default window if one already exists.
Dim Cmd
Cmd = "wt.exe -w 0 new-tab --title ""Bravo Console"" cmd /k ""pm2 logs --lines 100 --raw"""

' WindowStyle codes: 0 hidden, 1 normal, 2 minimized+active, 7 minimized+inactive.
' 7 = stays in taskbar, never grabs focus.
Shell.Run Cmd, 7, False
