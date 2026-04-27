// C-Suite cross-agent context module
// =====================================
// Single source of truth for "what do the other agents know / read".
// Used by:
//   - telegram_agent.js (Bravo's Telegram bridge)
//   - any future Bravo Node CLI that needs cross-agent state
//   - reference implementation that Maven's bridge mirrors verbatim
//
// Public API:
//   SIBLING_REPOS                       — env-overridable repo path map
//   readSiblingRepo(agent, rel, max?)   — read a file from a sibling repo
//   readSelfRepo(rel, max?)             — read a file from Bravo's own repo
//   loadCSuiteSnapshot(opts?)           — return the canonical 4-agent snapshot
//   loadSiblingPulses(opts?)            — return a multi-line "current state"
//                                         summary of Maven/Atlas/Aura pulses
//
// Why a module: the bridge previously had these helpers inline with eval-
// only tests. Extracting them to a require()-able module makes them unit-
// testable (see scripts/test_c_suite_context.js) and reusable.

const fs = require('fs');
const path = require('path');

const IS_MAC = process.platform === 'darwin';

// ---- SIBLING REPO PATHS ----
// Resolution order: env var → platform default. Defaults assume CC's
// canonical Windows layout; on Mac, $HOME-relative. If a sibling repo
// doesn't exist on this machine, all readSiblingRepo() calls for that
// agent return empty string — no crash.
const SIBLING_REPOS = {
    bravo: process.env.BRAVO_REPO || path.resolve(__dirname, '..'),
    maven: process.env.MAVEN_REPO || (IS_MAC
        ? path.join(process.env.HOME || '', 'CMO-Agent')
        : 'C:\\Users\\User\\CMO-Agent'),
    atlas: process.env.ATLAS_REPO || (IS_MAC
        ? path.join(process.env.HOME || '', 'APPS', 'CFO-Agent')
        : 'C:\\Users\\User\\APPS\\CFO-Agent'),
    aura: process.env.AURA_REPO || (IS_MAC
        ? path.join(process.env.HOME || '', 'AURA')
        : 'C:\\Users\\User\\AURA'),
};

// ---- FILE READERS ----

// Read a file from a sibling agent's repo. Returns trimmed content or
// '' on any error (missing repo, missing file, permission denied, etc.).
function readSiblingRepo(agent, relPath, maxLines = 0) {
    const root = SIBLING_REPOS[agent];
    if (!root) return '';
    try {
        const content = fs.readFileSync(path.join(root, relPath), 'utf8');
        if (maxLines > 0) {
            return content.split('\n').slice(0, maxLines).join('\n').trim();
        }
        return content.trim();
    } catch (_) { return ''; }
}

// Read a file from Bravo's own repo (the directory containing scripts/).
function readSelfRepo(relPath, maxLines = 0) {
    return readSiblingRepo('bravo', relPath, maxLines);
}

// ---- C-SUITE SNAPSHOT ----

// Pull the canonical 4-agent table out of brain/CROSS_AGENT_AWARENESS.md.
// Falls back to a hardcoded minimal snapshot if the canonical doc is
// missing or unparseable. The PYTHON binding is the path to the local
// Python interpreter so the embedded inbox-call examples render with
// the right invocation.
function loadCSuiteSnapshot(opts = {}) {
    const PYTHON = opts.python || (IS_MAC ? 'python3' : 'python');
    const HEADER = `=== C-SUITE (CC's 4-agent team — always load) ===`;
    const FOOTER = `\nCross-agent messaging: ${PYTHON} scripts/agent_inbox.py post --from bravo --to <atlas|maven|aura> --subject "..." --body "..."\nPulse files: data/pulse/ceo_pulse.json (yours), ../CMO-Agent/data/pulse/cmo_pulse.json (Maven), ../APPS/CFO-Agent/data/pulse/cfo_pulse.json (Atlas)`;

    const canon = readSelfRepo('brain/CROSS_AGENT_AWARENESS.md');
    if (canon) {
        const tableMatch = canon.match(/## The 4 Agents at a Glance\s*\n([\s\S]*?)(?=\n##\s)/);
        if (tableMatch && tableMatch[1].trim()) {
            return `${HEADER}\n${tableMatch[1].trim()}${FOOTER}`;
        }
    }

    return `${HEADER}
- BRAVO (CEO) — C:\\Users\\User\\Business-Empire-Agent — strategy, clients, revenue, cold outreach, primary retainer/Skool, calendar
- ATLAS (CFO) — C:\\Users\\User\\APPS\\CFO-Agent — tax, accounting, runway, research, portfolio advisory; writes cfo_pulse.json
- MAVEN (CMO) — C:\\Users\\User\\CMO-Agent — paid ads (Meta+Google), social (Late/Zernio), Instagram, content pipeline, brand voice
- AURA (Life/Home) — C:\\Users\\User\\AURA — smart home, habits, presence, life context${FOOTER}`;
}

// ---- SIBLING PULSE SUMMARIZER ----

// Internal: format a millisecond timestamp diff as a human-readable age.
function formatAge(iso, now = Date.now()) {
    if (!iso) return 'unknown';
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return 'unknown';
    const ageMs = now - t;
    if (ageMs < 0) return 'future';
    if (ageMs < 60_000) return 'just now';
    const minutes = Math.floor(ageMs / 60_000);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

// Read each sibling's pulse JSON and return a multi-line summary block.
// `staleHours` (default 24) controls when a pulse gets the ⚠ STALE flag.
// `now` is overridable for deterministic testing.
function loadSiblingPulses(opts = {}) {
    const staleHours = opts.staleHours || 24;
    const now = opts.now || Date.now();
    const lines = ['=== SIBLING PULSES (current state of Maven/Atlas/Aura) ==='];

    const targets = [
        ['maven', 'cmo_pulse.json', 'CMO'],
        ['atlas', 'cfo_pulse.json', 'CFO'],
        ['aura',  'aura_pulse.json', 'Life'],
    ];

    for (const [agent, file, role] of targets) {
        const raw = readSiblingRepo(agent, `data/pulse/${file}`);
        if (!raw) {
            lines.push(`- ${agent.toUpperCase()} (${role}): pulse not reachable (sibling repo missing on this machine, or pulse never written)`);
            continue;
        }
        try {
            const pulse = JSON.parse(raw);
            const note = (pulse.session_note || pulse.note || '').trim().slice(0, 200);
            const tsField = pulse.updated_at || pulse.timestamp;
            const age = formatAge(tsField, now);
            const tsMs = new Date(tsField || 0).getTime();
            const stale = Number.isNaN(tsMs) || (now - tsMs) > staleHours * 3600_000;
            const flag = stale ? ' ⚠ STALE' : '';
            lines.push(`- ${agent.toUpperCase()} (${role}, ${age}${flag}): ${note || '(no session_note)'}`);
        } catch (_) {
            lines.push(`- ${agent.toUpperCase()} (${role}): pulse exists but failed to parse`);
        }
    }
    return lines.join('\n');
}

module.exports = {
    SIBLING_REPOS,
    readSiblingRepo,
    readSelfRepo,
    loadCSuiteSnapshot,
    loadSiblingPulses,
    // Exported for unit tests only — not part of the stable public API.
    _formatAge: formatAge,
    _IS_MAC: IS_MAC,
};
