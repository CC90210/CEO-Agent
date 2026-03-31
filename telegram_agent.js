require('dotenv').config({ path: '.env.agents' });
const TelegramBot = require('node-telegram-bot-api');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// ============================================================
// BRAVO TELEGRAM BRIDGE V13.0
//
// V11.0: Full-Context Parity — loads CLAUDE.md, brain files, skills refs.
// V12.0: Conversation Memory — stores last 15 messages per chat,
//         injects chat history into every Claude/Gemini spawn so
//         CC can reference previous messages naturally.
// V13.0: Context Optimization — tiered context loading (T1/T2/T3),
//         cost tracking integration, maintenance tool access.
//         Inspired by Claude Code's internal harness patterns.
// ============================================================

const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const LOG_FILE = path.join(__dirname, 'memory', 'telegram_bridge.log');

if (!TELEGRAM_TOKEN) {
    console.error('TELEGRAM_BOT_TOKEN missing in .env.agents');
    process.exit(1);
}

const bot = new TelegramBot(TELEGRAM_TOKEN, {
    polling: {
        autoStart: true,
        params: { timeout: 30 }
    },
    request: { timeout: 60000 }
});

const log = (msg) => {
    const line = `[${new Date().toISOString()}] ${msg}\n`;
    console.log(line.trim());
    try { fs.appendFileSync(LOG_FILE, line); } catch (_) {}
};

log('Bravo Telegram Bridge V13.0 (Context Optimization) starting...');

// ---- CONVERSATION HISTORY ----
// Stores last N message pairs (user + assistant) per chat.
// Persisted to disk so PM2 restarts don't lose context.
const MAX_HISTORY = 15; // messages (not pairs) — covers ~7-8 exchanges
const HISTORY_FILE = path.join(__dirname, 'tmp', 'telegram_history.json');

// { chatId: [ { role: 'user'|'assistant', text: '...', ts: ISO } ] }
let chatHistory = {};

// Load persisted history on startup
try {
    if (fs.existsSync(HISTORY_FILE)) {
        chatHistory = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf8'));
        const chatCount = Object.keys(chatHistory).length;
        if (chatCount > 0) log(`[HISTORY] Loaded ${chatCount} chat(s) from disk`);
    }
} catch (_) { chatHistory = {}; }

const saveHistory = () => {
    try { fs.writeFileSync(HISTORY_FILE, JSON.stringify(chatHistory)); } catch (_) {}
};

const addToHistory = (chatId, role, text) => {
    const id = String(chatId);
    if (!chatHistory[id]) chatHistory[id] = [];
    chatHistory[id].push({ role, text: text.substring(0, 2000), ts: new Date().toISOString() });
    // Trim to MAX_HISTORY messages
    if (chatHistory[id].length > MAX_HISTORY) {
        chatHistory[id] = chatHistory[id].slice(-MAX_HISTORY);
    }
    saveHistory();
};

const getHistoryBlock = (chatId) => {
    const id = String(chatId);
    const msgs = chatHistory[id];
    if (!msgs || msgs.length === 0) return '';
    return '\n=== RECENT CONVERSATION HISTORY ===\n' +
        msgs.map(m => `[${m.role.toUpperCase()}]: ${m.text}`).join('\n') +
        '\n=== END HISTORY ===\n';
};

// ---- PATHS ----
// Resolve actual script paths so we spawn node directly (no .cmd wrappers)
const NODE_EXE = process.execPath; // The node.exe running this script
const GEMINI_SCRIPT = path.join(
    process.env.APPDATA || '',
    'npm', 'node_modules', '@google', 'gemini-cli', 'dist', 'index.js'
);
const CLAUDE_EXE = path.join(
    process.env.USERPROFILE || '', '.local', 'bin', 'claude.exe'
);

// Verify paths exist at startup
if (!fs.existsSync(GEMINI_SCRIPT)) {
    log(`[WARN] Gemini script not found: ${GEMINI_SCRIPT}`);
}
if (!fs.existsSync(CLAUDE_EXE)) {
    log(`[WARN] Claude exe not found: ${CLAUDE_EXE}`);
}

// ---- CONFIG ----
const GEMINI_TIMEOUT = 300000; // 5 min — MCP tools need time to load
const CLAUDE_TIMEOUT = 600000; // 10 min — Claude handles complex tasks

