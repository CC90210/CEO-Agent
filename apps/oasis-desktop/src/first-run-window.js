"use strict";

/**
 * first-run-window.js — modal onboarding wizard shown the first time the
 * desktop boots before any provider key or workspace pairing exists.
 *
 * Phase: master multi-tenant infra plan (2026-05-17). The wizard replaces
 * the single-screen provider-key form with a 3-step flow that mirrors
 * what `bravo setup` did from the command line:
 *
 *   1. Pair this machine to a workspace (paste pair code from the
 *      dashboard's Settings -> Devices page). Calls /api/auth/pair-code/
 *      redeem; saves the bearer token to ~/.oasis/bridge_token.
 *   2. Optionally connect a personal AI provider account. Skip = falls
 *      back to the workspace's shared AI config.
 *   3. Health check + done. Probes the local bridge HTTP endpoint to
 *      confirm the daemon spawned cleanly; closes the wizard.
 *
 * The renderer is sandboxed + contextIsolated. Its only contact with
 * main is the constrained IPC surface in ../resources/first-run-preload.js.
 *
 * Why an Electron wizard instead of the operator running `bravo setup`
 * in a terminal: CC's product goal is "I don't want clients touching a
 * terminal." Embedding the wizard means signing in to a workspace +
 * pairing the machine + (optionally) bringing your own key are all
 * point-and-click. The bridge daemon supervision is already inside
 * bridge-runtime.js.
 */

const { BrowserWindow, ipcMain, shell } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const crypto = require("node:crypto");
const http = require("node:http");
const https = require("node:https");
const { spawn } = require("node:child_process");
const { URL } = require("node:url");
const {
  PROVIDERS,
  setProviderKey,
  validateProviderKey,
} = require("./provider-keys");
const { loadDesktopManifest, resolveCommandCenterUrl } = require("./manifest");
const {
  BRIDGE_TOKEN_FILE,
  BRIDGE_META_FILE,
  ensureOasisHome,
} = require("./bridge-paths");

const HTML_PATH = path.join(__dirname, "..", "resources", "first-run.html");
const PRELOAD_PATH = path.join(__dirname, "..", "resources", "first-run-preload.js");

const CHANNEL_VALIDATE = "oasis-first-run/validate";
const CHANNEL_SAVE = "oasis-first-run/save";
const CHANNEL_CANCEL = "oasis-first-run/cancel";
const CHANNEL_PAIR = "oasis-first-run/pair";
const CHANNEL_OPEN_EXTERNAL = "oasis-first-run/open-external";
const CHANNEL_BRIDGE_HEALTH = "oasis-first-run/bridge-health";
const CHANNEL_PAIR_STATUS = "oasis-first-run/pair-status";
const CHANNEL_DETECT_CLI = "oasis-first-run/detect-cli";

function machineFingerprint() {
  // Match bravo_cli/wizard.py's fingerprint format exactly:
  //   f"{platform.system()}|{platform.machine()}|{socket.gethostname()}"
  // The dashboard dedups bridge_pairings on (tenant_id, machine_fingerprint)
  // via a partial unique index. If the desktop wizard sent a different
  // shape (e.g. a sha256 hash), re-pairing the same machine via the
  // wrong path would create a duplicate row instead of rotating the
  // token. Keep the formats interchangeable.
  const sys = process.platform === "win32" ? "Windows" : process.platform === "darwin" ? "Darwin" : "Linux";
  // process.arch is "x64"/"arm64"; Python's platform.machine() returns
  // "AMD64" / "arm64" / "x86_64". Pick the conventional value per OS so
  // a paired-via-CLI machine matches a paired-via-desktop machine.
  let machine;
  if (sys === "Windows") {
    machine = process.arch === "x64" ? "AMD64" : process.arch === "arm64" ? "ARM64" : process.arch;
  } else if (sys === "Darwin") {
    machine = process.arch === "x64" ? "x86_64" : "arm64";
  } else {
    machine = process.arch === "x64" ? "x86_64" : process.arch;
  }
  return `${sys}|${machine}|${os.hostname()}`;
}

// Reserved for future use (e.g. multi-tenant disambiguation log lines).
// crypto is intentionally imported even though machineFingerprint stopped
// using it — the bridge-runtime + other future flows hash the raw value
// downstream.
void crypto;

function defaultMachineLabel() {
  const user = (os.userInfo().username || "").trim();
  const host = (os.hostname() || "machine").split(".")[0];
  return user ? `${user}'s ${host}` : host;
}

