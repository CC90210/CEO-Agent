"use strict";

const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packagePath = path.join(root, "package.json");
const manifestPath = path.join(root, "desktop.manifest.json");
const mainPath = path.join(root, "src", "main.js");
const authNavigationPath = path.join(root, "src", "auth-navigation.js");
const diagnosticsPath = path.join(root, "src", "diagnostics.js");
const secureStorePath = path.join(root, "src", "secure-store.js");
const manifestModulePath = path.join(root, "src", "manifest.js");
const bridgeRuntimePath = path.join(root, "src", "bridge-runtime.js");
const windowsPortablePath = path.join(root, "scripts", "create-windows-portable.js");
const signingStatusPath = path.join(root, "scripts", "signing-status.js");
const releaseMetadataPath = path.join(root, "scripts", "write-release-metadata.js");
const workflowPath = path.resolve(root, "..", "..", ".github", "workflows", "oasis-desktop.yml");

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
const authNavigation = fs.readFileSync(authNavigationPath, "utf8");
const diagnostics = fs.readFileSync(diagnosticsPath, "utf8");
const secureStore = fs.readFileSync(secureStorePath, "utf8");
const manifestModule = fs.readFileSync(manifestModulePath, "utf8");
const bridgeRuntime = fs.readFileSync(bridgeRuntimePath, "utf8");
const windowsPortable = fs.readFileSync(windowsPortablePath, "utf8");
const signingStatus = fs.readFileSync(signingStatusPath, "utf8");
const releaseMetadata = fs.readFileSync(releaseMetadataPath, "utf8");
const workflow = fs.readFileSync(workflowPath, "utf8");

assert(pkg.name === "oasis-ai-desktop", "desktop package name is stable");
assert(pkg.main === "src/main.js", "desktop main entry is src/main.js");
assert(typeof pkg.homepage === "string" && pkg.homepage.startsWith("https://"), "desktop package has HTTPS homepage metadata");
assert(typeof pkg.author === "string" && pkg.author.includes("@"), "desktop package author includes maintainer email");
assert(fs.existsSync(path.join(root, "package-lock.json")), "package-lock.json exists for repeatable installs");
assert(includesExact(pkg.build.files, "desktop.manifest.json"), "desktop manifest is included in packaged app");
assert(includesExact(pkg.build.files, "README.md"), "desktop README is included in packaged app");
assert(includesExact(pkg.build.files, "RELEASE.md"), "desktop release playbook is included in packaged app");
assert(pkg.build.linux?.maintainer?.includes("@"), "Linux package maintainer metadata is set");
assert(pkg.scripts["auth:check"] === "node scripts/auth-navigation-check.js", "desktop auth navigation check script exists");
assert(pkg.scripts["portable:win"] === "node scripts/create-windows-portable.js", "Windows portable zip script exists");
assert(pkg.scripts["signing:check"] === "node scripts/signing-status.js", "Windows signing status script exists");
assert(!JSON.stringify(pkg.build.win?.target || []).includes("portable"), "Windows build avoids temp-running portable exe target");
assert(pkg.build.win?.requestedExecutionLevel === "asInvoker", "Windows installer does not request unnecessary elevation");

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
assert(main.includes("shouldAllowInDesktop"), "desktop navigation uses explicit desktop allow gate");
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

assert(authNavigation.includes("createAuthNavigationController"), "desktop OAuth navigation controller exists");
assert(authNavigation.includes("accounts.google.com"), "desktop OAuth navigation handles Google sign-in host");
assert(authNavigation.includes(".supabase.co"), "desktop OAuth navigation handles Supabase auth host");
assert(authNavigation.includes("hasTrustedRedirectTarget"), "desktop OAuth navigation requires trusted redirect target");

assert(manifestModule.includes("validateDesktopManifest"), "desktop manifest validation exists");
assert(manifestModule.includes("providerConnections must include api_key"), "manifest validation requires API-key provider connection");
assert(manifestModule.includes("runtimeAccess must include desktop"), "manifest validation requires desktop access");
assert(manifestModule.includes("wildcard origin is not allowed"), "manifest validation rejects wildcard origins");
assert(manifestModule.includes("bridge.healthUrl must stay loopback-only"), "manifest validation keeps bridge loopback-only");

assert(bridgeRuntime.includes("createBridgeRuntime"), "bridge runtime module exists");
assert(bridgeRuntime.includes("windowsHide: true"), "bridge runtime hides Windows child console");
assert(bridgeRuntime.includes("scrubLogLine"), "bridge runtime log redaction exists");

assert(windowsPortable.includes("win-unpacked"), "Windows portable script zips the unpacked app");
assert(windowsPortable.includes("OASIS AI.exe"), "Windows portable script verifies the app executable exists");
assert(windowsPortable.includes("Compress-Archive"), "Windows portable script uses a normal zip archive");
assert(workflow.includes("Create Windows portable zip"), "desktop CI creates Windows portable zip before metadata");
assert(signingStatus.includes("Get-AuthenticodeSignature"), "Windows signing status checks Authenticode signatures");
assert(signingStatus.includes("OASIS_REQUIRE_WINDOWS_SIGNING"), "Windows signing status can enforce production signing");
assert(workflow.includes("WINDOWS_CSC_LINK"), "desktop CI is wired for Windows code-signing certificate secret");
assert(workflow.includes("Windows signing status"), "desktop CI reports Windows signing status");

assert(releaseMetadata.includes("SHA256SUMS.txt"), "release metadata writes checksum file");
assert(releaseMetadata.includes("release-metadata.json"), "release metadata writes machine-readable manifest");
assert(releaseMetadata.includes("suspiciously small artifact"), "release metadata skips partial installer stubs");

console.log("OK  desktop release checks passed");
