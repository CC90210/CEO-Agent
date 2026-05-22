#!/usr/bin/env node
/**
 * notarize.js — afterSign hook for the mac build.
 *
 * electron-builder calls this after the .app is code-signed. We
 * submit to Apple's notary service ONLY when:
 *   - The platform is darwin (Mac).
 *   - OASIS_SKIP_NOTARIZE is NOT set (build-platform.js sets this
 *     for unsigned local builds).
 *   - APPLE_ID + APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID are
 *     all set in env.
 *
 * Otherwise this hook is a no-op so signed-but-not-notarized
 * builds + unsigned builds both fall through without errors.
 *
 * Uses @electron/notarize — peer-installed when the operator's
 * ready to ship a notarized build. We DON'T add it as a hard
 * devDependency because most local builds skip notarization.
 * If the env vars are set and the dep is missing we surface a
 * clear "npm i -D @electron/notarize" instruction.
 */
"use strict";

const path = require("path");

module.exports = async function notarizeHook(context) {
  if (process.env.OASIS_SKIP_NOTARIZE === "1") {
    console.log("[notarize] OASIS_SKIP_NOTARIZE=1 — skipping.");
    return;
  }
  if (process.platform !== "darwin" || context.electronPlatformName !== "darwin") {
    return;
  }
  const { APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID } = process.env;
  if (!APPLE_ID || !APPLE_APP_SPECIFIC_PASSWORD || !APPLE_TEAM_ID) {
    console.log(
      "[notarize] APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD / APPLE_TEAM_ID " +
        "missing — skipping notarization. Set all three to enable.",
    );
    return;
  }

  let notarize;
  try {
    ({ notarize } = require("@electron/notarize"));
  } catch (err) {
    console.error(
      "[notarize] @electron/notarize not installed. To enable " +
        "notarization run:\n  npm i -D @electron/notarize",
    );
    throw new Error("notarize_dep_missing");
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = path.join(context.appOutDir, `${appName}.app`);

  console.log(`[notarize] submitting ${appName}.app to Apple…`);
  await notarize({
    tool: "notarytool",
    appPath,
    appleId: APPLE_ID,
    appleIdPassword: APPLE_APP_SPECIFIC_PASSWORD,
    teamId: APPLE_TEAM_ID,
  });
  console.log("[notarize] success — Gatekeeper will trust this build.");
};
