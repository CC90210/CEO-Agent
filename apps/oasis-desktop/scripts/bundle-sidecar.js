"use strict";

/**
 * bundle-sidecar.js — collects the Python agent harness into a self-
 * contained tree under apps/oasis-desktop/resources/sidecar/ that
 * electron-builder picks up as `extraResources` and ships inside the
 * packaged app at `process.resourcesPath/sidecar/`.
 *
 * What this script intentionally does:
 *   - Hard-copies bravo_cli/, the *needed subset* of scripts/, brain/,
 *     and skills/ from the repo into resources/sidecar/.
 *   - Writes a `bundle.json` manifest with version, source git sha,
 *     and per-file SHA-256 so the desktop runtime can verify integrity
 *     before spawning the sidecar.
 *   - Skips any file matching .env.agents, *.key, *.pem, anything under
 *     scripts that includes "credentials", a __pycache__ dir, .pyc, .pyo.
 *     The bundle is auditable; secrets never leave the operator's machine.
 *
 * What this script intentionally does NOT do:
 *   - Download a Python runtime. That's a Phase 4.1 / CI concern (per-OS
 *     binary, ~30MB download per build). For now the desktop runtime
 *     spawns the system Python (`python3` on Mac/Linux, `python` on Win)
 *     and the /download page documents the Python 3.12 prerequisite.
 *   - Bundle the entire scripts/ dir. We curate by import-need so the
 *     desktop ships ~5MB of code instead of ~150MB, and so the audit
 *     surface stays small.
 *
 * Run: node apps/oasis-desktop/scripts/bundle-sidecar.js
 * Wired automatically before `electron-builder` via `prepack` script.
 */

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { execSync } = require("node:child_process");

const DESKTOP_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(DESKTOP_ROOT, "..", "..");
const SIDECAR_OUT = path.join(DESKTOP_ROOT, "resources", "sidecar");

// ---------------------------------------------------------------------------
// What goes in the bundle. Each entry is a (sourceRelToRepo, destRelToSidecar,
// optional includeFilter). The filter, when provided, runs against each file's
// path RELATIVE TO the source dir and must return true to copy.
// ---------------------------------------------------------------------------

const SIDECAR_TREE = [
  // bravo_cli is the sidecar entry point.
  {
    source: "bravo_cli",
    dest: "bravo_cli",
    include: (rel) => !/__pycache__|\.pyc$|\.pyo$|^test_/.test(rel),
  },
  // The minimum scripts/lib bravo_cli actually imports. Curated by hand
  // so we don't ship the full 47-script empire to every desktop user.
  // Keep this list short and review on every release.
  {
    source: "scripts/lib",
    dest: "scripts/lib",
    include: (rel) =>
      !/__pycache__|\.pyc$|\.pyo$|test_/.test(rel),
  },
  // The brain holds prompts the agent reads at runtime. Read-only for
  // the desktop runtime — the bundle is the source of truth, edits
  // happen in the repo and ship in the next release.
  {
    source: "brain",
    dest: "brain",
    include: (rel) =>
      rel.endsWith(".md") &&
      !rel.includes("STATE.md") &&
      !rel.includes("HEARTBEAT.md") &&
      !rel.includes("CROSS_AGENT_AWARENESS.md"),
  },
  // Skills the runtime can surface. Markdown only — no Python execution
  // out of skills/, they're prompt fragments.
  {
    source: "skills",
    dest: "skills",
    include: (rel) => rel.endsWith(".md") || rel.endsWith(".json"),
  },
];

// ---------------------------------------------------------------------------
// Hard-block list — any path matching one of these is never copied,
// regardless of include filter. Belt-and-suspenders for secrets.
// ---------------------------------------------------------------------------

const HARD_BLOCK = [
  /\.env(?:$|\.[^/\\]+)/i,
  /credentials/i,
  /[\\/]secrets?[\\/]/i,
  /\.key$/i,
  /\.pem$/i,
  /\.pfx$/i,
  /id_rsa/i,
];

