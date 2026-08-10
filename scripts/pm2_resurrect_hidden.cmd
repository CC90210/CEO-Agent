@echo off
rem PM2 Resurrect helper - called hidden by pm2_resurrect_hidden.vbs
rem
rem 2026-08-07 fix: under the S4U boot trigger neither HOME nor HOMEPATH is
rem set, so PM2 silently defaulted to C:\etc\.pm2, found no dump.pm2, and
rem left an empty elevated daemon squatting on the global \\.\pipe\rpc.sock,
rem which blocked every user-session pm2 client with
rem "connect EPERM //./pipe/rpc.sock". Pin PM2_HOME/HOME and kill any stale
rem daemon before resurrecting the saved process list.
set "PM2_HOME=C:\Users\User\.pm2"
set "HOME=C:\Users\User"
set "HOMEDRIVE=C:"
set "HOMEPATH=\Users\User"
set "USERPROFILE=C:\Users\User"

set "LOGDIR=C:\Users\User\.pm2\startup-log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

call "C:\Users\User\AppData\Roaming\npm\pm2.cmd" kill >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
timeout /t 3 /nobreak >nul
call "C:\Users\User\AppData\Roaming\npm\pm2.cmd" resurrect >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
call "C:\Users\User\AppData\Roaming\npm\pm2.cmd" save >> "%LOGDIR%\resurrect-out.log" 2>> "%LOGDIR%\resurrect-err.log"
