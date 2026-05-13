"use strict";

const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packagePath = path.join(root, "package.json");
const manifestPath = path.join(root, "desktop.manifest.json");
const mainPath = path.join(root, "src", "main.js");
const diagnosticsPath = path.join(root, "src", "diagnostics.js");
const secureStorePath = path.join(root, "src", "secure-store.js");
const manifestModulePath = path.join(root, "src", "manifest.js");
const bridgeRuntimePath = path.join(root, "src", "bridge-runtime.js");
const releaseMetadataPath = path.join(root, "scripts", "write-release-metadata.js");

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
  console.log(`OK  ${message}`);
}

function includesExact(list, value) {
  return Array.isArray(list) && list.includes(value);
}

const pkg = readJson(packagePath);
const manifest = readJson(manifestPath);
const main = fs.readFileSync(mainPath, "utf8");
const diagnostics = fs.readFileSync(diagnosticsPath, "utf8");
const secureStore = fs.readFileSync(secureStorePath, "utf8");
const manifestModule = fs.readFileSync(manifestModulePath, "utf8");
const bridgeRuntime = fs.readFileSync(bridgeRuntimePath, "utf8");
const releaseMetadata = fs.readFileSync(releaseMetadataPath, "utf8");

assert(pkg.name === "oasis-ai-desktop", "desktop package name is stable");
assert(pkg.main === "src/main.js", "desktop main entry is src/main.js");
assert(fs.existsSync(path.join(root, "package-lock.json")), "package-lock.json exists for repeatable installs");
assert(includesExact(pkg.build.files, "desktop.manifest.json"), "desktop manifest is included in packaged app");
assert(includesExact(pkg.build.files, "README.md"), "desktop README is included in packaged app");
assert(includesExact(pkg.build.files, "RELEASE.md"), "desktop release playbook is included in packaged app");

assert(manifest.schemaVersion === 1, "desktop manifest schema is v1");
assert(Array.isArray(manifest.providerConnections), "manifest separates provider connections");
assert(Array.isArray(manifest.runtimeAccess), "manifest separates runtime access");
assert(manifest.providerConnections.some((entry) => entry.id === "api_key"), "manifest supports API-key provider connection");
assert(manifest.runtimeAccess.some((entry) => entry.id === "desktop"), "manifest supports this-desktop access");
assert(manifest.commandCenter.defaultUrl.startsWith("https://"), "default Command Center URL uses HTTPS");
assert(!manifest.security.allowedOrigins.some((origin) => origin.includes("*")), "allowed origins contain no wildcards");
assert(manifest.security.denyNavigationByDefault === true, "navigation denies by default");
assert(manifest.security.nodeIntegration === false, "nodeIntegration remains disabled");
assert(manifest.security.contextIsolation === true, "contextIsolation remains enabled");
assert(manifest.security.sandbox === true, "Chromium sandbox remains enabled");

assert(main.includes("nodeIntegration: false"), "main process disables nodeIntegration");
assert(main.includes("contextIsolation: true"), "main process enables contextIsolation");
assert(main.includes("sandbox: true"), "main process enables sandbox");
assert(main.includes("webSecurity: true"), "main process keeps webSecurity enabled");
assert(main.includes("setPermissionRequestHandler"), "browser permission handler is installed");
assert(main.includes("setWindowOpenHandler"), "new-window navigation handler is installed");
assert(main.includes("will-navigate"), "top-level navigation handler is installed");
assert(main.includes("shell.openExternal"), "external links leave the desktop shell");
assert(main.includes("Desktop Diagnostics"), "desktop diagnostics menu item exists");
assert(main.includes("Create Support Bundle"), "support bundle menu item exists");
assert(main.includes("fallbackHtml"), "first-run fallback page exists");
assert(main.includes("allowLocalFallbackNavigation"), "local fallback navigation is explicitly scoped");

assert(diagnostics.includes("buildDiagnostics"), "diagnostics builder exists");
assert(diagnostics.includes("createSupportBundle"), "support bundle creator exists");
assert(diagnostics.includes("scrubLogLine"), "support bundle log redaction exists");
assert(!diagnostics.includes("process.env,"), "support bundle does not serialize environment variables");

assert(secureStore.includes("safeStorage"), "secure store uses Electron safeStorage");
assert(secureStore.includes("encryptString"), "secure store encrypts values before writing");
assert(secureStore.includes("decryptString"), "secure store can decrypt values for local runtime use");
assert(!secureStore.includes("console.log"), "secure store does not log secrets");

assert(manifestModule.includes("validateDesktopManifest"), "desktop manifest validation exists");
assert(manifestModule.includes("providerConnections must include api_key"), "manifest validation requires API-key provider connection");
assert(manifestModule.includes("runtimeAccess must include desktop"), "manifest validation requires desktop access");
assert(manifestModule.includes("wildcard origin is not allowed"), "manifest validation rejects wildcard origins");
assert(manifestModule.includes("bridge.healthUrl must stay loopback-only"), "manifest validation keeps bridge loopback-only");

assert(bridgeRuntime.includes("createBridgeRuntime"), "bridge runtime module exists");
assert(bridgeRuntime.includes("windowsHide: true"), "bridge runtime hides Windows child console");
assert(bridgeRuntime.includes("scrubLogLine"), "bridge runtime log redaction exists");

assert(releaseMetadata.includes("SHA256SUMS.txt"), "release metadata writes checksum file");
assert(releaseMetadata.includes("release-metadata.json"), "release metadata writes machine-readable manifest");
assert(releaseMetadata.includes("suspiciously small artifact"), "release metadata skips partial installer stubs");

console.log("OK  desktop release checks passed");
