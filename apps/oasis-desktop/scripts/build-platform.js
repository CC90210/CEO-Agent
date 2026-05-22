#!/usr/bin/env node
/**
 * build-platform.js — single entry point for win/mac builds with
 * conditional signing.
 *
 * Why a wrapper instead of npm scripts: signing config differs per
 * platform AND per "do I have a cert today?" state. We want one
 * canonical path that:
 *   - Bundles the sidecar (Python interpreter + bravo_cli).
 *   - Detects whether signing credentials are present in env.
 *   - Runs electron-builder with the right flags.
 *   - Logs a clear final status — signed / unsigned / failed —
 *     so the operator knows whether the artifact is distribution-
 *     ready or local-testing-only.
 *
 * Usage:
 *   node scripts/build-platform.js win
 *   node scripts/build-platform.js win --unsigned
 *   node scripts/build-platform.js mac
 *   node scripts/build-platform.js mac --unsigned
 *
 * Signing env vars (electron-builder convention):
 *   Mac:
 *     CSC_LINK             - path to .p12 OR https URL to cert
 *     CSC_KEY_PASSWORD     - .p12 password
 *     APPLE_ID             - Apple ID for notarization
 *     APPLE_APP_SPECIFIC_PASSWORD - app-specific password
 *     APPLE_TEAM_ID        - 10-char Team ID
 *   Win:
 *     CSC_LINK             - path to .pfx OR https URL
 *     CSC_KEY_PASSWORD     - .pfx password
 *
 * Set --unsigned to force an unsigned local build even when env
 * vars are present (useful for fast iteration without a notarize
 * round-trip).
 */
"use strict";

const { spawn } = require("child_process");
const path = require("path");

const PLATFORM = process.argv[2];
const UNSIGNED_FLAG = process.argv.includes("--unsigned");

if (!PLATFORM || !["win", "mac"].includes(PLATFORM)) {
  console.error("Usage: build-platform.js <win|mac> [--unsigned]");
  process.exit(1);
}

const env = { ...process.env };

// Detect signing readiness per platform.
const macSigningReady =
  PLATFORM === "mac" &&
  !!env.CSC_LINK &&
  !!env.CSC_KEY_PASSWORD;
const macNotarizeReady =
  macSigningReady && !!env.APPLE_ID && !!env.APPLE_APP_SPECIFIC_PASSWORD && !!env.APPLE_TEAM_ID;
const winSigningReady =
  PLATFORM === "win" && !!env.CSC_LINK && !!env.CSC_KEY_PASSWORD;

const forceUnsigned = UNSIGNED_FLAG;

let mode;
if (forceUnsigned) {
  mode = "unsigned (forced via --unsigned)";
  env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
  // Tell our notarize hook to skip.
  env.OASIS_SKIP_NOTARIZE = "1";
} else if (PLATFORM === "mac") {
  if (macNotarizeReady) mode = "signed + notarized";
  else if (macSigningReady) mode = "signed (notarization skipped — APPLE_* vars missing)";
  else {
    mode = "unsigned (CSC_LINK + CSC_KEY_PASSWORD not set — SmartScreen / Gatekeeper will warn)";
    env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
    env.OASIS_SKIP_NOTARIZE = "1";
  }
} else {
  // win
  if (winSigningReady) mode = "signed (Authenticode)";
  else {
    mode = "unsigned (CSC_LINK + CSC_KEY_PASSWORD not set — SmartScreen will warn on first run)";
    env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
  }
}

console.log("");
console.log("================================================================");
console.log(` OASIS AI desktop build — platform: ${PLATFORM}`);
console.log(` mode: ${mode}`);
console.log("================================================================");
console.log("");

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      stdio: "inherit",
      env,
      shell: process.platform === "win32",
      cwd: path.resolve(__dirname, ".."),
    });
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} exited with code ${code}`));
    });
  });
}

(async () => {
  try {
    await run("npm", ["run", "bundle:sidecar"]);
    const builderArgs = [
      "electron-builder",
      `--${PLATFORM}`,
      "--publish=never",
    ];
    await run("npx", builderArgs);
    console.log("");
    console.log("================================================================");
    console.log(` BUILD OK — ${PLATFORM} (${mode})`);
    console.log(` artifacts: apps/oasis-desktop/dist/`);
    if (forceUnsigned || (PLATFORM === "mac" && !macNotarizeReady) || (PLATFORM === "win" && !winSigningReady)) {
      console.log("");
      console.log(" NOTE: Unsigned artifacts will trigger Gatekeeper (mac) or");
      console.log(" SmartScreen (win) warnings on first launch. See SIGNING.md");
      console.log(" for how to provision a code-signing certificate.");
    }
    console.log("================================================================");
  } catch (err) {
    console.error("");
    console.error("================================================================");
    console.error(` BUILD FAILED — ${PLATFORM}`);
    console.error(` ${err.message}`);
    console.error("================================================================");
    process.exit(1);
  }
})();
