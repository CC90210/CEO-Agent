"use strict";

const https = require("node:https");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const version = packageJson.version;

const RELEASE_TAG = process.env.OASIS_RELEASE_TAG || `oasis-desktop-v${version}-alpha.4`;
const REPO = process.env.OASIS_RELEASE_REPO || "CC90210/CEO-Agent";
const BASE = `https://github.com/${REPO}/releases/download/${RELEASE_TAG}`;

const ASSETS = [
  { name: `OASIS-AI-${version}-win-x64-portable.zip`, minBytes: 100 * 1024 * 1024 },
  { name: `OASIS-AI-${version}-win-x64.exe`, minBytes: 80 * 1024 * 1024 },
  { name: `OASIS-AI-${version}-mac-arm64.dmg`, minBytes: 80 * 1024 * 1024 },
  { name: `OASIS-AI-${version}-linux-x86_64.AppImage`, minBytes: 80 * 1024 * 1024 },
  { name: `OASIS-AI-${version}-linux-amd64.deb`, minBytes: 60 * 1024 * 1024 },
];

function head(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, { method: "HEAD" }, (res) => {
      if (
        res.statusCode &&
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location &&
        maxRedirects > 0
      ) {
        resolve(head(res.headers.location, maxRedirects - 1));
        return;
      }
      resolve({
        status: res.statusCode || 0,
        length: Number(res.headers["content-length"] || 0),
      });
    });
    req.on("error", reject);
    req.setTimeout(15_000, () => {
      req.destroy(new Error("HEAD request timed out"));
    });
    req.end();
  });
}

(async () => {
  let failed = 0;
  console.log(`Checking release assets at ${BASE}`);
  for (const asset of ASSETS) {
    const url = `${BASE}/${asset.name}`;
    try {
      const { status, length } = await head(url);
      const sizeOk = length >= asset.minBytes;
      const statusOk = status === 200;
      const tag = statusOk && sizeOk ? "OK" : "FAIL";
      console.log(
        `  [${tag}] ${asset.name} — HTTP ${status}, ${length.toLocaleString()} bytes (min ${asset.minBytes.toLocaleString()})`
      );
      if (!statusOk || !sizeOk) failed += 1;
    } catch (err) {
      failed += 1;
      console.log(`  [FAIL] ${asset.name} — ${err.message}`);
    }
  }
  if (failed > 0) {
    console.error(`\n${failed} asset(s) failed validation.`);
    process.exit(1);
  }
  console.log("\nAll release assets reachable and at expected minimum size.");
})();
