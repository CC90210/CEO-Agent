"use strict";

/**
 * Preload for the first-run window. The renderer is sandboxed +
 * contextIsolated — its only contact with the main process is the small
 * surface exposed below. No node APIs, no shell APIs, no FS, no remote.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("oasisFirstRun", {
  validate: (provider, key) =>
    ipcRenderer.invoke("oasis-first-run/validate", { provider, key }),
  save: (provider, key) =>
    ipcRenderer.invoke("oasis-first-run/save", { provider, key }),
  cancel: () => ipcRenderer.send("oasis-first-run/cancel"),
});
