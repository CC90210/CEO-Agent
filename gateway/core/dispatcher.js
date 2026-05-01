'use strict';

/**
 * GatewayDispatcher — multi-platform message routing core
 *
 * Routes incoming messages from any platform adapter to the correct
 * AI agent (bravo / atlas / maven / aura) based on keyword patterns
 * loaded from brain/AGENTS.md at startup.
 *
 * Design notes:
 * - Pattern matching is additive: first rule in ROUTE_TABLE wins.
 * - Per (agent, sender) context isolation prevents history bleed.
 * - EventEmitter lets adapters observe routing decisions without coupling.
 */

const EventEmitter = require('events');
const fs = require('fs');
const path = require('path');

// ---- STATIC ROUTING TABLE (from brain/AGENTS.md patterns) ----
// Keys are agent names. Values are arrays of RegExp patterns.
// Order matters: first match wins. bravo is the catch-all default.
const ROUTE_TABLE = [
    {
        agent: 'atlas',
        patterns: [
            /\b(tax|taxes|taxe?s|rrsp|tfsa|fhsa|cra|t1|t2125|t5013)\b/i,
            /\b(accounting|accountant|bookkeep|deducti|write.?off)\b/i,
            /\b(trad(e|ing)|stock|equity|crypto|portfolio|rebalance)\b/i,
            /\b(budget|cash.?flow|runway|burn.?rate|invoice|financial model)\b/i,
            /\b(fire|wealth|net.?worth|retirement|savings.?rate)\b/i,
            /\b(compliance|corporate.?structure|sole.?prop|incorporation)\b/i,
            /\b(stripe balance|revenue forecast|unit economics)\b/i,
        ],
    },
    {
        agent: 'maven',
        patterns: [
            /\b(content|post(ing)?|tweet|instagram|tiktok|linkedin|threads|facebook|social.?media)\b/i,
            /\b(brand|brandvoice|brand.?voice|copy|caption|hook)\b/i,
            /\b(ad campaign|meta ads|google ads|paid.?media|roas|cpm|ctr)\b/i,
            /\b(funnel|landing.?page|lead.?magnet|opt.?in|conversion)\b/i,
            /\b(seo|aeo|backlink|keyword|organic.?reach)\b/i,
            /\b(content.?calendar|content.?strategy|editorial)\b/i,
            /\b(video edit|remotion|thumbnail|caption.?sync)\b/i,
            /\b(marketing|advertis|promotion|campaign)\b/i,
        ],
    },
    {
        agent: 'aura',
        patterns: [
            /\b(smart.?home|home.?assistant|raspberry.?pi|esp32)\b/i,
            /\b(habit(s)?|routine|morning.?routine|evening.?routine)\b/i,
            /\b(apartment|home.?automation|thermostat|lights?|sensor)\b/i,
            /\b(sleep.?track|workout.?log|gym.?log|nutrition.?log)\b/i,
            /\b(life.?log|journa(l|ling)|daily.?review)\b/i,
        ],
    },
    // bravo is the default — no pattern check needed
];

// ---- CONVERSATION CONTEXT ----
// Stores per (agent, sender) tuple so Atlas history never bleeds into Bravo.
/** @typedef {{ agent: string, messages: Array<{role: string, text: string, ts: string}> }} ConversationContext */

const MAX_CTX_MESSAGES = 20;

class GatewayDispatcher extends EventEmitter {
    constructor(options = {}) {
        super();
        this._repoRoot = options.repoRoot || path.resolve(__dirname, '..', '..');
        this._defaultAgent = options.defaultAgent || 'bravo';
        /** @type {Map<string, ConversationContext>} */
        this._contexts = new Map();
        this._ready = false;
    }

