@echo off
rem PM2 Resurrect helper - called hidden by pm2_resurrect_hidden.vbs
rem
rem 2026-08-07 fix: under the S4U boot trigger neither HOME nor HOMEPATH is
rem set, so PM2 silently defaulted to C:\etc\.pm2, found no dump.pm2, and
rem left an empty elevated daemon squatting on the global \\.\pipe\rpc.sock,
rem which blocked every user-session pm2 client with
rem "connect EPERM //./pipe/rpc.sock". Pin PM2_HOME/HOME and kill any stale
rem daemon before resurrecting the saved process list.
rem
rem 2026-08-14 fix: `pm2 kill` alone cannot recover from EPERM — it must
rem CONNECT to the same wedged named pipe before it can kill anything, so it
rem dies with the same error and the stale daemon survives. Sweep stale PM2
rem daemons BY PID first (any node.exe running pm2\lib\Daemon.js or a
rem ProcessContainerFork wrapper), clear stale pid files, THEN pm2 kill /
rem resurrect. NOTE: this sweep can only kill daemons running in the caller's
rem own security context — an ELEVATED daemon (the 2026-08-14 incident, caused
rem by this task running with RunLevel=Highest) must be removed from an
rem elevated shell. The scheduled task now runs with RunLevel=Limited so the
rem daemon it spawns is always reachable from CC's interactive session.
set "PM2_HOME=C:\Users\User\.pm2"
set "HOME=C:\Users\User"
set "HOMEDRIVE=C:"
set "HOMEPATH=\Users\User"
set "USERPROFILE=C:\Users\User"

set "LOGDIR=C:\Users\User\.pm2\startup-log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem --- PID-based stale-daemon sweep (runs before pm2 kill on purpose) ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { $_.CommandLine -match 'pm2[\\/]+lib[\\/]+Daemon\.js|ProcessContainerFork' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output (\"killed stale pm2 pid \" + $_.ProcessId) }" >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
if exist "%PM2_HOME%\pm2.pid" del /f "%PM2_HOME%\pm2.pid" >> "%LOGDIR%\resurrect-out.log" 2>&1
if exist "%PM2_HOME%\pids\*.pid" del /f "%PM2_HOME%\pids\*.pid" >> "%LOGDIR%\resurrect-out.log" 2>&1
timeout /t 2 /nobreak >nul

call "C:\Users\User\AppData\Roaming\npm\pm2.cmd" kill >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
timeout /t 3 /nobreak >nul
call "C:\Users\User\AppData\Roaming\npm\pm2.cmd" resurrect >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
call "C:\Users\User\AppData\Roaming\npm\pm2.cmd" save >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
