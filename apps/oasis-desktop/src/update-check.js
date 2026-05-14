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

const path = require("node:path");
const fs = require("node:fs");
const { httpsGetJson } = require("./https");

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

/**
 * Compare two SemVer-2.0.0 strings. Returns -1 if a < b, 1 if a > b, 0 if equal.
 *
 * The key SemVer rule the previous implementation got wrong: a version WITH
 * a pre-release suffix has LOWER precedence than the same version without
 * one. So "0.1.0-alpha" < "0.1.0", not the reverse. Walking the parts
 * naïvely (which is what we used to do) made an undefined slot beat a
 * pre-release token, which inverted that rule.
 *
 * Algorithm:
 *   1. Split into MAJOR.MINOR.PATCH and an optional pre-release tail.
 *   2. Compare the numeric MAJOR/MINOR/PATCH triple first.
 *   3. If equal: pre-release LOSES to no-pre-release.
 *   4. If both have pre-release: compare dot-separated identifiers per
 *      SemVer §11.4 (numeric identifiers compare numerically; alphanumerics
 *      compare lexicographically; numeric always loses to alphanumeric).
 */
function compareVersions(a, b) {
  if (a === b) return 0;
  const parse = (v) => {
    const [core, pre] = String(v).split("-", 2);
    const [maj, min, pat] = core.split(".").map((n) => Number(n) || 0);
    return { maj, min, pat, pre: pre || null };
  };
  const A = parse(a);
  const B = parse(b);
  if (A.maj !== B.maj) return A.maj < B.maj ? -1 : 1;
  if (A.min !== B.min) return A.min < B.min ? -1 : 1;
  if (A.pat !== B.pat) return A.pat < B.pat ? -1 : 1;
  // Equal core triple — pre-release LOSES to no-pre-release.
  if (A.pre === null && B.pre === null) return 0;
  if (A.pre === null) return 1;
  if (B.pre === null) return -1;
  // Both have pre-release. Compare dot-separated identifiers per SemVer 11.4.
  const idsA = A.pre.split(".");
  const idsB = B.pre.split(".");
  const len = Math.max(idsA.length, idsB.length);
  for (let i = 0; i < len; i++) {
    const ia = idsA[i];
    const ib = idsB[i];
    if (ia === undefined) return -1; // shorter pre-release loses on equal prefix
    if (ib === undefined) return 1;
    const numA = /^\d+$/.test(ia);
    const numB = /^\d+$/.test(ib);
    if (numA && numB) {
      const na = Number(ia);
      const nb = Number(ib);
      if (na !== nb) return na < nb ? -1 : 1;
    } else if (numA) {
      return -1; // numeric < alphanumeric per SemVer 11.4.3
    } else if (numB) {
      return 1;
    } else {
      if (ia !== ib) return ia < ib ? -1 : 1;
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
  const data = await httpsGetJson(
    `https://api.github.com/repos/${RELEASE_REPO}/releases/latest`,
    { accept: "application/vnd.github+json" }
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
