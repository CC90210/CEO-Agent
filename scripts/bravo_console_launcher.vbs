' Opens one visible, read-only Bravo fleet log console at login.
' The command file reads fleet_watchdog-owned logs directly; it does not start
' or depend on a second process supervisor.
Option Explicit

Dim Shell, Script, Cmd
Set Shell = CreateObject("WScript.Shell")
Script = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\")) & "bravo_console_tail.cmd"
Cmd = "cmd /k """ & Script & """"
Shell.Run Cmd, 1, False
