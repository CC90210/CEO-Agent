/**
 * PM2 Ecosystem Config — Bravo Business Operations (v2, 2026-04-11)
 *
 * HARD RULES (see brain/CROSS_MACHINE_SYNC.md Rule 2):
 *   - bravo-scheduler runs on WINDOWS ONLY. Never Mac. Never Linux.
 *     Running a second scheduler against the same Supabase cron_jobs table
 *     causes every cron job to fire twice. Incident 2026-04-11 cost ~40h
 *     of duplicate Telegram routing before we caught it.
 *
 *   - bravo-telegram is defined for BOTH platforms but only ONE runs at
 *     a time. Windows is the default (always-on desktop, low latency).
 *     Mac is a cold-standby — start it manually only when CC wants to
 *     control Telegram from the MacBook (travel, demo, testing).
 *     Two bridges on the same TELEGRAM_BOT_TOKEN = random message routing.
 *
 *   - The Skool daemon is NOT in this ecosystem. It runs as a standalone
 *     process with its own OS-level DaemonLock (msvcrt on Windows). Moving
 *     it into PM2 would fight the lock. Windows only, started via:
 *       python scripts/skool_engine.py daemon --interval 5
 *
 * USAGE:
 *
 *   # Windows (CCPC) — control center, runs scheduler + skool + telegram
 *   cd /c/Users/User/Business-Empire-Agent
 *   pm2 start ecosystem.config.js --only bravo-scheduler
 *   pm2 start ecosystem.config.js --only bravo-telegram
 *   (skool runs standalone, not via PM2)
 *   pm2 save
 *
 *   # Mac — cold standby telegram bridge only
 *   cd ~/Downloads/business-empire-agent
 *   pm2 start ecosystem.config.js --only bravo-telegram   # only when wanted
 *   pm2 stop bravo-telegram                                # when done
 *   pm2 save                                                # persist state
 *
 * TELEGRAM HANDOFF PROTOCOL (Windows <-> Mac):
 *   # Hand off FROM Windows TO Mac:
 *   ssh cc-mac "cd ~/Downloads/business-empire-agent && pm2 start bravo-telegram"
 *   pm2 stop bravo-telegram  (on Windows, after Mac confirms start)
 *
 *   # Hand off FROM Mac TO Windows:
 *   pm2 start bravo-telegram  (on Windows)
 *   ssh cc-mac "pm2 stop bravo-telegram"  (from Windows, after local start)
 *
 * NEVER run both at once. Same TELEGRAM_BOT_TOKEN → random message routing.
 */

const os = require('os');
const path = require('path');

const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';
const IS_LINUX = process.platform === 'linux';

// Project root per machine — these paths are load-bearing.
// Mac lives at Downloads/ not ~/APPS/ (historical — see CROSS_MACHINE_SYNC.md).
const PROJECT_ROOT = IS_MAC
    ? path.join(os.homedir(), 'Downloads', 'business-empire-agent')
    : (IS_WIN
        ? 'C:\\Users\\User\\Business-Empire-Agent'
        : path.join(os.homedir(), 'business-empire-agent'));

// Python interpreter per machine.
// Mac: brew-installed python@3.12 inside a venv we just created.
// Windows: venv at .venv/Scripts/python.exe (Windows virtualenv layout).
const PYTHON = IS_MAC
    ? path.join(PROJECT_ROOT, '.venv', 'bin', 'python')
    : path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe');

// Node interpreter — both platforms use whatever's on PATH.
// Mac has nvm node v24+, Windows has whatever the user installed.
const NODE = 'node';

const apps = [];

// ============================================================================
// bravo-scheduler — WINDOWS ONLY
// ============================================================================
if (IS_WIN) {
    apps.push({
        name: "bravo-scheduler",
        script: "scripts/scheduler.py",
        interpreter: PYTHON,
        cwd: PROJECT_ROOT,
        watch: false,
        autorestart: true,
        max_restarts: 10,
        restart_delay: 30000,
        env: {
            PYTHONIOENCODING: "utf-8",
            PYTHONUNBUFFERED: "1",
        },
        log_date_format: "YYYY-MM-DD HH:mm:ss",
        error_file: "tmp/pm2-scheduler-error.log",
        out_file: "tmp/pm2-scheduler-out.log",
        merge_logs: true,
        max_size: "10M",
    });
}

// ============================================================================
// bravo-telegram — BOTH PLATFORMS, but Mac runs cold-standby
// ============================================================================
//
// Declared for both platforms so the handoff commands are symmetric. The
// operational rule (see header): Windows is the always-on default, Mac only
// runs when CC explicitly starts it. Both boxes track state via `pm2 save`
// so reboots don't accidentally start the "wrong" bridge.
apps.push({
    name: "bravo-telegram",
    script: "telegram_agent.js",
    interpreter: NODE,
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
});

module.exports = { apps };