// SECURITY: Only CC's Telegram user ID can interact with this bot.
// Auto-registers first user if TELEGRAM_ALLOWED_USERS is empty in .env.agents.
// After first message, the ID is saved and all other users are blocked.
const ENV_FILE = path.join(__dirname, '.env.agents');
let ALLOWED_USERS = (process.env.TELEGRAM_ALLOWED_USERS || '')
    .split(',')
    .map(id => id.trim())
    .filter(Boolean);

const autoRegisterUser = (userId) => {
    try {
        let envContent = fs.readFileSync(ENV_FILE, 'utf8');
        if (envContent.includes('TELEGRAM_ALLOWED_USERS=')) {
            envContent = envContent.replace(/TELEGRAM_ALLOWED_USERS=.*/, `TELEGRAM_ALLOWED_USERS=${userId}`);
        } else {
            envContent += `\nTELEGRAM_ALLOWED_USERS=${userId}\n`;
        }
        fs.writeFileSync(ENV_FILE, envContent);
        ALLOWED_USERS = [String(userId)];
        log(`[SECURITY] Auto-registered owner: ${userId}. All other users now blocked.`);
    } catch (e) {
        log(`[SECURITY] Failed to save user ID: ${e.message}`);
    }
};

// Static prompt for Gemini (Gemini reads brain files via MCP anyway)
const buildGeminiPrompt = (chatId) => {
    const history = getHistoryBlock(chatId);
    return `You are BRAVO, CC's AI assistant on Telegram. RULES: (1) Answer the question directly in 1-5 sentences. (2) Do NOT summarize recent work, session history, or system status unless explicitly asked. (3) Do NOT greet CC with a status update. (4) Do NOT say what you just fixed or built. (5) Just answer what was asked. (6) Use the CONVERSATION HISTORY below for context from prior messages.
${history}
CC's message:`;
};

// Reads a file safely, returns content or empty string
const readFileSafe = (relPath, maxLines = 0) => {
    try {
        const content = fs.readFileSync(path.join(__dirname, relPath), 'utf8');
        if (maxLines > 0) {
            return content.split('\n').slice(0, maxLines).join('\n').trim();
        }
        return content.trim();
    } catch (_) { return ''; }
};

// ---- CONTEXT TIER CLASSIFICATION (from Claude Code harness patterns) ----
// Claude Code uses "simple mode" (184 tools → 3) for lightweight queries.
// We mirror this: classify query → load only needed context.
const T1_KEYWORDS = ['status', 'check', 'what', 'how much', 'mrr', 'balance', 'count', 'list', 'show', 'hello', 'hey', 'hi', 'thanks'];
const T3_KEYWORDS = ['redesign', 'architecture', 'refactor', 'migrate', 'schema', 'system', 'overhaul', 'sparc', 'complex', 'multi-file'];
// T2 is the default for everything else (build, fix, implement, debug, etc.)

const classifyTier = (text) => {
    const t = text.toLowerCase();
    // T3 keywords win first (most specific)
    if (T3_KEYWORDS.some(k => t.includes(k))) return 3;
    // T1 only if ALL words match simple patterns (no action verbs)
    const words = t.split(/\s+/);
    const hasActionVerb = /\b(build|fix|implement|create|update|add|modify|debug|test|deploy|write|change|edit|push|ship|review)\b/.test(t);
    if (!hasActionVerb && T1_KEYWORDS.some(k => t.includes(k))) return 1;
    return 2;
};