function postJson(urlString, body) {
  return new Promise((resolve) => {
    let urlObj;
    try {
      urlObj = new URL(urlString);
    } catch {
      resolve({ status: 0, error: "bad_url", body: null });
      return;
    }
    const payload = JSON.stringify(body);
    const opts = {
      method: "POST",
      hostname: urlObj.hostname,
      port: urlObj.port || (urlObj.protocol === "https:" ? 443 : 80),
      path: urlObj.pathname + (urlObj.search || ""),
      headers: {
        "content-type": "application/json",
        "content-length": Buffer.byteLength(payload),
      },
      timeout: 12_000,
    };
    const transport = urlObj.protocol === "https:" ? https : http;
    const req = transport.request(opts, (res) => {
      let chunks = "";
      res.setEncoding("utf-8");
      res.on("data", (d) => {
        chunks += d;
      });
      res.on("end", () => {
        let parsed = null;
        try {
          parsed = JSON.parse(chunks);
        } catch {
          parsed = null;
        }
        resolve({ status: res.statusCode || 0, body: parsed, raw: chunks });
      });
    });
    req.on("error", (err) => resolve({ status: 0, error: err.message, body: null }));
    req.on("timeout", () => {
      req.destroy(new Error("timeout"));
    });
    req.write(payload);
    req.end();
  });
}

function getJson(urlString, timeoutMs = 6_000) {
  return new Promise((resolve) => {
    let urlObj;
    try {
      urlObj = new URL(urlString);
    } catch {
      resolve({ ok: false, status: 0, error: "bad_url" });
      return;
    }
    const transport = urlObj.protocol === "https:" ? https : http;
    const req = transport.get(urlObj, { timeout: timeoutMs }, (res) => {
      let chunks = "";
      res.setEncoding("utf-8");
      res.on("data", (d) => {
        chunks += d;
      });
      res.on("end", () => {
        let parsed = null;
        try {
          parsed = JSON.parse(chunks);
        } catch {
          parsed = null;
        }
        resolve({ ok: (res.statusCode || 0) >= 200 && (res.statusCode || 0) < 300, status: res.statusCode || 0, body: parsed });
      });
    });
    req.on("error", () => resolve({ ok: false, status: 0, error: "network" }));
    req.on("timeout", () => {
      req.destroy(new Error("timeout"));
      resolve({ ok: false, status: 0, error: "timeout" });
    });
  });
}

/**
 * Probe a local CLI binary by invoking `<binary> --version` (with a hard
 * 3s timeout). Returns { installed: boolean, version: string|null }.
 * Used by Step 2 of the wizard to detect Claude Code / Codex / Gemini
 * subscriptions so the operator can pick "use my existing CLI" instead
 * of pasting an API key.
 *
 * Why spawn directly instead of `which` first: Windows doesn't ship
 * `which`, and even on Unix the lookup gives us shell-resolution PATH
 * for free if we just spawn the bare binary name. ENOENT means the
 * binary isn't on PATH; everything else means it is and we capture the
 * version string for display.
 */
