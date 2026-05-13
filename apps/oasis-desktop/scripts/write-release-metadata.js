"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const distDir = path.join(root, "dist");
const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const manifest = JSON.parse(fs.readFileSync(path.join(root, "desktop.manifest.json"), "utf8"));
const MIN_INSTALLER_BYTES = 10 * 1024 * 1024;

function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function walk(dir) {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(fullPath);
    return [fullPath];
  });
}

const artifacts = walk(distDir)
  .filter((filePath) => {
    const normalized = filePath.replace(/\\/g, "/");
    if (normalized.includes("/win-unpacked/")) return false;
    if (normalized.endsWith(".nsis.7z")) return false;
    if (!/\.(exe|zip|dmg|appimage|deb|rpm|msi)$/i.test(filePath)) return false;
    const stat = fs.statSync(filePath);
    if (/\.(exe|dmg|appimage|deb|rpm|msi)$/i.test(filePath) && stat.size < MIN_INSTALLER_BYTES) {
      console.warn(`Skipping suspiciously small artifact: ${path.relative(distDir, filePath)} (${stat.size} bytes)`);
      return false;
    }
    return true;
  })
  .map((filePath) => {
    const stat = fs.statSync(filePath);
    return {
      file: path.relative(distDir, filePath).replace(/\\/g, "/"),
      bytes: stat.size,
      sha256: sha256(filePath)
    };
  })
  .sort((a, b) => a.file.localeCompare(b.file));

if (artifacts.length === 0) {
  console.error("No release artifacts found in apps/oasis-desktop/dist.");
  process.exit(1);
}

const metadata = {
  generatedAt: new Date().toISOString(),
  product: manifest.product,
  version: packageJson.version,
  channel: manifest.product.channel,
  artifacts
};

const metadataPath = path.join(distDir, "release-metadata.json");
fs.writeFileSync(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
console.log(`Wrote ${metadataPath}`);

const checksumsPath = path.join(distDir, "SHA256SUMS.txt");
const checksums = artifacts.map((artifact) => `${artifact.sha256}  ${artifact.file}`).join("\n");
fs.writeFileSync(checksumsPath, `${checksums}\n`, "utf8");
console.log(`Wrote ${checksumsPath}`);
