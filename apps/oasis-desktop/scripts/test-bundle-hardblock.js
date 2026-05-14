"use strict";

/**
 * Real test of the bundle's HARD_BLOCK regex set — runs each pattern
 * against canonical bad inputs (must match) and known-good inputs
 * (must NOT match). The release-check.js suite asserts the pattern
 * strings are PRESENT in the source; this script asserts they
 * ACTUALLY work, which is a different and stronger guarantee.
 *
 * Run: node apps/oasis-desktop/scripts/test-bundle-hardblock.js
 * Exit code 0 on pass; non-zero with a printed failure list on fail.
 */

const path = require("node:path");
const { HARD_BLOCK, isHardBlocked } = require("./bundle-sidecar.js");

// Each tuple: [bad path that MUST be blocked, why]. Every pattern in
// HARD_BLOCK should have at least one corresponding entry here — if you
// add a pattern, add a case. Run this test after every HARD_BLOCK edit.
const MUST_BLOCK = [
  // .env family
  [".env",                                  "bare .env file"],
  [".env.local",                            "next.js local env file"],
  [".env.production",                       "production env file"],
  ["bravo_cli/.env.agents",                 ".env nested under bundled dir"],

  // credentials / secrets
  ["scripts/credentials.json",              "credentials json"],
  ["my-credentials.txt",                    "credentials substring"],
  ["app/secrets/api.txt",                   "secrets directory"],
  ["scripts/secret/db.txt",                 "secret directory singular"],

  // key material
  ["server.key",                            ".key extension"],
  ["server.pem",                            ".pem extension"],
  ["wildcard.pfx",                          ".pfx extension"],
  ["cert.p12",                              ".p12 extension"],
  ["public.crt",                            ".crt extension"],
  ["public.cer",                            ".cer extension"],
  ["password-store.kdbx",                   "KeePass database"],
  [".htpasswd",                             "Apache htpasswd"],

  // ssh / aws / gnupg / docker / git
  ["home/user/.ssh/id_rsa",                 "private key in .ssh dir"],
  ["home/user/.ssh/id_ed25519",             "any file in .ssh"],
  ["home/user/.aws/credentials",            "aws credentials file"],
  ["home/user/.aws/config",                 "aws config file"],
  ["home/user/.gnupg/secring.gpg",          "gnupg secrets ring"],
  ["myproject/.git/config",                 ".git directory"],
  ["home/user/.docker/config.json",         "docker config tokens"],
  ["bravo_cli/id_rsa",                      "id_rsa anywhere"],

  // npm / token files
  [".npmrc",                                ".npmrc (often holds auth)"],
  ["home/user/.npmrc",                      ".npmrc in user home"],
  ["tokens.json",                           "token JSON dump"],
  ["my-tokens.json",                        "token JSON with prefix"],
];

// Each tuple: [legitimate path that MUST NOT be blocked, why].
// Catches over-broad regex (e.g., a pattern like /key/ that would eat
// "keyboard.py" by mistake).
const MUST_NOT_BLOCK = [
  ["bravo_cli/__init__.py",                 "core sidecar entry"],
  ["bravo_cli/local_bridge.py",             "primary bridge"],
  ["bravo_cli/bridge_chat_server.py",       "chat server"],
  ["scripts/lib/secret_loader.py",          "secret_LOADER (not a secret itself)"],
  ["brain/SOUL.md",                         "operator brain markdown"],
  ["brain/EXECUTION_RULES.md",              "execution rules"],
  ["skills/outreach-send/SKILL.md",         "skill spec"],
  ["bundle.json",                           "bundle manifest"],
  ["bravo_cli/agent_roots.py",              "agent_roots — no key/cred markers"],
  ["scripts/lib/git_helpers.py",            ".git substring but not in path component"],
];

function run() {
  const failures = [];

  for (const [target, reason] of MUST_BLOCK) {
    if (!isHardBlocked(target)) {
      failures.push(`SHOULD BLOCK but didn't: ${target} (${reason})`);
    }
  }
  for (const [target, reason] of MUST_NOT_BLOCK) {
    if (isHardBlocked(target)) {
      failures.push(`SHOULD ALLOW but blocked: ${target} (${reason})`);
    }
  }

  // Coverage check — every HARD_BLOCK pattern should have caught at
  // least one MUST_BLOCK case. A pattern that catches nothing is dead
  // code at best and a typo at worst.
  const uncoveredPatterns = [];
  for (const pattern of HARD_BLOCK) {
    const caught = MUST_BLOCK.some(([target]) => pattern.test(target));
    if (!caught) {
      uncoveredPatterns.push(pattern.toString());
    }
  }
  for (const p of uncoveredPatterns) {
    failures.push(`UNCOVERED pattern: ${p} (no MUST_BLOCK case matches)`);
  }

  const total = MUST_BLOCK.length + MUST_NOT_BLOCK.length + uncoveredPatterns.length;
  const passed = total - failures.length;
  console.log(`[hardblock-test] ${passed}/${total} checks passed`);
  console.log(`  must-block cases: ${MUST_BLOCK.length}`);
  console.log(`  must-allow cases: ${MUST_NOT_BLOCK.length}`);
  console.log(`  pattern coverage: ${HARD_BLOCK.length - uncoveredPatterns.length}/${HARD_BLOCK.length}`);

  if (failures.length === 0) {
    console.log("OK  every HARD_BLOCK pattern catches its intended target; no false positives");
    return 0;
  }
  console.error(`\nFAIL  ${failures.length} issue(s):`);
  for (const f of failures) console.error(`  - ${f}`);
  return 1;
}

if (require.main === module) {
  process.exit(run());
}

module.exports = { run, MUST_BLOCK, MUST_NOT_BLOCK };
