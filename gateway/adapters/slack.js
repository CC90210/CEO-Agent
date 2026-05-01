'use strict';

/**
 * SlackAdapter — @slack/bolt skeleton for the multi-platform gateway.
 *
 * Mirrors TelegramAdapter's public interface:
 *   start()                         — start the Bolt app
 *   stop()                          — graceful shutdown
 *   sendMessage(channelId, text)    — post a text message
 *   onMessage(handler)              — register message handler
 *
 * Falls back to a no-op if SLACK_BOT_TOKEN is absent — non-fatal.
 * Socket Mode is used (SLACK_APP_TOKEN with xapp- prefix required).
 */

const EventEmitter = require('events');
const path = require('path');

// @slack/bolt is an optional dep — guard so gateway starts without it
let App, LogLevel;
try {
    const bolt = require('@slack/bolt');
    App = bolt.App;
    LogLevel = bolt.LogLevel;
} catch (_) {
    // @slack/bolt not installed — adapter will no-op
}

const REPO_ROOT = path.resolve(__dirname, '..', '..');

const log = (msg) => {
    process.stdout.write(`[${new Date().toISOString()}] [SLACK] ${msg}\n`);
};

// Maximum Slack message length (blocks can go higher, but text field cap)
const SLACK_MAX_LENGTH = 3000;

/**
 * Split a long string into Slack-safe chunks.
 * @param {string} text
 * @returns {string[]}
 */
const splitForSlack = (text) => {
    const chunks = [];
    let remaining = text;
    while (remaining.length > 0) {
        chunks.push(remaining.substring(0, SLACK_MAX_LENGTH));
        remaining = remaining.substring(SLACK_MAX_LENGTH);
    }
    return chunks.length > 0 ? chunks : ['(empty)'];
};

class SlackAdapter extends EventEmitter {
    constructor(dispatcher, options = {}) {
        super();
        this._dispatcher = dispatcher;
        this._botToken = process.env.SLACK_BOT_TOKEN;
        this._appToken = process.env.SLACK_APP_TOKEN; // xapp- socket mode token
        this._signingSecret = process.env.SLACK_SIGNING_SECRET;
        this._app = null;
        this._messageHandlers = [];
        this._ready = false;
    }

    // ---- PUBLIC INTERFACE ----

    /**
     * Start the Slack adapter.
     * No-op if SLACK_BOT_TOKEN is absent or @slack/bolt is unavailable.
     */
    async start() {
        if (!this._botToken) {
            log('SLACK_BOT_TOKEN not set — Slack adapter inactive.');
            return;
        }
        if (!App) {
            log('@slack/bolt not installed (npm install @slack/bolt@^3) — Slack adapter inactive.');
            return;
        }

        const appConfig = {
            token: this._botToken,
            logLevel: LogLevel ? LogLevel.ERROR : 'error',
        };

        if (this._appToken) {
            // Socket Mode (preferred for development / bots without public URL)
            appConfig.appToken = this._appToken;
            appConfig.socketMode = true;
        } else if (this._signingSecret) {
            // HTTP mode — requires a public URL and SLACK_SIGNING_SECRET
            appConfig.signingSecret = this._signingSecret;
        } else {
            log('Neither SLACK_APP_TOKEN (Socket Mode) nor SLACK_SIGNING_SECRET (HTTP) set — Slack adapter inactive.');
            return;
        }

        this._app = new App(appConfig);

        // Listen for all messages (in channels the bot is a member of)
        this._app.message(async ({ message, say }) => {
            if (message.subtype) return; // skip bot messages, edits, deletes
            await this._handleMessage(message, say);
        });

        // Shortcut: /bravo in any channel
        this._app.command('/bravo', async ({ command, ack, respond }) => {
            await ack();
            await this._handleSlashCommand(command, 'bravo', respond);
        });

        this._app.command('/atlas', async ({ command, ack, respond }) => {
            await ack();
            await this._handleSlashCommand(command, 'atlas', respond);
        });

        this._app.command('/maven', async ({ command, ack, respond }) => {
            await ack();
            await this._handleSlashCommand(command, 'maven', respond);
        });

        this._app.command('/aura', async ({ command, ack, respond }) => {
            await ack();
            await this._handleSlashCommand(command, 'aura', respond);
        });

        this._app.error(async (err) => {
            log(`App error: ${err.message || err}`);
            this.emit('error', err);
        });

        try {
            const port = Number(process.env.SLACK_PORT || 3001);
            await this._app.start(this._appToken ? undefined : port);
            this._ready = true;
            log(`Adapter started${this._appToken ? ' (Socket Mode)' : ` on port ${port}`}.`);
            this.emit('ready');
        } catch (err) {
            log(`Start failed: ${err.message}`);
            this.emit('error', err);
        }
    }

    /**
     * Stop the Slack adapter gracefully.
     */
    async stop() {
        if (this._app) {
            try { await this._app.stop(); } catch (_) {}
            log('Adapter stopped.');
        }
    }

    /**
     * Post a message to a Slack channel.
     * @param {string} channelId   Slack channel ID (C... or D... for DMs).
     * @param {string} text
     * @param {object} [_opts]     Unused (interface parity).
     */
    async sendMessage(channelId, text, _opts = {}) {
        if (!this._app || !this._ready) {
            throw new Error('SlackAdapter not started or not ready.');
        }
        const chunks = splitForSlack(text);
        for (const chunk of chunks) {
            await this._app.client.chat.postMessage({
                channel: channelId,
                text: chunk,
            });
        }
    }

    /**
     * Register a message handler.
     * @param {function} handler  async (message: SlackMessage) => void
     */
    onMessage(handler) {
        this._messageHandlers.push(handler);
    }

    // ---- PRIVATE ----

    async _handleMessage(message, say) {
        const content = message.text || '';
        const sender = message.user;

        for (const handler of this._messageHandlers) {
            try { await handler(message); } catch (_) {}
        }

        if (this._dispatcher) {
            try {
                const { agent } = this._dispatcher.route(content, 'slack', sender);
                this._dispatcher.addToContext(agent, sender, 'user', content);
                log(`[ROUTE] ${sender} -> ${agent}`);
            } catch (err) {
                log(`Dispatcher error: ${err.message}`);
            }
        }

        this.emit('messageReceived', { content, sender, platform: 'slack' });
    }

    async _handleSlashCommand(command, agentName, respond) {
        const message = command.text || '(no message)';
        const sender = command.user_id;

        log(`[SLASH] /${agentName} from ${sender}: ${message.substring(0, 80)}`);

        if (this._dispatcher) {
            try {
                this._dispatcher.addToContext(agentName, sender, 'user', message);
                this._dispatcher.emit('messageRouted', {
                    message, platform: 'slack', sender, agent: agentName,
                    contextKey: `${agentName}:${sender}`,
                });
            } catch (err) {
                log(`Dispatcher error: ${err.message}`);
            }
        }

        const response = `[${agentName.toUpperCase()}] Received: "${message}"\n\nNote: Slack CLI execution not yet wired. Use Telegram for full agent responses.`;
        await respond({ text: response });

        if (this._dispatcher) {
            try {
                this._dispatcher.addToContext(agentName, sender, 'assistant', response);
                this._dispatcher.notifyReplyDispatched('slack', sender, agentName, response);
            } catch (_) {}
        }
    }
}

module.exports = { SlackAdapter };
