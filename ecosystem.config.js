/**
 * PM2 Ecosystem Config — Bravo Business Operations (v3, 2026-05-15)
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
 *   - The Skool daemon was archived 2026-05-18 (preserved at
 *     scripts/_archive/skool/). It was never in PM2 — it ran standalone
 *     with its own OS-level lock. Will be revived for CC's own Skool
 *     community in the future; see scripts/_archive/skool/README.md.
 *
 *   - V6 + giggly-reef local daemons added 2026-05-15. Four new entries:
 *       claude-bridge       — localhost:9100 chat HTTP server (giggly-reef
 *                              Phase 2: /chat warm pool, /exec-tool browser
 *                              proxy, /local-chat Ollama passthrough).
 *                              Per-machine; multiple operator machines run
 *                              their own bridges in parallel.
 *       claude-bridge-ping  — heartbeat to /api/bridge/ping (keeps
 *                              bridge_pairings.last_seen_at fresh so the
 *                              dashboard knows the bridge is online) AND
 *                              tenant cron-job poller (giggly-reef Phase I,
 *                              calls cron_runner.poll_once each cycle).
 *       event-router        — V6 Apex Phase 3 cross-agent event bus tail.
 *
 * USAGE:
 *
 *   # Windows (CCPC) — control center, runs everything
 *   cd /c/Users/User/Business-Empire-Agent
 *   pm2 start ecosystem.config.js          # boots all enabled-for-this-platform
 *   pm2 save                                # persist state across reboots
 *
 *   # Selective start (e.g. just the chat bridge):
 *   pm2 start ecosystem.config.js --only claude-bridge
 *
 *   # Mac — on-the-go workstation, no daemons run by default. Only start
 *   # bridges manually when CC is travelling and Windows is offline.
 *   cd ~/CEO-Agent
 *   pm2 start ecosystem.config.js --only bravo-telegram
 *   pm2 start ecosystem.config.js --only claude-bridge,claude-bridge-ping
 *
 * TELEGRAM HANDOFF PROTOCOL (Windows <-> Mac):
 *   # Hand off FROM Windows TO Mac:
 *   ssh cc-mac "cd ~/CEO-Agent && pm2 start bravo-telegram"
 *   pm2 stop bravo-telegram  (on Windows, after Mac confirms start)
 *
 *   # Hand off FROM Mac TO Windows:
 *   pm2 start bravo-telegram  (on Windows)
 *   ssh cc-mac "pm2 stop bravo-telegram"  (from Windows, after local start)
 *
 * NEVER run both telegram bridges at once — same TELEGRAM_BOT_TOKEN → random
 * message routing. Claude-bridge has no such conflict (per-machine port + the
 * dashboard auto-discovers via bridge_pairings tokens).
 */

const os = require('os');
const path = require('path');

const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';
const IS_LINUX = process.platform === 'linux';

// Project root per machine — these paths are load-bearing.
// Mac canonical location is ~/CEO-Agent (moved from ~/Downloads/business-empire-agent
// on 2026-05-19 — see CROSS_MACHINE_SYNC.md).
const PROJECT_ROOT = IS_MAC
    ? path.join(os.homedir(), 'CEO-Agent')
    : (IS_WIN
        ? 'C:\\Users\\User\\Business-Empire-Agent'
        : (IS_LINUX
            ? '/srv/sunbiz/ceo-agent'
            : path.join(os.homedir(), 'business-empire-agent')));

// Python interpreter per machine.
// Mac: brew-installed python@3.12 inside a venv we just created.
// Windows: venv at .venv/Scripts/python.exe (Windows virtualenv layout).
// Linux (VPS): POSIX venv layout at .venv/bin/python (same as Mac).
const PYTHON = IS_WIN
    ? path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
    : path.join(PROJECT_ROOT, '.venv', 'bin', 'python');

