require('dotenv').config({ path: '.env.agents' });
const TelegramBot = require('node-telegram-bot-api');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// ============================================================
// BRAVO TELEGRAM BRIDGE V15.4
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
// V15.3.1: Auth Bulletproofing — startup API health check on every boot,
//         401 error detection with clear Telegram alert. Uses Claude Code
//         subscription auth (long-lived token via claude setup-token).
// V15.4: Stress-Tested + mousetool C binary — native CoreGraphics mouse control
//         (replaces broken Python Quartz), smooth animated cursor, drag support,
//         youtube-play atomic command, window/browser guard fixes, T0 max-turns 6,
//         tier classifier 24/24 PASS (coding exclusions prevent false T0 routing).
// ============================================================

// ---- PLATFORM DETECTION ----
const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';
const PYTHON = IS_MAC ? 'python3' : path.join(__dirname, '.venv', 'Scripts', 'python.exe');
const MACHINE_NAME = IS_MAC ? 'MacBook' : 'Windows Desktop';
const TEMP_PATH = IS_MAC ? '/tmp' : (process.env.TEMP || 'C:\\Temp');

const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const LOG_FILE = path.join(__dirname, 'memory', 'telegram_bridge.log');
const LOCK_FILE = path.join(__dirname, 'tmp', 'bravo_telegram.lock.json');

const log = (msg) => {
    const line = `[${new Date().toISOString()}] ${msg}\n`;
    console.log(line.trim());
    try { fs.appendFileSync(LOG_FILE, line); } catch (_) {}
};

const ensureTmpDir = () => {
    try { fs.mkdirSync(path.join(__dirname, 'tmp'), { recursive: true }); } catch (_) {}
};

const isPidAlive = (pid) => {
    if (!pid || Number.isNaN(Number(pid))) return false;
    try {
        process.kill(Number(pid), 0);
        return true;
    } catch (_) {
        return false;
    }
};

const acquireInstanceLock = () => {
    ensureTmpDir();
    try {
        if (fs.existsSync(LOCK_FILE)) {
            const existing = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
            if (existing.pid && existing.pid !== process.pid && isPidAlive(existing.pid)) {
                log(`[LOCK] Another local bridge owns polling (pid ${existing.pid}, ${existing.machine || 'unknown machine'}). Exiting cleanly.`);
                process.exit(0);
            }
            log(`[LOCK] Replacing stale bridge lock from pid ${existing.pid || 'unknown'}.`);
        }
    } catch (err) {
        log(`[LOCK] Could not read existing lock; replacing it (${err.message || err}).`);
    }

    fs.writeFileSync(LOCK_FILE, JSON.stringify({
        pid: process.pid,
        machine: MACHINE_NAME,
        platform: process.platform,
        started_at: new Date().toISOString()
    }, null, 2));
};

const releaseInstanceLock = () => {
    try {
        if (!fs.existsSync(LOCK_FILE)) return;
        const existing = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
        if (existing.pid === process.pid) fs.unlinkSync(LOCK_FILE);
    } catch (_) {}
};

if (!TELEGRAM_TOKEN) {
    console.error('TELEGRAM_BOT_TOKEN missing in .env.agents');
    process.exit(1);
}

acquireInstanceLock();
process.on('exit', releaseInstanceLock);

const bot = new TelegramBot(TELEGRAM_TOKEN, {
    polling: {
        autoStart: false,
        params: { timeout: 30 }
    },
    request: { timeout: 60000 }
});

log(`Bravo Telegram Bridge V15.4 (${IS_MAC ? 'macOS' : 'Windows'} - guarded autonomy) starting...`);

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

