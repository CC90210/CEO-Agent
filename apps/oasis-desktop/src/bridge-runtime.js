"use strict";

/**
 * bridge-runtime.js — spawns and supervises the Python sidecar.
 *
 * Resolution order for "where does the sidecar code live":
 *   1. process.env.OASIS_BRIDGE_CWD  — explicit override (debugging / CI).
 *   2. process.resourcesPath/sidecar — the bundle scripts/bundle-sidecar.js
 *      writes at build time, shipped inside the packaged app. THIS is the
 *      production path; users never need a repo clone.
 *   3. findRepoRoot(startDir)        — walk up from the app's start dir
 *      looking for bravo_cli/local_bridge.py. Dev convenience so working
 *      out of `apps/oasis-desktop/` while running `npm start` still picks
 *      up edits from the parent repo without a rebuild.
 *
 * Python resolution is delegated to ../scripts/bootstrap-python.js, which
 * version-gates on >=3.12 (the floor the bridge needs) and writes a
 * manifest into the Electron user-data dir so subsequent launches can
 * skip the probe. The bootstrap module returns either a verified
 * interpreter path or a structured failure with the OS-appropriate
 * install hint. OASIS_PYTHON env override still wins (debug escape).
 */

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const bootstrapPython = require("../scripts/bootstrap-python");

const DEFAULT_START_TIMEOUT_MS = 12_000;
const SECRET_PATTERNS = [
  [/(api[_-]?key|token|secret|password)=\S+/gi, "$1=[redacted]"],
  [/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]"],
  [/sk-[A-Za-z0-9_-]+/g, "sk-[redacted]"],
  [/x-api-key:\s*[A-Za-z0-9._~+/=-]+/gi, "x-api-key: [redacted]"],
];

function scrubLogLine(line) {
  let result = String(line);
  for (const [re, sub] of SECRET_PATTERNS) result = result.replace(re, sub);
  return result;
}

function findRepoRoot(startDir) {
  let current = startDir;
  while (current && current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, "bravo_cli", "local_bridge.py"))) {
      return current;
    }
    current = path.dirname(current);
  }
  return null;
}

function bundledSidecarRoot(app) {
  // process.resourcesPath is only meaningful inside a packaged Electron app.
  // In `electron .` dev mode it points at electron's own resources; we
  // protect against that by checking for our bundle marker.
  const candidate = process.resourcesPath
    ? path.join(process.resourcesPath, "sidecar")
    : null;
  if (!candidate) return null;
  if (!fs.existsSync(path.join(candidate, "bravo_cli", "local_bridge.py"))) return null;
  return candidate;
}

function createBridgeRuntime({ app, desktopManifest, bridgeHealthUrl, startDir, getEnvOverrides }) {
  let bridgeProcess = null;
  let bridgeStartedAt = null;

  function getBridgeLogPath() {
    return path.join(app.getPath("userData"), "oasis-desktop-bridge.log");
  }

  function getSidecarRoot() {
    if (process.env.OASIS_BRIDGE_CWD) return process.env.OASIS_BRIDGE_CWD;
    return bundledSidecarRoot(app) || findRepoRoot(startDir);
  }

  function getBundleManifest() {
    const root = getSidecarRoot();
    if (!root) return null;
    const manifestPath = path.join(root, "bundle.json");
    if (!fs.existsSync(manifestPath)) return null;
    try {
      return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    } catch {
      return null;
    }
  }

  function getResolvedPython() {
    if (process.env.OASIS_PYTHON) {
      return { ok: true, source: "env", python: { path: process.env.OASIS_PYTHON } };
    }
    return bootstrapPython.bootstrap({
      resourcesPath: getSidecarRoot(),
      userDataDir: app.getPath("userData"),
    });
  }

  function writeBridgeLog(line) {
    fs.appendFile(getBridgeLogPath(), `[${new Date().toISOString()}] ${scrubLogLine(line)}\n`, () => {});
  }

  function isBridgeHealthy() {
    return new Promise((resolve) => {
      const request = http.get(bridgeHealthUrl, { timeout: 1500 }, (response) => {
        response.resume();
        resolve(response.statusCode >= 200 && response.statusCode < 500);
      });
      request.on("timeout", () => {
        request.destroy();
        resolve(false);
      });
      request.on("error", () => resolve(false));
    });
  }

  async function waitForBridge(deadlineMs = DEFAULT_START_TIMEOUT_MS) {
    const started = Date.now();
    while (Date.now() - started < deadlineMs) {
      if (await isBridgeHealthy()) return true;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    return false;
  }

  async function startIfAvailable() {
    if (process.env.OASIS_DESKTOP_START_BRIDGE === "false") return false;
    if (desktopManifest.bridge.startByDefault === false) return false;
    if (await isBridgeHealthy()) return true;

    const cwd = getSidecarRoot();
    if (!cwd) {
      writeBridgeLog("Bridge sidecar root not found (no bundled resources, no repo clone). Desktop will use cloud mode only.");
      return false;
    }

    const resolved = getResolvedPython();
    if (!resolved.ok) {
      writeBridgeLog(
        `No Python >=3.12 found. ${resolved.hint || ""} ` +
          `install_command="${resolved.install_command || ""}" ` +
          `installer_url="${resolved.installer_url || ""}". ` +
          `Desktop will use cloud mode only until a runtime is provisioned.`,
      );
      return false;
    }
    const python = resolved.python.path;
    writeBridgeLog(`Spawning bridge: python=${python} source=${resolved.source} cwd=${cwd}`);

    // Pull caller-supplied env overrides (typically the decrypted API
    // key from safeStorage). Never log values from this map.
    const overrides = typeof getEnvOverrides === "function" ? (getEnvOverrides() || {}) : {};
    const env = {
      ...process.env,
      ...overrides,
      OASIS_DESKTOP: "1",
      PYTHONUNBUFFERED: "1",
    };

    bridgeProcess = spawn(python, desktopManifest.bridge.serveArgs, {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    bridgeStartedAt = Date.now();

    bridgeProcess.stdout.on("data", (chunk) => writeBridgeLog(chunk));
    bridgeProcess.stderr.on("data", (chunk) => writeBridgeLog(chunk));
    bridgeProcess.on("exit", (code, signal) => {
      const ranMs = bridgeStartedAt ? Date.now() - bridgeStartedAt : 0;
      writeBridgeLog(`Bridge exited code=${code ?? "null"} signal=${signal ?? "null"} ran=${ranMs}ms`);
      bridgeProcess = null;
      bridgeStartedAt = null;
    });
    bridgeProcess.on("error", (err) => {
      writeBridgeLog(`Bridge spawn error: ${err && err.message ? err.message : String(err)}`);
    });

    return waitForBridge();
  }

  function getProcessState() {
    return bridgeProcess
      ? { pid: bridgeProcess.pid, killed: bridgeProcess.killed, startedAt: bridgeStartedAt }
      : null;
  }

  function stop() {
    if (bridgeProcess && !bridgeProcess.killed) {
      bridgeProcess.kill();
    }
  }

  // Legacy alias for diagnostics consumers that pre-date the rename.
  function getBridgeCwd() {
    return getSidecarRoot();
  }

  return {
    getBridgeCwd,
    getBridgeLogPath,
    getBundleManifest,
    getProcessState,
    getResolvedPython,
    getSidecarRoot,
    isBridgeHealthy,
    startIfAvailable,
    stop,
  };
}

module.exports = {
  bundledSidecarRoot,
  createBridgeRuntime,
  findRepoRoot,
  scrubLogLine,
};
