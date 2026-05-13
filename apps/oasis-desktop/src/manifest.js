"use strict";

const fs = require("node:fs");
const path = require("node:path");

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Invalid desktop manifest: ${message}`);
  }
}

function parseUrl(value, label) {
  try {
    return new URL(value);
  } catch {
    throw new Error(`Invalid desktop manifest: ${label} must be a valid URL`);
  }
}

function isLoopback(url) {
  return ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
}

function validateDesktopManifest(manifest) {
  assert(manifest?.schemaVersion === 1, "schemaVersion must be 1");
  assert(manifest.product?.name, "product.name is required");
  assert(manifest.product?.appId, "product.appId is required");
  assert(manifest.commandCenter?.defaultUrl, "commandCenter.defaultUrl is required");
  assert(Array.isArray(manifest.providerConnections), "providerConnections must be an array");
  assert(Array.isArray(manifest.runtimeAccess), "runtimeAccess must be an array");
  assert(manifest.providerConnections.some((entry) => entry.id === "api_key"), "providerConnections must include api_key");
  assert(manifest.runtimeAccess.some((entry) => entry.id === "cloud"), "runtimeAccess must include cloud");
  assert(manifest.runtimeAccess.some((entry) => entry.id === "desktop"), "runtimeAccess must include desktop");

  const defaultUrl = parseUrl(manifest.commandCenter.defaultUrl, "commandCenter.defaultUrl");
  assert(defaultUrl.protocol === "https:", "commandCenter.defaultUrl must use HTTPS");

  const origins = manifest.security?.allowedOrigins;
  assert(Array.isArray(origins) && origins.length > 0, "security.allowedOrigins must be a non-empty array");
  for (const origin of origins) {
    assert(!origin.includes("*"), `wildcard origin is not allowed (${origin})`);
    const parsed = parseUrl(origin, `security.allowedOrigins entry ${origin}`);
    assert(parsed.origin === origin, `allowed origin must not include a path (${origin})`);
    assert(parsed.protocol === "https:" || isLoopback(parsed), `allowed origin must be HTTPS or loopback (${origin})`);
  }

  assert(manifest.security.nodeIntegration === false, "security.nodeIntegration must be false");
  assert(manifest.security.contextIsolation === true, "security.contextIsolation must be true");
  assert(manifest.security.sandbox === true, "security.sandbox must be true");
  assert(manifest.security.denyNavigationByDefault === true, "security.denyNavigationByDefault must be true");

  const bridgeHealthUrl = parseUrl(manifest.bridge?.healthUrl, "bridge.healthUrl");
  assert(isLoopback(bridgeHealthUrl), "bridge.healthUrl must stay loopback-only");
  assert(Array.isArray(manifest.bridge.serveArgs), "bridge.serveArgs must be an array");

  return true;
}

function loadDesktopManifest(manifestPath = path.resolve(__dirname, "..", "desktop.manifest.json")) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  validateDesktopManifest(manifest);
  return manifest;
}

function resolveCommandCenterUrl(manifest) {
  const configured = process.env.OASIS_COMMAND_CENTER_URL || manifest.commandCenter.defaultUrl;
  const url = parseUrl(configured, "OASIS_COMMAND_CENTER_URL");
  if (url.protocol !== "https:" && !isLoopback(url)) {
    throw new Error("OASIS_COMMAND_CENTER_URL must be HTTPS or loopback for local development.");
  }
  return url;
}

function buildAllowedOrigins(manifest, commandCenterUrl) {
  return new Set([
    commandCenterUrl.origin,
    ...(manifest.security.allowedOrigins || [])
  ]);
}

module.exports = {
  buildAllowedOrigins,
  loadDesktopManifest,
  resolveCommandCenterUrl,
  validateDesktopManifest
};