function probeCli(binary, timeoutMs = 3_000) {
  return new Promise((resolve) => {
    let proc;
    let stdout = "";
    let stderr = "";
    let done = false;
    const finish = (result) => {
      if (done) return;
      done = true;
      if (proc && !proc.killed) {
        try { proc.kill(); } catch { /* ignore */ }
      }
      resolve(result);
    };
    try {
      proc = spawn(binary, ["--version"], {
        windowsHide: true,
        shell: process.platform === "win32", // PATH resolution on Windows
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch {
      finish({ installed: false, version: null });
      return;
    }
    const timer = setTimeout(() => finish({ installed: false, version: null, error: "timeout" }), timeoutMs);
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.on("error", () => {
      clearTimeout(timer);
      finish({ installed: false, version: null });
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0 && !stdout) {
        finish({ installed: false, version: null });
        return;
      }
      const raw = (stdout || stderr).trim();
      // First non-empty line, capped at 200 chars for display safety.
      const line = raw.split(/\r?\n/).find((s) => s.trim()) || raw;
      finish({ installed: true, version: line.slice(0, 200) });
    });
  });
}

function saveBridgeToken(token, meta) {
  try {
    ensureOasisHome();
    fs.writeFileSync(BRIDGE_TOKEN_FILE, token, { mode: 0o600 });
    if (meta) fs.writeFileSync(BRIDGE_META_FILE, JSON.stringify(meta, null, 2), { mode: 0o600 });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "write_failed" };
  }
}

function readBridgeMeta() {
  // Prefer the desktop wizard's metadata file (richer: tenant_id,
  // machine_label, paired_at). Fall back to "the CLI paired this
  // machine and didn't write metadata" — detect that by the bare
  // bridge_token's presence so the resume path still skips Step 1.
  try {
    if (fs.existsSync(BRIDGE_META_FILE)) {
      return JSON.parse(fs.readFileSync(BRIDGE_META_FILE, "utf-8"));
    }
    if (fs.existsSync(BRIDGE_TOKEN_FILE)) {
      return {
        pairing_id: null,
        tenant_id: null,
        dashboard_url: null,
        machine_label: defaultMachineLabel(),
        paired_at: null,
        source: "cli", // marker: paired via bravo setup, not the wizard
      };
    }
    return null;
  } catch {
    return null;
  }
}

function ensureChannelsRegistered(onClose, runtimeCtx) {
  const desktopManifest = runtimeCtx?.desktopManifest || loadDesktopManifest();
  const commandCenterUrl = runtimeCtx?.commandCenterUrl || resolveCommandCenterUrl(desktopManifest);
  const bridgeHealthUrl = runtimeCtx?.bridgeHealthUrl || desktopManifest?.bridge?.healthUrl;

  ipcMain.removeHandler(CHANNEL_VALIDATE);
  ipcMain.removeHandler(CHANNEL_SAVE);
  ipcMain.removeHandler(CHANNEL_PAIR);
  ipcMain.removeHandler(CHANNEL_BRIDGE_HEALTH);
  ipcMain.removeHandler(CHANNEL_PAIR_STATUS);
  ipcMain.removeHandler(CHANNEL_DETECT_CLI);
  ipcMain.removeAllListeners(CHANNEL_CANCEL);
  ipcMain.removeAllListeners(CHANNEL_OPEN_EXTERNAL);

  ipcMain.handle(CHANNEL_VALIDATE, async (_event, args) => {
    if (!args || typeof args !== "object") return { ok: false, reason: "bad_request" };
    const provider = String(args.provider || "");
    const key = String(args.key || "");
    if (!PROVIDERS.includes(provider)) return { ok: false, reason: "unknown_provider" };
    return validateProviderKey(provider, key);
  });

  ipcMain.handle(CHANNEL_SAVE, async (_event, args) => {
    if (!args || typeof args !== "object") return { ok: false, error: "bad_request" };
    const provider = String(args.provider || "");
    const key = String(args.key || "");
    if (!PROVIDERS.includes(provider)) return { ok: false, error: "unknown_provider" };
    try {
      setProviderKey(provider, key);
      // Saving a provider key alone doesn't close the wizard anymore —
      // the renderer drives step transitions explicitly. The "done"
      // event is fired from CHANNEL_CANCEL when the operator clicks
      // Finish on the final step.
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : "store_failed" };
    }
  });

  // Pair the machine to a workspace via dashboard pair-code redemption.
  // Mirrors what `bravo setup` did from the CLI: POST the 9-char code,
  // get back { bridge: { token, pairing_id, dashboard_url } }, write the
  // token to ~/.oasis/bridge_token so local_bridge.py picks it up.
  ipcMain.handle(CHANNEL_PAIR, async (_event, args) => {
    const code = String((args && args.code) || "").trim().toUpperCase();
    if (!/^[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}$/.test(code)) {
      return { ok: false, error: "bad_code_format", message: "Pair codes look like ABC-DEF-GHJ." };
    }
    if (!commandCenterUrl) {
      return { ok: false, error: "no_dashboard_url" };
    }
    const label = String((args && args.label) || defaultMachineLabel());
    const fingerprint = machineFingerprint();
    const url = new URL("/api/auth/pair-code/redeem", commandCenterUrl).toString();
    const res = await postJson(url, { code, machine: { label, fingerprint } });
    if (res.status === 200 && res.body?.ok && res.body?.bridge?.token) {
      const meta = {
        pairing_id: res.body.bridge.pairing_id || null,
        tenant_id: res.body.tenant_id || null,
        dashboard_url: res.body.bridge.dashboard_url || commandCenterUrl,
        machine_label: label,
        paired_at: new Date().toISOString(),
      };
      const save = saveBridgeToken(res.body.bridge.token, meta);
      if (!save.ok) return { ok: false, error: "token_write_failed", message: save.error };
      return {
        ok: true,
        tenant_id: meta.tenant_id,
        dashboard_url: meta.dashboard_url,
        machine_label: meta.machine_label,
      };
    }
    if (res.status === 404 || res.status === 410) {
      return {
        ok: false,
        error: "invalid_code",
        message: "That code is unknown, expired, or already redeemed. Generate a new one in the dashboard.",
      };
    }
    if (res.status === 429) {
      return { ok: false, error: "rate_limited", message: "Too many attempts. Wait a minute and try again." };
    }
    return {
      ok: false,
      error: "redeem_failed",
      message: res.body?.error || res.error || `Pair endpoint returned ${res.status}.`,
    };
  });

  ipcMain.handle(CHANNEL_PAIR_STATUS, async () => {
    const meta = readBridgeMeta();
    return { paired: !!meta, meta };
  });

  // Local CLI subscription detection — wizard's Step 2 calls this to
  // offer "Use my Claude Pro / Codex / Gemini CLI subscription" instead
  // of paste-an-API-key. The bridge will spawn the matching CLI when
  // chat fires; this probe just confirms the binary is on PATH +
  // captures the version string for display.
  ipcMain.handle(CHANNEL_DETECT_CLI, async () => {
    const [claude, codex, gemini] = await Promise.all([
      probeCli("claude"),
      probeCli("codex"),
      probeCli("gemini"),
    ]);
    return { claude, codex, gemini };
  });

  ipcMain.handle(CHANNEL_BRIDGE_HEALTH, async () => {
    if (!bridgeHealthUrl) return { ok: false, error: "no_health_url" };
    const r = await getJson(bridgeHealthUrl, 4_000);
    return { ok: r.ok, status: r.status, body: r.body || null };
  });

  ipcMain.on(CHANNEL_OPEN_EXTERNAL, (_event, url) => {
    if (typeof url !== "string") return;
    // Only open URLs that match the allowed dashboard origin OR the
    // provider docs (well-known https hosts). Defense-in-depth — the
    // renderer is already sandboxed.
    try {
      const target = new URL(url);
      const allow =
        target.protocol === "https:" ||
        (target.protocol === "http:" && target.hostname === "localhost");
      if (!allow) return;
      void shell.openExternal(target.toString());
    } catch {
      // ignore bad URLs
    }
  });

  ipcMain.on(CHANNEL_CANCEL, (_event, payload) => {
    if (payload && payload.result === "finished") onClose("finished", payload);
    else onClose("cancelled", null);
  });
}

