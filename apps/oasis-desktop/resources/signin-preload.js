"use strict";

/**
 * signin-preload.js — sandboxed bridge between the sign-in landing
 * renderer (resources/signin-landing.html) and the main process.
 *
 * Only the channels declared here are exposed; the renderer is fully
 * sandboxed + contextIsolated and cannot reach `electron` or `node:*`.
 */

const { contextBridge, ipcRenderer } = require("electron");

const CHANNEL_OPEN_SIGNIN = "oasis-signin/open-signin";
const CHANNEL_REDEEM_CODE = "oasis-signin/redeem-code";
const CHANNEL_PAIRED = "oasis-signin/paired";
const CHANNEL_ERROR = "oasis-signin/deep-link-error";
const CHANNEL_READY = "oasis-signin/ready";

contextBridge.exposeInMainWorld("oasisDesktop", {
  openSignIn: (opts) => ipcRenderer.send(CHANNEL_OPEN_SIGNIN, opts || {}),
  redeemCode: (code) => ipcRenderer.invoke(CHANNEL_REDEEM_CODE, { code }),
  onDeepLinkPaired: (handler) => {
    ipcRenderer.on(CHANNEL_PAIRED, (_event, payload) => {
      try { handler(payload); } catch {}
    });
  },
  onDeepLinkError: (handler) => {
    ipcRenderer.on(CHANNEL_ERROR, (_event, payload) => {
      try { handler(payload); } catch {}
    });
  },
  ready: () => ipcRenderer.send(CHANNEL_READY),
});
