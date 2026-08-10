'use strict';

/**
 * gateway/index.js — Multi-platform messaging gateway entry point.
 *
 * ⚠️  DORMANT — DO NOT START (2026-08-03 review). This gateway is NOT the live
 * Telegram path: telegram_agent.js (PM2 "bravo-telegram") is. This layer is not
 * in PM2/ecosystem, its health.json is stale, and the Telegram adapter has
 * DRIFTED from the live bridge (missing /ping + /sb, no 401 handling, no
 * scripts/bridge_lock.py multi-machine arbitration — starting it while
 * bravo-telegram runs anywhere causes 409 poll conflicts and message loss).
 * If you ever revive it: add bridge_lock arbitration to adapters/telegram.js
 * FIRST, then reconcile the command surface with telegram_agent.js.
 *
 * Loads all adapters that have credentials configured, wires them to
 * GatewayDispatcher, starts the HTTP control server, and writes
 * periodic heartbeats to gateway/health.json.
 *
 * Usage:
 *   node gateway/index.js
 *
 * PM2:
 *   pm2 start gateway/index.js --name bravo-gateway
 */

require('dotenv').config({ path: require('path').resolve(__dirname, '..', '.env.agents') });

const http = require('http');
const fs = require('fs');
const path = require('path');

const { createDispatcher } = require('./core/dispatcher');
const { TelegramAdapter } = require('./adapters/telegram');
const { DiscordAdapter } = require('./adapters/discord');
const { SlackAdapter } = require('./adapters/slack');

// ---- CONFIG ----
const CONTROL_PORT = Number(process.env.GATEWAY_CONTROL_PORT || 7773);
const HEARTBEAT_INTERVAL_MS = 30000;
const HEALTH_FILE = path.join(__dirname, 'health.json');
const REPO_ROOT = path.resolve(__dirname, '..');

const log = (msg) => {
    process.stdout.write(`[${new Date().toISOString()}] [GATEWAY] ${msg}\n`);
};

// ---- ADAPTER REGISTRY ----
// Adapters are stored here after init so the HTTP server can report status.
/** @type {Array<{ name: string, adapter: object, active: boolean }>} */
const adapterRegistry = [];

// ---- HEARTBEAT ----
let heartbeatTimer = null;

const writeHeartbeat = () => {
    const health = {
        gateway_version: '1.0.0',
        pid: process.pid,
        uptime_s: Math.round(process.uptime()),
        ts: new Date().toISOString(),
        adapters: adapterRegistry.map(({ name, active }) => ({ name, active })),
        dispatcher_agents: [],
    };
    try { fs.writeFileSync(HEALTH_FILE, JSON.stringify(health, null, 2)); } catch (_) {}
};

// ---- HTTP CONTROL SERVER ----
// Tiny admin API on localhost:7773 — used by gateway_admin.py.
// All endpoints accept and return JSON.

const handleHttpRequest = async (req, res) => {
    const sendJson = (code, body) => {
        const payload = JSON.stringify(body, null, 2);
        res.writeHead(code, {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
        });
        res.end(payload);
    };

    const url = new URL(req.url, `http://localhost:${CONTROL_PORT}`);
    const method = req.method.toUpperCase();

    // GET /status — gateway health + adapter states
    if (method === 'GET' && url.pathname === '/status') {
        let healthData = {};
        try { healthData = JSON.parse(fs.readFileSync(HEALTH_FILE, 'utf8')); } catch (_) {}
        return sendJson(200, {
            ok: true,
            gateway: healthData,
            adapters: adapterRegistry.map(({ name, active }) => ({ name, active })),
        });
    }

    // GET /adapters — list adapter names + status
    if (method === 'GET' && url.pathname === '/adapters') {
        return sendJson(200, {
            ok: true,
            adapters: adapterRegistry.map(({ name, active }) => ({ name, active })),
        });
    }

    // POST /send — dispatch a message to a specific platform + recipient
    // Body: { platform: string, to: string, message: string }
    if (method === 'POST' && url.pathname === '/send') {
        let body = '';
        req.on('data', (chunk) => { body += chunk.toString(); });
        req.on('end', async () => {
            let payload;
            try { payload = JSON.parse(body); } catch (_) {
                return sendJson(400, { ok: false, error: 'Invalid JSON body.' });
            }
            const { platform, to, message } = payload;
            if (!platform || !to || !message) {
                return sendJson(400, { ok: false, error: 'Required fields: platform, to, message.' });
            }
            const entry = adapterRegistry.find(a => a.name === platform && a.active);
            if (!entry) {
                return sendJson(404, { ok: false, error: `No active adapter for platform: ${platform}` });
            }
            try {
                await entry.adapter.sendMessage(to, message);
                log(`[HTTP /send] ${platform} -> ${to}: "${message.substring(0, 60)}"`);
                return sendJson(200, { ok: true, platform, to, length: message.length });
            } catch (err) {
                return sendJson(500, { ok: false, error: err.message });
            }
        });
        return;
    }

    // POST /stop — graceful shutdown
    if (method === 'POST' && url.pathname === '/stop') {
        sendJson(200, { ok: true, message: 'Shutting down gateway...' });
        setTimeout(() => shutdown('HTTP /stop'), 500);
        return;
    }

    return sendJson(404, { ok: false, error: `Unknown endpoint: ${method} ${url.pathname}` });
};

