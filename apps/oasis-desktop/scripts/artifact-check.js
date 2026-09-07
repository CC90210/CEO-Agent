"use strict";

const asar = require("@electron/asar");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const distDir = path.join(root, "dist");
const exePath = path.join(distDir, "win-unpacked", "OASIS AI.exe");

// THE VERSION COMES FROM package.json, NOT A LITERAL.
//
// These three paths and the metadata assertion below hardcoded "0.1.0" while
// the package sat at 0.1.0-alpha.6, so the check looked for artifacts that
// electron-builder had never named and failed with "Windows portable zip
// exists" and "release metadata version is 0.1.0" on a build that had in fact
// succeeded on all three platforms.
//
// It went unnoticed because this step is the LAST one in the job and the job
// had been failing earlier, at release-check, since 2026-05-22 — so the artifact
// check had not run to completion in months. Fixing the earlier gate is what
// surfaced it.
//
// Pinning a version literal in a check that runs on every build is a guard with
// an expiry date. Reading it from the package keeps the invariant (the metadata
// must match the package it was built from) without the expiry.
const pkgVersion = JSON.parse(
  fs.readFileSync(path.join(root, "package.json"), "utf8"),
).version;
const windowsInstallerPath = path.join(distDir, `OASIS-AI-${pkgVersion}-win-x64.exe`);
const windowsPortableZipPath = path.join(distDir, `OASIS-AI-${pkgVersion}-win-x64-portable.zip`);
const metadataPath = path.join(distDir, "release-metadata.json");
const sumsPath = path.join(distDir, "SHA256SUMS.txt");
const MIN_INSTALLER_BYTES = 10 * 1024 * 1024;
const MIN_PORTABLE_BYTES = 100 * 1024 * 1024;

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
  assert(fs.statSync(exePath).size > MIN_PORTABLE_BYTES, "Windows executable has expected Electron runtime size");
  if (fs.existsSync(windowsInstallerPath)) {
    const installerBytes = fs.statSync(windowsInstallerPath).size;
    if (installerBytes < MIN_INSTALLER_BYTES) {
      console.warn(`WARN Windows NSIS installer is a suspicious local stub and must not be released: ${installerBytes} bytes`);
    } else {
      assert(true, "Windows NSIS installer has expected release size");
    }
  } else {
    console.warn("WARN Windows NSIS installer is absent; portable zip remains the alpha release artifact");
  }
  assert(fs.existsSync(windowsPortableZipPath), "Windows portable zip exists");
  assert(fs.statSync(windowsPortableZipPath).size > MIN_PORTABLE_BYTES, "Windows portable zip has expected Electron runtime size");
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
assert(
  metadata.version === pkgVersion,
  `release metadata version matches package.json (${pkgVersion})`,
);
assert(metadata.channel === "alpha", "release metadata channel is alpha");
assert(Array.isArray(metadata.artifacts) && metadata.artifacts.length > 0, "release metadata has artifacts");

for (const artifact of metadata.artifacts) {
  const artifactPath = path.join(distDir, artifact.file);
  assert(fs.existsSync(artifactPath), `artifact exists: ${artifact.file}`);
  if (/\.exe$/i.test(artifact.file)) {
    assert(fs.statSync(artifactPath).size > MIN_INSTALLER_BYTES, `installer artifact is not a stub: ${artifact.file}`);
  }
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
