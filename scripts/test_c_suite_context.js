// Tests for scripts/c_suite_context.js
// =====================================
// Run: node scripts/test_c_suite_context.js
//
// Covers:
//   - SIBLING_REPOS resolution (env override, defaults, self-pointing)
//   - readSiblingRepo on missing repo / missing file / valid file
//   - loadCSuiteSnapshot canonical-table extraction + fallback
//   - loadSiblingPulses with synthetic pulse fixtures (fresh / stale / missing / malformed)
//   - formatAge boundary cases
//
// No mocha, no jest — kept dependency-free so it runs anywhere Node runs.
// Prints PASS / FAIL per case + summary; exits non-zero on any failure.

const fs = require('fs');
const path = require('path');
const os = require('os');

let passed = 0;
let failed = 0;
const fails = [];

function assert(cond, label) {
    if (cond) {
        passed++;
        console.log(`  ✓ ${label}`);
    } else {
        failed++;
        fails.push(label);
        console.log(`  ✗ ${label}`);
    }
}

function assertEq(actual, expected, label) {
    const ok = actual === expected;
    if (ok) {
        passed++;
        console.log(`  ✓ ${label}`);
    } else {
        failed++;
        fails.push(`${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
        console.log(`  ✗ ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
}

// ---- Test fixture: temp sibling-repo skeleton ----
function withTempSiblings(fn) {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'csuite-test-'));
    const repos = {
        bravo: path.join(tmp, 'bravo'),
        maven: path.join(tmp, 'maven'),
        atlas: path.join(tmp, 'atlas'),
        aura:  path.join(tmp, 'aura'),
    };
    for (const root of Object.values(repos)) {
        fs.mkdirSync(path.join(root, 'data', 'pulse'), { recursive: true });
        fs.mkdirSync(path.join(root, 'brain'), { recursive: true });
    }
    const prevEnv = {
        BRAVO_REPO: process.env.BRAVO_REPO,
        MAVEN_REPO: process.env.MAVEN_REPO,
        ATLAS_REPO: process.env.ATLAS_REPO,
        AURA_REPO:  process.env.AURA_REPO,
    };
    process.env.BRAVO_REPO = repos.bravo;
    process.env.MAVEN_REPO = repos.maven;
    process.env.ATLAS_REPO = repos.atlas;
    process.env.AURA_REPO  = repos.aura;
    try {
        // Fresh require to pick up env overrides
        delete require.cache[require.resolve('./c_suite_context.js')];
        const mod = require('./c_suite_context.js');
        fn({ tmp, repos, mod });
    } finally {
        for (const [k, v] of Object.entries(prevEnv)) {
            if (v === undefined) delete process.env[k];
            else process.env[k] = v;
        }
        fs.rmSync(tmp, { recursive: true, force: true });
        delete require.cache[require.resolve('./c_suite_context.js')];
    }
}


// ============================================================
console.log('SIBLING_REPOS resolution');
// ============================================================
withTempSiblings(({ repos, mod }) => {
    assertEq(mod.SIBLING_REPOS.bravo, repos.bravo, 'BRAVO_REPO env override applied');
    assertEq(mod.SIBLING_REPOS.maven, repos.maven, 'MAVEN_REPO env override applied');
    assertEq(mod.SIBLING_REPOS.atlas, repos.atlas, 'ATLAS_REPO env override applied');
    assertEq(mod.SIBLING_REPOS.aura,  repos.aura,  'AURA_REPO env override applied');
});


// ============================================================
console.log('\nreadSiblingRepo behavior');
// ============================================================
withTempSiblings(({ repos, mod }) => {
    fs.writeFileSync(path.join(repos.maven, 'brain', 'STATE.md'),
        'line1\nline2\nline3\nline4\nline5\n');

    assertEq(mod.readSiblingRepo('maven', 'brain/STATE.md'),
        'line1\nline2\nline3\nline4\nline5',
        'reads existing sibling file, trimmed');

    assertEq(mod.readSiblingRepo('maven', 'brain/STATE.md', 2),
        'line1\nline2',
        'maxLines truncation');

    assertEq(mod.readSiblingRepo('maven', 'does/not/exist.md'), '',
        'missing file → empty string, no throw');

    assertEq(mod.readSiblingRepo('nobody', 'anything'), '',
        'unknown agent → empty string');

    assertEq(mod.readSiblingRepo('atlas', 'brain/STATE.md'), '',
        'sibling repo exists but file missing → empty');
});


