"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const distDir = path.join(root, "dist");
const unpackedDir = path.join(distDir, "win-unpacked");
const zipPath = path.join(distDir, `OASIS-AI-${packageJson.version}-win-x64-portable.zip`);

function fail(message) {
  console.error(message);
  process.exit(1);
}

function quotePowerShell(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

if (process.platform !== "win32") {
  fail("Windows portable zip can only be created on Windows.");
}

if (!fs.existsSync(unpackedDir)) {
  fail(`Missing ${unpackedDir}. Run the Windows desktop build before creating the portable zip.`);
}

if (!fs.existsSync(path.join(unpackedDir, "OASIS AI.exe"))) {
  fail("Missing OASIS AI.exe inside win-unpacked.");
}

fs.rmSync(zipPath, { force: true });

const command = [
  "$ErrorActionPreference = 'Stop'",
  `$source = Join-Path ${quotePowerShell(unpackedDir)} '*'`,
  `Compress-Archive -Path $source -DestinationPath ${quotePowerShell(zipPath)} -Force`
].join("; ");

const result = spawnSync(
  "powershell.exe",
  ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
  { stdio: "inherit" }
);

if (result.status !== 0) {
  fail(`Failed to create Windows portable zip at ${zipPath}.`);
}

const size = fs.statSync(zipPath).size;
if (size < 100 * 1024 * 1024) {
  fail(`Windows portable zip is suspiciously small: ${size} bytes.`);
}

console.log(`Created ${zipPath}`);