// Loads project context for Claude — tier-aware loading
// T1 (~2000 chars): STATE + ACTIVE_TASKS only — for status checks
// T2 (~5000 chars): T1 + CLAUDE.md + SOUL + USER + SESSION_LOG + tools
// T3 (~8000 chars): T2 + APP_REGISTRY + AGENTS + full CLAUDE.md
const loadContext = (tier = 2) => {
    const chunks = [];

    // --- TIER 1: Always loaded (minimal context) ---
    const state = readFileSafe('brain/STATE.md');
    if (state) chunks.push(`=== STATE.md (current state) ===\n${state}`);

    const tasks = readFileSafe('memory/ACTIVE_TASKS.md', 50);
    if (tasks) chunks.push(`=== ACTIVE_TASKS.md ===\n${tasks}`);

    if (tier === 1) {
        chunks.push(`=== Context Tier: T1 MINIMAL (status query) ===`);
        return chunks.join('\n\n');
    }

    // --- TIER 2: Standard context (feature work, operations) ---
    const claude_md = readFileSafe('CLAUDE.md', tier === 3 ? 200 : 120);
    if (claude_md) chunks.push(`=== CLAUDE.md (project instructions) ===\n${claude_md}`);

    const soul = readFileSafe('brain/SOUL.md', 40);
    if (soul) chunks.push(`=== SOUL.md (identity) ===\n${soul}`);

    const user = readFileSafe('brain/USER.md', 50);
    if (user) chunks.push(`=== USER.md (CC's profile) ===\n${user}`);

    const sessionLog = readFileSafe('memory/SESSION_LOG.md');
    if (sessionLog) {
        const lastN = sessionLog.split('\n').slice(tier === 3 ? -50 : -30).join('\n').trim();
        if (lastN) chunks.push(`=== SESSION_LOG.md (recent) ===\n${lastN}`);
    }

    // Tool routing summary — includes new maintenance tools
    chunks.push(`=== Available CLI Tools ===
- n8n: python scripts/n8n_tool.py [list|get|execute|activate]
- Late (social): python scripts/late_tool.py [accounts|posts|create]
- Supabase: python scripts/supabase_tool.py [select|insert|sql]
- Stripe: python scripts/stripe_tool.py [balance|customers|invoices]
- Email/Calendar: python scripts/google_tool.py [gmail send|gmail list|calendar list|calendar create]
- Context Manager: python scripts/context_manager.py [tier|compact|status|health]
- Cost Tracker: python scripts/cost_tracker.py [log|summary|session|budget]
- Memory Aging: python scripts/memory_aging.py [scan|stale|health|archive]
- MCP servers: Playwright, Context7, Memory, Sequential Thinking`);

    if (tier === 2) {
        chunks.push(`=== Context Tier: T2 STANDARD ===`);
        const full = chunks.join('\n\n');
        return full.length > 6000 ? full.substring(0, 6000) + '\n...(truncated)' : full;
    }

    // --- TIER 3: Full context (architecture, complex multi-file) ---
    const appReg = readFileSafe('brain/APP_REGISTRY.md', 50);
    if (appReg) chunks.push(`=== APP_REGISTRY.md ===\n${appReg}`);

    const agents = readFileSafe('brain/AGENTS.md', 80);
    if (agents) chunks.push(`=== AGENTS.md (sub-agent registry) ===\n${agents}`);

    const patterns = readFileSafe('memory/PATTERNS.md', 30);
    if (patterns) chunks.push(`=== PATTERNS.md ===\n${patterns}`);

    const mistakes = readFileSafe('memory/MISTAKES.md', 30);
    if (mistakes) chunks.push(`=== MISTAKES.md ===\n${mistakes}`);

    chunks.push(`=== Context Tier: T3 FULL ===`);
    const full = chunks.join('\n\n');
    return full.length > 10000 ? full.substring(0, 10000) + '\n...(truncated)' : full;
};

// Dynamic prompt for Claude — tier-aware context loading + conversation history
const buildPrompt = (chatId, userText = '') => {
    const tier = classifyTier(userText);
    const context = loadContext(tier);
    const history = getHistoryBlock(chatId);
    log(`[TIER] Query classified as T${tier} — loading ${tier === 1 ? 'minimal' : tier === 2 ? 'standard' : 'full'} context`);
    return `You are BRAVO V5.5, CC's Lead Architect and AI business manager, running via Telegram bridge.
You have full access to the Business-Empire-Agent project at C:\\Users\\User\\Business-Empire-Agent.

${context}
${history}
TELEGRAM-SPECIFIC RULES:
(1) Answer directly in 1-5 sentences unless the task requires more.
(2) Do NOT dump file contents unless asked.
(3) Use the CLI tools listed above for database, social media, Stripe, and n8n operations.
(4) For code changes in apps, cd to the app's LOCAL PATH from APP_REGISTRY.md.
(5) After any significant work, update memory/SESSION_LOG.md and memory/ACTIVE_TASKS.md.
(6) Address the user as CC. Be direct, no filler. Use "Conaugh McKenna" for external/B2B comms.
(7) You have up to 25 turns — use them for multi-step tasks. Don't rush.
(8) All credentials are in .env.agents — NEVER hardcode secrets.
(9) IMPORTANT: The RECENT CONVERSATION HISTORY above contains previous messages from this chat session. Use it to maintain context. If CC references something from a prior message, check the history.

CC's message:`;
};

