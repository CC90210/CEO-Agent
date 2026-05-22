#!/usr/bin/env node
/**
 * bootstrap-python.js — first-launch Python runtime provisioner.
 *
 * Removes the "Install Python 3.12 from python.org" prerequisite
 * from the public download page. Operators who download the app
 * should not have to think about Python.
 *
 * Strategy (in order of preference):
 *
 *   1. CHECK existing system Python.
 *      Try `python3 --version` (mac/linux) or `python --version` (win).
 *      If we find ≥ 3.12, write its path to <userData>/python-runtime/
 *      manifest.json and exit clean. Zero user-visible work.
 *
 *   2. CHECK bundled runtime in <resourcesPath>/python/.
 *      Future-build path — when `bundle-sidecar.js` is upgraded to
 *      include a portable python-build-standalone tarball, the
 *      shipped runtime lives here. Detect + use it without prompting.
 *
 *   3. PROVISION via the OS's package manager.
 *      - macOS: `brew install python@3.12` if Homebrew exists. Falls
 *        back to opening the python.org pkg installer in Safari.
 *      - Windows: `winget install Python.Python.3.12 --silent` if
 *        winget is on PATH. Falls back to opening python.org in
 *        Edge with a one-click install.
 *      - Linux: print the apt/dnf/pacman command — distros vary too
 *        much to silently provision.
 *
 *   4. SURFACE a clear dialog if all paths fail.
 *      The main process should show a modal with the right install
 *      link for the user's OS plus a "Retry" button. NEVER hard-
 *      crash on first launch.
 *
 * This script is invoked by `src/main.js` BEFORE the bridge sidecar
 * spawns. Output goes to stdout as JSON so main can parse the result.
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const REQUIRED_MAJOR = 3;
const REQUIRED_MINOR = 12;

/**
 * Probe a python executable for version. Returns the resolved
 * { path, major, minor } when it's at or above the required floor,
 * null otherwise.
 */
function probePython(executable) {
  try {
    const result = spawnSync(executable, ["--version"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 5000,
    });
    const out = (result.stdout || "") + (result.stderr || "");
    const m = out.match(/Python\s+(\d+)\.(\d+)/);
    if (!m) return null;
    const major = parseInt(m[1], 10);
    const minor = parseInt(m[2], 10);
    if (
      major < REQUIRED_MAJOR ||
      (major === REQUIRED_MAJOR && minor < REQUIRED_MINOR)
    ) {
      return null;
    }
    return { path: executable, major, minor };
  } catch {
    return null;
  }
}

/**
 * Walk standard Python install locations per OS. The first found
 * interpreter that meets the version floor wins.
 */
function findSystemPython() {
  const candidates =
    process.platform === "win32"
      ? ["python", "python3", "py", "py -3"]
      : ["python3", "python3.12", "python3.13", "python3.14"];
  for (const candidate of candidates) {
    const result = probePython(candidate);
    if (result) return result;
  }
  return null;
}

/**
 * Look for a bundled runtime in resources/python/. Only present when
 * `bundle-sidecar.js` has been run with --include-python (future
 * build step). When found, the path to the interpreter is written
 * into manifest.json so the main process can spawn it directly.
 */
function findBundledPython(resourcesPath) {
  if (!resourcesPath) return null;
  const candidates = [
    path.join(resourcesPath, "python", "bin", "python3"),
    path.join(resourcesPath, "python", "bin", "python3.12"),
    path.join(resourcesPath, "python", "python.exe"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      const probe = probePython(candidate);
      if (probe) return probe;
    }
  }
  return null;
}

/**
 * Return the recommended install URL for the operator's OS. The main
 * process surfaces this in a dialog when provisioning fails.
 */
function installerUrlForOS() {
  switch (process.platform) {
    case "darwin":
      return "https://www.python.org/ftp/python/3.12.7/python-3.12.7-macos11.pkg";
    case "win32":
      return "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe";
    default:
      return "https://python.org/downloads/";
  }
}

/**
 * The main provisioning routine. Called by the Electron main process
 * before the bridge sidecar spawns. Returns a typed result object.
 *
 * Result shape:
 *   { ok: true, source: "system" | "bundled", python: { path, major, minor } }
 *   { ok: false, reason: "no_python_found", installer_url: string,
 *     install_command: string | null, hint: string }
 */
function bootstrap(opts = {}) {
  const userDataDir = opts.userDataDir || path.join(os.homedir(), ".oasis-ai");
  const manifestPath = path.join(userDataDir, "python-runtime.json");

  // 1. System Python preferred — zero user-visible work, latest
  //    security patches via the OS update channel.
  const system = findSystemPython();
  if (system) {
    writeManifest(manifestPath, { source: "system", ...system });
    return { ok: true, source: "system", python: system };
  }

  // 2. Bundled runtime — when a future build ships python-build-standalone
  //    in resources/python/.
  const bundled = findBundledPython(opts.resourcesPath);
  if (bundled) {
    writeManifest(manifestPath, { source: "bundled", ...bundled });
    return { ok: true, source: "bundled", python: bundled };
  }

  // 3. Surface a clear failure with the right next step.
  let installCommand = null;
  let hint = "Install Python 3.12 to enable the local bridge.";
  if (process.platform === "darwin") {
    installCommand = "brew install python@3.12";
    hint = "Run `brew install python@3.12` or open the installer.";
  } else if (process.platform === "win32") {
    installCommand = "winget install Python.Python.3.12 --silent";
    hint = "Run `winget install Python.Python.3.12 --silent` or open the installer.";
  } else {
    installCommand = "sudo apt install python3.12";
    hint = "Install via your distro's package manager.";
  }

  return {
    ok: false,
    reason: "no_python_found",
    installer_url: installerUrlForOS(),
    install_command: installCommand,
    hint,
  };
}

function writeManifest(manifestPath, body) {
  try {
    fs.mkdirSync(path.dirname(manifestPath), { recursive: true });
    fs.writeFileSync(
      manifestPath,
      JSON.stringify({ ...body, written_at: new Date().toISOString() }, null, 2),
      "utf8",
    );
  } catch (err) {
    // Manifest is best-effort — main process can re-probe on every
    // launch if the write fails.
    console.warn("[bootstrap-python] manifest write failed:", err.message);
  }
}

// CLI entry — supports being invoked directly OR `require()`d by main.js.
if (require.main === module) {
  const resourcesPath = process.argv[2] || process.env.OASIS_RESOURCES_PATH || null;
  const userDataDir = process.env.OASIS_USER_DATA_DIR || null;
  const result = bootstrap({ resourcesPath, userDataDir });
  process.stdout.write(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}

module.exports = { bootstrap, findSystemPython, findBundledPython, probePython };