// pythonw.exe — Windows GUI variant of python.exe. CRITICAL: pythonw
// DOES NOT allocate a console window. Use this for any daemon that
// should NEVER pop a terminal on the operator's screen. The
// difference matters because PM2's windowsHide setting is unreliable
// across PM2 versions on Windows; pythonw guarantees no window
// regardless of restart loops, crashes, or PM2 quirks. Mac/Linux
// have no console concept here so we fall back to plain python.
const PYTHONW = IS_WIN
    ? path.join(PROJECT_ROOT, '.venv', 'Scripts', 'pythonw.exe')
    : path.join(PROJECT_ROOT, '.venv', 'bin', 'python');

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
        // PYTHONW (no-console) — was PYTHON until 2026-05-16, which caused a
        // python.exe console window to flash on every PM2 spawn/restart.
        // Matches the pattern of every other daemon in this file.
        interpreter: PYTHONW,
        cwd: PROJECT_ROOT,
        watch: false,
        autorestart: true,
        max_restarts: 10,
        restart_delay: 30000,
        windowsHide: true,
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
    restart_delay: 45000,   // Must exceed Telegram's 30s long-poll timeout to prevent 409 conflict loops
    kill_timeout: 10000,    // Give graceful shutdown time to release the poll connection
    windowsHide: true,
    env: {
        NODE_ENV: "production",
    },
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "tmp/pm2-telegram-error.log",
    out_file: "tmp/pm2-telegram-out.log",
    merge_logs: true,
    max_size: "10M",
});

// ============================================================================
// claude-bridge — localhost:9100 chat HTTP server (giggly-reef Phase 2)
// ============================================================================
//
// The HTTP server the dashboard's ChatWidget talks to in CLI mode + the
// cloud-mode tool proxy target. Hosts:
//   POST /chat          — warm-pool-backed Claude Code subprocess (Phase 1
//                         with subscription→API-key auth fallback baked in).
//   POST /exec-tool     — browser-mediated tool execution for cloud_bridge_tools
//                         mode (Phase 2). Cloud LLM emits tool_use, browser
//                         POSTs here, bridge dispatches via bridge_tools.
//   POST /local-chat    — Ollama / LM Studio passthrough.
//   GET  /health        — dashboard's online-check probe (every 30s).
//
// Per-machine: each operator's machine runs its own bridge on its own
// port. The dashboard discovers it via the bridge_pairings token in
// ~/.oasis/bridge_token. bridge_lock.py prevents two machines from both
// claiming ownership of Telegram routing simultaneously; for chat, having
// multiple bridges paired is fine (each one services its own operator).
apps.push({
    name: "claude-bridge",
    script: PYTHONW,  // no-console interpreter; popup-suppressed even on crash-loop
    args: ["-m", "bravo_cli.bridge_chat_server"],
    cwd: PROJECT_ROOT,
    watch: false,
    autorestart: true,
    max_restarts: 20,
    restart_delay: 5000,
    windowsHide: true,
    env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
    },
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "tmp/pm2-claude-bridge-error.log",
    out_file: "tmp/pm2-claude-bridge-out.log",
    merge_logs: true,
    max_size: "10M",
});

// ============================================================================
// claude-bridge-ping — heartbeat + tenant cron poller (giggly-reef Phase I)
// ============================================================================
//
// Two responsibilities, fused into one ping loop so they share the same
// bridge token + dashboard-URL plumbing:
//   1. Heartbeat to /api/bridge/ping every 60s — keeps
//      bridge_pairings.last_seen_at fresh so the dashboard's bridge-online
//      check returns true. Also advertises tool_capabilities (Phase F).
//   2. Tenant cron poller (cron_runner.poll_once) — pulls
//      /api/cron-jobs/poll, evaluates 5-field cron expressions locally,
//      executes due jobs via bridge_tools, POSTs results back. The
//      dashboard never runs cron jobs itself — operator's machine owns
//      execution. Survives operator reboots once PM2 is configured to
//      auto-start (`pm2 save` + `pm2 startup`).
apps.push({
    name: "claude-bridge-ping",
    script: PYTHONW,  // no-console interpreter; popup-suppressed even on crash-loop
    args: ["-m", "bravo_cli.local_bridge", "_loop"],
    cwd: PROJECT_ROOT,
    watch: false,
    autorestart: true,
    max_restarts: 20,
    restart_delay: 10000,
    windowsHide: true,
    env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
    },
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "tmp/pm2-claude-bridge-ping-error.log",
    out_file: "tmp/pm2-claude-bridge-ping-out.log",
    merge_logs: true,
    max_size: "10M",
});

