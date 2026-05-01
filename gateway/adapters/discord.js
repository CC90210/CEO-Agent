'use strict';

/**
 * DiscordAdapter — discord.js v14 adapter for the multi-platform gateway.
 *
 * Mirrors TelegramAdapter's public interface exactly:
 *   start()                         — login and register slash commands
 *   stop()                          — logout gracefully
 *   sendMessage(channelId, text)    — send a text message to a channel
 *   onMessage(handler)              — register message/interaction handler
 *
 * Slash commands: /bravo /atlas /maven /aura
 * Falls back to a no-op if DISCORD_TOKEN is absent — non-fatal.
 */

const EventEmitter = require('events');
const path = require('path');

// discord.js is an optional dep — guard the require so the gateway starts
// even without it installed.
let Client, GatewayIntentBits, REST, Routes, SlashCommandBuilder;
try {
    const discordjs = require('discord.js');
    Client = discordjs.Client;
    GatewayIntentBits = discordjs.GatewayIntentBits;
    REST = discordjs.REST;
    Routes = discordjs.Routes;
    SlashCommandBuilder = discordjs.SlashCommandBuilder;
} catch (_) {
    // discord.js not installed — adapter will no-op
}

const REPO_ROOT = path.resolve(__dirname, '..', '..');

const log = (msg) => {
    process.stdout.write(`[${new Date().toISOString()}] [DISCORD] ${msg}\n`);
};

// Slash command definitions — built lazily inside start() when discord.js is present
const AGENT_SLASH_DEFS = [
    { name: 'bravo', description: 'Ask Bravo (CEO / general AI ops)' },
    { name: 'atlas', description: 'Ask Atlas (CFO — tax, finance, trading)' },
    { name: 'maven', description: 'Ask Maven (CMO — content, ads, brand)' },
    { name: 'aura',  description: 'Ask Aura (smart home, habits, life)' },
];

// Maximum Discord message length
const DISCORD_MAX_LENGTH = 2000;

/**
 * Split a long string into Discord-safe chunks.
 * @param {string} text
 * @returns {string[]}
 */
const splitForDiscord = (text) => {
    const chunks = [];
    let remaining = text;
    while (remaining.length > 0) {
        chunks.push(remaining.substring(0, DISCORD_MAX_LENGTH));
        remaining = remaining.substring(DISCORD_MAX_LENGTH);
    }
    return chunks.length > 0 ? chunks : ['(empty)'];
};

class DiscordAdapter extends EventEmitter {
    constructor(dispatcher, options = {}) {
        super();
        this._dispatcher = dispatcher;
        this._token = process.env.DISCORD_TOKEN;
        this._client = null;
        this._messageHandlers = [];
        this._ready = false;
    }

    // ---- PUBLIC INTERFACE ----

    /**
     * Start the Discord adapter.
     * No-op with a log message if DISCORD_TOKEN is absent or discord.js unavailable.
     */
    async start() {
        if (!this._token) {
            log('DISCORD_TOKEN not set — Discord adapter inactive.');
            return;
        }
        if (!Client) {
            log('discord.js not installed (npm install discord.js@^14) — Discord adapter inactive.');
            return;
        }

        this._client = new Client({
            intents: [
                GatewayIntentBits.Guilds,
                GatewayIntentBits.GuildMessages,
                GatewayIntentBits.MessageContent,
                GatewayIntentBits.DirectMessages,
            ],
        });

        this._client.once('ready', async () => {
            log(`Logged in as ${this._client.user.tag}`);
            this._ready = true;
            await this._registerSlashCommands();
            this.emit('ready');
        });

        this._client.on('messageCreate', async (message) => {
            if (message.author.bot) return;
            await this._handleMessage(message);
        });

        this._client.on('interactionCreate', async (interaction) => {
            if (!interaction.isChatInputCommand()) return;
            await this._handleSlashCommand(interaction);
        });

        this._client.on('error', (err) => {
            log(`Client error: ${err.message}`);
            this.emit('error', err);
        });

        try {
            await this._client.login(this._token);
        } catch (err) {
            log(`Login failed: ${err.message}`);
            this.emit('error', err);
        }
    }

