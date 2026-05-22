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
 * Signing env vars (electron-builder convention, platform-specific
 * vars override the cross-platform ones — matches what the existing
 * .github/workflows/oasis-desktop.yml CI sets):
 *   Mac:
 *     MAC_CSC_LINK or CSC_LINK             - path to .p12 OR https URL
 *     MAC_CSC_KEY_PASSWORD or CSC_KEY_PASSWORD - .p12 password
 *     APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID — for notarytool
 *   Win:
 *     WIN_CSC_LINK or CSC_LINK             - path to .pfx OR https URL
 *     WIN_CSC_KEY_PASSWORD or CSC_KEY_PASSWORD - .pfx password
 *
 * Strict mode:
 *   OASIS_REQUIRE_WINDOWS_SIGNING=true  — fail the build if win signing
 *                                        env vars are missing. Matches
 *                                        scripts/release-check.js and
 *                                        scripts/signing-status.js so a
 *                                        production CI can pin "no
 *                                        unsigned artifacts ever".
 *   OASIS_REQUIRE_MAC_SIGNING=true      — same enforcement for Mac.
 *
 * Set --unsigned to force an unsigned local build even when env
 * vars are present (useful for fast iteration without a notarize
 * round-trip). --unsigned overrides OASIS_REQUIRE_* so the operator
 * can intentionally bypass strict mode for one local build.
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

// Detect signing readiness per platform. Honors the platform-specific
// electron-builder env vars (WIN_CSC_LINK / MAC_CSC_LINK) AND the
// cross-platform fallback (CSC_LINK). CI sets WIN_CSC_LINK explicitly
// per .github/workflows/oasis-desktop.yml; local operators usually
// just set CSC_LINK — both work.
const macCert = !!(env.MAC_CSC_LINK || env.CSC_LINK);
const macPassword = !!(env.MAC_CSC_KEY_PASSWORD || env.CSC_KEY_PASSWORD);
const winCert = !!(env.WIN_CSC_LINK || env.CSC_LINK);
const winPassword = !!(env.WIN_CSC_KEY_PASSWORD || env.CSC_KEY_PASSWORD);

const macSigningReady = PLATFORM === "mac" && macCert && macPassword;
const macNotarizeReady =
  macSigningReady && !!env.APPLE_ID && !!env.APPLE_APP_SPECIFIC_PASSWORD && !!env.APPLE_TEAM_ID;
const winSigningReady = PLATFORM === "win" && winCert && winPassword;

const forceUnsigned = UNSIGNED_FLAG;

// Strict-mode enforcement — refuses to build unsigned when set, unless
// --unsigned was explicitly passed (escape hatch for local debugging).
// Mirrors scripts/release-check.js + scripts/signing-status.js so a
// production CI can pin "no unsigned artifacts ever ship."
const requireWinSigning = env.OASIS_REQUIRE_WINDOWS_SIGNING === "true";
const requireMacSigning = env.OASIS_REQUIRE_MAC_SIGNING === "true";
if (!forceUnsigned && PLATFORM === "win" && requireWinSigning && !winSigningReady) {
  console.error("");
  console.error("================================================================");
  console.error(" BUILD REFUSED — OASIS_REQUIRE_WINDOWS_SIGNING=true but no");
  console.error(" Windows signing certificate is configured in env. Set");
  console.error(" WIN_CSC_LINK + WIN_CSC_KEY_PASSWORD (or CSC_LINK +");
  console.error(" CSC_KEY_PASSWORD) to proceed. See SIGNING.md.");
  console.error(" Bypass for local debug: pass --unsigned.");
  console.error("================================================================");
  process.exit(2);
}
if (!forceUnsigned && PLATFORM === "mac" && requireMacSigning && !macSigningReady) {
  console.error("");
  console.error("================================================================");
  console.error(" BUILD REFUSED — OASIS_REQUIRE_MAC_SIGNING=true but no Mac");
  console.error(" Developer ID certificate is configured in env. Set");
  console.error(" MAC_CSC_LINK + MAC_CSC_KEY_PASSWORD (or CSC_LINK +");
  console.error(" CSC_KEY_PASSWORD). See SIGNING.md.");
  console.error(" Bypass for local debug: pass --unsigned.");
  console.error("================================================================");
  process.exit(2);
}

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
