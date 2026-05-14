"use strict";

/**
 * first-run-window.js — opens a modal Electron window the first time the
 * desktop boots without any provider key. Renders a local HTML form
 * (no React, no network for assets) with provider tiles + key input +
 * live validation against the provider's REST API.
 *
 * The window communicates with the main process via a preload script
 * (../resources/first-run-preload.js) that exposes a constrained IPC
 * surface — no `nodeIntegration`, no `enableRemoteModule`. The renderer
 * can ONLY call:
 *
 *   window.oasisFirstRun.validate(provider, key)   → { ok, reason? }
 *   window.oasisFirstRun.save(provider, key)       → { ok, error? }
 *   window.oasisFirstRun.cancel()                  → closes the window
 *
 * Save success closes the window and resolves the caller's promise so
 * main.js can continue boot (spawn bridge with the new key, load
 * Command Center).
 */

const { BrowserWindow, ipcMain } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const {
  PROVIDERS,
  setProviderKey,
  validateProviderKey,
} = require("./provider-keys");

const HTML_PATH = path.join(__dirname, "..", "resources", "first-run.html");
const PRELOAD_PATH = path.join(__dirname, "..", "resources", "first-run-preload.js");

const CHANNEL_VALIDATE = "oasis-first-run/validate";
const CHANNEL_SAVE = "oasis-first-run/save";
const CHANNEL_CANCEL = "oasis-first-run/cancel";

function ensureChannelsRegistered(onClose) {
  // Use ipcMain.handle (request-response) so the renderer awaits results.
  ipcMain.removeHandler(CHANNEL_VALIDATE);
  ipcMain.removeHandler(CHANNEL_SAVE);
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
      onClose("saved", { provider });
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : "store_failed" };
    }
  });
  ipcMain.removeAllListeners(CHANNEL_CANCEL);
  ipcMain.on(CHANNEL_CANCEL, () => onClose("cancelled", null));
}

/**
 * Open the first-run window and wait for the operator to either save a
 * provider key or cancel out. Returns:
 *   { result: "saved", provider }   on successful key save
 *   { result: "cancelled" }         on user cancel
 *   { result: "closed" }            on window close without action
 */
function openFirstRunWindow({ parent } = {}) {
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
      try { ipcMain.removeAllListeners(CHANNEL_CANCEL); } catch {}
      if (win && !win.isDestroyed()) win.close();
      resolve(value);
    };

    const win = new BrowserWindow({
      width: 720,
      height: 720,
      minWidth: 640,
      minHeight: 620,
      title: "OASIS AI — Connect a provider",
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

    ensureChannelsRegistered((kind, payload) => {
      if (kind === "saved") settle({ result: "saved", provider: payload?.provider });
      else if (kind === "cancelled") settle({ result: "cancelled" });
    });

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
  CHANNEL_CANCEL,
  CHANNEL_SAVE,
  CHANNEL_VALIDATE,
  openFirstRunWindow,
};
