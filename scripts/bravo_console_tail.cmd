@echo off
REM Bravo Console tail — the pm2 log stream CC keeps on screen.
REM
REM This file exists to keep `--lines` / `--raw` away from wt.exe's command-line
REM parser. Passing them inline (`wt ... cmd /k pm2 logs --lines 100 --raw`)
REM makes wt try to consume them as ITS OWN options, and quoting them instead
REM (`cmd /k "pm2 logs ..."`) makes wt strip the quotes and mangle the command.
REM Either way the tab opened EMPTY. A batch file has no flags for wt to
REM misread, so the launcher passes a single bare path and nothing can be
REM reinterpreted. Verified 2026-08-13.
REM
REM 2026-08-14 fail-safe: at logon this window can race the "PM2 Resurrect"
REM scheduled task and hit `connect EPERM //./pipe/rpc_User.sock`. The old
REM behavior fell through to `cmd /k`, leaving a stuck error window on the
REM desktop. Now: retry 4x with 15s gaps (covers the resurrect race), and if
REM it still fails, append to bravo-console-fail.log, ping CC on Telegram,
REM and exit — no orphaned error terminal.
title Bravo Console
cd /d "%~dp0.."

set "FAILLOG=C:\Users\User\.pm2\startup-log\bravo-console-fail.log"
set ATTEMPTS=0

:try
pm2 logs --lines 100 --raw
set CODE=%ERRORLEVEL%
if "%CODE%"=="0" exit /b 0
set /a ATTEMPTS+=1
if %ATTEMPTS% LSS 4 (
    timeout /t 15 /nobreak >nul
    goto :try
)

>>"%FAILLOG%" echo [%DATE% %TIME%] pm2 logs failed after %ATTEMPTS% attempts, last exit code %CODE%
python "%~dp0notify.py" "Bravo Console: pm2 logs failed at logon - see .pm2/startup-log/bravo-console-fail.log" >>"%FAILLOG%" 2>&1
exit /b %CODE%
