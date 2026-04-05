require('dotenv').config({ path: '.env.agents' });
const TelegramBot = require('node-telegram-bot-api');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// ============================================================
// BRAVO TELEGRAM BRIDGE V15.3
//
// V11.0: Full-Context Parity — loads CLAUDE.md, brain files, skills refs.
// V12.0: Conversation Memory — stores last 15 messages per chat,
//         injects chat history into every Claude/Gemini spawn so
//         CC can reference previous messages naturally.
// V13.0: Context Optimization — tiered context loading (T1/T2/T3),
//         cost tracking integration, maintenance tool access.
// V14.0: Cross-Platform + Computer Control — macOS/Windows runtime detection,
//         natural language desktop control via macos_control.py,
//         approval gate for destructive actions (inline Telegram buttons).
// V15.2: Full Computer Control — 60+ commands: apps, windows, browser, files, processes,
//         input (scroll/right-click/double-click), network, audio, power, permissions,
//         SoundCloud music, screenshots/recordings auto-relayed to Telegram chat.
// V15.3: Security Hardening — AppleScript injection sanitization, !sys blocklist,
//         callback user ID verification, execFile for cost tracking, sensitive path
//         blocking, protected process list, rate limiting (5/10s).
// ============================================================

// ---- PLATFORM DETECTION ----
const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';
const PYTHON = IS_MAC ? 'python3' : path.join(__dirname, '.venv', 'Scripts', 'python.exe');
const MACHINE_NAME = IS_MAC ? 'MacBook' : 'Windows Desktop';
const TEMP_PATH = IS_MAC ? '/tmp' : (process.env.TEMP || 'C:\\Temp');

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

log(`Bravo Telegram Bridge V15.3 (${IS_MAC ? 'macOS' : 'Windows'} — Full Autonomy) starting...`);

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

// ---- RATE LIMITING ----
const RATE_LIMIT_WINDOW = 10000; // 10 seconds
const RATE_LIMIT_MAX = 5;        // max 5 messages per window
const rateLimitMap = {};          // userId -> [timestamps]

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

// ---- PATHS (cross-platform) ----
const NODE_EXE = process.execPath;

const CLAUDE_EXE = IS_MAC
    ? 'claude'  // in PATH via nvm global install
    : path.join(process.env.USERPROFILE || '', '.local', 'bin', 'claude.exe');

const GEMINI_SCRIPT = IS_MAC
    ? (() => {
        const nvmDir = path.join(process.env.HOME || '', '.nvm', 'versions', 'node');
        const candidate = path.join(nvmDir, process.version, 'lib', 'node_modules',
            '@google', 'gemini-cli', 'dist', 'index.js');
        return candidate;
      })()
    : path.join(process.env.APPDATA || '',
        'npm', 'node_modules', '@google', 'gemini-cli', 'dist', 'index.js');