// ============================================================
console.log('\nloadCSuiteSnapshot — canonical extraction');
// ============================================================
withTempSiblings(({ repos, mod }) => {
    const canonContent = `# CROSS-AGENT AWARENESS

## The 4 Agents at a Glance

| Agent | Scope | Lives At | Pulse |
|-------|-------|----------|-------|
| **Bravo** (CEO) | strategy | path-to-bravo | ceo_pulse.json |
| **Atlas** (CFO) | money | path-to-atlas | cfo_pulse.json |

## Next Section
Other content.
`;
    fs.writeFileSync(path.join(repos.bravo, 'brain', 'CROSS_AGENT_AWARENESS.md'), canonContent);

    const snap = mod.loadCSuiteSnapshot();
    assert(snap.includes('=== C-SUITE'), 'snapshot has header');
    assert(snap.includes('Bravo') && snap.includes('Atlas'),
        'snapshot includes parsed agents');
    assert(!snap.includes('Next Section'),
        'parser stops at next ## heading');
    assert(snap.includes('agent_inbox.py'),
        'footer with cross-agent messaging command included');
});


// ============================================================
console.log('\nloadCSuiteSnapshot — fallback when canonical missing');
// ============================================================
withTempSiblings(({ mod }) => {
    // No CROSS_AGENT_AWARENESS.md was written — should fall back
    const snap = mod.loadCSuiteSnapshot();
    assert(snap.includes('BRAVO (CEO)'), 'fallback includes Bravo');
    assert(snap.includes('ATLAS (CFO)'), 'fallback includes Atlas');
    assert(snap.includes('MAVEN (CMO)'), 'fallback includes Maven');
    assert(snap.includes('AURA (Life/Home)'), 'fallback includes Aura');
});


// ============================================================
console.log('\nloadSiblingPulses — fresh / stale / missing / malformed');
// ============================================================
withTempSiblings(({ repos, mod }) => {
    const NOW = new Date('2026-04-26T12:00:00Z').getTime();

    // Maven: fresh pulse (1 hour old)
    fs.writeFileSync(path.join(repos.maven, 'data', 'pulse', 'cmo_pulse.json'),
        JSON.stringify({
            updated_at: '2026-04-26T11:00:00Z',
            session_note: 'Shipping Q2 ad creative',
        }));

    // Atlas: stale pulse (3 days old)
    fs.writeFileSync(path.join(repos.atlas, 'data', 'pulse', 'cfo_pulse.json'),
        JSON.stringify({
            updated_at: '2026-04-23T12:00:00Z',
            session_note: 'Reviewed runway',
        }));

    // Aura: malformed JSON
    fs.writeFileSync(path.join(repos.aura, 'data', 'pulse', 'aura_pulse.json'),
        '{ this is not json');

    const out = mod.loadSiblingPulses({ now: NOW });

    assert(out.includes('MAVEN (CMO, 1h ago'), 'maven pulse age formatted');
    assert(!out.match(/MAVEN.*STALE/), 'fresh maven not flagged stale');
    assert(out.includes('Shipping Q2 ad creative'), 'maven session_note rendered');

    assert(out.includes('ATLAS (CFO, 3d ago ⚠ STALE'),
        'atlas stale (3d) flagged with ⚠');

    assert(out.includes('failed to parse'),
        'malformed aura pulse surfaces parse failure');
});


// ============================================================
console.log('\nloadSiblingPulses — missing pulse files');
// ============================================================
withTempSiblings(({ mod }) => {
    // No pulse files written
    const out = mod.loadSiblingPulses();
    assert(out.includes('pulse not reachable'),
        'missing pulse files surfaced explicitly, not silently empty');
});