// C-Suite snapshot loader — single source of truth for the 4-agent fleet
// awareness. Used by every Telegram bridge (Bravo here, Atlas's
// telegram_bridge.py, Maven's telegram_agent.js when built) so a path or
// domain change in brain/CROSS_AGENT_AWARENESS.md propagates to all 3
// chats automatically. Falls back to a minimal inline snapshot if the
// canonical file is unavailable (fresh checkout, sibling-repo missing).
const loadCSuiteSnapshot = () => {
    const HEADER = '=== C-SUITE (CC\'s 4-agent team — always load) ===';
    const FOOTER = `\nCross-agent messaging: ${PYTHON} scripts/agent_inbox.py post --from bravo --to <atlas|maven|aura> --subject "..." --body "..."\nPulse files: data/pulse/ceo_pulse.json (yours), ../CMO-Agent/data/pulse/cmo_pulse.json (Maven), ../APPS/CFO-Agent/data/pulse/cfo_pulse.json (Atlas)`;

    // Preferred path: parse the canonical 4-agent table from brain/CROSS_AGENT_AWARENESS.md.
    const canon = readFileSafe('brain/CROSS_AGENT_AWARENESS.md');
    if (canon) {
        // Extract the table block ("## The 4 Agents at a Glance" → next heading).
        const tableMatch = canon.match(/## The 4 Agents at a Glance\s*\n([\s\S]*?)(?=\n##\s)/);
        if (tableMatch && tableMatch[1].trim()) {
            return `${HEADER}\n${tableMatch[1].trim()}${FOOTER}`;
        }
    }

    // Fallback: minimal hardcoded snapshot if the canonical file is missing.
    // Kept short — first responsibility is correctness, second is brevity.
    return `${HEADER}
- BRAVO (CEO, you) — C:\\Users\\User\\Business-Empire-Agent — strategy, clients, revenue, cold outreach, primary retainer/Skool, calendar
- ATLAS (CFO) — C:\\Users\\User\\APPS\\CFO-Agent — tax, accounting, runway, research, portfolio advisory; writes cfo_pulse.json
- MAVEN (CMO) — C:\\Users\\User\\CMO-Agent — paid ads (Meta+Google), social (Late/Zernio), Instagram, content pipeline, brand voice
- AURA (Life/Home) — C:\\Users\\User\\AURA — smart home, habits, presence, life context${FOOTER}`;
};

// ---- CONTEXT TIER CLASSIFICATION (from Claude Code harness patterns) ----
// Claude Code uses "simple mode" (184 tools → 3) for lightweight queries.
// We mirror this: classify query → load only needed context.
const T1_KEYWORDS = ['status', 'check', 'what', 'how much', 'mrr', 'balance', 'count', 'list', 'show', 'hello', 'hey', 'hi', 'thanks'];
const T3_KEYWORDS = ['redesign', 'architecture', 'refactor', 'migrate', 'schema', 'system', 'overhaul', 'sparc', 'complex', 'multi-file'];
// T2 is the default for everything else (build, fix, implement, debug, etc.)

// T0 keywords — quick actions that need minimal context (computer control + business tools)
const T0_KEYWORDS = /\b(open|launch|click|screenshot|volume|mute|play|switch|type|close|quit|move|resize|fullscreen|minimize|snap|record|dark.?mode|wifi|bluetooth|brightness|clipboard|copy|paste|lock|sleep|battery|sysinfo|soundcloud|music|song|track|browse|tab|website|url|amazon|download|scroll|mouse|drag|ping|network|ip|audio|shutdown|restart|cart|inbox|email|gmail|calendar|meeting|schedule|stripe|balance|invoice|payment|customer|post|social|linkedin|instagram|threads|tiktok|youtube|facebook|reddit|workflow|n8n|supabase|database|running|processes|apps)\b/i;
// Coding-task verbs that indicate T2 even if T0 keywords are present (e.g. "fix the supabase bug")
const T0_CODING_EXCLUSIONS = /\b(fix|debug|implement|refactor|build feature|write code|write function|failing test|unit test|create api|create endpoint|create route|create table|create schema)\b/i;

const classifyTier = (text) => {
    const t = text.toLowerCase();
    // T0: Quick action — minimal prompt for computer control + business tools
    // Exclude coding tasks even if they mention T0 keywords (e.g. "fix the supabase schema")
    if (T0_KEYWORDS.test(t) && !T3_KEYWORDS.some(k => t.includes(k)) && !T0_CODING_EXCLUSIONS.test(t)) return 0;
    // T3 keywords win first (most specific)
    if (T3_KEYWORDS.some(k => t.includes(k))) return 3;
    // T1 only if ALL words match simple patterns (no action verbs)
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
    // C-Suite snapshot — loaded at every tier so Bravo always knows about
    // Atlas + Maven + Aura. Reads brain/CROSS_AGENT_AWARENESS.md (single
    // source of truth — same file Atlas + Maven bridges read). Falls back
    // to a minimal hardcoded snapshot if the canonical file is unavailable
    // (e.g. fresh checkout, file moved, parse error).
    chunks.push(loadCSuiteSnapshot());

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
- Social posting (Maven owns — cross-repo): ${PYTHON} ../CMO-Agent/scripts/late_tool.py [accounts|posts|create]
- Supabase: ${PYTHON} scripts/supabase_tool.py [select|insert|sql]
- Stripe: ${PYTHON} scripts/stripe_tool.py [balance|customers|invoices]
- Email/Calendar: ${PYTHON} scripts/google_tool.py [gmail send|gmail list|calendar list|calendar create]
- Context Manager: ${PYTHON} scripts/context_manager.py [tier|compact|status|health]
- Cost Tracker: ${PYTHON} scripts/cost_tracker.py [log|summary|session|budget]
- Memory Aging: ${PYTHON} scripts/memory_aging.py [scan|stale|health|archive]
- Firecrawl (web scraping): ${PYTHON} scripts/firecrawl_tool.py [scrape|crawl|search|extract|map] <url|query>
- Semantic memory (mem0): ${PYTHON} scripts/mem0_tool.py [add|search|list|get|delete|stats]
- MCP servers: Playwright, Context7, Memory, Sequential Thinking, Firecrawl`);

    // Computer control (cross-platform — macOS + Windows)
    const REVEAL_CMD = IS_MAC ? 'reveal-in-finder' : 'reveal-in-explorer';
    chunks.push(`=== ${IS_MAC ? 'macOS' : 'Windows'} Computer Control V2.1 (60+ commands — FULL CONTROL) ===
APPS: open --app X | quit --app X | list-apps | frontmost
INPUT: type --text "..." | keystroke --keys "${IS_MAC ? 'cmd' : 'ctrl'}+c" | click --x N --y N | right-click --x N --y N | double-click --x N --y N | scroll --direction up|down [--amount N] | mouse-move --x N --y N | mouse-animate --x N --y N [--duration 0.5] [--steps 30] | drag --x1 N --y1 N --x2 N --y2 N [--duration 0.5]
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
WINDOWS EXTRAS: installed-apps | startup-apps | disk-usage | open-settings [--page X] | open-with --file X --app Y | focus-window --title "..." | open-task-manager | open-folder --path X
UTILITIES: download-file --url "..." [--path X] | set-wallpaper --path X | screen-resolution [--width N --height N]
VIRTUAL DESKTOPS: virtual-desktop-new | virtual-desktop-switch --direction left|right | virtual-desktop-close
HEADLESS BROWSER (background — no GUI, no mouse, CC keeps working): headless-browse --url "..." --action text|screenshot|links|title|html [--path X]

MONITORING: services [--all] | scheduled-tasks | event-log [--log System|Application] [--count N] | env-var --name X [--value Y] | uptime

CONCURRENCY RULES:
- BACKGROUND commands (safe while CC works): All file ops, network, system info, clipboard, browser CDP, headless-browse, download-file, list-*, get-*, sysinfo, search-*
- FOREGROUND commands (will interact with CC's screen): click, type, keystroke, scroll, mouse-move, drag, window-*, open (apps), task-switcher. WARN CC before using these.
- PREFER headless-browse over browser-open when CC is using the PC — it runs in background without touching the screen
- PREFER browser CDP commands (browser-js, browser-click-element, browser-fill) over click/type for web interaction — CDP works via WebSocket, no mouse movement
All via: \${PYTHON} scripts/${IS_MAC ? 'macos' : 'windows'}_control.py <command> [args] [--json]

=== SoundCloud Music Control (atomic — use this, NOT manual browser steps) ===
PLAY: \${PYTHON} scripts/music_control.py play --query "artist or song name"
PAUSE/RESUME: \${PYTHON} scripts/music_control.py pause | resume
SKIP/PREV: \${PYTHON} scripts/music_control.py skip | previous
NOW PLAYING: \${PYTHON} scripts/music_control.py current
SEARCH: \${PYTHON} scripts/music_control.py search --query "..."
All support --json flag.

CRITICAL: Use ATOMIC commands: youtube-play (1 cmd → YouTube playing), open --wait (waits for app launch). For web browsing, use browser-open/browser-js. For visual demos, use mouse-animate (smooth cursor movement). NEVER manually orchestrate what a built-in command already does — you WILL run out of turns.
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
    const history = getHistoryBlock(chatId);
    log(`[TIER] Query classified as T${tier} — loading ${tier === 0 ? 'COMPUTER CONTROL' : tier === 1 ? 'minimal' : tier === 2 ? 'standard' : 'full'} context`);

    // T0: Quick action — minimal prompt, use the RIGHT tool
    if (tier === 0) {
        return `You are Bravo, CC's Lead Architect on his ${MACHINE_NAME}. Full CLI access. Be direct.

BUSINESS OPS (use these — NOT the browser):
- Email: ${PYTHON} scripts/google_tool.py gmail list | gmail read <id> | gmail send --to "..." --subject "..." --body "..."
- Calendar: ${PYTHON} scripts/google_tool.py calendar list | calendar create --title "..." --start "..." --end "..."
- Revenue: ${PYTHON} scripts/revenue_engine.py mrr | dashboard | forecast | clients | goal
- Stripe: ${PYTHON} scripts/stripe_tool.py balance | customers | invoices
- CEO Briefing: ${PYTHON} scripts/ceo_dashboard.py briefing | revenue | pipeline | content | full
- Leads/CRM: ${PYTHON} scripts/lead_engine.py list | add "Name" --email x | followups | view <id>
- Client Health: ${PYTHON} scripts/client_health.py report | alerts | score <name>
- Content: ${PYTHON} ../CMO-Agent/scripts/content_engine.py calendar | create --platform x --pillar ceo_log --body "..." | due
- Social (Maven cross-repo): ${PYTHON} ../CMO-Agent/scripts/late_tool.py accounts | posts | create --text "..." --account <id>
- Instagram (Maven cross-repo): ${PYTHON} ../CMO-Agent/scripts/instagram_engine.py check-dms | auto-reply
- Image gen (Maven cross-repo): ${PYTHON} ../CMO-Agent/scripts/codex_image_gen.py generate "<prompt>"
- n8n: ${PYTHON} scripts/n8n_tool.py list | execute <id>
- Database: ${PYTHON} scripts/supabase_tool.py select <table> --project bravo --limit 10
- Financial: ${PYTHON} scripts/financial_model.py unit-economics | forecast | scenario --type base|bull|bear
- Skool metrics: ${PYTHON} scripts/skool_engine.py metrics --json (scrapes dashboard, updates revenue DB automatically)
- Web scraping: ${PYTHON} scripts/firecrawl_tool.py scrape <url> | crawl <url> --limit 10 | search "query" | map <url>
- Semantic memory: ${PYTHON} scripts/mem0_tool.py add "fact" | search "query" | list | stats

COMPUTER CONTROL (${IS_MAC ? 'macOS' : 'Windows'}):
${IS_MAC ? `SINGLE-COMMAND WORKFLOWS (use these first — atomic, 1 turn):
- Play YouTube: python3 scripts/macos_control.py youtube-play --query "lofi beats" --json
- Open app (wait for launch): python3 scripts/macos_control.py open --app "Serato DJ Pro" --wait --json
- Screenshot: python3 scripts/macos_control.py screenshot --json  (auto-sent to Telegram)
- Volume/mute: python3 scripts/macos_control.py volume --level N --json | mute --toggle --json
- Music (SoundCloud): python3 scripts/music_control.py play --query "..." --json
- Open URL in Chrome: python3 scripts/macos_control.py browser-open --url "https://..." --json

MOUSE & INTERACTION (visual — CC can watch the cursor move):
- Smooth move: python3 scripts/macos_control.py mouse-animate --x N --y N --duration 0.5 --json
- Click: python3 scripts/macos_control.py click --x N --y N --json
- Drag: python3 scripts/macos_control.py drag --x1 N --y1 N --x2 N --y2 N --duration 0.5 --json
- Type text: python3 scripts/macos_control.py type --text "..." --json
- Run JS in Chrome: python3 scripts/macos_control.py browser-js --script "document.querySelector('button').click()" --json
- Get screen size: python3 scripts/macos_control.py screen-size --json

ANY OTHER ACTION: python3 scripts/macos_control.py <command> [args] --json  (65+ commands)` : `- System/apps/windows: python scripts/windows_control.py <command> [args] --json
- Open URL in Chrome: python scripts/browse_and_capture.py --url "https://..."
- Music: python scripts/music_control.py play --query "..." --json`}

RULES: Use ATOMIC commands first (youtube-play, open --wait). For multi-step tasks, chain commands across turns — max 6 turns. Always prefer the single-command version when it exists. Never manually orchestrate what a built-in command already does.
${history}
CC says:`;
    }

    const context = loadContext(tier);
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
(6) Address the user as CC. Be direct, no filler.
(7) SPEED IS CRITICAL. Simple tasks = 1-3 turns MAX. Do NOT overthink.
(8) All credentials are in .env.agents — NEVER hardcode secrets.
(9) Use RECENT CONVERSATION HISTORY for context from prior messages.
(10) APPROVAL GATE: Before destructive actions, output "⚠️ CONFIRM: [description]" and STOP.
(11) COMPUTER CONTROL: ${PYTHON} scripts/${IS_MAC ? 'macos' : 'windows'}_control.py <command> --json for desktop control. ${PYTHON} scripts/browse_and_capture.py --url "URL" for opening webpages in CC's real Chrome.
(12) FILE RELAY: Screenshots/files saved to ${TEMP_PATH} are auto-sent to Telegram.
(13) MUSIC: ${PYTHON} scripts/music_control.py for SoundCloud.

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
        const tier = classifyTier(userPrompt);
        const timeout = tool === 'claude' ? (tier === 0 ? 300000 : CLAUDE_TIMEOUT) : GEMINI_TIMEOUT; // T0: 5min, others: 10min
        let cmd, args;

        if (tool === 'claude') {
            const maxTurns = tier === 0 ? '6' : '10';
            cmd = CLAUDE_EXE;
            args = [
                '-p', fullPrompt,
                '--permission-mode', 'acceptEdits',
                '--output-format', 'text',
                '--max-turns', maxTurns
            ];
        } else {
            const mcps = detectMcps(userPrompt);
            const mcpArgs = mcps.flatMap(m => ['--allowed-mcp-server-names', m]);
            cmd = NODE_EXE;
            args = [
                '--no-warnings=DEP0040',
                GEMINI_SCRIPT,
                '-p', fullPrompt,
                '--approval-mode', 'auto_edit',
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

            // Auth error detection — 401/OAuth expiry gets a clear message to CC
            if (code !== 0 && /authentication_error|OAuth token has expired|401|Invalid API key|Please obtain a new token/i.test(raw)) {
                log(`[AUTH ERROR] ${tool} returned auth failure — check ANTHROPIC_API_KEY in .env.agents`);
                resolve('Auth error — check that ANTHROPIC_API_KEY is valid in .env.agents, then: pm2 restart bravo-telegram');
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
        if (match[1]) paths.add(match[1]);
    }

    // Match bare temp paths (Windows C:\...\Temp\ or Unix /tmp/)
    const pattern2 = new RegExp(DIRECT_PATH_PATTERN.source, DIRECT_PATH_PATTERN.flags);
    while ((match = pattern2.exec(text)) !== null) {
        if (match[1]) paths.add(match[1]);
        else if (match[0]) paths.add(match[0]); // fallback to full match
    }

    // Safety net: brute-force extract any Windows temp file path
    const winTempPattern = /[A-Z]:\\[^\s,)"']*\\Temp\\[^\s,)"']+\.(?:png|jpg|jpeg|gif|mov|mp4|pdf)/gi;
    while ((match = winTempPattern.exec(text)) !== null) {
        paths.add(match[0]);
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

// ---- VOICE NOTE TRANSCRIPTION ----
const handleVoiceMessage = async (msg) => {
    const chatId = msg.chat.id;
    const voice = msg.voice || msg.audio;
    if (!voice) return null;

    try {
        await bot.sendMessage(chatId, '🎙️ Transcribing...');
        log(`[VOICE] Received voice note: ${voice.duration}s, ${voice.file_size} bytes`);

        // Download the voice file from Telegram
        const fileInfo = await bot.getFile(voice.file_id);
        const fileUrl = `https://api.telegram.org/file/bot${TELEGRAM_TOKEN}/${fileInfo.file_path}`;
        const tmpDir = process.env.TEMP || '/tmp';
        const oggPath = path.join(tmpDir, `voice_${Date.now()}.ogg`);

        // Download using curl (reliable on both platforms)
        const { execSync } = require('child_process');
        execSync(`curl -s -o "${oggPath}" "${fileUrl}"`, { timeout: 15000, windowsHide: true });

        if (!fs.existsSync(oggPath)) {
            await bot.sendMessage(chatId, 'Failed to download voice note.');
            return null;
        }

        // Transcribe using local Whisper
        const { execFile } = require('child_process');
        const transcription = await new Promise((resolve) => {
            execFile(PYTHON, [
                'scripts/transcribe.py',
                '--file', oggPath,
                '--model', voice.duration > 30 ? 'base' : 'tiny'  // tiny for short, base for longer
            ], {
                cwd: __dirname,
                timeout: 120000,  // 2min max for transcription
                windowsHide: true,
            }, (err, stdout, stderr) => {
                // Clean up OGG file
                try { fs.unlinkSync(oggPath); } catch (_) {}

                if (err) {
                    log(`[VOICE] Transcription error: ${err.message}`);
                    resolve(null);
                    return;
                }
                try {
                    const result = JSON.parse(stdout.trim());
                    if (result.ok && result.text) {
                        log(`[VOICE] Transcribed (${result.duration_s}s): "${result.text.substring(0, 80)}..."`);
                        resolve(result.text);
                    } else {
                        log(`[VOICE] Transcription failed: ${result.error || 'empty'}`);
                        resolve(null);
                    }
                } catch (e) {
                    log(`[VOICE] Parse error: ${e.message}`);
                    resolve(null);
                }
            });
        });

        if (transcription) {
            await bot.sendMessage(chatId, `📝 "${transcription}"\n\nProcessing...`);
            return transcription;
        } else {
            await bot.sendMessage(chatId, "Couldn't transcribe that. Try again or type your message.");
            return null;
        }
    } catch (e) {
        log(`[VOICE] Error: ${e.message}`);
        await bot.sendMessage(chatId, 'Voice processing failed.').catch(() => {});
        return null;
    }
};


// ---- TELEGRAM HANDLER ----
bot.on('message', async (msg) => {
    pollErrorCount = 0;
    const chatId = msg.chat.id;

    // Handle voice notes — transcribe and process as text
    let text = msg.text;
    if (!text && (msg.voice || msg.audio)) {
        text = await handleVoiceMessage(msg);
        if (!text) return;
    }
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
            `Bravo Bridge V15.4 (${MACHINE_NAME} — Full Computer Control)`,
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
            '!sys is disabled; use natural-language computer control commands instead.',
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
        // Raw shell passthrough is intentionally disabled. Use the natural
        // language computer-control route, which has scoped tools and approval
        // gates for destructive actions.
        if (text.startsWith('!sys ')) {
            const sysCmd = text.slice(5).trim();
            log(`[SECURITY] Rejected disabled !sys command: ${sysCmd.substring(0, 200)}`);
            await bot.sendMessage(chatId, '!sys is disabled. Ask me in normal language and I will route it through guarded computer-control tools.');
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

    // ---- OUTREACH BATCH: Approve / Skip inline buttons ----
    if (data.startsWith('outreach_send_') || data.startsWith('outreach_skip_')) {
        const leadId = data.replace(/^outreach_(send|skip)_/, '');
        const action = data.startsWith('outreach_send_') ? 'send' : 'skip';
        const draftPath = require('path').join(__dirname, 'tmp', 'outreach_drafts', `${leadId}.json`);

        await bot.answerCallbackQuery(query.id, { text: action === 'send' ? '📤 Sending…' : '⏭️ Skipped' }).catch(() => {});

        if (action === 'send') {
            await bot.sendMessage(chatId, '📤 Sending email...');
            log(`[OUTREACH] Approved send for lead ${leadId}`);
            const { execFile } = require('child_process');
            const PYTHON_BIN = IS_MAC ? 'python3' : 'python';
            execFile(PYTHON_BIN, ['scripts/outreach_batch.py', '--send-draft', draftPath], { cwd: __dirname, timeout: 30000 }, (err, stdout, stderr) => {
                let msg = stdout ? stdout.trim() : '';
                try { const j = JSON.parse(msg); msg = j.output || msg; } catch (_) {}
                if (err || stderr) msg = msg || `Error: ${stderr || err}`;
                bot.sendMessage(chatId, msg || '✅ Email sent.').catch(() => {});
            });
        } else {
            log(`[OUTREACH] Skipped lead ${leadId}`);
            const { execFile } = require('child_process');
            const PYTHON_BIN = IS_MAC ? 'python3' : 'python';
            execFile(PYTHON_BIN, ['scripts/outreach_batch.py', '--skip-draft', draftPath], { cwd: __dirname, timeout: 15000 }, () => {});
            await bot.sendMessage(chatId, `⏭️ Lead skipped.`);
        }
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
let pollingDormant = false;
bot.on('polling_error', (e) => {
    pollErrorCount++;
    const msg = e.message || String(e);
    // 409 Conflict = another bot instance is polling (dual-machine scenario)
    if (msg.includes('409') || msg.includes('Conflict')) {
        if (!pollingDormant) {
            pollingDormant = true;
            log('[POLL] 409 conflict: another bot instance owns this Telegram token. Entering dormant mode until PM2 restarts this process.');
        }
        bot.stopPolling().catch(() => {});
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

log(`Bridge V15.4 ready. Platform: ${IS_MAC ? 'macOS' : 'Windows'}. Computer control: FULL CONTROL (60+ cmds).`);

try {
    const pollingStart = bot.startPolling();
    log('[POLL] Polling requested.');
    if (pollingStart && typeof pollingStart.catch === 'function') {
        pollingStart.catch((err) => {
            log(`[POLL] Failed to start polling: ${err.message || err}`);
        });
    }
} catch (err) {
    log(`[POLL] Failed to start polling: ${err.message || err}`);
}

// ---- STARTUP AUTH HEALTH CHECK ----
// Tests ANTHROPIC_API_KEY directly on every boot. If it fails, Telegram alerts CC.
// Runs 5s after start so polling settles first.
setTimeout(() => {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
        log('[HEALTH] ANTHROPIC_API_KEY missing — Claude requests will fail');
        return;
    }
    const https = require('https');
    const body = JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 5,
        messages: [{ role: 'user', content: 'ping' }]
    });
    const req = https.request({
        hostname: 'api.anthropic.com',
        path: '/v1/messages',
        method: 'POST',
        headers: {
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
            'content-length': Buffer.byteLength(body)
        }
    }, (res) => {
        if (res.statusCode === 200) {
            log('[HEALTH] Anthropic API key: OK');
        } else {
            log(`[HEALTH] Anthropic API key FAILED (HTTP ${res.statusCode}) — check .env.agents`);
            if (ALLOWED_USERS.length > 0) {
                bot.sendMessage(ALLOWED_USERS[0],
                    `⚠️ Bravo startup: API key check failed (HTTP ${res.statusCode}).\nBravo will not respond until fixed. Update ANTHROPIC_API_KEY in .env.agents then: pm2 restart bravo-telegram`
                ).catch(() => {});
            }
        }
    });
    req.on('error', (e) => log(`[HEALTH] API check error: ${e.message}`));
    req.write(body);
    req.end();
}, 5000);
