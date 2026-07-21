/**
 * Standalone PM2 ecosystem for the Breeze Advance go-live watch (2026-07-21).
 * Kept OUT of the main ecosystem.config.js because it's a client-app monitor
 * for onboarding week, not core Bravo substrate — remove when go-live settles:
 *   pm2 delete breeze-live-watch && pm2 save
 *
 * Start:  pm2 start breeze_watch.ecosystem.js && pm2 save
 * Args go through the `args` array (not `-- loop`) because PM2's CLI arg parser
 * mis-handles `--flags` after `--` on Windows PowerShell.
 */
const path = require("path");
const ROOT = "C:\\Users\\User\\Business-Empire-Agent";
// pythonw = no console window, matching every other Windows daemon in the fleet.
const PYTHONW = path.join(ROOT, ".venv", "Scripts", "pythonw.exe");

module.exports = {
  apps: [
    {
      name: "breeze-live-watch",
      script: "scripts/breeze_live_watch.py",
      args: ["loop", "--interval", "300"],
      interpreter: PYTHONW,
      cwd: ROOT,
      watch: false,
      autorestart: true,
      max_restarts: 20,
      restart_delay: 10000,
      windowsHide: true,
      env: { PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "tmp/pm2-breeze-live-watch-error.log",
      out_file: "tmp/pm2-breeze-live-watch-out.log",
      merge_logs: true,
      max_size: "10M",
    },
  ],
};