    /**
     * Initialise dispatcher — reads AGENTS.md to confirm routing config.
     * Call once at startup before wiring adapters.
     */
    async init() {
        const agentsPath = path.join(this._repoRoot, 'brain', 'AGENTS.md');
        try {
            // We use the static ROUTE_TABLE above (derived from AGENTS.md).
            // This read is a startup sanity check so the process fails fast
            // if the repo root is wrong.
            fs.accessSync(agentsPath, fs.constants.R_OK);
            this._ready = true;
            this.emit('ready', { agentsPath, routeCount: ROUTE_TABLE.length + 1 /* +1 for bravo default */ });
        } catch (err) {
            this.emit('error', new Error(`AGENTS.md not readable at ${agentsPath}: ${err.message}`));
        }
    }

    /**
     * Route a message to the appropriate agent.
     *
     * @param {string} message   Raw text from the user.
     * @param {string} platform  Adapter platform id ('telegram' | 'discord' | 'slack').
     * @param {string} sender    Platform-specific user/sender id (used for context isolation).
     * @returns {{ agent: string, context: ConversationContext }}
     */
    route(message, platform, sender) {
        if (!this._ready) {
            throw new Error('GatewayDispatcher.init() has not been called or failed.');
        }

        const agent = this._matchAgent(message);
        const contextKey = `${agent}:${sender}`;
        const context = this._getOrCreateContext(contextKey, agent);

        this.emit('messageReceived', { message, platform, sender, agent });
        this.emit('messageRouted', { message, platform, sender, agent, contextKey });

        return { agent, context };
    }

    /**
     * Append a message pair to the per-agent context.
     *
     * @param {string} agent
     * @param {string} sender
     * @param {'user' | 'assistant'} role
     * @param {string} text
     */
    addToContext(agent, sender, role, text) {
        const contextKey = `${agent}:${sender}`;
        const context = this._getOrCreateContext(contextKey, agent);
        context.messages.push({
            role,
            text: text.substring(0, 2000),
            ts: new Date().toISOString(),
        });
        if (context.messages.length > MAX_CTX_MESSAGES) {
            context.messages = context.messages.slice(-MAX_CTX_MESSAGES);
        }
    }

    /**
     * Returns formatted history block for injection into LLM prompts.
     *
     * @param {string} agent
     * @param {string} sender
     * @returns {string}
     */
    getHistoryBlock(agent, sender) {
        const contextKey = `${agent}:${sender}`;
        const context = this._contexts.get(contextKey);
        if (!context || context.messages.length === 0) return '';
        return (
            '\n=== RECENT CONVERSATION HISTORY ===\n' +
            context.messages.map(m => `[${m.role.toUpperCase()}]: ${m.text}`).join('\n') +
            '\n=== END HISTORY ===\n'
        );
    }

    /**
     * Emit a reply dispatched event (call after sending the reply).
     *
     * @param {string} platform
     * @param {string} sender
     * @param {string} agent
     * @param {string} reply
     */
    notifyReplyDispatched(platform, sender, agent, reply) {
        this.emit('replyDispatched', { platform, sender, agent, replyLength: reply.length });
    }

    /**
     * Returns list of agent names in routing priority order (for diagnostics).
     * @returns {string[]}
     */
    getAgentList() {
        return [...ROUTE_TABLE.map(r => r.agent), this._defaultAgent];
    }

    // ---- private ----

    _matchAgent(message) {
        for (const rule of ROUTE_TABLE) {
            for (const pattern of rule.patterns) {
                if (pattern.test(message)) {
                    return rule.agent;
                }
            }
        }
        return this._defaultAgent;
    }

    _getOrCreateContext(contextKey, agent) {
        if (!this._contexts.has(contextKey)) {
            this._contexts.set(contextKey, { agent, messages: [] });
        }
        return this._contexts.get(contextKey);
    }
}

/**
 * Factory — creates and initialises a GatewayDispatcher.
 *
 * @param {object} [options]
 * @param {string} [options.repoRoot]     Absolute path to Business-Empire-Agent root.
 * @param {string} [options.defaultAgent] Default agent when no pattern matches.
 * @returns {Promise<GatewayDispatcher>}
 */
async function createDispatcher(options = {}) {
    const dispatcher = new GatewayDispatcher(options);
    await dispatcher.init();
    return dispatcher;
}

module.exports = { GatewayDispatcher, createDispatcher };
