"use strict";

// One-shot "free distribution" build: produces unsigned artifacts for the
// host OS, runs the portable-zip + START_HERE_WINDOWS.txt step on Windows,
// and ad-hoc signs the .app on macOS so the bundle has a stable identity.
//
// Mac and Windows builds can only run on their native OS (electron-builder
// limitation for native code signing/install steps). This script is platform-
// aware and runs the right subset for the current host.

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

function run(label, command, args, opts = {}) {
  console.log(`\n› ${label}`);
  const result = spawnSync(command, args, { stdio: "inherit", cwd: root, shell: process.platform === "win32", ...opts });
  if (result.status !== 0) {
    console.error(`failed: ${label}`);
    process.exit(result.status || 1);
  }
}

console.log(`OASIS Desktop — free distribution build (host: ${process.platform})`);

if (process.platform === "win32") {
  run("Build Windows NSIS (unsigned)", "npm", ["run", "build:win"]);
  run("Create Windows portable zip + START_HERE_WINDOWS.txt", "npm", ["run", "portable:win"]);
  run("Verify release artifact", "npm", ["run", "artifact:check"]);
} else if (process.platform === "darwin") {
  run("Build macOS dmg + zip (unsigned)", "npm", ["run", "build:mac"]);
  const app = path.join(root, "dist", "mac-arm64", "OASIS AI.app");
  run("Ad-hoc sign the app", "bash", [path.join("scripts", "adhoc-sign-mac.sh"), app]);
  run("Verify release artifact", "npm", ["run", "artifact:check"]);
} else if (process.platform === "linux") {
  run("Build Linux AppImage + deb", "npm", ["run", "build:linux"]);
  run("Verify release artifact", "npm", ["run", "artifact:check"]);
} else {
  console.error(`Unsupported platform: ${process.platform}`);
  process.exit(1);
}

console.log("\n✔ free-tier build complete. Unsigned alpha — see /download for user instructions.");