// Verify paths at startup
if (!fs.existsSync(GEMINI_SCRIPT)) {
    log(`[WARN] Gemini script not found: ${GEMINI_SCRIPT}`);
}
if (!IS_MAC && !fs.existsSync(CLAUDE_EXE)) {
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
    const hasActionVerb = /\b(build|fix|implement|create|update|add|modify|debug|test|deploy|write|change|edit|push|ship|review|open|launch|click|screenshot|volume|mute|play|switch|type|control|close|quit|move|resize|fullscreen|minimize|snap|record|recording|dark|wifi|bluetooth|brightness|clipboard|copy|paste|lock|sleep|battery|sysinfo|soundcloud|music|song|track|browse|search|navigate|tab|website|url|google|download|upload|scroll|right.click|double.click|mouse|file|process|kill|delete|reveal|finder|ping|network|ip|audio|shutdown|restart|logout|power)\b/.test(t);
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
- n8n: ${PYTHON} scripts/n8n_tool.py [list|get|execute|activate]
- Late (social): ${PYTHON} scripts/late_tool.py [accounts|posts|create]
- Supabase: ${PYTHON} scripts/supabase_tool.py [select|insert|sql]
- Stripe: ${PYTHON} scripts/stripe_tool.py [balance|customers|invoices]
- Email/Calendar: ${PYTHON} scripts/google_tool.py [gmail send|gmail list|calendar list|calendar create]
- Context Manager: ${PYTHON} scripts/context_manager.py [tier|compact|status|health]
- Cost Tracker: ${PYTHON} scripts/cost_tracker.py [log|summary|session|budget]
- Memory Aging: ${PYTHON} scripts/memory_aging.py [scan|stale|health|archive]
- MCP servers: Playwright, Context7, Memory, Sequential Thinking`);

    // Computer control (cross-platform — macOS + Windows)
    const REVEAL_CMD = IS_MAC ? 'reveal-in-finder' : 'reveal-in-explorer';
    chunks.push(`=== ${IS_MAC ? 'macOS' : 'Windows'} Computer Control V2.1 (60+ commands — FULL CONTROL) ===
APPS: open --app X | quit --app X | list-apps | frontmost
INPUT: type --text "..." | keystroke --keys "${IS_MAC ? 'cmd' : 'ctrl'}+c" | click --x N --y N | right-click --x N --y N | double-click --x N --y N | scroll --direction up|down [--amount N] | mouse-move --x N --y N
WINDOWS: window-move --app X --x N --y N | window-resize --app X --w N --h N | window-fullscreen --app X | window-left/right/center --app X | window-minimize/restore --app X | list-windows
SCREENSHOTS: screenshot [--path ${TEMP_PATH}/X.png] | screenshot-window [--path ${TEMP_PATH}/X.png]
RECORDING: record-start [--path ${TEMP_PATH}/X.${IS_MAC ? 'mov' : 'mp4'}] | record-stop
SYSTEM: dark-mode [--toggle|--on|--off] | dnd --on|--off | wifi --on|--off | bluetooth --on|--off | brightness --level N | volume --level N | mute [--toggle|--on|--off] | sleep-display | lock-screen | trash-empty | battery | sysinfo
CLIPBOARD: clipboard-read | clipboard-write --text "..."
MEDIA: say --text "..." | url --url "https://..." | notify --title "..." --message "..."
FILES: list-files [--path X] [--recursive] | read-file --path X | write-file --path X --content "..." | move-file --src X --dst Y | copy-file --src X --dst Y | delete-file --path X [--force] | search-files --query X [--dir Y] | ${REVEAL_CMD} --path X
PROCESSES: list-processes [--sort cpu|mem] [--limit N] | kill-process --pid N | kill-process --name X
NETWORK: get-ip | ping --host X [--count N]
AUDIO: list-audio | switch-audio --device X
POWER: shutdown --confirm | restart --confirm | logout --confirm
BROWSER (Chrome via DevTools Protocol): browser-open --url "..." | browser-js --script "..." | browser-tab-url | browser-tab-title | browser-new-tab --url "..." | browser-close-tab | browser-list-tabs | browser-switch-tab --tab N | browser-back | browser-forward | browser-reload | browser-screenshot [--path X] | browser-get-text | browser-click-element --selector "css" | browser-fill --selector "css" --value "text"
CDP SETUP: browser-enable-cdp (restarts Chrome with DevTools — run once) | browser-cdp-status
WINDOWS EXTRAS: installed-apps | startup-apps | disk-usage | open-settings [--page display|sound|network|...] | open-with --file X --app Y | drag --x1 N --y1 N --x2 N --y2 N | task-switcher | focus-window --title "..."
All via: \${PYTHON} scripts/${IS_MAC ? 'macos' : 'windows'}_control.py <command> [args] [--json]

=== SoundCloud Music Control (atomic — use this, NOT manual browser steps) ===
PLAY: \${PYTHON} scripts/music_control.py play --query "artist or song name"
PAUSE/RESUME: \${PYTHON} scripts/music_control.py pause | resume
SKIP/PREV: \${PYTHON} scripts/music_control.py skip | previous
NOW PLAYING: \${PYTHON} scripts/music_control.py current
SEARCH: \${PYTHON} scripts/music_control.py search --query "..."
All support --json flag.

CRITICAL: For music, use music_control.py (1 command = done). For web browsing, use browser-open/browser-js commands. NEVER try to manually orchestrate multi-step browser interactions — you WILL run out of turns. Use the atomic scripts.
IMPORTANT: When taking screenshots or recordings, the file is AUTOMATICALLY sent back to the Telegram chat. Always use ${TEMP_PATH}${IS_MAC ? '/' : '\\\\'} paths.
POWER COMMANDS (shutdown/restart/logout) require --confirm flag. Always ask the user for confirmation FIRST.`);

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
You have full access to the Business-Empire-Agent project at ${__dirname}.
Platform: ${IS_MAC ? 'macOS (darwin)' : 'Windows 11 (win32)'} — Machine: ${MACHINE_NAME}
If CC asks "what machine are you on?" or "where are you running?", answer: "${MACHINE_NAME}" (${IS_MAC ? 'CC\'s MacBook' : 'CC\'s Windows Desktop PC — AMD Ryzen 5 5600GT, 16GB RAM, 1080p'}).

${context}
${history}
TELEGRAM-SPECIFIC RULES:
(1) Answer directly in 1-5 sentences unless the task requires more.
(2) Do NOT dump file contents unless asked.
(3) Use the CLI tools listed above for database, social media, Stripe, and n8n operations. Use ${PYTHON} (not python) for all script calls.
(4) For code changes in apps, cd to the app's LOCAL PATH from APP_REGISTRY.md.
(5) After any significant work, update memory/SESSION_LOG.md and memory/ACTIVE_TASKS.md.
(6) Address the user as CC. Be direct, no filler. Use "Conaugh McKenna" for external/B2B comms.
(7) You have up to 25 turns — use them for multi-step tasks. Don't rush.
(8) All credentials are in .env.agents — NEVER hardcode secrets.
(9) IMPORTANT: The RECENT CONVERSATION HISTORY above contains previous messages from this chat session. Use it to maintain context. If CC references something from a prior message, check the history.
(10) APPROVAL GATE: Before executing ANY destructive action (deleting files, sending emails to clients, publishing content, modifying production data, running rm/del commands, shutting down services), you MUST output exactly this pattern and STOP:
⚠️ CONFIRM: [one-line description of what you are about to do]
Do NOT proceed until the next message says APPROVED or DENIED.
(11) COMPUTER CONTROL: You have FULL control of this ${IS_MAC ? 'Mac' : 'PC'} via ${PYTHON} scripts/${IS_MAC ? 'macos' : 'windows'}_control.py (60+ commands). Categories: Apps (open/quit/list), Input (type/click/right-click/double-click/scroll/mouse-move/keystroke), Windows (move/resize/fullscreen/left/right/center/minimize/restore), Screenshots & Recording, System (dark-mode/dnd/wifi/bluetooth/brightness/volume/mute/sleep/lock/battery/sysinfo), Clipboard (read/write), Files (list/read/write/move/copy/delete/search/${IS_MAC ? 'reveal-in-finder' : 'reveal-in-explorer'}), Processes (list/kill), Network (get-ip/ping), Audio (list/switch devices), Power (shutdown/restart/logout — need --confirm), Browser (Chrome: open URLs, JS, tabs), Media (say/notify/url). Use natural language — figure out the right command from CC's intent.
(12) FILE RELAY: When you take a screenshot or create a file, the bridge AUTOMATICALLY sends it back to this Telegram chat. Always save to ${TEMP_PATH}${IS_MAC ? '/' : '\\\\'} paths. Include the full file path in your response text so the relay can find it.
(13) MUSIC: Use ${PYTHON} scripts/music_control.py for SoundCloud control. NEVER try to manually control the browser step-by-step for music. The script handles search, navigation, and playback in ONE atomic call.
(14) BROWSER: Use browser-open/browser-js/browser-new-tab commands from ${IS_MAC ? 'macos' : 'windows'}_control.py for ANY web task. These are atomic — one command does the job. NEVER burn turns trying to manually orchestrate browser steps. On Windows: run browser-enable-cdp ONCE per session to activate Chrome DevTools Protocol (full JS execution, tab control, page screenshots, element clicking, form filling). Use browser-click-element/browser-fill for interacting with page elements.

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

// ---- APPROVAL GATE ----
// Pattern Claude outputs when it needs confirmation for destructive actions.
// Bridge intercepts, asks CC via Telegram inline keyboard, then re-spawns.
const CONFIRM_PATTERN = /⚠️\s*CONFIRM:\s*(.+)$/m;
const PENDING_CONFIRMATIONS = {}; // chatId -> { description, timestamp }

// Clean stale confirmations every 5 minutes
setInterval(() => {
    const now = Date.now();
    for (const [chatId, pending] of Object.entries(PENDING_CONFIRMATIONS)) {
        if (now - pending.timestamp > 300000) {
            delete PENDING_CONFIRMATIONS[chatId];
            log(`[APPROVAL] Stale confirmation expired for chat ${chatId}`);
        }
    }
}, 300000);

// ---- PROCESS TRACKING ----
const activeChildren = new Set();

const killTree = (pid) => {
    try {
        if (IS_WIN) {
            spawn('taskkill', ['/pid', String(pid), '/T', '/F'], {
                windowsHide: true, stdio: 'ignore', shell: false
            });
        } else {
            process.kill(pid, 'SIGKILL');
        }
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

            // Cost tracking — log the CLI execution (uses execFile to prevent injection)
            const units = tool === 'claude' ? Math.ceil(elapsed / 60) * 3 : Math.ceil(elapsed / 60) * 2;
            const { execFile: execFileTrack } = require('child_process');
            execFileTrack(PYTHON, [
                'scripts/cost_tracker.py', 'log',
                '--label', `telegram_${tool}`,
                '--units', String(units),
                '--detail', userPrompt.substring(0, 80)
            ], { cwd: __dirname, windowsHide: true, timeout: 5000 }, () => {}); // fire-and-forget

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

// ---- FILE RELAY ----
// Scans Claude's response for file paths and sends them back to Telegram as
// photos (images) or documents (videos, PDFs, etc.). This enables "take a
// screenshot" → image appears in chat, "start recording" → video sent, etc.
// File path detection — cross-platform (Unix /tmp/ and Windows C:\...\Temp\)
// Windows paths use single backslash in Claude's output text
const FILE_EXTS = 'png|jpg|jpeg|gif|mov|mp4|pdf|txt|csv|md|html|zip';
const FILE_PATH_PATTERN = new RegExp(`(?:saved to|File:|file:|Screenshot|screenshot|Recording)[:\\s]+((?:[/~]|[A-Z]:[\\\\\/])[^\\s,)"']+\\.(?:${FILE_EXTS}))`, 'gi');
const DIRECT_PATH_PATTERN = new RegExp(`((?:\\/tmp\\/|[A-Z]:[\\\\\/](?:[^\\s,)"']*[\\\\\/])?(?:Temp|tmp|AppData[\\\\\/]Local[\\\\\/]Temp)[\\\\\/])[^\\s,)"']+\\.(?:${FILE_EXTS}))`, 'gi');

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif']);
const VIDEO_EXTS = new Set(['mov', 'mp4']);

const sendFilesToChat = async (chatId, text) => {
    const paths = new Set();
    let match;

    // Match "saved to /path/file.ext" patterns
    const pattern1 = new RegExp(FILE_PATH_PATTERN.source, FILE_PATH_PATTERN.flags);
    while ((match = pattern1.exec(text)) !== null) {
        paths.add(match[1]);
    }

    // Match bare /tmp/ paths
    const pattern2 = new RegExp(DIRECT_PATH_PATTERN.source, DIRECT_PATH_PATTERN.flags);
    while ((match = pattern2.exec(text)) !== null) {
        paths.add(match[1]);
    }

    let sent = 0;
    for (const filePath of paths) {
        try {
            if (!fs.existsSync(filePath)) continue;
            const stat = fs.statSync(filePath);
            if (stat.size === 0 || stat.size > 50 * 1024 * 1024) continue; // skip empty or >50MB

            const ext = path.extname(filePath).slice(1).toLowerCase();

            if (IMAGE_EXTS.has(ext)) {
                await bot.sendPhoto(chatId, filePath, { caption: path.basename(filePath) });
                sent++;
                log(`[FILE] Sent photo: ${filePath} (${(stat.size / 1024).toFixed(0)} KB)`);
            } else if (VIDEO_EXTS.has(ext)) {
                await bot.sendVideo(chatId, filePath, { caption: path.basename(filePath) });
                sent++;
                log(`[FILE] Sent video: ${filePath} (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
            } else {
                await bot.sendDocument(chatId, filePath, { caption: path.basename(filePath) });
                sent++;
                log(`[FILE] Sent document: ${filePath} (${(stat.size / 1024).toFixed(0)} KB)`);
            }
        } catch (e) {
            log(`[FILE] Failed to send ${filePath}: ${e.message}`);
        }
    }
    return sent;
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

    // SECURITY: Rate limiting
    const now = Date.now();
    if (!rateLimitMap[userId]) rateLimitMap[userId] = [];
    rateLimitMap[userId] = rateLimitMap[userId].filter(t => now - t < RATE_LIMIT_WINDOW);
    if (rateLimitMap[userId].length >= RATE_LIMIT_MAX) {
        log(`[RATE] Throttled ${user} (${userId})`);
        return bot.sendMessage(chatId, 'Slow down — max 5 messages per 10 seconds.').catch(() => {});
    }
    rateLimitMap[userId].push(now);

    log(`[MSG] ${user} (${userId}): ${text}`);

    if (text === '/start' || text === '/help') {
        return bot.sendMessage(chatId, [
            `Bravo Bridge V15.3 (${MACHINE_NAME} — Full Computer Control)`,
            '',
            'Just type anything → Claude handles it (25 turns)',
            '',
            'FULL COMPUTER CONTROL (60+ commands):',
            `  Apps: "Open Chrome" / "Quit ${IS_MAC ? 'Safari' : 'Notepad'}" / "What apps are running?"`,
            '  Windows: "Snap Terminal left" / "Fullscreen Chrome"',
            '  Input: "Click at 500,300" / "Scroll down" / "Type hello"',
            '  Browser: "Open google.com" / "List tabs"',
            '  Files: "List files on Desktop" / "Search for invoices"',
            '  Music: "Play Carti on SoundCloud" / "Skip" / "What\'s playing?"',
            '  System: "Dark mode" / "WiFi off" / "Battery?" / "Brightness 80"',
            '  Screenshots: "Take a screenshot" → sent here automatically',
            '  Network: "What\'s my IP?" / "Ping google.com"',
            '  Power: "Restart" / "Shutdown" (asks for confirmation)',
            '',
            '!gemini <query> → Gemini CLI (fallback)',
            `!sys <cmd> → shell command on ${IS_MAC ? 'Mac' : 'PC'}`,
            '',
            'Destructive actions require approval (inline buttons).',
            'Screenshots & files auto-sent back to this chat.',
            '',
            '/costs — today\'s operation cost summary',
            '/memhealth — memory system health grade',
            '/compact — SESSION_LOG compaction status',
            '/stale — facts older than 30 days',
            '/clear — clear conversation history',
            '/whoami — show your Telegram user ID'
        ].filter(Boolean).join('\n'));
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
        exec(`${PYTHON} scripts/cost_tracker.py summary --period today`, { cwd: __dirname, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
            bot.sendMessage(chatId, out || err?.message || 'No cost data.').catch(() => {});
        });
        return;
    }

    if (text === '/memhealth') {
        exec(`${PYTHON} scripts/memory_aging.py health`, { cwd: __dirname, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
            bot.sendMessage(chatId, out || err?.message || 'Health check failed.').catch(() => {});
        });
        return;
    }

    if (text === '/compact') {
        exec(`${PYTHON} scripts/context_manager.py status`, { cwd: __dirname, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
            bot.sendMessage(chatId, out || err?.message || 'Status check failed.').catch(() => {});
        });
        return;
    }

    if (text === '/stale') {
        exec(`${PYTHON} scripts/memory_aging.py stale --days 30`, { cwd: __dirname, windowsHide: IS_WIN, timeout: 10000 }, (err, out) => {
            const result = out || err?.message || 'No stale facts found.';
            bot.sendMessage(chatId, result.substring(0, 4000)).catch(() => {});
        });
        return;
    }

    try {
        // Shell passthrough — with security blocklist
        if (text.startsWith('!sys ')) {
            const sysCmd = text.slice(5).trim();
            const SYS_BLOCKLIST = [
                /rm\s+(-rf?|--recursive)\s+[\/~]/i,    // rm -rf / or ~
                /mkfs/i, /dd\s+if=/i,                   // disk destruction
                />\s*\/dev\/sd/i,                        // write to raw devices
                /DROP\s+TABLE/i, /TRUNCATE\s+TABLE/i,   // database destruction
                /git\s+push\s+--force\s+(main|master)/i, // force push to main
                /git\s+reset\s+--hard/i,                 // hard reset
                /curl.*\|\s*(sh|bash)/i,                 // pipe curl to shell
                /wget.*\|\s*(sh|bash)/i,                 // pipe wget to shell
                /\.env/i,                                // .env file access
                /chmod\s+777/i,                          // world-writable permissions
                /sudo\s+rm/i,                            // sudo rm
            ];
            if (SYS_BLOCKLIST.some(p => p.test(sysCmd))) {
                await bot.sendMessage(chatId, 'BLOCKED: This command matches a security blocklist pattern.');
                log(`[SECURITY] Blocked !sys command: ${sysCmd}`);
                return;
            }
            log(`[SYS] Executing: ${sysCmd}`);
            await bot.sendMessage(chatId, 'Running...');
            exec(sysCmd, { windowsHide: true, timeout: 30000 }, (err, out, serr) => {
                const r = out || serr || (err ? err.message : 'Done.');
                log(`[SYS] Result: ${r.substring(0, 200)}`);
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
        log(`[RESULT] ${tool} returned ${(result || '').length} chars`);

        // --- APPROVAL GATE: Check if Claude is requesting confirmation ---
        const confirmMatch = (result || '').match(CONFIRM_PATTERN);
        if (confirmMatch) {
            const description = confirmMatch[1].trim();
            PENDING_CONFIRMATIONS[String(chatId)] = {
                description,
                timestamp: Date.now()
            };
            log(`[APPROVAL] Confirmation requested: ${description}`);
            // Store partial response (before the CONFIRM line) in history
            const idx = result.indexOf(confirmMatch[0]);
            const beforeConfirm = result.substring(0, idx).trim();
            if (beforeConfirm) {
                addToHistory(chatId, 'assistant', beforeConfirm);
                const preChunks = beforeConfirm.match(/[\s\S]{1,4000}/g) || [];
                for (const c of preChunks) await bot.sendMessage(chatId, c);
            }
            await bot.sendMessage(chatId,
                `🔒 Bravo wants to perform a destructive action:\n\n${description}\n\nApprove?`,
                {
                    reply_markup: {
                        inline_keyboard: [[
                            { text: '✅ Yes, proceed', callback_data: 'approve_yes' },
                            { text: '❌ No, cancel', callback_data: 'approve_no' }
                        ]]
                    }
                }
            );
            return; // Wait for callback
        }

        // Store assistant response in history (first 2000 chars)
        addToHistory(chatId, 'assistant', result || 'No response.');

        // Telegram limit is 4096 chars
        const chunks = (result || 'No response.').match(/[\s\S]{1,4000}/g) || ['No response.'];
        for (const c of chunks) {
            await bot.sendMessage(chatId, c);
        }
        log(`[SENT] Delivered ${chunks.length} chunk(s) to chat ${chatId}`);

        // V15.3: File relay — send any screenshots/recordings/files back to chat
        const filesSent = await sendFilesToChat(chatId, result || '');
        if (filesSent > 0) log(`[FILE] Relayed ${filesSent} file(s) to chat`);
    } catch (err) {
        log(`[CRASH] ${err.message}\n${err.stack}`);
        bot.sendMessage(chatId, `Error: ${err.message}`).catch(() => {});
    }
});

// ---- APPROVAL GATE: Inline keyboard callback handler ----
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const callbackUserId = String(query.from.id);
    const data = query.data;

    // SECURITY: Verify the callback comes from an authorized user
    if (!ALLOWED_USERS.includes(callbackUserId)) {
        log(`[BLOCKED] Unauthorized callback from user ${callbackUserId}`);
        await bot.answerCallbackQuery(query.id, { text: 'Unauthorized' }).catch(() => {});
        return;
    }

    const pending = PENDING_CONFIRMATIONS[String(chatId)];

    await bot.answerCallbackQuery(query.id).catch(() => {});

    if (!pending) {
        await bot.sendMessage(chatId, 'No pending confirmation found.');
        return;
    }

    delete PENDING_CONFIRMATIONS[String(chatId)];

    if (data === 'approve_yes') {
        await bot.sendMessage(chatId, '✅ Approved. Executing...');
        log(`[APPROVAL] User approved: ${pending.description}`);
        addToHistory(chatId, 'user', `APPROVED: Proceed with: ${pending.description}`);

        await bot.sendChatAction(chatId, 'typing');
        const followUp = `The user has APPROVED the following action: "${pending.description}". Proceed with execution now.`;
        const result = await executeCli('claude', followUp, chatId);

        addToHistory(chatId, 'assistant', result || 'Done.');
        const chunks = (result || 'Done.').match(/[\s\S]{1,4000}/g) || ['Done.'];
        for (const c of chunks) {
            await bot.sendMessage(chatId, c);
        }
    } else {
        await bot.sendMessage(chatId, '❌ Cancelled. Action was NOT performed.');
        log(`[APPROVAL] User denied: ${pending.description}`);
        addToHistory(chatId, 'assistant', `Action cancelled by user: ${pending.description}`);
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
    const msg = e.message || String(e);
    // 409 Conflict = another bot instance is polling (dual-machine scenario)
    if (msg.includes('409') || msg.includes('Conflict')) {
        log(`[POLL] 409 CONFLICT — another bot instance is running (likely the other machine). Backing off for 60s...`);
        // Don't crash — just wait. The other machine's bot will handle messages.
        // PM2 will keep us alive. When the other machine's bot stops, we'll resume.
        bot.stopPolling();
        setTimeout(() => {
            if (!shuttingDown) {
                log(`[POLL] Resuming polling after 409 backoff...`);
                bot.startPolling();
            }
        }, 60000);
        return;
    }
    // Log first error, then only every 50th to avoid filling logs
    if (pollErrorCount === 1 || pollErrorCount % 50 === 0) {
        log(`[POLL] EFATAL: ${msg} (count: ${pollErrorCount})`);
    }
});

// Catch unhandled rejections to prevent crash
process.on('unhandledRejection', (err) => {
    log(`[UNHANDLED] ${err.message || err}`);
});

log(`Bridge V15.3 ready. Platform: ${IS_MAC ? 'macOS' : 'Windows'}. Computer control: FULL CONTROL (60+ cmds).`);
