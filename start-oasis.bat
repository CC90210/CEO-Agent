@echo off
title OASIS Town Server
echo ===================================================
echo Booting OASIS Town Simulation Engine & Brains...
echo ===================================================

echo Starting the Python Brain Daemon...
cd C:\Users\User\Business-Empire-Agent
call pm2 start scripts/oasis_embed_server.py --name oasis-embed --interpreter python

echo Starting the Quest Log Sync...
call pm2 start scripts/quest_publisher.py --name oasis-quest-sync --interpreter python -- loop --interval 60

echo Starting the Visual Town Server...
cd C:\Users\User\APPS\oasis-town
set PATH=C:\Users\User\AppData\Local\nvm\v20.18.0;%PATH%
npm run dev
