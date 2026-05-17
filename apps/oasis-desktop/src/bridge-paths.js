"use strict";

/**
 * bridge-paths.js — shared file-system locations the desktop and the
 * Python sidecar (bravo_cli) both agree on.
 *
 * Single source of truth so main.js, first-run-window.js, future
 * "re-pair" flows, and the diagnostics window can't drift on path
 * shape. Mirrors what bravo_cli/wizard.py writes:
 *
 *   ~/.oasis/                       — directory (mode 0700 on POSIX)
 *   ~/.oasis/bridge_token            — raw bearer token, UTF-8, mode 0600
 *   ~/.oasis/bridge_pairing.json     — desktop-only metadata (tenant_id,
 *                                       machine_label, paired_at, etc.)
 *
 * The CLI doesn't write bridge_pairing.json today — only the desktop
 * wizard does. Resume code paths must handle either combination:
 *   token present + meta present  → wizard paired
 *   token present + meta absent   → CLI paired (treat as paired)
 *   token absent                  → not paired
 */

const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");

const OASIS_HOME_DIR = path.join(os.homedir(), ".oasis");
const BRIDGE_TOKEN_FILE = path.join(OASIS_HOME_DIR, "bridge_token");
const BRIDGE_META_FILE = path.join(OASIS_HOME_DIR, "bridge_pairing.json");

function ensureOasisHome() {
  if (!fs.existsSync(OASIS_HOME_DIR)) {
    fs.mkdirSync(OASIS_HOME_DIR, { recursive: true, mode: 0o700 });
  }
}

function bridgePaired() {
  return fs.existsSync(BRIDGE_TOKEN_FILE);
}

module.exports = {
  OASIS_HOME_DIR,
  BRIDGE_TOKEN_FILE,
  BRIDGE_META_FILE,
  ensureOasisHome,
  bridgePaired,
};
