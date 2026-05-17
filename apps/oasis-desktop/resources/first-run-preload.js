"use strict";

/**
 * Preload for the first-run wizard. The renderer is sandboxed +
 * contextIsolated; this preload is its only contact with the main
 * process. Every method below maps to a single IPC channel exposed
 * by src/first-run-window.js — no node APIs, no FS, no remote, no shell.
 *
 * The wizard is 3 steps:
 *   1. Pair the machine to a workspace        → pair(code)
 *   2. Optional: connect a personal AI account → validate(...) + save(...)
 *   3. Health check + finish                   → bridgeHealth() then finish()
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("oasisFirstRun", {
  // Workspace pairing (Step 1).
  pair: (code, label) =>
    ipcRenderer.invoke("oasis-first-run/pair", { code, label }),
  pairStatus: () => ipcRenderer.invoke("oasis-first-run/pair-status"),

  // Provider key (Step 2 — optional).
  validate: (provider, key) =>
    ipcRenderer.invoke("oasis-first-run/validate", { provider, key }),
  save: (provider, key) =>
    ipcRenderer.invoke("oasis-first-run/save", { provider, key }),

  // Local CLI detection (Step 2 — offer "use my subscription" before key paste).
  detectCli: () => ipcRenderer.invoke("oasis-first-run/detect-cli"),

  // Health check (Step 3).
  bridgeHealth: () => ipcRenderer.invoke("oasis-first-run/bridge-health"),

  // Open external links (dashboard pair-code page, provider docs).
  openExternal: (url) => ipcRenderer.send("oasis-first-run/open-external", url),

  // Finish / cancel the wizard.
  finish: (payload) =>
    ipcRenderer.send("oasis-first-run/cancel", { result: "finished", ...(payload || {}) }),
  cancel: () => ipcRenderer.send("oasis-first-run/cancel"),
});
