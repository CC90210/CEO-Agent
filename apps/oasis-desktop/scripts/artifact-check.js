"use strict";

const asar = require("@electron/asar");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const distDir = path.join(root, "dist");
const exePath = path.join(distDir, "win-unpacked", "OASIS AI.exe");
const metadataPath = path.join(distDir, "release-metadata.json");
const sumsPath = path.join(distDir, "SHA256SUMS.txt");

function assert(condition, message) {
  if (!condition) throw new Error(message);
  console.log(`OK  ${message}`);
}

function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function walk(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(fullPath);
    return [fullPath];
  });
}

if (fs.existsSync(exePath)) {
  assert(fs.statSync(exePath).size > 100 * 1024 * 1024, "Windows executable has expected Electron runtime size");
}

const asarPath = walk(distDir).find((filePath) => filePath.endsWith(`${path.sep}app.asar`));
assert(fs.existsSync(asarPath), "Packaged app.asar exists");
assert(fs.existsSync(metadataPath), "release metadata exists");
assert(fs.existsSync(sumsPath), "SHA256SUMS exists");

const filesystem = asar.listPackage(asarPath).map((entry) => entry.replace(/\\/g, "/"));
for (const required of [
  "/src/main.js",
  "/src/auth-navigation.js",
  "/src/manifest.js",
  "/src/bridge-runtime.js",
  "/src/diagnostics.js",
  "/src/secure-store.js",
  "/desktop.manifest.json",
  "/README.md",
  "/RELEASE.md",
  "/scripts/auth-navigation-check.js",
  "/scripts/release-check.js",
  "/scripts/write-release-metadata.js"
]) {
  assert(filesystem.includes(required), `app.asar includes ${required}`);
}

const metadata = JSON.parse(fs.readFileSync(metadataPath, "utf8"));
assert(metadata.version === "0.1.0", "release metadata version is 0.1.0");
assert(metadata.channel === "alpha", "release metadata channel is alpha");
assert(Array.isArray(metadata.artifacts) && metadata.artifacts.length > 0, "release metadata has artifacts");

for (const artifact of metadata.artifacts) {
  const artifactPath = path.join(distDir, artifact.file);
  assert(fs.existsSync(artifactPath), `artifact exists: ${artifact.file}`);
  assert(
    fs.statSync(artifactPath).mtimeMs >= fs.statSync(asarPath).mtimeMs,
    `artifact is not older than packaged app.asar: ${artifact.file}`
  );
  assert(fs.statSync(artifactPath).size === artifact.bytes, `artifact byte count matches: ${artifact.file}`);
  assert(sha256(artifactPath) === artifact.sha256, `artifact sha256 matches: ${artifact.file}`);
}

const sums = fs.readFileSync(sumsPath, "utf8");
for (const artifact of metadata.artifacts) {
  assert(sums.includes(`${artifact.sha256}  ${artifact.file}`), `SHA256SUMS includes ${artifact.file}`);
}

console.log("OK  desktop artifact checks passed");
