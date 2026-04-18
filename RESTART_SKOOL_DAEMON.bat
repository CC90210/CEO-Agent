@echo off
REM Double-click this to syntax-check skool_engine.py and restart the daemon.
cd /d "%~dp0"
echo === Syntax check ===
py -3 -c "import ast; ast.parse(open(r'scripts/skool_engine.py').read()); print('syntax OK')"
if errorlevel 1 (
  echo SYNTAX ERROR -- aborting restart.
  pause
  exit /b 1
)
echo.
echo === Restarting daemon via watchdog ===
py -3 scripts\skool_watchdog.py
echo.
echo === New heartbeat ===
type tmp\skool_daemon.heartbeat
echo.
pause
