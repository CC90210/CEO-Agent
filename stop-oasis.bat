@echo off
echo ===================================================
echo Shutting down OASIS Town Brains...
echo ===================================================
cd C:\Users\User\Business-Empire-Agent
call pm2 stop oasis-embed
call pm2 stop oasis-quest-sync
echo.
echo The Visual Town Server shuts down when you close its black window.
echo All background engines are safely powered off!
pause