// Detect which MCP servers a query needs (keeps Gemini startup fast)
const detectMcps = (text) => {
    const t = text.toLowerCase();
    const mcps = [];
    if (/post|tweet|schedule|social|linkedin|instagram|threads|tiktok|bluesky|content/i.test(t)) mcps.push('late');
    if (/database|supabase|table|sql|query|schema/i.test(t)) mcps.push('supabase');
    if (/workflow|n8n|automat/i.test(t)) mcps.push('n8n-mcp');
    if (/stripe|payment|invoice|subscription|balance/i.test(t)) mcps.push('stripe');
    if (/browse|website|screenshot|url|http/i.test(t)) mcps.push('playwright');
    if (/docs|library|documentation|api reference/i.test(t)) mcps.push('context7');
    // Always include lightweight ones
    mcps.push('memory', 'sequential-thinking');
    return mcps;
};

// ---- PROCESS TRACKING ----
const activeChildren = new Set();

const killTree = (pid) => {
    try {
        // Windows: taskkill /T kills entire process tree
        spawn('taskkill', ['/pid', String(pid), '/T', '/F'], {
            windowsHide: true,
            stdio: 'ignore',
            shell: false
        });
    } catch (_) {}
};

// ---- CLI EXECUTION ----
const executeCli = (tool, userPrompt, chatId) => {
    return new Promise((resolve) => {
        const fullPrompt = tool === 'claude' ? `${buildPrompt(chatId, userPrompt)} ${userPrompt}` : `${buildGeminiPrompt(chatId)} ${userPrompt}`;
        const timeout = tool === 'claude' ? CLAUDE_TIMEOUT : GEMINI_TIMEOUT;
        let cmd, args;

        if (tool === 'claude') {
            cmd = CLAUDE_EXE;
            args = [
                '-p', fullPrompt,
                '--dangerously-skip-permissions',
                '--output-format', 'text',
                '--max-turns', '25'
            ];
        } else {
            const mcps = detectMcps(userPrompt);
            const mcpArgs = mcps.flatMap(m => ['--allowed-mcp-server-names', m]);
            cmd = NODE_EXE;
            args = [
                '--no-warnings=DEP0040',
                GEMINI_SCRIPT,
                '-p', fullPrompt,
                '--approval-mode', 'yolo',
                '--output-format', 'text',
                ...mcpArgs
            ];
            log(`[MCP] Loading: ${mcps.join(', ')}`);
        }

        log(`[EXEC] ${tool}: "${userPrompt.substring(0, 80)}..."`);

        const child = spawn(cmd, args, {
            env: {
                ...process.env,
                CI: 'true',
                NONINTERACTIVE: 'true',
                PAGER: 'cat',
                NO_COLOR: '1',
                FORCE_COLOR: '0'
            },
            stdio: ['ignore', 'pipe', 'pipe'],
            shell: false,
            windowsHide: true,
            cwd: __dirname
        });

        activeChildren.add(child);

        let stdout = '';
        let stderr = '';
        let hasOutput = false;
        child.stdout.on('data', (d) => { stdout += d.toString(); hasOutput = true; });
        child.stderr.on('data', (d) => { stderr += d.toString(); });

        const startTime = Date.now();

        // Progress update — only after 2+ minutes, every 2 minutes (reduced noise)
        const progressTimer = setInterval(() => {
            if (chatId) {
                const elapsed = Math.round((Date.now() - startTime) / 1000);
                bot.sendChatAction(chatId, 'typing').catch(() => {});
                if (elapsed >= 120 && elapsed % 120 === 0) {
                    bot.sendMessage(chatId, `Still working... (${elapsed}s)`).catch(() => {});
                }
            }
        }, 15000);

        const timer = setTimeout(() => {
            log(`[TIMEOUT] ${tool} killed after ${timeout / 1000}s`);
            if (child.pid) killTree(child.pid);
            const partial = cleanOutput(stdout.trim());
            if (partial && partial.length > 20) {
                resolve(`(Partial — timed out after ${timeout / 1000}s)\n\n${partial}`);
            } else {
                resolve(`Timed out after ${timeout / 1000}s. The task may be too complex for Telegram. Try ${tool === 'claude' ? '!gemini' : '!claude'} or run it directly.`);
            }
        }, timeout);

        child.on('close', (code) => {
            clearTimeout(timer);
            clearInterval(progressTimer);
            activeChildren.delete(child);
            const elapsed = Math.round((Date.now() - startTime) / 1000);
            log(`[DONE] ${tool} code=${code} stdout=${stdout.length}b stderr=${stderr.length}b time=${elapsed}s`);

            // Cost tracking — log the CLI execution
            const units = tool === 'claude' ? Math.ceil(elapsed / 60) * 3 : Math.ceil(elapsed / 60) * 2;
            exec(`python scripts/cost_tracker.py log --label "telegram_${tool}" --units ${units} --detail "${userPrompt.substring(0, 80).replace(/"/g, "'")}"`, {
                cwd: __dirname, windowsHide: true, timeout: 5000
            }, () => {}); // fire-and-forget

            const raw = (stdout.trim() || stderr.trim());
            if (!raw) {
                resolve(code === 0 ? 'Done.' : `Error (code ${code}). Try !claude for complex tasks.`);
                return;
            }
            resolve(cleanOutput(raw));
        });

        child.on('error', (err) => {
            clearTimeout(timer);
            clearInterval(progressTimer);
            activeChildren.delete(child);
            log(`[ERROR] ${tool}: ${err.message}`);
            resolve(`Error: ${err.message}`);
        });
    });
};

