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
// Phase 4 modules
const bundleScriptPath = path.join(root, "scripts", "bundle-sidecar.js");
const providerKeysPath = path.join(root, "src", "provider-keys.js");
const firstRunWindowPath = path.join(root, "src", "first-run-window.js");
const firstRunHtmlPath = path.join(root, "resources", "first-run.html");
const firstRunPreloadPath = path.join(root, "resources", "first-run-preload.js");
const updateCheckPath = path.join(root, "src", "update-check.js");
const httpsHelperPath = path.join(root, "src", "https.js");

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
const bundleScript = fs.readFileSync(bundleScriptPath, "utf8");
const providerKeys = fs.readFileSync(providerKeysPath, "utf8");
const firstRunWindow = fs.readFileSync(firstRunWindowPath, "utf8");
const firstRunHtml = fs.readFileSync(firstRunHtmlPath, "utf8");
const firstRunPreload = fs.readFileSync(firstRunPreloadPath, "utf8");
const updateCheck = fs.readFileSync(updateCheckPath, "utf8");
const httpsHelper = fs.readFileSync(httpsHelperPath, "utf8");

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

// ---------------------------------------------------------------------------
// Phase 4 — bundled sidecar + first-run provider flow + update probe.
// Catches regressions if any of these files get accidentally removed or
// their security-critical invariants drift.
// ---------------------------------------------------------------------------

assert(pkg.scripts["bundle:sidecar"] === "node scripts/bundle-sidecar.js", "bundle:sidecar npm script wired");
assert(pkg.scripts.prepack === "node scripts/bundle-sidecar.js", "bundle runs automatically on prepack");
assert(pkg.scripts["build:win"]?.includes("bundle:sidecar"), "Windows build runs sidecar bundle first");
assert(pkg.scripts["build:mac"]?.includes("bundle:sidecar"), "Mac build runs sidecar bundle first");
assert(pkg.scripts["build:linux"]?.includes("bundle:sidecar"), "Linux build runs sidecar bundle first");
assert(
  Array.isArray(pkg.build.extraResources) &&
    pkg.build.extraResources.some((r) => r.from === "resources/sidecar" && r.to === "sidecar"),
  "electron-builder ships the bundled sidecar as extraResources"
);

// Live test the patterns actually catch their targets — a regex typo
// in HARD_BLOCK would silently pass the "pattern string present" check
// but fail to block the real path. test-bundle-hardblock.js exits 0
// only when all must-block targets match AND all must-allow paths
// pass AND every pattern in HARD_BLOCK has at least one test case
// hitting it.
const { spawnSync } = require("node:child_process");
const hardblockTest = spawnSync(process.execPath, [path.join(root, "scripts", "test-bundle-hardblock.js")], {
  stdio: "pipe",
  encoding: "utf8",
});
assert(
  hardblockTest.status === 0,
  `bundle HARD_BLOCK regexes actually catch bad paths (see scripts/test-bundle-hardblock.js):\n${hardblockTest.stdout}${hardblockTest.stderr}`
);

assert(bundleScript.includes("HARD_BLOCK"), "bundle script enforces a hard-block list for secrets");
assert(bundleScript.includes("\\.env"), "bundle script hard-blocks .env files");
assert(bundleScript.includes("credentials"), "bundle script hard-blocks credentials* files");
assert(bundleScript.includes("\\.key"), "bundle script hard-blocks .key files");
assert(bundleScript.includes("\\.pem"), "bundle script hard-blocks .pem files");
assert(bundleScript.includes("\\.ssh"), "bundle script hard-blocks ~/.ssh dirs");
assert(bundleScript.includes("\\.aws"), "bundle script hard-blocks ~/.aws dirs");
assert(bundleScript.includes("\\.gnupg"), "bundle script hard-blocks ~/.gnupg dirs");
assert(bundleScript.includes("\\.npmrc"), "bundle script hard-blocks .npmrc auth tokens");
assert(bundleScript.includes("\\.kdbx"), "bundle script hard-blocks KeePass databases");
assert(bundleScript.includes("\\.docker"), "bundle script hard-blocks Docker config tokens");
assert(bundleScript.includes("sha256"), "bundle script records per-file SHA-256 in the manifest");
assert(bundleScript.includes("bundle.json"), "bundle script writes a bundle manifest for runtime audit");

