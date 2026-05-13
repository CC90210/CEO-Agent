"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const DEFAULT_START_TIMEOUT_MS = 10_000;

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

function scrubLogLine(line) {
  return String(line)
    .replace(/(api[_-]?key|token|secret|password)=\S+/gi, "$1=[redacted]")
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
    .replace(/sk-[A-Za-z0-9_-]+/g, "sk-[redacted]");
}

function createBridgeRuntime({ app, desktopManifest, bridgeHealthUrl, startDir }) {
  let bridgeProcess = null;

  function getBridgeLogPath() {
    return path.join(app.getPath("userData"), "oasis-desktop-bridge.log");
  }

  function getBridgeCwd() {
    if (process.env.OASIS_BRIDGE_CWD) {
      return process.env.OASIS_BRIDGE_CWD;
    }
    return findRepoRoot(startDir);
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

    const cwd = getBridgeCwd();
    if (!cwd) {
      writeBridgeLog("Bridge repo root not found. Desktop shell will use cloud/API-key mode only.");
      return false;
    }

    const python = process.env.OASIS_PYTHON || (process.platform === "win32" ? "python" : "python3");
    bridgeProcess = spawn(python, desktopManifest.bridge.serveArgs, {
      cwd,
      env: {
        ...process.env,
        OASIS_DESKTOP: "1",
        PYTHONUNBUFFERED: "1"
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });

    bridgeProcess.stdout.on("data", (chunk) => writeBridgeLog(chunk));
    bridgeProcess.stderr.on("data", (chunk) => writeBridgeLog(chunk));
    bridgeProcess.on("exit", (code, signal) => {
      writeBridgeLog(`Bridge exited code=${code ?? "null"} signal=${signal ?? "null"}`);
      bridgeProcess = null;
    });

    return waitForBridge();
  }

  function getProcessState() {
    return bridgeProcess
      ? { pid: bridgeProcess.pid, killed: bridgeProcess.killed }
      : null;
  }

  function stop() {
    if (bridgeProcess && !bridgeProcess.killed) {
      bridgeProcess.kill();
    }
  }

  return {
    getBridgeCwd,
    getBridgeLogPath,
    getProcessState,
    isBridgeHealthy,
    startIfAvailable,
    stop
  };
}

module.exports = {
  createBridgeRuntime,
  findRepoRoot,
  scrubLogLine
};