// ---- SHUTDOWN ----
let shuttingDown = false;

const shutdown = async (sig) => {
    if (shuttingDown) return;
    shuttingDown = true;
    log(`Shutdown (${sig}) — stopping adapters...`);
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    for (const { adapter } of adapterRegistry) {
        try { await adapter.stop(); } catch (_) {}
    }
    log('All adapters stopped. Exiting.');
    setTimeout(() => process.exit(0), 1000);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('unhandledRejection', (err) => {
    log(`[UNHANDLED] ${err && err.message ? err.message : err}`);
});

// ---- MAIN ----

(async () => {
    log('Starting multi-platform gateway...');

    // 1. Create dispatcher
    const dispatcher = await createDispatcher({ repoRoot: REPO_ROOT });
    dispatcher.on('ready', ({ routeCount }) => {
        log(`Dispatcher ready — ${routeCount} routing rules loaded.`);
    });
    dispatcher.on('messageRouted', ({ platform, sender, agent }) => {
        log(`[ROUTE] ${platform}:${sender} -> ${agent}`);
    });
    dispatcher.on('error', (err) => {
        log(`Dispatcher error: ${err.message}`);
    });

    // 2. Create adapters
    const telegramAdapter = new TelegramAdapter(dispatcher);
    const discordAdapter = new DiscordAdapter(dispatcher);
    const slackAdapter = new SlackAdapter(dispatcher);

    // 3. Register all adapters (active flag set after start)
    adapterRegistry.push(
        { name: 'telegram', adapter: telegramAdapter, active: false },
        { name: 'discord', adapter: discordAdapter, active: false },
        { name: 'slack', adapter: slackAdapter, active: false },
    );

    // 4. Start adapters that have credentials
    // Telegram is the primary adapter — its activation is what makes the
    // gateway useful. Discord and Slack are additive.
    const startResults = await Promise.allSettled([
        telegramAdapter.start().then(() => {
            if (process.env.TELEGRAM_BOT_TOKEN) {
                const entry = adapterRegistry.find(a => a.name === 'telegram');
                if (entry) entry.active = true;
                log('Telegram adapter active.');
            }
        }),
        discordAdapter.start().then(() => {
            if (process.env.DISCORD_TOKEN) {
                const entry = adapterRegistry.find(a => a.name === 'discord');
                if (entry) entry.active = true;
                log('Discord adapter active.');
            }
        }),
        slackAdapter.start().then(() => {
            if (process.env.SLACK_BOT_TOKEN) {
                const entry = adapterRegistry.find(a => a.name === 'slack');
                if (entry) entry.active = true;
                log('Slack adapter active.');
            }
        }),
    ]);

    for (const result of startResults) {
        if (result.status === 'rejected') {
            log(`Adapter start error: ${result.reason && result.reason.message ? result.reason.message : result.reason}`);
        }
    }

    // Update dispatcher agent list in health after adapters init
    const activeAdapters = adapterRegistry.filter(a => a.active).map(a => a.name);
    log(`Active adapters: ${activeAdapters.length > 0 ? activeAdapters.join(', ') : 'none'}`);

    // 5. Start HTTP control server
    const httpServer = http.createServer(handleHttpRequest);
    httpServer.listen(CONTROL_PORT, '127.0.0.1', () => {
        log(`HTTP control server listening on localhost:${CONTROL_PORT}`);
    });
    httpServer.on('error', (err) => {
        log(`HTTP server error: ${err.message} (is port ${CONTROL_PORT} already in use?)`);
    });

    // 6. Write initial heartbeat, then every 30s
    writeHeartbeat();
    heartbeatTimer = setInterval(writeHeartbeat, HEARTBEAT_INTERVAL_MS);

    log('Gateway initialisation complete.');
})();