// Strip ANSI codes and CLI noise
const cleanOutput = (raw) => {
    let text = raw
        .replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '')
        .replace(/[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]/g, '');

    const noise = [
        /^[█▓░▀▄▐▌]+/,
        /logged in with/i,
        /waiting for mcp/i,
        /^Gemini CLI/i,
        /^Using model/i,
        /^Loading/i,
        /YOLO mode is enabled/i,
        /Loaded cached credentials/i,
        /supports tool updates/i,
        /^Bravo online\.?\s*$/i,
        /^Memory synced\.?\s*$/i,
        /Listening for changes/i,
        /^Server '/i,
        /^\s*$/
    ];

    return text.split('\n')
        .filter(line => !noise.some(p => p.test(line.trim())))
        .join('\n')
        .trim() || text.trim();
};

// ---- TELEGRAM HANDLER ----
bot.on('message', async (msg) => {
    pollErrorCount = 0;
    const chatId = msg.chat.id;
    const text = msg.text;
    if (!text) return;

    const userId = String(msg.from.id);
    const user = msg.from.username || msg.from.first_name || '?';

    // SECURITY FIREWALL: Auto-register first user, block all others
    if (ALLOWED_USERS.length === 0) {
        autoRegisterUser(userId);
        log(`[SECURITY] First user registered as owner: ${user} (${userId})`);
    } else if (!ALLOWED_USERS.includes(userId)) {
        log(`[BLOCKED] Unauthorized user: ${user} (ID: ${userId})`);
        return bot.sendMessage(chatId, 'Unauthorized.').catch(() => {});
    }

    log(`[MSG] ${user} (${userId}): ${text}`);

    if (text === '/start' || text === '/help') {
        return bot.sendMessage(chatId, [
            'Bravo Bridge V13.0 (Context Optimization)',
            '',
            'Just type anything → Claude Code (default, 25 turns)',
            '!gemini <query> → Gemini CLI (fallback)',
            '!sys <cmd> → shell command on PC',
            '',
            'Context: Auto-classifies T1/T2/T3 per query.',
            'Claude: 10 min timeout + last 15 messages.',
            'Gemini: 5 min timeout, MCP-aware.',
            '',
            '/costs — today\'s operation cost summary',
            '/memhealth — memory system health grade',
            '/compact — SESSION_LOG compaction status',
            '/stale — facts older than 30 days',
            '/clear — clear conversation history',
            '/whoami — show your Telegram user ID'
        ].join('\n'));
    }

    if (text === '/whoami') {
        return bot.sendMessage(chatId, `User ID: ${userId}\nUsername: ${user}\nChat ID: ${chatId}`);
    }

    if (text === '/clear') {
        chatHistory[String(chatId)] = [];
        saveHistory();
        return bot.sendMessage(chatId, 'Conversation history cleared.');
    }

    // V13.0: System maintenance commands — direct access to optimization tools
    if (text === '/costs') {
        exec('python scripts/cost_tracker.py summary --period today', { cwd: __dirname, windowsHide: true, timeout: 10000 }, (err, out) => {
            bot.sendMessage(chatId, out || err?.message || 'No cost data.').catch(() => {});
        });
        return;
    }

    if (text === '/memhealth') {
        exec('python scripts/memory_aging.py health', { cwd: __dirname, windowsHide: true, timeout: 10000 }, (err, out) => {
            bot.sendMessage(chatId, out || err?.message || 'Health check failed.').catch(() => {});
        });
        return;
    }

    if (text === '/compact') {
        exec('python scripts/context_manager.py status', { cwd: __dirname, windowsHide: true, timeout: 10000 }, (err, out) => {
            bot.sendMessage(chatId, out || err?.message || 'Status check failed.').catch(() => {});
        });
        return;
    }

    if (text === '/stale') {
        exec('python scripts/memory_aging.py stale --days 30', { cwd: __dirname, windowsHide: true, timeout: 10000 }, (err, out) => {
            const result = out || err?.message || 'No stale facts found.';
            bot.sendMessage(chatId, result.substring(0, 4000)).catch(() => {});
        });
        return;
    }

    try {
        // Shell passthrough
        if (text.startsWith('!sys ')) {
            await bot.sendMessage(chatId, 'Running...');
            exec(text.slice(5), { windowsHide: true, timeout: 30000 }, (err, out, serr) => {
                const r = out || serr || (err ? err.message : 'Done.');
                bot.sendMessage(chatId, r.substring(0, 4000));
            });
            return;
        }

        // V9.0: Default to Claude (CC has Max plan), !gemini for fallback
        const isGemini = text.startsWith('!gemini');
        const prompt = text.replace(/^!(claude|gemini|bravo)\s+/, '');
        const tool = isGemini ? 'gemini' : 'claude';

        // Store user message in history
        addToHistory(chatId, 'user', prompt);

        await bot.sendChatAction(chatId, 'typing');
        await bot.sendMessage(chatId, isGemini ? 'Gemini thinking...' : 'Claude thinking...');

        const result = await executeCli(tool, prompt, chatId);

        // Store assistant response in history (first 2000 chars)
        addToHistory(chatId, 'assistant', result || 'No response.');

        // Telegram limit is 4096 chars
        const chunks = (result || 'No response.').match(/[\s\S]{1,4000}/g) || ['No response.'];
        for (const c of chunks) {
            await bot.sendMessage(chatId, c);
        }
    } catch (err) {
        log(`[CRASH] ${err.message}`);
        bot.sendMessage(chatId, `Error: ${err.message}`).catch(() => {});
    }
});

