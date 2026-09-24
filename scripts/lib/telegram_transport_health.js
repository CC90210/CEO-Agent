'use strict';

const fs = require('fs');
const path = require('path');

function createTelegramTransportHealth({ bot, filePath, name, log, intervalMs = 300000 }) {
    let stickyFailure = null;
    let lastState = null;
    let lastDetail = null;
    let timer = null;

    const persist = (ok, detail) => {
        const payload = {
            bridge: name,
            pid: process.pid,
            ok: Boolean(ok),
            detail: String(detail || (ok ? 'ok' : 'failed')).slice(0, 80),
            checked_at: new Date().toISOString(),
        };
        try {
            fs.mkdirSync(path.dirname(filePath), { recursive: true });
            const tmp = `${filePath}.${process.pid}.${Date.now()}.tmp`;
            fs.writeFileSync(tmp, `${JSON.stringify(payload)}\n`, { encoding: 'utf8' });
            try {
                fs.renameSync(tmp, filePath);
            } catch (_) {
                fs.rmSync(filePath, { force: true });
                fs.renameSync(tmp, filePath);
            }
        } catch (err) {
            if (lastDetail !== 'health_write_failed') {
                log(`[TRANSPORT] health heartbeat write failed: ${err.message || err}`);
            }
            lastDetail = 'health_write_failed';
        }
        if (lastState !== payload.ok || lastDetail !== payload.detail) {
            log(`[TRANSPORT] ${payload.ok ? 'healthy' : 'degraded'}: ${payload.detail}`);
        }
        lastState = payload.ok;
        lastDetail = payload.detail;
        return payload.ok;
    };

    const probe = async () => {
        if (stickyFailure) return persist(false, stickyFailure);
        try {
            await bot.getMe();
            return persist(true, 'get_me_ok');
        } catch (_) {
            return persist(false, 'get_me_failed');
        }
    };

    const markFailure = (detail, { sticky = false } = {}) => {
        if (sticky) stickyFailure = String(detail || 'polling_failed');
        return persist(false, detail || 'polling_failed');
    };

    const markSuccess = (detail = 'update_received') => {
        stickyFailure = null;
        return persist(true, detail);
    };

    const clearFailure = async () => {
        stickyFailure = null;
        return probe();
    };

    const start = () => {
        void probe();
        timer = setInterval(() => { void probe(); }, intervalMs);
        if (timer && typeof timer.unref === 'function') timer.unref();
    };

    const stop = () => {
        if (timer) clearInterval(timer);
        timer = null;
    };

    return { start, stop, probe, markFailure, markSuccess, clearFailure };
}

module.exports = { createTelegramTransportHealth };
