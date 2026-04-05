/**
 * PM2 Ecosystem Config — Bravo Business Operations
 *
 * Usage:
 *   pm2 start ecosystem.config.js
 *   pm2 stop all / pm2 restart all
 *   pm2 logs bravo-telegram
 *
 * Auto-start on reboot:
 *   pm2 startup
 *   pm2 save
 */
const os = require('os');
const path = require('path');

const IS_MAC = process.platform === 'darwin';
const PROJECT_ROOT = IS_MAC
    ? path.join(os.homedir(), 'Downloads', 'business-empire-agent')
    : 'C:\\Users\\User\\Business-Empire-Agent';

module.exports = {
  apps: [
    {
      name: "bravo-scheduler",
      script: "scripts/scheduler.py",
      interpreter: IS_MAC ? "python3" : "python",
      cwd: PROJECT_ROOT,
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 30000,
      env: {
        PYTHONIOENCODING: "utf-8",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "tmp/pm2-scheduler-error.log",
      out_file: "tmp/pm2-scheduler-out.log",
      merge_logs: true,
      max_size: "10M",
    },
    {
      name: "bravo-telegram",
      script: "telegram_agent.js",
      cwd: PROJECT_ROOT,
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      kill_timeout: 5000,
      env: {
        NODE_ENV: "production",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "tmp/pm2-telegram-error.log",
      out_file: "tmp/pm2-telegram-out.log",
      merge_logs: true,
      max_size: "10M",
    },
  ],
};
