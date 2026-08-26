'use strict';

/**
 * TelegramAdapter — wraps all telegram_agent.js logic as a class.
 *
 * 100% backward-compatible with every command and feature in
 * telegram_agent.js (V15.8). The adapter delegates routing decisions
 * to GatewayDispatcher while keeping all Telegram-specific logic here.
 *
 * Public interface (mirrors all other adapters):
 *   start()                       — begin polling
 *   stop()                        — graceful shutdown
 *   sendMessage(chatId, text, opts) — send a text message
 *   onMessage(handler)            — register message handler
 */

require('dotenv').config({ path: require('path').resolve(__dirname, '..', '..', '.env.agents') });

const TelegramBot = require('node-telegram-bot-api');
const { spawn, exec } = require('child_process');
const { execFile, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const EventEmitter = require('events');

// ---- PLATFORM DETECTION (preserved from telegram_agent.js) ----
// All hardcoded paths now fall back to sensible defaults but accept env-var
// overrides so operators on non-standard layouts (Linux, WSL, custom venv
// locations) can configure without editing this file. Document the env vars
// in gateway/README.md.
const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON = process.env.BRAVO_PYTHON
    || (IS_MAC
        ? 'python3'
        : path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'));
const MACHINE_NAME = process.env.BRAVO_MACHINE_NAME
    || (IS_MAC ? 'MacBook' : 'Windows Desktop');
const TEMP_PATH = process.env.BRAVO_TEMP_DIR
    || (IS_MAC ? '/tmp' : (process.env.TEMP || path.join(REPO_ROOT, 'tmp')));

// C-Suite module (shared with telegram_agent.js)
const cSuite = require(path.join(REPO_ROOT, 'scripts', 'c_suite_context.js'));
const {
    readSiblingRepo,
    buildClaudeSpawnEnv,
    isClaudeAuthOrQuotaFailure,
    checkClaudeAuthPaths,
} = cSuite;

const LOG_FILE = path.join(REPO_ROOT, 'memory', 'telegram_bridge.log');
const LOCK_FILE = path.join(REPO_ROOT, 'tmp', 'bravo_telegram.lock.json');

const log = (msg) => {
    const line = `[${new Date().toISOString()}] [TELEGRAM] ${msg}\n`;
    process.stdout.write(line);
    try { fs.appendFileSync(LOG_FILE, line); } catch (_) {}
};

const isPidAlive = (pid) => {
    if (!pid || Number.isNaN(Number(pid))) return false;
    try { process.kill(Number(pid), 0); return true; } catch (_) { return false; }
};

const ensureTmpDir = () => {
    try { fs.mkdirSync(path.join(REPO_ROOT, 'tmp'), { recursive: true }); } catch (_) {}
};

const killTree = (pid) => {
    try {
        if (IS_WIN) {
            spawn('taskkill', ['/pid', String(pid), '/T', '/F'],
                { windowsHide: true, stdio: 'ignore', shell: false });
        } else {
            process.kill(pid, 'SIGKILL');
        }
    } catch (_) {}
};

// Strip ANSI codes and CLI noise (preserved from telegram_agent.js)
const cleanOutput = (raw) => {
    let text = raw
        .replace(/[][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '')
        .replace(/[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]/g, '');
    const noise = [
        /^[█▓░▀▄▐▌]+/,
        /logged in with/i, /waiting for mcp/i, /^Gemini CLI/i,
        /^Using model/i, /^Loading/i, /YOLO mode is enabled/i,
        /Loaded cached credentials/i, /supports tool updates/i,
        /^Bravo online\.?\s*$/i, /^Memory synced\.?\s*$/i,
        /Listening for changes/i, /^Server '/i, /^\s*$/,
    ];
    return text.split('\n')
        .filter(line => !noise.some(p => p.test(line.trim())))
        .join('\n').trim() || text.trim();
};

// File relay extensions (preserved from telegram_agent.js)
const FILE_EXTS = 'png|jpg|jpeg|gif|mov|mp4|pdf|txt|csv|md|html|zip';
const FILE_PATH_PATTERN = new RegExp(
    `(?:saved to|File:|file:|Screenshot|screenshot|Recording)[:\\s]+((?:[/~]|[A-Z]:[\\\\\/])[^\\s,)"']+\\.(?:${FILE_EXTS}))`, 'gi');
const DIRECT_PATH_PATTERN = new RegExp(
    `((?:\\/tmp\\/|[A-Z]:[\\\\\/](?:[^\\s,)"']*[\\\\\/])?(?:Temp|tmp|AppData[\\\\\/]Local[\\\\\/]Temp)[\\\\\/])[^\\s,)"']+\\.(?:${FILE_EXTS}))`, 'gi');
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif']);
const VIDEO_EXTS = new Set(['mov', 'mp4']);

class TelegramAdapter extends EventEmitter {
    constructor(dispatcher, options = {}) {
        super();
        this._dispatcher = dispatcher;
        this._token = process.env.TELEGRAM_BOT_TOKEN;
        this._bot = null;
        this._messageHandlers = [];
        this._shuttingDown = false;
        this._activeChildren = new Set();
        this._pollErrorCount = 0;
        this._pollingDormant = false;

        // ---- CONVERSATION HISTORY (preserved from telegram_agent.js) ----
        const MAX_HISTORY = 15;
        const HISTORY_FILE = path.join(REPO_ROOT, 'tmp', 'telegram_history.json');
        let chatHistory = {};
        try {
            if (fs.existsSync(HISTORY_FILE)) {
                chatHistory = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf8'));
            }
        } catch (_) { chatHistory = {}; }

        this._MAX_HISTORY = MAX_HISTORY;
        this._HISTORY_FILE = HISTORY_FILE;
        this._chatHistory = chatHistory;

        // ---- RATE LIMITING (preserved) ----
        this._rateLimitMap = {};
        this._RATE_LIMIT_WINDOW = 10000;
        this._RATE_LIMIT_MAX = 5;

        // ---- ALLOWED USERS (preserved) ----
        this._allowedUsers = (process.env.TELEGRAM_ALLOWED_USERS || '')
            .split(',').map(id => id.trim()).filter(Boolean);

        // ---- APPROVAL GATE (preserved) ----
        this._CONFIRM_PATTERN = /⚠️\s*CONFIRM:\s*(.+)$/m;
        this._pendingConfirmations = {};

        // ---- PATHS (env-overridable; documented in gateway/README.md) ----
        // BRAVO_CLAUDE_EXE / BRAVO_GEMINI_SCRIPT can override the auto-detected
        // CLI locations when operators install the tools to non-default paths.
        this._NODE_EXE = process.execPath;
        this._CLAUDE_EXE = process.env.BRAVO_CLAUDE_EXE
            || (IS_MAC
                ? 'claude'
                : path.join(process.env.USERPROFILE || '', '.local', 'bin', 'claude.exe'));
        this._GEMINI_SCRIPT = process.env.BRAVO_GEMINI_SCRIPT
            || (IS_MAC
                ? (() => {
                    const nvmDir = path.join(process.env.HOME || '', '.nvm', 'versions', 'node');
                    return path.join(nvmDir, process.version, 'lib', 'node_modules',
                        '@google', 'gemini-cli', 'dist', 'index.js');
                })()
                : path.join(process.env.APPDATA || '',
                    'npm', 'node_modules', '@google', 'gemini-cli', 'dist', 'index.js'));

        this._MCP_CONFIG_PATH = path.join(REPO_ROOT, '.claude', 'mcp.json');
        this._HAS_MCP_CONFIG = fs.existsSync(this._MCP_CONFIG_PATH);

        // OpenCode CLI — fallback when Claude subscription quota/auth fails
        // (2026-08-26, mirrors telegram_agent.js + coordination_agent.js).
        // Native binary only (never .cmd/.ps1 shims), prompt via stdin,
        // restricted bravo-oneshot agent (all tools denied). Fallback replies
        // are always TEXT-ONLY regardless of tier.
        this._OPENCODE_EXE = IS_MAC || !IS_WIN
            ? 'opencode'
            : path.join(process.env.APPDATA || '', 'npm', 'node_modules', 'opencode-ai', 'bin', 'opencode.exe');
        this._HAS_OPENCODE = (() => {
            try {
                if (IS_WIN) return fs.existsSync(this._OPENCODE_EXE);
                execFileSync('which', ['opencode'], { stdio: 'ignore' });
                return true;
            } catch (_) { return false; }
        })();
        this._OPENCODE_FALLBACK_MODEL = 'opencode/big-pickle';
        this._OPENCODE_TIMEOUT = 180000;
        if (this._HAS_OPENCODE) log(`[OPENCODE] Fallback available: ${this._OPENCODE_EXE}`);
        else log('[OPENCODE] Fallback NOT available — opencode not found (npm i -g opencode-ai)');

        // Timeouts
        this._GEMINI_TIMEOUT = 300000;
        this._CLAUDE_TIMEOUT = 600000;

        // ---- TIER CLASSIFIERS (preserved from telegram_agent.js) ----
        this._T1_KEYWORDS = ['status', 'check', 'what', 'how much', 'mrr', 'balance', 'count',
            'list', 'show', 'hello', 'hey', 'hi', 'thanks'];
        this._T3_KEYWORDS = ['redesign', 'architecture', 'refactor', 'migrate', 'schema',
            'system', 'overhaul', 'sparc', 'complex', 'multi-file'];
        this._T0_KEYWORDS = /\b(open|launch|click|screenshot|volume|mute|play|switch|type|close|quit|move|resize|fullscreen|minimize|snap|record|dark.?mode|wifi|bluetooth|brightness|clipboard|copy|paste|lock|sleep|battery|sysinfo|soundcloud|music|song|track|browse|tab|website|url|amazon|download|scroll|mouse|drag|ping|network|ip|audio|shutdown|restart|cart|inbox|email|gmail|calendar|meeting|schedule|stripe|balance|invoice|payment|customer|post|social|linkedin|instagram|threads|tiktok|youtube|facebook|reddit|workflow|n8n|supabase|database|running|processes|apps)\b/i;
        this._T0_CODING_EXCLUSIONS = /\b(fix|debug|implement|refactor|build feature|write code|write function|failing test|unit test|create api|create endpoint|create route|create table|create schema)\b/i;

        // Stale confirmation cleanup
        this._confirmCleanupTimer = null;
    }

    // ---- PUBLIC INTERFACE ----

    /**
     * Start polling for Telegram messages.
     */
    async start() {
        if (!this._token) {
            log('TELEGRAM_BOT_TOKEN not set — Telegram adapter inactive.');
            return;
        }

        this._acquireInstanceLock();

        this._bot = new TelegramBot(this._token, {
            polling: { autoStart: false, params: { timeout: 30 } },
            request: { timeout: 60000 },
        });

        this._registerHandlers();

        this._confirmCleanupTimer = setInterval(() => {
            const now = Date.now();
            for (const [chatId, pending] of Object.entries(this._pendingConfirmations)) {
                if (now - pending.timestamp > 300000) {
                    delete this._pendingConfirmations[chatId];
                    log(`[APPROVAL] Stale confirmation expired for chat ${chatId}`);
                }
            }
        }, 300000);

        try {
            const pollingStart = this._bot.startPolling();
            log('Polling started.');
            if (pollingStart && typeof pollingStart.catch === 'function') {
                pollingStart.catch(err => log(`Polling start error: ${err.message}`));
            }
        } catch (err) {
            log(`Failed to start polling: ${err.message}`);
        }

        this._startupHealthCheck();
    }

    /**
     * Stop polling gracefully.
     */
    async stop() {
        if (this._shuttingDown) return;
        this._shuttingDown = true;
        log('Stopping adapter...');
        if (this._confirmCleanupTimer) clearInterval(this._confirmCleanupTimer);
        for (const c of this._activeChildren) killTree(c.pid);
        try { if (this._bot) await this._bot.stopPolling(); } catch (_) {}
        this._releaseInstanceLock();
        setTimeout(() => {}, 100);
    }

    /**
     * Send a text message to a chat.
     * @param {string|number} chatId
     * @param {string} text
     * @param {object} [opts]   node-telegram-bot-api send options
     */
    async sendMessage(chatId, text, opts = {}) {
        if (!this._bot) throw new Error('TelegramAdapter not started');
        return this._bot.sendMessage(chatId, text, opts);
    }

    /**
     * Register a message handler (called for every authorised message).
     * @param {function} handler  async (msg: TelegramMessage) => void
     */
    onMessage(handler) {
        this._messageHandlers.push(handler);
    }

    // ---- PRIVATE: INSTANCE LOCK ----

    _acquireInstanceLock() {
        ensureTmpDir();
        try {
            if (fs.existsSync(LOCK_FILE)) {
                const existing = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
                if (existing.pid && existing.pid !== process.pid && isPidAlive(existing.pid)) {
                    log(`[LOCK] Another bridge owns polling (pid ${existing.pid}). Exiting.`);
                    process.exit(0);
                }
                log(`[LOCK] Replacing stale lock from pid ${existing.pid || 'unknown'}.`);
            }
        } catch (err) {
            log(`[LOCK] Could not read lock: ${err.message}`);
        }
        fs.writeFileSync(LOCK_FILE, JSON.stringify({
            pid: process.pid, machine: MACHINE_NAME,
            platform: process.platform, started_at: new Date().toISOString(),
        }, null, 2));
    }

    _releaseInstanceLock() {
        try {
            if (!fs.existsSync(LOCK_FILE)) return;
            const existing = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
            if (existing.pid === process.pid) fs.unlinkSync(LOCK_FILE);
        } catch (_) {}
    }

    // ---- PRIVATE: HISTORY ----

    _saveHistory() {
        try { fs.writeFileSync(this._HISTORY_FILE, JSON.stringify(this._chatHistory)); } catch (_) {}
    }

    _addToHistory(chatId, role, text) {
        const id = String(chatId);
        if (!this._chatHistory[id]) this._chatHistory[id] = [];
        this._chatHistory[id].push({ role, text: text.substring(0, 2000), ts: new Date().toISOString() });
        if (this._chatHistory[id].length > this._MAX_HISTORY) {
            this._chatHistory[id] = this._chatHistory[id].slice(-this._MAX_HISTORY);
        }
        this._saveHistory();
    }

    _getHistoryBlock(chatId) {
        const id = String(chatId);
        const msgs = this._chatHistory[id];
        if (!msgs || msgs.length === 0) return '';
        return '\n=== RECENT CONVERSATION HISTORY ===\n' +
            msgs.map(m => `[${m.role.toUpperCase()}]: ${m.text}`).join('\n') +
            '\n=== END HISTORY ===\n';
    }

    // ---- PRIVATE: TIER CLASSIFICATION (preserved) ----

    _classifyTier(text) {
        const t = text.toLowerCase();
        if (this._T0_KEYWORDS.test(t) && !this._T3_KEYWORDS.some(k => t.includes(k)) &&
            !this._T0_CODING_EXCLUSIONS.test(t)) return 0;
        if (this._T3_KEYWORDS.some(k => t.includes(k))) return 3;
        const hasActionVerb = /\b(build|fix|implement|create|update|add|modify|debug|test|deploy|write|change|edit|push|ship|review)\b/.test(t);
        if (!hasActionVerb && this._T1_KEYWORDS.some(k => t.includes(k))) return 1;
        return 2;
    }

    // ---- PRIVATE: FILE READING (preserved) ----

    _readFileSafe(relPath, maxLines = 0) {
        try {
            const content = fs.readFileSync(path.join(REPO_ROOT, relPath), 'utf8');
            if (maxLines > 0) return content.split('\n').slice(0, maxLines).join('\n').trim();
            return content.trim();
        } catch (_) { return ''; }
    }

    // ---- PRIVATE: CONTEXT LOADING (preserved) ----

    _loadCSuiteSnapshot() { return cSuite.loadCSuiteSnapshot({ python: PYTHON }); }
    _loadLocalSiblingPaths() { return cSuite.loadLocalSiblingPaths({ machineName: MACHINE_NAME }); }
    _loadSiblingPulses() { return cSuite.loadSiblingPulses(); }

    _loadContext(tier = 2) {
        const chunks = [];
        const state = this._readFileSafe('brain/STATE.md');
        if (state) chunks.push(`=== STATE.md (current state) ===\n${state}`);
        const tasks = this._readFileSafe('memory/ACTIVE_TASKS.md', 50);
        if (tasks) chunks.push(`=== ACTIVE_TASKS.md ===\n${tasks}`);

        if (tier === 1) {
            chunks.push('=== Context Tier: T1 MINIMAL (status query) ===');
            return chunks.join('\n\n');
        }

        chunks.push(this._loadCSuiteSnapshot());
        chunks.push(this._loadLocalSiblingPaths());
        chunks.push(this._loadSiblingPulses());
        const claude_md = this._readFileSafe('CLAUDE.md');
        if (claude_md) chunks.push(`=== CLAUDE.md (project instructions) ===\n${claude_md}`);
        const soul = this._readFileSafe('brain/SOUL.md', 40);
        if (soul) chunks.push(`=== SOUL.md (identity) ===\n${soul}`);
        const user = this._readFileSafe('brain/USER.md', 50);
        if (user) chunks.push(`=== USER.md (CC's profile) ===\n${user}`);
        const sessionLog = this._readFileSafe('memory/SESSION_LOG.md');
        if (sessionLog) {
            const lastN = sessionLog.split('\n').slice(tier === 3 ? -50 : -30).join('\n').trim();
            if (lastN) chunks.push(`=== SESSION_LOG.md (recent) ===\n${lastN}`);
        }
        chunks.push(`=== Available CLI Tools ===
- n8n: ${PYTHON} scripts/integrations/n8n_tool.py [list|get|execute|activate]
- Supabase: ${PYTHON} scripts/integrations/supabase_tool.py [select|insert|sql]
- Stripe: ${PYTHON} scripts/integrations/stripe_tool.py [balance|customers|invoices]
- Email/Calendar: ${PYTHON} scripts/integrations/google_tool.py [gmail send|gmail list|calendar list]
- Context Manager: ${PYTHON} scripts/core/context_manager.py [tier|compact|status|health]
- Cost Tracker: ${PYTHON} scripts/cost_tracker.py [log|summary|session|budget]
- Firecrawl: ${PYTHON} scripts/integrations/firecrawl_tool.py [scrape|crawl|search|extract|map]
- Semantic memory: ${PYTHON} scripts/integrations/mem0_tool.py [add|search|list|get|delete|stats]`);

        if (tier === 2) {
            chunks.push('=== Context Tier: T2 STANDARD ===');
            const full = chunks.join('\n\n');
            return full.length > 6000 ? full.substring(0, 6000) + '\n...(truncated)' : full;
        }

        // T3
        const appReg = this._readFileSafe('brain/APP_REGISTRY.md', 50);
        if (appReg) chunks.push(`=== APP_REGISTRY.md ===\n${appReg}`);
        const agents = this._readFileSafe('brain/AGENTS.md', 80);
        if (agents) chunks.push(`=== AGENTS.md (sub-agent registry) ===\n${agents}`);
        const mavenState = readSiblingRepo('maven', 'brain/STATE.md', 30);
        if (mavenState) chunks.push(`=== MAVEN brain/STATE.md (top 30 lines) ===\n${mavenState}`);
        const atlasState = readSiblingRepo('atlas', 'brain/STATE.md', 30);
        if (atlasState) chunks.push(`=== ATLAS brain/STATE.md (top 30 lines) ===\n${atlasState}`);
        const patterns = this._readFileSafe('memory/PATTERNS.md', 30);
        if (patterns) chunks.push(`=== PATTERNS.md ===\n${patterns}`);
        const mistakes = this._readFileSafe('memory/MISTAKES.md', 30);
        if (mistakes) chunks.push(`=== MISTAKES.md ===\n${mistakes}`);
        chunks.push('=== Context Tier: T3 FULL ===');
        const full = chunks.join('\n\n');
        return full.length > 10000 ? full.substring(0, 10000) + '\n...(truncated)' : full;
    }

    // ---- PRIVATE: PROMPT BUILDERS (preserved) ----

    _buildGeminiPrompt(chatId) {
        const history = this._getHistoryBlock(chatId);
        const csuite = this._loadCSuiteSnapshot();
        const reach = this._loadLocalSiblingPaths();
        return `You are BRAVO (CEO agent), CC's AI assistant on Telegram. RULES: (1) Answer the question directly in 1-5 sentences. (2) Do NOT summarize recent work unless asked. (3) Do NOT greet CC with a status update. (4) Use CONVERSATION HISTORY below for context. (5) You are ONE of FOUR agents — see C-SUITE table. Route Atlas/Maven/Aura queries using that table.

${csuite}

${reach}
${history}
CC's message:`;
    }

    _buildPrompt(chatId, userText = '') {
        const tier = this._classifyTier(userText);
        const history = this._getHistoryBlock(chatId);
        log(`[TIER] T${tier} — loading ${tier === 0 ? 'COMPUTER CONTROL' : tier === 1 ? 'minimal' : tier === 2 ? 'standard' : 'full'} context`);

        if (tier === 0) {
            const csuite = this._loadCSuiteSnapshot();
            const reach = this._loadLocalSiblingPaths();
            return `You are Bravo (CEO agent), CC's right hand — CEO, COO & CTO in one — on his ${MACHINE_NAME}. Full CLI access. Be direct.

${csuite}

${reach}

BUSINESS OPS:
- Email: ${PYTHON} scripts/integrations/google_tool.py gmail list | gmail send --to "..." --subject "..." --body "..."
- Revenue: ${PYTHON} scripts/revenue_engine.py mrr | dashboard | forecast | clients | goal
- Stripe: ${PYTHON} scripts/integrations/stripe_tool.py balance | customers | invoices
- CEO Briefing: ${PYTHON} scripts/ceo_dashboard.py briefing | revenue | pipeline | content | full
- Leads/CRM: ${PYTHON} scripts/lead_engine.py list | add "Name" --email x | followups | view <id>
- Database: ${PYTHON} scripts/integrations/supabase_tool.py select <table> --project bravo --limit 10
- n8n: ${PYTHON} scripts/integrations/n8n_tool.py list | execute <id>

COMPUTER CONTROL (${IS_MAC ? 'macOS' : 'Windows'}):
- All commands: ${PYTHON} scripts/${IS_MAC ? 'macos' : 'windows'}_control.py <command> [args] --json

${history}
CC says:`;
        }

        const context = this._loadContext(tier);
        const csuite = this._loadCSuiteSnapshot();
        const reach = this._loadLocalSiblingPaths();
        return `You are BRAVO V5.5 (CEO agent), CC's right hand — CEO, COO & CTO in one — running via Telegram bridge on ${MACHINE_NAME}.
You have full access to the Business-Empire-Agent project at ${REPO_ROOT}.
Platform: ${IS_MAC ? 'macOS' : 'Windows 11'} — Machine: ${MACHINE_NAME}

${csuite}

${reach}

${context}
${history}
TELEGRAM RULES: (1) Answer directly in 1-5 sentences. (2) No file dumps unless asked. (3) Use CLI tools for DB/social/Stripe/n8n. (4) cd to app LOCAL PATH for code changes. (5) Update SESSION_LOG.md after significant work. (6) Address CC by name. (7) All credentials in .env.agents — NEVER hardcode. (8) APPROVAL GATE: Before destructive actions, output "⚠️ CONFIRM: [description]" and STOP.

CC's message:`;
    }

    // ---- PRIVATE: MCP DETECTION (preserved) ----

    _detectMcps(text) {
        const t = text.toLowerCase();
        const mcps = [];
        if (/post|tweet|schedule|social|linkedin|instagram|content/i.test(t)) mcps.push('late');
        if (/database|supabase|table|sql|query|schema/i.test(t)) mcps.push('supabase');
        if (/workflow|n8n|automat/i.test(t)) mcps.push('n8n-mcp');
        if (/stripe|payment|invoice|subscription|balance/i.test(t)) mcps.push('stripe');
        if (/browse|website|screenshot|url|http/i.test(t)) mcps.push('playwright');
        if (/docs|library|documentation|api reference/i.test(t)) mcps.push('context7');
        mcps.push('memory', 'sequential-thinking');
        return mcps;
    }

    // ---- PRIVATE: CLI EXECUTION (preserved from telegram_agent.js) ----

    /**
     * _executeOpenCodeFallback — text-only OpenCode reply when the Claude
     * spawn fails (quota/auth/missing CLI). Returns the model's text or null.
     * Always the tool-denied bravo-oneshot agent: a degraded answer beats no
     * answer, and it can never mutate anything.
     */
    _executeOpenCodeFallback(userPrompt) {
        return new Promise((resolve) => {
            if (!this._HAS_OPENCODE) { resolve(null); return; }
            log(`[OPENCODE FALLBACK] spawning ${this._OPENCODE_FALLBACK_MODEL}`);
            const args = [
                'run', '--model', this._OPENCODE_FALLBACK_MODEL, '--agent', 'bravo-oneshot',
                '--format', 'default', '--dir', REPO_ROOT,
            ];
            const child = spawn(this._OPENCODE_EXE, args, {
                env: { ...process.env, CI: 'true', NONINTERACTIVE: 'true', PAGER: 'cat', NO_COLOR: '1', FORCE_COLOR: '0' },
                stdio: ['pipe', 'pipe', 'pipe'], shell: false, windowsHide: true, cwd: REPO_ROOT,
            });
            child.stdin.write(userPrompt);
            child.stdin.end();
            this._activeChildren.add(child);
            let stdout = '', stderr = '';
            child.stdout.on('data', (d) => { stdout += d.toString(); });
            child.stderr.on('data', (d) => { stderr += d.toString(); });
            const timer = setTimeout(() => {
                log('[OPENCODE FALLBACK] timed out');
                if (child.pid) killTree(child.pid);
                this._activeChildren.delete(child);
                resolve(null);
            }, this._OPENCODE_TIMEOUT);
            child.on('close', (code) => {
                clearTimeout(timer);
                this._activeChildren.delete(child);
                log(`[OPENCODE FALLBACK] code=${code} stdout=${stdout.length}b`);
                if (code !== 0) { resolve(null); return; }
                const cleaned = cleanOutput(stdout.trim());
                resolve(cleaned || null);
            });
            child.on('error', (e) => {
                clearTimeout(timer);
                this._activeChildren.delete(child);
                log(`[OPENCODE FALLBACK ERR] ${e.message}`);
                resolve(null);
            });
        });
    }

    _executeCli(tool, userPrompt, chatId, modelOverride = null) {
        return new Promise((resolve) => {
            const fullPrompt = tool === 'claude'
                ? `${this._buildPrompt(chatId, userPrompt)} ${userPrompt}`
                : `${this._buildGeminiPrompt(chatId)} ${userPrompt}`;
            const tier = this._classifyTier(userPrompt);
            const timeout = tool === 'claude'
                ? (tier === 0 ? 300000 : this._CLAUDE_TIMEOUT)
                : this._GEMINI_TIMEOUT;

            let cmd, args;
            if (tool === 'claude') {
                cmd = this._CLAUDE_EXE;
                args = [
                    '-p', fullPrompt,
                    '--permission-mode', 'acceptEdits',
                    '--output-format', 'text',
                    '--max-turns', tier === 0 ? '6' : '25',
                    '--setting-sources', 'project,local',
                ];
                if (this._HAS_MCP_CONFIG) args.push('--mcp-config', this._MCP_CONFIG_PATH);
                if (modelOverride) args.push('--model', modelOverride);
            } else {
                const mcps = this._detectMcps(userPrompt);
                cmd = this._NODE_EXE;
                args = [
                    '--no-warnings=DEP0040', this._GEMINI_SCRIPT,
                    '-p', fullPrompt, '--approval-mode', 'auto_edit',
                    '--output-format', 'text',
                    ...mcps.flatMap(m => ['--allowed-mcp-server-names', m]),
                ];
            }

            log(`[EXEC] ${tool}: "${userPrompt.substring(0, 80)}..."`);

            // Subscription-ONLY (2026-07-18): buildClaudeSpawnEnv's default
            // strips ANTHROPIC_API_KEY (key dead + banned, CLI-only rule).
            const spawnEnv = tool === 'claude'
                ? buildClaudeSpawnEnv({
                    extras: { CI: 'true', NONINTERACTIVE: 'true', PAGER: 'cat', NO_COLOR: '1', FORCE_COLOR: '0' },
                })
                : { ...process.env, CI: 'true', NONINTERACTIVE: 'true', PAGER: 'cat', NO_COLOR: '1', FORCE_COLOR: '0' };

            const child = spawn(cmd, args, {
                env: spawnEnv, stdio: ['ignore', 'pipe', 'pipe'],
                shell: false, windowsHide: true, cwd: REPO_ROOT,
            });
            this._activeChildren.add(child);

            let stdout = '', stderr = '';
            child.stdout.on('data', d => { stdout += d.toString(); });
            child.stderr.on('data', d => { stderr += d.toString(); });
            const startTime = Date.now();

            const progressTimer = setInterval(() => {
                if (chatId && this._bot) {
                    const elapsed = Math.round((Date.now() - startTime) / 1000);
                    this._bot.sendChatAction(chatId, 'typing').catch(() => {});
                    if (elapsed >= 120 && elapsed % 120 === 0) {
                        this._bot.sendMessage(chatId, `Still working... (${elapsed}s)`).catch(() => {});
                    }
                }
            }, 15000);

            const timer = setTimeout(() => {
                log(`[TIMEOUT] ${tool} killed after ${timeout / 1000}s`);
                if (child.pid) killTree(child.pid);
                const partial = cleanOutput(stdout.trim());
                resolve(partial && partial.length > 20
                    ? `(Partial — timed out after ${timeout / 1000}s)\n\n${partial}`
                    : `Timed out after ${timeout / 1000}s.`);
            }, timeout);

            child.on('close', async (code) => {
                clearTimeout(timer);
                clearInterval(progressTimer);
                this._activeChildren.delete(child);
                const elapsed = Math.round((Date.now() - startTime) / 1000);
                log(`[DONE] ${tool} code=${code} stdout=${stdout.length}b time=${elapsed}s`);

                // Cost tracking
                const units = tool === 'claude' ? Math.ceil(elapsed / 60) * 3 : Math.ceil(elapsed / 60) * 2;
                execFile(PYTHON, ['scripts/cost_tracker.py', 'log',
                    '--label', `telegram_${tool}`, '--units', String(units),
                    '--detail', userPrompt.substring(0, 80)],
                    { cwd: REPO_ROOT, windowsHide: true, timeout: 5000 }, () => {});

                // State sync after successful Claude runs
                if (tool === 'claude' && code === 0 && tier > 0) {
                    execFile(PYTHON, ['scripts/state/state_sync.py',
                        '--note', `telegram T${tier}: ${userPrompt.substring(0, 140)}`],
                        { cwd: REPO_ROOT, windowsHide: true, timeout: 8000 }, () => {});
                }

                const raw = stdout.trim() || stderr.trim();
                if (!raw) {
                    resolve(code === 0 ? 'Done.' : `Error (code ${code}).`);
                    return;
                }

                // Fail LOUD — no metered-key retry (key dead + banned). But a
                // quota/auth outage no longer dead-ends the chat: degrade to
                // the OpenCode free tier (text-only) before giving up.
                const looksLikeAuth = isClaudeAuthOrQuotaFailure(raw, code);
                if (looksLikeAuth && tool === 'claude') {
                    log(`[AUTH FAIL] subscription quota/auth failure: ${raw.substring(0, 200)}`);
                    const fb = await this._executeOpenCodeFallback(userPrompt);
                    resolve(fb || 'Claude subscription quota or auth failure. If quota: wait for the window to reset. If auth: run `claude setup-token`, then restart the bridge.');
                    return;
                }
                resolve(cleanOutput(raw));
            });

            child.on('error', async (err) => {
                clearTimeout(timer);
                clearInterval(progressTimer);
                this._activeChildren.delete(child);
                log(`[ERROR] ${tool}: ${err.message}`);
                if (tool === 'claude') {
                    const fb = await this._executeOpenCodeFallback(userPrompt);
                    if (fb) { resolve(fb); return; }
                }
                resolve(`Error: ${err.message}`);
            });
        });
    }

    // ---- PRIVATE: FILE RELAY (preserved) ----

    async _sendFilesToChat(chatId, text) {
        const paths = new Set();
        let match;
        const p1 = new RegExp(FILE_PATH_PATTERN.source, FILE_PATH_PATTERN.flags);
        while ((match = p1.exec(text)) !== null) { if (match[1]) paths.add(match[1]); }
        const p2 = new RegExp(DIRECT_PATH_PATTERN.source, DIRECT_PATH_PATTERN.flags);
        while ((match = p2.exec(text)) !== null) {
            if (match[1]) paths.add(match[1]);
            else if (match[0]) paths.add(match[0]);
        }
        const winTempPattern = /[A-Z]:\\[^\s,)"']*\\Temp\\[^\s,)"']+\.(?:png|jpg|jpeg|gif|mov|mp4|pdf)/gi;
        while ((match = winTempPattern.exec(text)) !== null) { paths.add(match[0]); }

        let sent = 0;
        for (const filePath of paths) {
            try {
                if (!fs.existsSync(filePath)) continue;
                const stat = fs.statSync(filePath);
                if (stat.size === 0 || stat.size > 50 * 1024 * 1024) continue;
                const ext = path.extname(filePath).slice(1).toLowerCase();
                if (IMAGE_EXTS.has(ext)) {
                    await this._bot.sendPhoto(chatId, filePath, { caption: path.basename(filePath) });
                } else if (VIDEO_EXTS.has(ext)) {
                    await this._bot.sendVideo(chatId, filePath, { caption: path.basename(filePath) });
                } else {
                    await this._bot.sendDocument(chatId, filePath, { caption: path.basename(filePath) });
                }
                sent++;
            } catch (e) {
                log(`[FILE] Failed to send ${filePath}: ${e.message}`);
            }
        }
        return sent;
    }

    // ---- PRIVATE: VOICE TRANSCRIPTION (preserved) ----

    async _handleVoiceMessage(msg) {
        const chatId = msg.chat.id;
        const voice = msg.voice || msg.audio;
        if (!voice) return null;
        try {
            await this._bot.sendMessage(chatId, 'Transcribing...');
            const fileInfo = await this._bot.getFile(voice.file_id);
            const fileUrl = `https://api.telegram.org/file/bot${this._token}/${fileInfo.file_path}`;
            const tmpDir = process.env.TEMP || '/tmp';
            const oggPath = path.join(tmpDir, `voice_${Date.now()}.ogg`);
            const { execSync } = require('child_process');
            execSync(`curl -s -o "${oggPath}" "${fileUrl}"`, { timeout: 15000, windowsHide: true });
            if (!fs.existsSync(oggPath)) {
                await this._bot.sendMessage(chatId, 'Failed to download voice note.');
                return null;
            }
            const transcription = await new Promise((resolve) => {
                execFile(PYTHON, ['scripts/transcribe.py', '--file', oggPath,
                    '--model', voice.duration > 30 ? 'base' : 'tiny'],
                    { cwd: REPO_ROOT, timeout: 120000, windowsHide: true },
                    (err, stdout) => {
                        try { fs.unlinkSync(oggPath); } catch (_) {}
                        if (err) { resolve(null); return; }
                        try {
                            const result = JSON.parse(stdout.trim());
                            resolve(result.ok && result.text ? result.text : null);
                        } catch (_) { resolve(null); }
                    });
            });
            if (transcription) {
                await this._bot.sendMessage(chatId, `"${transcription}"\n\nProcessing...`);
                return transcription;
            }
            await this._bot.sendMessage(chatId, "Couldn't transcribe. Try typing your message.");
            return null;
        } catch (e) {
            log(`[VOICE] Error: ${e.message}`);
            await this._bot.sendMessage(chatId, 'Voice processing failed.').catch(() => {});
            return null;
        }
    }

    // ---- PRIVATE: MAIN MESSAGE HANDLER (preserved) ----

    _registerHandlers() {
        this._bot.on('message', async (msg) => {
            const chatId = msg.chat.id;
            let text = msg.text;
            if (!text && (msg.voice || msg.audio)) {
                text = await this._handleVoiceMessage(msg);
                if (!text) return;
            }
            if (!text) return;

            const userId = String(msg.from.id);
            const user = msg.from.username || msg.from.first_name || '?';

            // Security: auto-register first user
            if (this._allowedUsers.length === 0) {
                this._autoRegisterUser(userId);
                log(`[SECURITY] First user registered: ${user} (${userId})`);
            } else if (!this._allowedUsers.includes(userId)) {
                log(`[BLOCKED] Unauthorized: ${user} (${userId})`);
                return this._bot.sendMessage(chatId, 'Unauthorized.').catch(() => {});
            }

            // Rate limiting
            const now = Date.now();
            if (!this._rateLimitMap[userId]) this._rateLimitMap[userId] = [];
            this._rateLimitMap[userId] = this._rateLimitMap[userId].filter(t => now - t < this._RATE_LIMIT_WINDOW);
            if (this._rateLimitMap[userId].length >= this._RATE_LIMIT_MAX) {
                return this._bot.sendMessage(chatId, 'Slow down — max 5 messages per 10 seconds.').catch(() => {});
            }
            this._rateLimitMap[userId].push(now);

            log(`[MSG] ${user} (${userId}): ${text}`);

            // Notify external handlers (for dispatcher integration)
            for (const handler of this._messageHandlers) {
                try { await handler(msg); } catch (_) {}
            }

            // Also route through dispatcher for tracking (does not change behavior — bravo default)
            if (this._dispatcher) {
                try {
                    const { agent } = this._dispatcher.route(text, 'telegram', userId);
                    if (agent !== 'bravo') {
                        log(`[DISPATCH] Routed to ${agent} (note: Telegram adapter always uses Claude/Gemini — dispatcher tracking only)`);
                    }
                    this._dispatcher.addToContext(agent, userId, 'user', text);
                } catch (_) {}
            }

            await this._handleCommand(chatId, userId, user, text);
        });

        this._bot.on('callback_query', async (query) => {
            await this._handleCallbackQuery(query);
        });

        // 409 handling: in-process exponential backoff, do NOT go silently
        // dormant (old pattern left bridges dead for days) and do NOT exit
        // (creates ghost long-poll connections that re-trigger the 409 on
        // restart — see Maven 2026-05-18, 512 pm2 restarts). Stay alive,
        // wait for the stale long-poll to expire on Telegram's side, then
        // resume polling in-process. Counter resets after 5 min healthy.
        this._pollConflictCount = 0;
        this._pollResumeTimer = null;
        this._lastPollOkAt = Date.now();
        this._scheduleResumeAfterConflict = () => {
            if (this._pollResumeTimer) return;
            const baseDelays = [60000, 90000, 120000, 180000, 300000];
            const c = this._pollConflictCount;
            const delay = c <= baseDelays.length
                ? baseDelays[Math.min(c - 1, baseDelays.length - 1)]
                : 600000;
            log(`[POLL] 409 conflict #${c}: pausing polling for ${Math.round(delay/1000)}s ` +
                `to let the stale long-poll connection expire on Telegram's side.`);
            this._pollResumeTimer = setTimeout(async () => {
                this._pollResumeTimer = null;
                try { await this._bot.stopPolling(); } catch (_) {}
                try {
                    await this._bot.startPolling({ restart: true });
                    log('[POLL] Resumed polling after 409 backoff.');
                    setTimeout(() => {
                        if (Date.now() - this._lastPollOkAt > 4.5 * 60 * 1000) {
                            this._pollConflictCount = 0;
                            log('[POLL] 5 min stable since last 409 — backoff counter reset.');
                        }
                    }, 5 * 60 * 1000);
                } catch (err) {
                    log(`[POLL] startPolling after backoff failed: ${err.message || err}.`);
                }
            }, delay);
        };

        this._bot.on('polling_error', (e) => {
            this._pollErrorCount++;
            const msg = e.message || String(e);
            if (msg.includes('409') || msg.includes('Conflict')) {
                this._pollConflictCount++;
                this._bot.stopPolling().catch(() => {});
                this._scheduleResumeAfterConflict();
                return;
            }
            if (this._pollErrorCount === 1 || this._pollErrorCount % 50 === 0) {
                log(`[POLL] Error: ${msg} (count: ${this._pollErrorCount})`);
            }
        });
        // Track polls so the conflict counter resets after healthy traffic
        this._bot.on('message', () => { this._lastPollOkAt = Date.now(); });
    }

    // ---- PRIVATE: COMMAND HANDLER (all commands preserved) ----

    async _handleCommand(chatId, userId, user, text) {
        // /start, /help
        if (text === '/start' || text === '/help') {
            return this._bot.sendMessage(chatId, [
                `Bravo Bridge V15.8 (${MACHINE_NAME} — via Gateway)`,
                '',
                'Just type anything → Claude handles it',
                '',
                '!gemini <query> → Gemini CLI',
                '!opus / !sonnet / !haiku <query> → choose model',
                '',
                'WORKFLOWS:',
                '/ship [branch] — full release flow',
                '/retro [date] — session retrospective',
                '/review [file] — code review',
                '/plan <task> — plan-then-execute',
                '',
                'OPS:',
                '/costs — today\'s cost summary',
                '/memhealth — memory health',
                '/compact — compaction status',
                '/stale — facts older than 30 days',
                '/clear — clear conversation history',
                '/whoami — show your Telegram user ID',
            ].join('\n'));
        }

        if (text === '/whoami') {
            return this._bot.sendMessage(chatId, `User ID: ${userId}\nUsername: ${user}\nChat ID: ${chatId}`);
        }

        // Workflow slash commands
        const WORKFLOW_COMMANDS = {
            '/ship': (arg) => `Run the /ship workflow. Load skills/ship/SKILL.md and execute the full release flow${arg ? ` for branch: ${arg}` : ''}. Confirm before any destructive action.`,
            '/retro': (arg) => `Run the /retro workflow. Load skills/retro/SKILL.md and produce a retrospective${arg ? ` for ${arg}` : ' for the current session'}.`,
            '/review': (arg) => `Run the /review workflow. Load skills/code-review/SKILL.md and review${arg ? ` ${arg}` : ' the pending changes on the current branch'}.`,
            '/plan': (arg) => `Enter plan mode for this task: ${arg || '(no task supplied — ask CC for details)'}. Do NOT execute until CC approves.`,
        };
        const slashMatch = text.match(/^(\/(?:ship|retro|review|plan))(?:\s+(.+))?$/);
        if (slashMatch && WORKFLOW_COMMANDS[slashMatch[1]]) {
            const cmd = slashMatch[1];
            const arg = (slashMatch[2] || '').trim();
            const synthetic = WORKFLOW_COMMANDS[cmd](arg);
            log(`[SLASH] ${cmd} -> synthetic prompt`);
            this._addToHistory(chatId, 'user', `${cmd} ${arg}`.trim());
            await this._bot.sendChatAction(chatId, 'typing');
            await this._bot.sendMessage(chatId, `Running ${cmd}...`);
            const result = await this._executeCli('claude', synthetic, chatId);
            this._addToHistory(chatId, 'assistant', result || 'Done.');
            const chunks = (result || 'Done.').match(/[\s\S]{1,4000}/g) || ['Done.'];
            for (const c of chunks) await this._bot.sendMessage(chatId, c);
            return;
        }

        if (text === '/clear') {
            this._chatHistory[String(chatId)] = [];
            this._saveHistory();
            return this._bot.sendMessage(chatId, 'Conversation history cleared.');
        }

        if (text === '/costs') {
            exec(`${PYTHON} scripts/cost_tracker.py summary --period today`,
                { cwd: REPO_ROOT, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
                    this._bot.sendMessage(chatId, out || err?.message || 'No cost data.').catch(() => {});
                });
            return;
        }

        if (text === '/memhealth') {
            exec(`${PYTHON} scripts/core/memory_aging.py health`,
                { cwd: REPO_ROOT, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
                    this._bot.sendMessage(chatId, out || err?.message || 'Health check failed.').catch(() => {});
                });
            return;
        }

        if (text === '/compact') {
            exec(`${PYTHON} scripts/core/context_manager.py status`,
                { cwd: REPO_ROOT, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
                    this._bot.sendMessage(chatId, out || err?.message || 'Status check failed.').catch(() => {});
                });
            return;
        }

        if (text === '/stale') {
            exec(`${PYTHON} scripts/core/memory_aging.py stale --days 30`,
                { cwd: REPO_ROOT, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
                    this._bot.sendMessage(chatId, (out || err?.message || 'No stale facts.').substring(0, 4000)).catch(() => {});
                });
            return;
        }

        // !sys disabled
        if (text.startsWith('!sys ')) {
            const sysCmd = text.slice(5).trim();
            log(`[SECURITY] Rejected !sys: ${sysCmd.substring(0, 200)}`);
            await this._bot.sendMessage(chatId, '!sys is disabled. Ask in natural language.');
            return;
        }

        // Model selection + tool routing
        const isGemini = text.startsWith('!gemini');
        let modelOverride = null;
        let workingText = text;
        const modelMatch = workingText.match(/^!(opus|sonnet|haiku)\s+/i);
        if (modelMatch) {
            modelOverride = modelMatch[1].toLowerCase();
            workingText = workingText.replace(/^!(opus|sonnet|haiku)\s+/i, '');
        }
        const prompt = workingText.replace(/^!(claude|gemini|bravo)\s+/, '');
        const tool = isGemini ? 'gemini' : 'claude';

        this._addToHistory(chatId, 'user', prompt);
        await this._bot.sendChatAction(chatId, 'typing');
        const thinkingMsg = isGemini ? 'Gemini thinking...' : (modelOverride ? `Claude (${modelOverride}) thinking...` : 'Claude thinking...');
        await this._bot.sendMessage(chatId, thinkingMsg);

        try {
            const result = await this._executeCli(tool, prompt, chatId, modelOverride);

            // Approval gate
            const confirmMatch = (result || '').match(this._CONFIRM_PATTERN);
            if (confirmMatch) {
                const description = confirmMatch[1].trim();
                this._pendingConfirmations[String(chatId)] = { description, timestamp: Date.now() };
                log(`[APPROVAL] Requested: ${description}`);
                const idx = result.indexOf(confirmMatch[0]);
                const beforeConfirm = result.substring(0, idx).trim();
                if (beforeConfirm) {
                    this._addToHistory(chatId, 'assistant', beforeConfirm);
                    const preChunks = beforeConfirm.match(/[\s\S]{1,4000}/g) || [];
                    for (const c of preChunks) await this._bot.sendMessage(chatId, c);
                }
                await this._bot.sendMessage(chatId,
                    `Bravo wants to perform a destructive action:\n\n${description}\n\nApprove?`,
                    {
                        reply_markup: {
                            inline_keyboard: [[
                                { text: 'Yes, proceed', callback_data: 'approve_yes' },
                                { text: 'No, cancel', callback_data: 'approve_no' },
                            ]],
                        },
                    });
                return;
            }

            this._addToHistory(chatId, 'assistant', result || 'No response.');
            const chunks = (result || 'No response.').match(/[\s\S]{1,4000}/g) || ['No response.'];
            for (const c of chunks) await this._bot.sendMessage(chatId, c);
            log(`[SENT] Delivered ${chunks.length} chunk(s) to chat ${chatId}`);

            const filesSent = await this._sendFilesToChat(chatId, result || '');
            if (filesSent > 0) log(`[FILE] Relayed ${filesSent} file(s)`);

            // Update dispatcher context with assistant reply
            if (this._dispatcher) {
                const { agent } = this._dispatcher.route(prompt, 'telegram', userId);
                this._dispatcher.addToContext(agent, userId, 'assistant', result || '');
                this._dispatcher.notifyReplyDispatched('telegram', userId, agent, result || '');
            }
        } catch (err) {
            log(`[CRASH] ${err.message}\n${err.stack}`);
            this._bot.sendMessage(chatId, `Error: ${err.message}`).catch(() => {});
        }
    }

    // ---- PRIVATE: CALLBACK QUERY HANDLER (preserved) ----

    async _handleCallbackQuery(query) {
        const chatId = query.message.chat.id;
        const callbackUserId = String(query.from.id);
        const data = query.data;

        if (!this._allowedUsers.includes(callbackUserId)) {
            log(`[BLOCKED] Unauthorized callback from ${callbackUserId}`);
            await this._bot.answerCallbackQuery(query.id, { text: 'Unauthorized' }).catch(() => {});
            return;
        }

        // Cold-outreach Approve/Skip callbacks removed 2026-05-16 (see
        // telegram_agent.js for the matching change). Stale buttons fall
        // through to "No pending confirmation found." — safe no-op.

        const pending = this._pendingConfirmations[String(chatId)];
        await this._bot.answerCallbackQuery(query.id).catch(() => {});
        if (!pending) {
            await this._bot.sendMessage(chatId, 'No pending confirmation found.');
            return;
        }
        delete this._pendingConfirmations[String(chatId)];

        if (data === 'approve_yes') {
            await this._bot.sendMessage(chatId, 'Approved. Executing...');
            log(`[APPROVAL] Approved: ${pending.description}`);
            this._addToHistory(chatId, 'user', `APPROVED: Proceed with: ${pending.description}`);
            await this._bot.sendChatAction(chatId, 'typing');
            const followUp = `The user has APPROVED the following action: "${pending.description}". Proceed now.`;
            const result = await this._executeCli('claude', followUp, chatId);
            this._addToHistory(chatId, 'assistant', result || 'Done.');
            const chunks = (result || 'Done.').match(/[\s\S]{1,4000}/g) || ['Done.'];
            for (const c of chunks) await this._bot.sendMessage(chatId, c);
        } else {
            await this._bot.sendMessage(chatId, 'Cancelled. Action was NOT performed.');
            log(`[APPROVAL] Denied: ${pending.description}`);
            this._addToHistory(chatId, 'assistant', `Action cancelled: ${pending.description}`);
        }
    }

    // ---- PRIVATE: USER REGISTRATION (preserved) ----

    _autoRegisterUser(userId) {
        try {
            const envFile = path.join(REPO_ROOT, '.env.agents');
            let envContent = fs.readFileSync(envFile, 'utf8');
            if (envContent.includes('TELEGRAM_ALLOWED_USERS=')) {
                envContent = envContent.replace(/TELEGRAM_ALLOWED_USERS=.*/, `TELEGRAM_ALLOWED_USERS=${userId}`);
            } else {
                envContent += `\nTELEGRAM_ALLOWED_USERS=${userId}\n`;
            }
            fs.writeFileSync(envFile, envContent);
            this._allowedUsers = [String(userId)];
            log(`[SECURITY] Auto-registered owner: ${userId}`);
        } catch (e) {
            log(`[SECURITY] Failed to save user ID: ${e.message}`);
        }
    }

    // ---- PRIVATE: STARTUP HEALTH CHECK ----
    // V15.10 (2026-05-06): TELEGRAM SENDS REMOVED. PM2 crash-loops were
    // spamming the operator with the same "OAuth not found" message every
    // minute. Auth-state diagnostics stay in the log; nothing goes to
    // Telegram from this code path.

    _startupHealthCheck() {
        setTimeout(() => {
            // Subscription-only auth (2026-07-18): the metered-key fallback
            // was removed, so OAuth presence is the only signal that matters.
            const auth = checkClaudeAuthPaths();
            if (!auth.hasOAuth) {
                log('[HEALTH] Claude OAuth not found — run `claude setup-token`. Claude calls WILL fail until then (no metered fallback). (Telegram notification suppressed.)');
            } else {
                log(`[HEALTH] Claude OAuth present at ${auth.oauthPath} (sole auth path)`);
            }
        }, 5000);
    }
}

module.exports = { TelegramAdapter };