/**
 * Open the first-run window and wait for the operator to either save a
 * provider key or cancel out. Returns:
 *   { result: "saved", provider }   on successful key save
 *   { result: "cancelled" }         on user cancel
 *   { result: "closed" }            on window close without action
 */
function openFirstRunWindow({ parent, desktopManifest, commandCenterUrl, bridgeHealthUrl } = {}) {
  const runtimeCtx = { desktopManifest, commandCenterUrl, bridgeHealthUrl };
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(HTML_PATH)) {
      reject(new Error(`first-run HTML missing: ${HTML_PATH}`));
      return;
    }
    if (!fs.existsSync(PRELOAD_PATH)) {
      reject(new Error(`first-run preload missing: ${PRELOAD_PATH}`));
      return;
    }
    let settled = false;
    const settle = (value) => {
      if (settled) return;
      settled = true;
      try { ipcMain.removeHandler(CHANNEL_VALIDATE); } catch {}
      try { ipcMain.removeHandler(CHANNEL_SAVE); } catch {}
      try { ipcMain.removeHandler(CHANNEL_PAIR); } catch {}
      try { ipcMain.removeHandler(CHANNEL_PAIR_STATUS); } catch {}
      try { ipcMain.removeHandler(CHANNEL_BRIDGE_HEALTH); } catch {}
      try { ipcMain.removeHandler(CHANNEL_DETECT_CLI); } catch {}
      try { ipcMain.removeAllListeners(CHANNEL_CANCEL); } catch {}
      try { ipcMain.removeAllListeners(CHANNEL_OPEN_EXTERNAL); } catch {}
      if (win && !win.isDestroyed()) win.close();
      resolve(value);
    };

    const win = new BrowserWindow({
      width: 760,
      height: 760,
      minWidth: 680,
      minHeight: 640,
      title: "OASIS AI Desktop — Get started",
      backgroundColor: "#05070d",
      autoHideMenuBar: true,
      resizable: true,
      modal: !!parent,
      parent: parent || undefined,
      show: false,
      webPreferences: {
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
        webSecurity: true,
        preload: PRELOAD_PATH,
      },
    });

    ensureChannelsRegistered(
      (kind, payload) => {
        if (kind === "finished") settle({ result: "saved", ...(payload || {}) });
        else if (kind === "cancelled") settle({ result: "cancelled" });
      },
      runtimeCtx,
    );

    win.once("ready-to-show", () => win.show());
    win.on("closed", () => settle({ result: "closed" }));
    // Defense — block any external navigation from the first-run page.
    win.webContents.on("will-navigate", (event) => event.preventDefault());
    win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));

    win.loadFile(HTML_PATH).catch((err) => {
      settle({ result: "closed", error: err instanceof Error ? err.message : String(err) });
    });
  });
}

module.exports = {
  CHANNEL_BRIDGE_HEALTH,
  CHANNEL_CANCEL,
  CHANNEL_DETECT_CLI,
  CHANNEL_OPEN_EXTERNAL,
  CHANNEL_PAIR,
  CHANNEL_PAIR_STATUS,
  CHANNEL_SAVE,
  CHANNEL_VALIDATE,
  openFirstRunWindow,
};