function isHardBlocked(absPath) {
  return HARD_BLOCK.some((re) => re.test(absPath));
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function copyDirFiltered(srcAbs, destAbs, includeFn, relPrefix = "") {
  const entries = fs.readdirSync(srcAbs, { withFileTypes: true });
  for (const entry of entries) {
    const childSrc = path.join(srcAbs, entry.name);
    const childDest = path.join(destAbs, entry.name);
    const rel = relPrefix ? `${relPrefix}/${entry.name}` : entry.name;
    if (isHardBlocked(childSrc) || isHardBlocked(rel)) continue;
    if (entry.isDirectory()) {
      copyDirFiltered(childSrc, childDest, includeFn, rel);
    } else if (entry.isFile()) {
      if (!includeFn(rel)) continue;
      ensureDir(path.dirname(childDest));
      fs.copyFileSync(childSrc, childDest);
    }
  }
}

function sha256File(absPath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(absPath));
  return hash.digest("hex");
}

function walkFiles(rootAbs, basePrefix = "") {
  if (!fs.existsSync(rootAbs)) return [];
  const out = [];
  const stack = [{ abs: rootAbs, prefix: basePrefix }];
  while (stack.length) {
    const { abs, prefix } = stack.pop();
    const entries = fs.readdirSync(abs, { withFileTypes: true });
    for (const entry of entries) {
      const childAbs = path.join(abs, entry.name);
      const childPrefix = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) stack.push({ abs: childAbs, prefix: childPrefix });
      else if (entry.isFile()) out.push({ abs: childAbs, rel: childPrefix });
    }
  }
  return out.sort((a, b) => a.rel.localeCompare(b.rel));
}

function gitSha(repoRoot) {
  try {
    return execSync("git rev-parse --short=12 HEAD", { cwd: repoRoot, stdio: ["ignore", "pipe", "ignore"] })
      .toString().trim();
  } catch {
    return "unknown";
  }
}

function gitClean(repoRoot) {
  try {
    const status = execSync("git status --porcelain", { cwd: repoRoot, stdio: ["ignore", "pipe", "ignore"] })
      .toString().trim();
    return status.length === 0;
  } catch {
    return false;
  }
}

function main() {
  const startedAt = Date.now();
  // Wipe + recreate so deleted upstream files don't linger in the bundle.
  fs.rmSync(SIDECAR_OUT, { recursive: true, force: true });
  ensureDir(SIDECAR_OUT);

  let copiedCount = 0;
  let copiedBytes = 0;
  for (const tree of SIDECAR_TREE) {
    const srcAbs = path.join(REPO_ROOT, tree.source);
    const destAbs = path.join(SIDECAR_OUT, tree.dest);
    if (!fs.existsSync(srcAbs)) {
      console.warn(`[bundle-sidecar] missing source: ${tree.source} — skipping`);
      continue;
    }
    copyDirFiltered(srcAbs, destAbs, tree.include);
  }

  // Audit pass — every file under sidecar_out gets sha-256'd into the
  // manifest so the runtime can detect tampering or partial bundles.
  const allFiles = walkFiles(SIDECAR_OUT);
  const manifestFiles = allFiles
    .filter((f) => !f.rel.endsWith("bundle.json"))
    .map((f) => {
      const stat = fs.statSync(f.abs);
      copiedCount += 1;
      copiedBytes += stat.size;
      return { path: f.rel, sha256: sha256File(f.abs), size: stat.size };
    });

  const bundleManifest = {
    schema_version: 1,
    bundled_at: new Date().toISOString(),
    bundled_from_sha: gitSha(REPO_ROOT),
    bundled_from_clean: gitClean(REPO_ROOT),
    sources: SIDECAR_TREE.map((t) => ({ source: t.source, dest: t.dest })),
    file_count: manifestFiles.length,
    total_bytes: copiedBytes,
    files: manifestFiles,
  };
  fs.writeFileSync(
    path.join(SIDECAR_OUT, "bundle.json"),
    JSON.stringify(bundleManifest, null, 2),
    "utf8"
  );

  const ms = Date.now() - startedAt;
  console.log(`[bundle-sidecar] wrote ${copiedCount} files (${(copiedBytes / 1024).toFixed(1)} KiB) → ${path.relative(REPO_ROOT, SIDECAR_OUT)} in ${ms}ms`);
  console.log(`[bundle-sidecar] source git sha ${bundleManifest.bundled_from_sha}${bundleManifest.bundled_from_clean ? "" : " (dirty)"}`);
  if (!bundleManifest.bundled_from_clean) {
    console.warn("[bundle-sidecar] WARNING: source tree has uncommitted changes; bundle is not reproducible.");
  }
}

if (require.main === module) main();

module.exports = { main, SIDECAR_OUT };
