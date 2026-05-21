' PM2 Resurrect - hidden Windows logon launcher
'
' Task Scheduler should call this file with wscript.exe. The script invokes
' pm2.cmd through cmd.exe with windowStyle=0, so Windows never allocates a
' visible console window while PM2 restores the saved daemon list.
Option Explicit

Dim Shell, Fso, LogDir, Command
Set Shell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")

LogDir = Shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.pm2\startup-log"
If Not Fso.FolderExists(LogDir) Then
    Fso.CreateFolder(LogDir)
End If

Command = "cmd.exe /d /s /c " & _
    """" & """C:\Users\User\AppData\Roaming\npm\pm2.cmd""" & " resurrect" & _
    " >> """ & LogDir & "\resurrect-out.log""" & _
    " 2>> """ & LogDir & "\resurrect-err.log""" & """"

Shell.Run Command, 0, False
