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
 *   - The Skool daemon is NOT in this ecosystem. It runs as a standalone
 *     process with its own OS-level DaemonLock (msvcrt on Windows). Moving
 *     it into PM2 would fight the lock. Windows only, started via:
 *       python scripts/skool_engine.py daemon --interval 5
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
 *       override-consumer   — V6 Apex Phase 2 exec-override decision poller.
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
 *   # Mac — cold standby telegram bridge + local claude-bridge if desired
 *   cd ~/Downloads/business-empire-agent
 *   pm2 start ecosystem.config.js --only bravo-telegram
 *   pm2 start ecosystem.config.js --only claude-bridge,claude-bridge-ping
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
    script: PYTHON,
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
    script: PYTHON,
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
    script: "scripts/event_router.py",
    args: ["loop", "--interval", "3"],
    interpreter: PYTHON,
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

// ============================================================================
// override-consumer — V6 Apex Phase 2 exec-override decision poller
// ============================================================================
//
// Pulls approve/deny decisions for exec_guard-blocked actions from
// Supabase (cloud-side Approve/Deny UI) and applies them to the local
// state DB. HMAC-verified. Without this daemon running, dashboard-driven
// override approvals never reach the operator's machine.
apps.push({
    name: "override-consumer",
    script: "scripts/exec_override_consumer.py",
    args: ["loop", "--interval", "5"],
    interpreter: PYTHON,
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
    error_file: "tmp/pm2-override-consumer-error.log",
    out_file: "tmp/pm2-override-consumer-out.log",
    merge_logs: true,
    max_size: "10M",
});

// ============================================================================
// sequence-runner — drip-campaign engine (SunBiz CRM Phase 4)
// ============================================================================
//
// Two responsibilities in one daemon, alternated each tick:
//   1. Enrollment: reads new agent_events rows since last cursor, matches
//      against drip_sequences, inserts sequence_state rows for matching
//      (lead, sequence) pairs.
//   2. Execution: polls sequence_state for due rows, fires via
//      send_gateway.send (SMS/email), updates status, enqueues next step.
//
// CASL/cooldown/daily-cap enforcement is automatic because all sends
// route through send_gateway (the single outbound chokepoint). The
// daemon never bypasses it. Tenant isolation is at the row level
// (tenant_id match on sequence_state + drip_sequences); the daemon
// connects as service-role so it sees all tenants' rows but writes
// only against the resolved tenant_id from each event.
//
// 10s tick interval matches the typical operator expectation that a
// stage-change drip fires "within a couple seconds" without slamming
// agent_events with a poll storm. Cursor in state/sequence_runner.cursor
// so restarts don't re-enroll.
apps.push({
    name: "sequence-runner",
    script: "scripts/sequence_runner.py",
    args: ["loop", "--interval", "10"],
    interpreter: PYTHON,
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
    error_file: "tmp/pm2-sequence-runner-error.log",
    out_file: "tmp/pm2-sequence-runner-out.log",
    merge_logs: true,
    max_size: "10M",
});

// ============================================================================
// lender-response-classifier — Gmail label monitor for shop-out replies
// ============================================================================
//
// Phase 6.4 of SunBiz CRM. Polls application_lender_threads rows where
// status=sent + gmail_thread_id is non-null, fetches the latest message
// via scripts/google_tool.py, classifies via Claude Haiku 4.5 into
// approved/declined/info_requested/unclear, and updates status +
// last_response_summary. Operators see the funding-pipeline state on
// the application detail page without ever opening Gmail.
//
// Also runs an SLA sweep each tick: threads at status=sent older than
// the lender's sla_response_days auto-flip to no_response (no
// classifier call needed).
//
// 5-min default tick. Cheap-but-non-trivial because each tick does a
// Gmail thread fetch + Claude classification per pending thread.
// Operators can run with --interval 60 for tighter responsiveness
// during a busy submission day.
apps.push({
    name: "lender-response-classifier",
    script: "scripts/lender_response_classifier.py",
    args: ["loop", "--interval", "300"],
    interpreter: PYTHON,
    cwd: PROJECT_ROOT,
    watch: false,
    autorestart: true,
    max_restarts: 20,
    restart_delay: 30000,
    windowsHide: true,
    env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
    },
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "tmp/pm2-lender-classifier-error.log",
    out_file: "tmp/pm2-lender-classifier-out.log",
    merge_logs: true,
    max_size: "10M",
});

module.exports = { apps };
