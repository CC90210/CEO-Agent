@echo off
rem bravo — Windows launcher. Add this directory to PATH.
rem Resolves the repo root relative to this file, then invokes bravo_cli.
setlocal
set "HERE=%~dp0"
set "REPO=%HERE%.."
python "%REPO%\bravo_cli\main.py" %*
