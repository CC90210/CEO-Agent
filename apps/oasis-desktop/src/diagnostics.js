"use strict";

const { app, BrowserWindow } = require("electron");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { getSecureStoreStatus } = require("./secure-store");

const MAX_LOG_LINES = 200;

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function readPackageJson() {
  return readJson(path.resolve(__dirname, "..", "package.json"));
}

function scrubLogLine(line) {
  return String(line)
    .replace(/(api[_-]?key|token|secret|password)=\S+/gi, "$1=[redacted]")
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
    .replace(/sk-[A-Za-z0-9_-]+/g, "sk-[redacted]");
}

function tailFile(filePath, maxLines = MAX_LOG_LINES) {
  if (!fs.existsSync(filePath)) return [];
  return fs
    .readFileSync(filePath, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(-maxLines)
    .map(scrubLogLine);
}

function commandVersion(command, args) {
  const candidates = process.platform === "win32"
    ? [command, `${command}.exe`, `${command}.cmd`, `${command}.bat`]
    : [command];

  for (const executable of candidates) {
    const result = spawnSync(executable, args, {
      encoding: "utf8",
      windowsHide: true
    });
    if (result.error || result.status !== 0) continue;
    return (result.stdout || result.stderr).trim().split(/\r?\n/)[0] || "ok";
  }
  return null;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function buildDiagnostics(context) {
  const packageJson = readPackageJson();
  const bridgeHealthy = await context.isBridgeHealthy();
  const bridgeCwd = context.getBridgeCwd();
  const bridgeProcessState = context.getBridgeProcessState();
  const bridgeLogPath = context.getBridgeLogPath();

  return {
    generatedAt: new Date().toISOString(),
    product: {
      name: context.desktopManifest.product.name,
      appId: context.desktopManifest.product.appId,
      channel: context.desktopManifest.product.channel,
      version: packageJson.version
    },
    platform: {
      os: `${os.type()} ${os.release()}`,
      arch: os.arch(),
      electron: process.versions.electron,
      chrome: process.versions.chrome,
      node: process.versions.node
    },
    commandCenter: {
      url: context.commandCenterUrl.toString(),
      allowedOrigins: context.allowedOrigins
    },
    bridge: {
      healthUrl: context.bridgeHealthUrl.toString(),
      healthy: bridgeHealthy,
      repoRoot: bridgeCwd,
      repoRootFound: Boolean(bridgeCwd),
      process: bridgeProcessState,
      logPath: bridgeLogPath,
      logExists: fs.existsSync(bridgeLogPath)
    },
    tools: {
      python: commandVersion(process.platform === "win32" ? "python" : "python3", ["--version"]),
      npm: process.env.npm_config_user_agent
        ? process.env.npm_config_user_agent.split(" ")[0].replace("npm/", "")
        : commandVersion("npm", ["-v"])
    },
    secureStore: getSecureStoreStatus(),
    security: context.desktopManifest.security,
    releaseGates: context.desktopManifest.releaseGates
  };
}

function diagnosticsHtml(report) {
  const bridgeStatus = report.bridge.healthy ? "Online" : "Offline";
  const bridgeClass = report.bridge.healthy ? "ok" : "warn";
  const nextAction = report.bridge.healthy
    ? "This desktop should be available in the Command Center access selector."
    : report.bridge.repoRootFound
      ? "Bridge repo was found but did not answer health checks. Open the bridge log from the menu."
      : "Bridge repo was not found. Cloud workspace can still work; bundled runtime is the next production step.";

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OASIS Desktop Diagnostics</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #05070d;
      --panel: #0d131f;
      --line: #1b2a3f;
      --text: #edf6ff;
      --muted: #9fb1c7;
      --accent: #12d8ff;
      --ok: #45e58b;
      --warn: #ffca65;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 10% 0%, rgba(18,216,255,.16), transparent 28rem),
        linear-gradient(145deg, #05070d, #08101b 55%, #04060b);
      color: var(--text);
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { max-width: 980px; margin: 0 auto; padding: 40px 28px; }
    h1 { margin: 0; font-size: 30px; letter-spacing: -.03em; }
    h2 { margin: 28px 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: .18em; color: var(--accent); }
    p { color: var(--muted); }
    .hero { border: 1px solid rgba(18,216,255,.28); background: rgba(13,19,31,.82); border-radius: 22px; padding: 24px; box-shadow: 0 24px 80px rgba(0,0,0,.35); }
    .badge { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--warn); box-shadow: 0 0 14px currentColor; }
    .ok .dot { background: var(--ok); }
    .warn .dot { background: var(--warn); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 18px; }
    .card { border: 1px solid var(--line); border-radius: 16px; background: rgba(8,13,22,.78); padding: 14px; }
    .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .14em; }
    .value { margin-top: 4px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
    ul { margin: 8px 0 0; padding-left: 18px; color: var(--muted); }
    code { color: var(--accent); }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="badge ${bridgeClass}"><span class="dot"></span> Desktop bridge: ${escapeHtml(bridgeStatus)}</div>
      <h1>OASIS Desktop Diagnostics</h1>
      <p>${escapeHtml(nextAction)}</p>
      <div class="grid">
        <div class="card"><div class="label">Product</div><div class="value">${escapeHtml(report.product.name)} ${escapeHtml(report.product.version)} (${escapeHtml(report.product.channel)})</div></div>
        <div class="card"><div class="label">Command Center</div><div class="value">${escapeHtml(report.commandCenter.url)}</div></div>
        <div class="card"><div class="label">Bridge Repo</div><div class="value">${escapeHtml(report.bridge.repoRoot || "not found")}</div></div>
        <div class="card"><div class="label">Bridge Process</div><div class="value">${escapeHtml(report.bridge.process ? `pid ${report.bridge.process.pid}` : "not started by desktop")}</div></div>
        <div class="card"><div class="label">Python</div><div class="value">${escapeHtml(report.tools.python || "missing")}</div></div>
        <div class="card"><div class="label">Platform</div><div class="value">${escapeHtml(report.platform.os)} / ${escapeHtml(report.platform.arch)}</div></div>
        <div class="card"><div class="label">Secure Store</div><div class="value">${escapeHtml(report.secureStore.encryptionAvailable ? "encryption available" : "encryption unavailable")}</div></div>
      </div>
      <h2>Security Boundaries</h2>
      <ul>
        <li>Node integration: <code>${escapeHtml(report.security.nodeIntegration)}</code></li>
        <li>Context isolation: <code>${escapeHtml(report.security.contextIsolation)}</code></li>
        <li>Sandbox: <code>${escapeHtml(report.security.sandbox)}</code></li>
        <li>Allowed origins: <code>${escapeHtml(report.commandCenter.allowedOrigins.join(", "))}</code></li>
      </ul>
      <h2>Release Gates</h2>
      <ul>${report.releaseGates.map((gate) => `<li>${escapeHtml(gate)}</li>`).join("")}</ul>
      <h2>Support Paths</h2>
      <ul>
        <li>Bridge log: <code>${escapeHtml(report.bridge.logPath)}</code></li>
        <li>Secure store: <code>${escapeHtml(report.secureStore.path)}</code></li>
        <li>Generated: <code>${escapeHtml(report.generatedAt)}</code></li>
      </ul>
    </section>
  </main>
</body>
</html>`;
}

async function openDiagnosticsWindow(context) {
  const report = await buildDiagnostics(context);
  const win = new BrowserWindow({
    width: 980,
    height: 820,
    title: "OASIS Desktop Diagnostics",
    backgroundColor: "#05070d",
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    }
  });
  await win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(diagnosticsHtml(report))}`);
}

async function createSupportBundle(context) {
  const report = await buildDiagnostics(context);
  const supportDir = path.join(app.getPath("userData"), "support-bundles");
  fs.mkdirSync(supportDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const bundlePath = path.join(supportDir, `oasis-desktop-support-${stamp}.json`);
  const bundle = {
    report,
    bridgeLogTail: tailFile(context.getBridgeLogPath())
  };
  fs.writeFileSync(bundlePath, `${JSON.stringify(bundle, null, 2)}\n`, "utf8");
  return bundlePath;
}

module.exports = {
  buildDiagnostics,
  createSupportBundle,
  openDiagnosticsWindow
};