    /**
     * Stop the adapter gracefully.
     */
    async stop() {
        if (this._client) {
            try { await this._client.destroy(); } catch (_) {}
            log('Adapter stopped.');
        }
    }

    /**
     * Send a text message to a channel by ID.
     * @param {string} channelId   Discord channel snowflake.
     * @param {string} text
     * @param {object} [_opts]     Unused (interface parity).
     */
    async sendMessage(channelId, text, _opts = {}) {
        if (!this._client || !this._ready) {
            throw new Error('DiscordAdapter not started or not ready.');
        }
        const channel = await this._client.channels.fetch(channelId);
        if (!channel || !channel.isTextBased()) {
            throw new Error(`Channel ${channelId} not found or not text-based.`);
        }
        const chunks = splitForDiscord(text);
        for (const chunk of chunks) {
            await channel.send(chunk);
        }
    }

    /**
     * Register a handler for incoming messages.
     * @param {function} handler  async (message: Discord.Message) => void
     */
    onMessage(handler) {
        this._messageHandlers.push(handler);
    }

    // ---- PRIVATE ----

    async _registerSlashCommands() {
        if (!SlashCommandBuilder || !REST || !Routes) return;
        const slashCommands = AGENT_SLASH_DEFS.map(({ name, description }) =>
            new SlashCommandBuilder()
                .setName(name)
                .setDescription(description)
                .addStringOption(opt =>
                    opt.setName('message').setDescription('Your message').setRequired(true))
        );
        const rest = new REST({ version: '10' }).setToken(this._token);
        const commandData = slashCommands.map(cmd => cmd.toJSON());
        try {
            await rest.put(
                Routes.applicationCommands(this._client.user.id),
                { body: commandData },
            );
            log(`Registered ${commandData.length} slash commands globally.`);
        } catch (err) {
            log(`Slash command registration failed: ${err.message}`);
        }
    }

    async _handleMessage(message) {
        const content = message.content;
        const sender = message.author.id;

        // Notify external handlers
        for (const handler of this._messageHandlers) {
            try { await handler(message); } catch (_) {}
        }

        // Route through dispatcher for context tracking
        if (this._dispatcher) {
            try {
                const { agent } = this._dispatcher.route(content, 'discord', sender);
                this._dispatcher.addToContext(agent, sender, 'user', content);
                log(`[ROUTE] ${sender} -> ${agent}`);
            } catch (err) {
                log(`Dispatcher error: ${err.message}`);
            }
        }

        this.emit('messageReceived', { content, sender, platform: 'discord' });
    }

    async _handleSlashCommand(interaction) {
        const agentName = interaction.commandName; // bravo | atlas | maven | aura
        const message = interaction.options.getString('message');
        const sender = interaction.user.id;

        log(`[SLASH] /${agentName} from ${sender}: ${message.substring(0, 80)}`);

        // Defer reply so we have time to process
        await interaction.deferReply();

        if (this._dispatcher) {
            try {
                // Force route to the commanded agent (slash command is explicit)
                this._dispatcher.addToContext(agentName, sender, 'user', message);
                this._dispatcher.emit('messageRouted', {
                    message, platform: 'discord', sender, agent: agentName,
                    contextKey: `${agentName}:${sender}`,
                });
            } catch (err) {
                log(`Dispatcher error: ${err.message}`);
            }
        }

        // Skeleton response — the gateway/index.js connects this to the actual
        // CLI executor once the full pipeline is wired.
        const response = `[${agentName.toUpperCase()}] Message received: "${message}"\n\nNote: Discord CLI execution not yet wired. Use Telegram for full agent responses.`;
        const chunks = splitForDiscord(response);
        await interaction.editReply(chunks[0]);
        for (let i = 1; i < chunks.length; i++) {
            await interaction.followUp(chunks[i]);
        }

        if (this._dispatcher) {
            try {
                this._dispatcher.addToContext(agentName, sender, 'assistant', response);
                this._dispatcher.notifyReplyDispatched('discord', sender, agentName, response);
            } catch (_) {}
        }
    }
}

module.exports = { DiscordAdapter };