// ============================================================
console.log('\nloadLocalSiblingPaths reachability probe');
// ============================================================
withTempSiblings(({ repos, mod }) => {
    // All 4 sibling repos exist (set up by withTempSiblings) — should report REACHABLE for all
    const out = mod.loadLocalSiblingPaths({ machineName: 'TestMachine' });
    assert(out.includes('SIBLING AGENT REACHABILITY'), 'has header');
    assert(out.includes('TestMachine'), 'machineName parameter passed through');
    for (const agent of ['Atlas', 'Maven', 'Aura']) {
        assert(out.includes(`- ${agent}: REACHABLE`),
            `${agent} reported REACHABLE when its repo dir exists`);
    }
});

withTempSiblings(({ repos, mod }) => {
    // Force one repo to NOT exist by pointing env at a missing path
    const original = process.env.MAVEN_REPO;
    process.env.MAVEN_REPO = '/definitely/does/not/exist';
    try {
        // Re-require so MAVEN_REPO env override re-resolves
        delete require.cache[require.resolve('./c_suite_context.js')];
        const fresh = require('./c_suite_context.js');
        const out = fresh.loadLocalSiblingPaths();
        // Maven candidates fall back to platform defaults — those probably also don't
        // exist in the temp dir setup, so Maven should be NOT cloned.
        // Atlas + Aura still REACHABLE because they were created in the temp dir
        // and ATLAS_REPO/AURA_REPO env vars point there.
        assert(out.includes('Atlas: REACHABLE'), 'atlas still reachable');
    } finally {
        if (original === undefined) delete process.env.MAVEN_REPO;
        else process.env.MAVEN_REPO = original;
        delete require.cache[require.resolve('./c_suite_context.js')];
    }
});


// ============================================================
console.log('\n_resolveAgentRepo single-source resolution');
// ============================================================
withTempSiblings(({ repos, mod }) => {
    // Env override should win over candidates
    assertEq(mod.SIBLING_REPOS.maven, repos.maven,
        'env-overridden path used as canonical SIBLING_REPOS[maven]');
});

// Direct unit test of the resolver (with env override priority)
{
    const { _resolveAgentRepo } = require('./c_suite_context.js');
    const original = process.env.ATLAS_REPO;
    // Point env at a real existing dir
    process.env.ATLAS_REPO = require('os').tmpdir();
    try {
        delete require.cache[require.resolve('./c_suite_context.js')];
        const fresh = require('./c_suite_context.js');
        assertEq(fresh.SIBLING_REPOS.atlas, require('os').tmpdir(),
            'env override + dir exists → env wins');
    } finally {
        if (original === undefined) delete process.env.ATLAS_REPO;
        else process.env.ATLAS_REPO = original;
        delete require.cache[require.resolve('./c_suite_context.js')];
    }
}


// ============================================================
console.log('\nformatAge boundary cases');
// ============================================================
const { _formatAge: formatAge } = require('./c_suite_context.js');
const NOW = new Date('2026-04-26T12:00:00Z').getTime();
assertEq(formatAge('2026-04-26T11:59:30Z', NOW), 'just now', '< 1 minute');
assertEq(formatAge('2026-04-26T11:30:00Z', NOW), '30m ago',  '30 minutes');
assertEq(formatAge('2026-04-26T08:00:00Z', NOW), '4h ago',   '4 hours');
assertEq(formatAge('2026-04-23T12:00:00Z', NOW), '3d ago',   '3 days');
assertEq(formatAge(null, NOW),                   'unknown',  'null timestamp');
assertEq(formatAge('not-a-date', NOW),           'unknown',  'unparseable timestamp');
assertEq(formatAge('2026-04-27T00:00:00Z', NOW), 'future',   'future timestamp');


// ============================================================
console.log(`\n${'='.repeat(50)}`);
console.log(`PASSED: ${passed}   FAILED: ${failed}`);
if (failed > 0) {
    console.log('\nFailures:');
    fails.forEach(f => console.log(`  - ${f}`));
    process.exit(1);
}
console.log('All tests passed.');
