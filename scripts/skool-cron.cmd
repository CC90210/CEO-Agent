@echo off
REM Skool Community Engine - Daemon Launcher
REM Starts the Skool engine in daemon mode (runs continuously every 2 minutes).
REM
REM Auto-start on boot:
REM   schtasks /create /tn "SkoolEngine" /tr "C:\Users\User\Business-Empire-Agent\scripts\skool-cron.cmd" /sc onlogon /rl highest /f
REM
REM Or run manually: scripts\skool-cron.cmd
REM Stop: Ctrl+C in the terminal, or: taskkill /f /fi "windowtitle eq Skool*"

title Skool Community Engine

cd /d C:\Users\User\Business-Empire-Agent

REM Check if daemon is already running
.venv\Scripts\python.exe -c "import json,os; d=json.load(open('tmp/skool_daemon.pid')); os.kill(d['pid'],0); print('RUNNING')" 2>nul && (
    echo Skool daemon is already running.
    exit /b 0
)

echo Starting Skool Community Engine daemon...
.venv\Scripts\python.exe scripts\skool_engine.py daemon --interval 2
