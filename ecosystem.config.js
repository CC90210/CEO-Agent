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

// V6 staged cutover (2026-07-18): shadow = state_sync dual-writes flat files
// AND the state DB. Shadow NEVER runs the `on`-mode export, so flat files stay
// authoritative and nothing is clobbered — a safe soak before any future `on`
// flip. Spread into every app's env below so all daemons inherit it uniformly
// (non-uniform inheritance is the drift hazard the investigator flagged). Takes
// effect on the next `pm2 restart ecosystem.config.js --update-env`.
const V6_ENV = { EMPIRE_V6_MODE: "shadow" };

// Presence check for a non-empty key in .env.agents WITHOUT echoing its value.
// Used to gate the coordination bridge so it isn't crash-looped by PM2 before
// CC has provisioned the dedicated bot token.
const fs = require('fs');
function envKeyPresent(key) {
    try {
        const txt = fs.readFileSync(path.join(PROJECT_ROOT, '.env.agents'), 'utf8');
        const re = new RegExp('^' + key + '=\\s*\\S', 'm');
        return re.test(txt);
    } catch (_) { return false; }
}

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
// bravo-coord — OASIS coordination bridge (agent↔agent + boardroom group)
// ============================================================================
//
// Separate group-scoped Telegram bridge for the shared OASIS group
// (CC + Adon + Bravo + APEX). DISTINCT bot token (CC_AGENT_BOT_TOKEN) — the
// process refuses to start if the token is missing or equals the DM token, so
// it never 409s with bravo-telegram. Only registered here when the token is
// present in .env.agents (avoids a PM2 crash-loop before CC provisions it).
//
// Same multi-machine rule as bravo-telegram: one instance at a time, arbitrated
// via scripts/bridge_lock.py with agent name 'bravo-coord' (distinct lock, so
// it never collides with the DM bridge's 'bravo' lock). Windows is the always-on
// default. Agent↔agent state lives in the agent_activity table (bravo Supabase).
//
// Registered when EITHER: CC_AGENT_BOT_TOKEN is set (FULL two-way mode), or
// COORD_ENABLE is set (TABLE-ONLY mode — agent↔agent via the table, posting
// through the existing DM bot; no dedicated bot / no new credential).
if (envKeyPresent('CC_AGENT_BOT_TOKEN') || envKeyPresent('COORD_ENABLE')) {
    apps.push({
        name: "bravo-coord",
        script: "coordination_agent.js",
        interpreter: NODE,
        cwd: PROJECT_ROOT,
        watch: false,
        autorestart: true,
        max_restarts: 10,
        restart_delay: 45000,   // exceed Telegram's 30s long-poll to avoid 409 loops
        kill_timeout: 10000,
        windowsHide: true,
        env: { NODE_ENV: "production" },
        log_date_format: "YYYY-MM-DD HH:mm:ss",
        error_file: "tmp/pm2-coord-error.log",
        out_file: "tmp/pm2-coord-out.log",
        merge_logs: true,
        max_size: "10M",
    });
}

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
        // 2026-06-09: this VPS runs as root. Claude Code refuses
        // --dangerously-skip-permissions as root unless IS_SANDBOX=1, and the
        // Gemini CLI refuses an untrusted workspace unless this trust flag is
        // set. The bridge spawns claude/gemini/codex subprocesses that inherit
        // this env, so set it here for durability (survives redeploy/reboot).
        IS_SANDBOX: "1",
        GEMINI_CLI_TRUST_WORKSPACE: "true",
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
// VPS (LINUX) ONLY as of 2026-06-29 (was Windows-only). Same rule as
// extraction-consumer below: exactly ONE consumer must own the email queue, and
// the VPS is the right home — always-on (independent of CC's laptop) and already
// holds the shared submissions@ Gmail creds send_gateway uses for shop-out.
// Windows-only gating meant queued lead-emails never drained whenever CC's PC was
// off — the 2026-06-29 "Send Email doesn't work" report (21 rows stuck at
// metadata.status='queued', recipients never delivered). The synchronous
// auto-trigger in /api/leads/[id]/email still fires instantly for owner/admin;
// this daemon is the safety net that drains everything else (member roles, bridge
// hiccups). For Windows dev, run by hand:
//   python scripts/dashboard_email_consumer.py once
if (IS_LINUX) {
    apps.push({
        name: "dashboard-email-consumer",
        script: "scripts/dashboard_email_consumer.py",
        args: ["loop", "--interval", "10"],
        interpreter: PYTHON,  // Linux python (Windows used PYTHONW for no-console)
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

// ============================================================================
// extraction-consumer — SunBiz document-extraction daemon — VPS (LINUX) ONLY
// ============================================================================
//
// Drains document_extraction_jobs: reads dropped applications with the Claude
// Code CLI on CC's SUBSCRIPTION (OAuth, not the metered API), then POSTs the
// fields + signature box back to the dashboard (HMAC) at
// /api/internal/apply-extraction. Moves the per-application vision cost off the
// API onto the flat-rate subscription. Falls back to the API only on a quota cap.
//
// LINUX-ONLY (like bravo-scheduler is Windows-only): exactly ONE consumer must
// own the queue. The VPS is the right home — it's always-on (independent of CC's
// laptop) and already hosts the subscription `claude` CLI (claude-bridge). Two
// daemons polling the same 'queued' rows would double-process (the processing
// claim isn't a row lock). For Windows dev, run it by hand:
//   python scripts/integrations/extraction_consumer.py once
// Prereq: `claude setup-token` on the VPS so ~/.claude holds the subscription
// OAuth (else extractions fall to the metered API). Verify: `... doctor`.
if (IS_LINUX) {
    apps.push({
        name: "extraction-consumer",
        script: "scripts/integrations/extraction_consumer.py",
        args: ["loop", "--interval", "8"],
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
            // The spawned `claude` inherits this; the VPS runs as root and Claude
            // Code refuses non-interactive runs as root without it.
            IS_SANDBOX: "1",
        },
        log_date_format: "YYYY-MM-DD HH:mm:ss",
        error_file: "tmp/pm2-extraction-consumer-error.log",
        out_file: "tmp/pm2-extraction-consumer-out.log",
        merge_logs: true,
        max_size: "10M",
    });
}

// Uniformly stamp the V6 cutover mode onto every daemon's env (base layer, so
// any app-specific env key still wins). Applied here rather than in each block
// so a future daemon can't accidentally ship without it — non-uniform
// inheritance across state-writers is the drift hazard we're avoiding.
for (const app of apps) {
    app.env = { ...V6_ENV, ...(app.env || {}) };
}

module.exports = { apps };
