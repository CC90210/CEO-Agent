"use strict";

const { app, safeStorage } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

const STORE_FILE = "secure-store.json";

function getStorePath() {
  return path.join(app.getPath("userData"), STORE_FILE);
}

function readStore() {
  const storePath = getStorePath();
  if (!fs.existsSync(storePath)) return {};
  return JSON.parse(fs.readFileSync(storePath, "utf8"));
}

function writeStore(store) {
  const storePath = getStorePath();
  fs.mkdirSync(path.dirname(storePath), { recursive: true });
  fs.writeFileSync(storePath, `${JSON.stringify(store, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600
  });
}

function keyFor(scope, name) {
  return `${scope}:${name}`;
}

function assertEncryptionAvailable() {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error("Electron safeStorage encryption is not available on this machine.");
  }
}

function setSecret(scope, name, value) {
  assertEncryptionAvailable();
  const store = readStore();
  store[keyFor(scope, name)] = {
    updatedAt: new Date().toISOString(),
    value: safeStorage.encryptString(String(value)).toString("base64")
  };
  writeStore(store);
}

function getSecret(scope, name) {
  assertEncryptionAvailable();
  const entry = readStore()[keyFor(scope, name)];
  if (!entry?.value) return null;
  return safeStorage.decryptString(Buffer.from(entry.value, "base64"));
}

function deleteSecret(scope, name) {
  const store = readStore();
  delete store[keyFor(scope, name)];
  writeStore(store);
}

function getSecureStoreStatus() {
  const storePath = getStorePath();
  return {
    path: storePath,
    exists: fs.existsSync(storePath),
    encryptionAvailable: safeStorage.isEncryptionAvailable(),
    itemCount: fs.existsSync(storePath) ? Object.keys(readStore()).length : 0
  };
}

module.exports = {
  deleteSecret,
  getSecret,
  getSecureStoreStatus,
  setSecret
};
