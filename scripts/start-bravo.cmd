@echo off
:: Bravo Scheduler - Auto-start on Windows login
:: This script is registered with Windows Task Scheduler to run at logon.
:: It resurrects the PM2 process list (which includes bravo-scheduler).

pm2 resurrect
