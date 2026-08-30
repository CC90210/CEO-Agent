' PM2 Resurrect - hidden Windows logon launcher
'
' Task Scheduler should call this file with wscript.exe. The script invokes
' pm2_resurrect_hidden.cmd through cmd.exe with windowStyle=0, so Windows
' never allocates a visible console window while PM2 restores the saved
' daemon list. All logic (PM2_HOME pinning, stale-daemon kill, resurrect,
' save) lives in the .cmd file - keep it there, not inline here.
Option Explicit

Dim Shell
Set Shell = CreateObject("WScript.Shell")

Shell.Run "cmd.exe /d /s /c ""C:\Users\User\Business-Empire-Agent\scripts\pm2_resurrect_hidden.cmd""", 0, False
