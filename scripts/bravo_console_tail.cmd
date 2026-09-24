@echo off
REM Bravo Console tail — direct view of watchdog-owned daemon logs.
REM PM2 is retired on Windows. Calling `pm2 logs` here silently resurrected
REM its daemon at every login, so this viewer now reads the canonical logs that
REM fleet_watchdog.py owns and never starts or supervises a service itself.
title Bravo Console
cd /d "%~dp0.."

python "%~dp0ops\fleet_watchdog.py" status
if errorlevel 1 (
    echo.
    echo Fleet status is unavailable. See state\fleet_watchdog.log.
)

echo.
echo Streaming state\logs\daemon-*.log. Close this window to stop viewing.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$logs = Get-ChildItem -LiteralPath 'state\logs' -Filter 'daemon-*.log' -File -ErrorAction SilentlyContinue; if (-not $logs) { Write-Error 'No watchdog daemon logs exist yet.'; exit 2 }; Get-Content -Path ($logs.FullName) -Tail 100 -Wait"
exit /b %ERRORLEVEL%
