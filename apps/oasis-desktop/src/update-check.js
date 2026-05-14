"use strict";

/**
 * Lightweight GitHub-release update probe. Uses only node:https — no
 * electron-updater dependency tree (saves ~30MB of bundled native modules
 * + makes auto-update work for unsigned builds, which electron-updater
 * is hostile to).
 *
 * The flow:
 *   1. Fetch https://api.github.com/repos/<owner>/<repo>/releases/latest
 *   2. Parse the tag (oasis-desktop-v0.1.0-alpha.5 → 0.1.0-alpha.5)
 *   3. Semver-ish compare against process.env.npm_package_version
 *   4. Resolve the platform-appropriate asset URL from the release payload
 *
 * Phase 5 (signed builds) can swap this for electron-updater. Until then
 * the prompt → "Open release page" hand-off matches the alpha posture.
 */

const https = require("node:https");
const path = require("node:path");
const fs = require("node:fs");

const RELEASE_REPO = process.env.OASIS_RELEASE_REPO || "CC90210/CEO-Agent";

function readPackageVersion() {
  try {
    const pkg = JSON.parse(
      fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8")
    );
    return typeof pkg.version === "string" ? pkg.version : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

function httpsJson(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      {
        headers: {
          "user-agent": "OASIS-AI-Desktop",
          accept: "application/vnd.github+json",
          ...headers,
        },
        timeout: 10_000,
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          if (!res.statusCode || res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`http_${res.statusCode}:${body.slice(0, 200)}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (err) {
            reject(err);
          }
        });
      }
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy(new Error("timeout"));
    });
  });
}

/**
 * Compare two semver-ish strings ("0.1.0-alpha.4" vs "0.1.0-alpha.5").
 * Returns -1 if a < b, 1 if a > b, 0 if equal. Pre-release tags sort
 * lexicographically; the comparator only needs to detect "is newer."
 */
function compareVersions(a, b) {
  if (a === b) return 0;
  const partsA = a.split(/[-.]/);
  const partsB = b.split(/[-.]/);
  const len = Math.max(partsA.length, partsB.length);
  for (let i = 0; i < len; i++) {
    const pa = partsA[i];
    const pb = partsB[i];
    if (pa === undefined) return -1;
    if (pb === undefined) return 1;
    const na = Number(pa);
    const nb = Number(pb);
    if (!Number.isNaN(na) && !Number.isNaN(nb)) {
      if (na !== nb) return na < nb ? -1 : 1;
    } else {
      if (pa !== pb) return pa < pb ? -1 : 1;
    }
  }
  return 0;
}

function tagToVersion(tag) {
  // Expect tags like "oasis-desktop-v0.1.0-alpha.5"
  const m = String(tag || "").match(/v(\d+\.\d+\.\d+(?:-[^\s]+)?)/i);
  return m ? m[1] : null;
}

function pickAssetForPlatform(assets) {
  if (!Array.isArray(assets)) return null;
  const wants =
    process.platform === "win32" ? ["win-x64-portable.zip", "win-x64.exe"] :
    process.platform === "darwin" ? ["mac-arm64.dmg", "mac.dmg"] :
    ["linux-x86_64.AppImage", "linux-amd64.deb"];
  for (const want of wants) {
    const hit = assets.find((a) => typeof a.name === "string" && a.name.endsWith(want));
    if (hit) return hit;
  }
  return null;
}

async function checkForUpdate() {
  const current = readPackageVersion();
  const data = await httpsJson(
    `https://api.github.com/repos/${RELEASE_REPO}/releases/latest`
  );
  const latest = tagToVersion(data.tag_name);
  if (!latest) {
    return { ok: false, reason: "no_tag", current };
  }
  const cmp = compareVersions(current, latest);
  const asset = pickAssetForPlatform(data.assets);
  return {
    ok: true,
    current,
    latest,
    is_newer: cmp < 0,
    tag: data.tag_name,
    html_url: data.html_url,
    asset: asset
      ? { name: asset.name, url: asset.browser_download_url, size: asset.size }
      : null,
  };
}

module.exports = {
  RELEASE_REPO,
  checkForUpdate,
  compareVersions,
  readPackageVersion,
  tagToVersion,
};
