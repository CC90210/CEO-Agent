"use strict";

/**
 * signin-window.js — pre-pairing sign-in landing.
 *
 * When the desktop boots and the machine isn't paired yet, we show this
 * window INSTEAD of loading the dashboard. The Electron-Chromium browser
 * does not share cookies with the user's real Chrome / Safari, so OAuth
 * inside the app feels like an incognito session (no Google account
 * picker etc.). The fix is to push the user's first-touch into their
 * real browser:
 *
 *   1. Renderer button → main → shell.openExternal(https://<dashboard>/desktop-link)
 *   2. User signs in via Google / email / forgot-password in real Chrome
 *   3. Dashboard mints a pair code and fires oasis://pair?code=ABC-DEF-GHJ
 *   4. OS hands the URL to OASIS AI → deep-link.js redeems it → window closes
 *
 * Pasting the 9-char code by hand remains as a fallback path for users
 * whose default browser doesn't honor oasis:// (corporate Edge policies,
 * fresh Linux installs without xdg-mime mapping, etc.).
 */

const { BrowserWindow, ipcMain, shell } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { URL } = require("node:url");
const { redeemPairCode } = require("./deep-link");

const HTML_PATH = path.join(__dirname, "..", "resources", "signin-landing.html");
const PRELOAD_PATH = path.join(__dirname, "..", "resources", "signin-preload.js");

const CHANNEL_OPEN_SIGNIN = "oasis-signin/open-signin";
const CHANNEL_REDEEM_CODE = "oasis-signin/redeem-code";
const CHANNEL_PAIRED = "oasis-signin/paired";
const CHANNEL_ERROR = "oasis-signin/deep-link-error";
const CHANNEL_READY = "oasis-signin/ready";

let activeWindow = null;
let activeContext = null;
let readyHandlers = [];

function buildDesktopLinkUrl(commandCenterUrl, opts) {
  const base = new URL("/desktop-link", commandCenterUrl);
  if (opts?.signup) base.searchParams.set("intent", "signup");
  else if (opts?.forgot) base.searchParams.set("intent", "forgot");
  base.searchParams.set("via", "desktop");
  return base.toString();
}

function registerIpc(ctx) {
  ipcMain.removeHandler(CHANNEL_REDEEM_CODE);
  ipcMain.removeAllListeners(CHANNEL_OPEN_SIGNIN);
  ipcMain.removeAllListeners(CHANNEL_READY);

  ipcMain.on(CHANNEL_OPEN_SIGNIN, (_event, opts) => {
    if (!ctx?.commandCenterUrl) return;
    try {
      const target = buildDesktopLinkUrl(ctx.commandCenterUrl, opts || {});
      void shell.openExternal(target);
    } catch { /* ignore */ }
  });

  ipcMain.handle(CHANNEL_REDEEM_CODE, async (_event, args) => {
    const code = String((args && args.code) || "");
    const result = await redeemPairCode({ code, commandCenterUrl: ctx.commandCenterUrl });
    if (result?.ok) {
      // Fire the same "paired" signal as the deep-link path so the main
      // process can close the sign-in window + start the main window.
      ctx.onPaired(result);
    }
    return result;
  });

  ipcMain.on(CHANNEL_READY, () => {
    while (readyHandlers.length) {
      const fn = readyHandlers.shift();
      try { fn(); } catch { /* swallow */ }
    }
  });
}

function notifyPaired(payload) {
  if (!activeWindow || activeWindow.isDestroyed()) return;
  try { activeWindow.webContents.send(CHANNEL_PAIRED, payload); } catch { /* ignore */ }
}

function notifyError(payload) {
  if (!activeWindow || activeWindow.isDestroyed()) return;
  try { activeWindow.webContents.send(CHANNEL_ERROR, payload); } catch { /* ignore */ }
}

function whenReady(fn) {
  if (!activeWindow) {
    fn();
    return;
  }
  readyHandlers.push(fn);
}

function openSignInWindow({ commandCenterUrl, onPaired }) {
  if (activeWindow && !activeWindow.isDestroyed()) {
    activeWindow.focus();
    return activeWindow;
  }
  if (!fs.existsSync(HTML_PATH)) throw new Error(`sign-in HTML missing: ${HTML_PATH}`);
  if (!fs.existsSync(PRELOAD_PATH)) throw new Error(`sign-in preload missing: ${PRELOAD_PATH}`);

  activeContext = { commandCenterUrl, onPaired };
  registerIpc(activeContext);

  activeWindow = new BrowserWindow({
    width: 720,
    height: 760,
    minWidth: 600,
    minHeight: 680,
    title: "OASIS AI — Sign in",
    backgroundColor: "#05070d",
    autoHideMenuBar: true,
    resizable: true,
    show: false,
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
      preload: PRELOAD_PATH,
    },
  });

  activeWindow.once("ready-to-show", () => activeWindow.show());
  activeWindow.on("closed", () => {
    activeWindow = null;
    activeContext = null;
    readyHandlers = [];
  });
  // Lock down the sign-in landing — no nav, no popups.
  activeWindow.webContents.on("will-navigate", (event) => event.preventDefault());
  activeWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));

  activeWindow.loadFile(HTML_PATH).catch(() => { /* the close handler cleans up */ });
  return activeWindow;
}

function closeSignInWindow() {
  if (activeWindow && !activeWindow.isDestroyed()) {
    activeWindow.close();
  }
}

function isOpen() {
  return !!(activeWindow && !activeWindow.isDestroyed());
}

module.exports = {
  openSignInWindow,
  closeSignInWindow,
  notifyPaired,
  notifyError,
  whenReady,
  isOpen,
};