assert(bridgeRuntime.includes("bundledSidecarRoot"), "bridge runtime resolves the bundled sidecar root");
assert(bridgeRuntime.includes("resourcesPath"), "bridge runtime prefers process.resourcesPath when packaged");
assert(bridgeRuntime.includes("getEnvOverrides"), "bridge runtime accepts env overrides for provider keys");
assert(bridgeRuntime.includes("getBundleManifest"), "bridge runtime exposes bundle manifest to diagnostics");
assert(bridgeRuntime.includes("x-api-key"), "bridge runtime scrubs x-api-key headers from logs");

assert(providerKeys.includes("safeStorage") || providerKeys.includes("./secure-store"), "provider-keys stores via OS-encrypted secure-store");
assert(providerKeys.includes("validateProviderKey"), "provider-keys exposes live key validation");
assert(providerKeys.includes("composeBridgeEnv"), "provider-keys composes the bridge env without leaking keys to disk");
assert(
  ["anthropic", "openrouter", "openai", "google"].every((p) => providerKeys.includes(`"${p}"`)),
  "provider-keys covers anthropic + openrouter + openai + google"
);

assert(firstRunWindow.includes("contextIsolation: true"), "first-run window enforces contextIsolation");
assert(firstRunWindow.includes("nodeIntegration: false"), "first-run window disables nodeIntegration");
assert(firstRunWindow.includes("sandbox: true"), "first-run window keeps Chromium sandbox enabled");
assert(firstRunWindow.includes("setWindowOpenHandler"), "first-run window blocks popups");
assert(firstRunWindow.includes("will-navigate"), "first-run window blocks external navigation");

assert(firstRunPreload.includes("contextBridge.exposeInMainWorld"), "first-run preload uses contextBridge");
assert(!firstRunPreload.includes("nodeRequire"), "first-run preload does not expose require");
assert(
  firstRunHtml.includes("Content-Security-Policy") && firstRunHtml.includes("connect-src 'none'"),
  "first-run HTML CSP blocks outbound connections from the renderer"
);

assert(updateCheck.includes("compareVersions"), "update-check exposes semver-ish comparator");
assert(updateCheck.includes("OASIS_DESKTOP_DISABLE_UPDATE_CHECK") || main.includes("OASIS_DESKTOP_DISABLE_UPDATE_CHECK"), "update check is opt-out via env var");
assert(
  !/require\(['"]electron-updater['"]\)|from ['"]electron-updater['"]/.test(updateCheck) &&
    !pkg.dependencies?.["electron-updater"] &&
    !pkg.devDependencies?.["electron-updater"],
  "update check stays free of electron-updater dependency"
);

assert(httpsHelper.includes("httpsRequest"), "shared https helper exists for provider + update consumers");
assert(httpsHelper.includes("DEFAULT_TIMEOUT_MS"), "shared https helper enforces a default timeout");

assert(main.includes("openFirstRunWindow"), "main process invokes the first-run provider window");
assert(main.includes("composeBridgeEnv"), "main process feeds provider keys into the bridge env");
assert(main.includes("checkForUpdate"), "main process wires the update probe");
assert(main.includes("Connect / Update Provider Key"), "main menu exposes provider key configuration");
assert(main.includes("Reset Provider Keys"), "main menu exposes provider key reset with confirmation");
assert(main.includes("Sidecar Bundle Info"), "main menu exposes sidecar bundle info");

console.log("OK  desktop release checks passed");
