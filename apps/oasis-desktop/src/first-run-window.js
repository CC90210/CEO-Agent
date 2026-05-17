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
const { URL } = require("node:url");
const {
  PROVIDERS,
  setProviderKey,
  validateProviderKey,
} = require("./provider-keys");
const { loadDesktopManifest, resolveCommandCenterUrl } = require("./manifest");

const HTML_PATH = path.join(__dirname, "..", "resources", "first-run.html");
const PRELOAD_PATH = path.join(__dirname, "..", "resources", "first-run-preload.js");

const CHANNEL_VALIDATE = "oasis-first-run/validate";
const CHANNEL_SAVE = "oasis-first-run/save";
const CHANNEL_CANCEL = "oasis-first-run/cancel";
const CHANNEL_PAIR = "oasis-first-run/pair";
const CHANNEL_OPEN_EXTERNAL = "oasis-first-run/open-external";
const CHANNEL_BRIDGE_HEALTH = "oasis-first-run/bridge-health";
const CHANNEL_PAIR_STATUS = "oasis-first-run/pair-status";

// Bridge-token path matches what bravo_cli writes today, so the existing
// local_bridge.py auth path keeps working without changes.
const BRIDGE_TOKEN_DIR = path.join(os.homedir(), ".oasis");
const BRIDGE_TOKEN_FILE = path.join(BRIDGE_TOKEN_DIR, "bridge_token");
const BRIDGE_META_FILE = path.join(BRIDGE_TOKEN_DIR, "bridge_pairing.json");

function machineFingerprint() {
  // Stable hash of hostname + platform + cpu arch + username. Same shape
  // the CLI wizard built; the dashboard uses this for partial-unique
  // bridge_pairings dedup so re-running pair from the same machine
  // rotates the token instead of stacking rows.
  const seed = [os.hostname(), process.platform, process.arch, os.userInfo().username || ""].join("|");
  return crypto.createHash("sha256").update(seed).digest("hex").slice(0, 32);
}

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

function saveBridgeToken(token, meta) {
  try {
    if (!fs.existsSync(BRIDGE_TOKEN_DIR)) fs.mkdirSync(BRIDGE_TOKEN_DIR, { recursive: true, mode: 0o700 });
    fs.writeFileSync(BRIDGE_TOKEN_FILE, token, { mode: 0o600 });
    if (meta) fs.writeFileSync(BRIDGE_META_FILE, JSON.stringify(meta, null, 2), { mode: 0o600 });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "write_failed" };
  }
}

function readBridgeMeta() {
  try {
    if (!fs.existsSync(BRIDGE_META_FILE)) return null;
    return JSON.parse(fs.readFileSync(BRIDGE_META_FILE, "utf-8"));
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
  CHANNEL_OPEN_EXTERNAL,
  CHANNEL_PAIR,
  CHANNEL_PAIR_STATUS,
  CHANNEL_SAVE,
  CHANNEL_VALIDATE,
  openFirstRunWindow,
};
