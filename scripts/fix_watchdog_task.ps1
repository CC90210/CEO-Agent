# Fix SkoolWatchdog scheduled task — Run as Administrator
# Right-click this file > "Run with PowerShell" (as admin)

$pythonw = "C:\Users\User\AppData\Local\Programs\Python\Python312\pythonw.exe"
$script = "C:\Users\User\Business-Empire-Agent\scripts\skool_watchdog_silent.pyw"
$cwd = "C:\Users\User\Business-Empire-Agent"

$action = New-ScheduledTaskAction -Execute $pythonw -Argument $script -WorkingDirectory $cwd
Set-ScheduledTask -TaskName "SkoolWatchdog" -Action $action

Write-Host "SkoolWatchdog task updated successfully." -ForegroundColor Green
Write-Host "  Execute: $pythonw"
Write-Host "  Argument: $script"
Write-Host "  Working Directory: $cwd"
Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
