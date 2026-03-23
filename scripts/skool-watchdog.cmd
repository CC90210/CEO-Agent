@echo off
REM Skool Engine Watchdog — ensures exactly ONE daemon is running.
REM
REM To set up via Task Scheduler (NO ELEVATION — prevents unkillable processes):
REM   schtasks /create /tn "SkoolWatchdog" /tr "C:\Users\User\Business-Empire-Agent\scripts\skool-watchdog.cmd" /sc minute /mo 5 /f
REM
REM IMPORTANT: Do NOT use /rl highest — elevated processes can't be killed normally.
REM Fixed 2026-03-23: Python-based watchdog with proper process detection + no-window daemon.

cd /d C:\Users\User\Business-Empire-Agent
.venv\Scripts\python.exe scripts\skool_watchdog.py