// ---- SHUTDOWN ----
// Graceful shutdown: stop polling FIRST, wait for Telegram to release
// the connection, THEN exit. This prevents 409 Conflict (duplicate
// getUpdates) when PM2 restarts the bot.
let shuttingDown = false;
const shutdown = async (sig) => {
    if (shuttingDown) return; // prevent double-shutdown
    shuttingDown = true;
    log(`[SHUTDOWN] ${sig} — stopping polling...`);
    for (const c of activeChildren) killTree(c.pid);
    try {
        await bot.stopPolling();
    } catch (_) {}
    // Give Telegram 2s to release the long-poll connection
    setTimeout(() => process.exit(0), 2000);
};
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

// ---- CRASH RECOVERY ----
// Suppress polling errors (network drops, sleep/wake cycles)
// node-telegram-bot-api auto-retries polling — just log, don't crash
let pollErrorCount = 0;
bot.on('polling_error', (e) => {
    pollErrorCount++;
    // Log first error, then only every 50th to avoid filling logs
    if (pollErrorCount === 1 || pollErrorCount % 50 === 0) {
        log(`[POLL] EFATAL: ${e.message} (count: ${pollErrorCount})`);
    }
});

// Catch unhandled rejections to prevent crash
process.on('unhandledRejection', (err) => {
    log(`[UNHANDLED] ${err.message || err}`);
});

log('Bridge V13.0 ready.');
