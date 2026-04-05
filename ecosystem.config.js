/**
 * PM2 Ecosystem Config — Bravo Business Operations Daemon
 *
 * Usage:
 *   pm2 start ecosystem.config.js
 *   pm2 stop bravo-scheduler
 *   pm2 restart bravo-scheduler
 *   pm2 logs bravo-scheduler
 *
 * Auto-start on reboot:
 *   pm2 startup
 *   pm2 save
 */
module.exports = {
  apps: [
    {
      name: "bravo-scheduler",
      script: "scripts/scheduler.py",
      interpreter: "C:\\Users\\User\\Business-Empire-Agent\\.venv\\Scripts\\python.exe",
      cwd: "C:\\Users\\User\\Business-Empire-Agent",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 30000, // 30s between restarts
      env: {
        PYTHONIOENCODING: "utf-8",
      },
      // Log management
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "tmp/pm2-scheduler-error.log",
      out_file: "tmp/pm2-scheduler-out.log",
      merge_logs: true,
      max_size: "10M", // Rotate logs at 10MB
    },
  ],
};