// ============================================================================
// event-router — V6 Apex Phase 3 cross-agent event bus tail
// ============================================================================
//
// Cursor-based, lossless tail of Postgres agent_events into
// state/event_router.log on this host. Other agents (and the /feed page
// on the dashboard) consume this log. 3-second poll matches the dashboard
// /feed page's auto-refresh cadence so live state never lags more than
// one cycle behind.
apps.push({
    name: "event-router",
    script: "scripts/core/event_router.py",
    args: ["loop", "--interval", "3"],
    interpreter: PYTHONW,  // no-console interpreter; popup-suppressed
    cwd: PROJECT_ROOT,
    watch: false,
    autorestart: true,
    max_restarts: 20,
    restart_delay: 10000,
    windowsHide: true,
    env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
    },
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "tmp/pm2-event-router-error.log",
    out_file: "tmp/pm2-event-router-out.log",
    merge_logs: true,
    max_size: "10M",
});

// override-consumer daemon was deleted 2026-05-22 along with the entire
// exec_override approval-request system. The exec_guard hook still blocks
// destructive commands; it just refuses them outright now rather than
// queuing them for human approval. See scripts/state/exec_guard.py.

// SunBiz daemons (sequence-runner, lender-response-classifier) were
// relocated to SunBiz-Agent/ecosystem.config.js on 2026-05-28. Start
// them from that repo's PM2 ecosystem on the bridge host:
//   cd ~/SunBiz-Agent && pm2 start ecosystem.config.js
// Splitting them out of CEO-Agent's PM2 ecosystem lets per-tenant
// pause/restart happen without cycling Bravo's own daemons.

// ============================================================================
// dashboard-email-consumer — Command Center email sender daemon
// ============================================================================
//
// Polls Supabase lead_interactions every 10s for rows the operator queued
// from the Command Center's lead-drawer Email composer:
//   type='email_queued', channel='email', direction='outbound',
//   agent_source='dashboard_drawer', metadata.status='queued'
//
// For each row: resolves GMAIL_USER + GMAIL_APP_PASSWORD from .env.agents,
// sends via smtplib SMTP_SSL, and updates metadata.status to 'sent' or
// 'failed' so the drawer's timeline reflects the outcome.
//
// Was originally registered via manual `pm2 start` with `python` interpreter
// (not pythonw), which popped a visible console window. Fixed 2026-05-19
// to use PYTHONW. Now also declared here so ecosystem.config.js boots it
// on `pm2 start ecosystem.config.js`.
if (IS_WIN) {
    apps.push({
        name: "dashboard-email-consumer",
        script: "scripts/dashboard_email_consumer.py",
        args: ["loop", "--interval", "10"],
        interpreter: PYTHONW,  // no-console interpreter; popup-suppressed
        cwd: PROJECT_ROOT,
        watch: false,
        autorestart: true,
        max_restarts: 20,
        restart_delay: 10000,
        windowsHide: true,
        env: {
            PYTHONIOENCODING: "utf-8",
            PYTHONUNBUFFERED: "1",
        },
        log_date_format: "YYYY-MM-DD HH:mm:ss",
        error_file: "tmp/pm2-dashboard-email-consumer-error.log",
        out_file: "tmp/pm2-dashboard-email-consumer-out.log",
        merge_logs: true,
        max_size: "10M",
    });
}

module.exports = { apps };
