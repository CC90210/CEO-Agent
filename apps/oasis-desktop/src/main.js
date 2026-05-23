"use strict";

const { app, BrowserWindow, Menu, dialog, shell, session } = require("electron");
const path = require("node:path");
const { createAuthNavigationController } = require("./auth-navigation");
const { createBridgeRuntime } = require("./bridge-runtime");
const { createSupportBundle, openDiagnosticsWindow } = require("./diagnostics");
const { buildAllowedOrigins, loadDesktopManifest, resolveCommandCenterUrl } = require("./manifest");
const { openFirstRunWindow } = require("./first-run-window");
const {
  composeBridgeEnv,
  clearProviderKey,
  listConfiguredProviders,
  PROVIDERS,
} = require("./provider-keys");
const { bridgePaired } = require("./bridge-paths");
const { checkForUpdate, RELEASE_REPO } = require("./update-check");
const {
  PROTOCOL: OASIS_PROTOCOL,
  parseDeepLink,
  redeemPairCode,
  makeDeepLinkBuffer,
} = require("./deep-link");
const signinWindow = require("./signin-window");

let mainWindow = null;
let allowLocalFallbackNavigation = false;
let pendingMagicLinkUrl = null;
const deepLinkBuffer = makeDeepLinkBuffer();

const desktopManifest = loadDesktopManifest();
const commandCenterUrl = resolveCommandCenterUrl(desktopManifest);
const allowedOrigins = buildAllowedOrigins(desktopManifest, commandCenterUrl);
const authNavigation = createAuthNavigationController({ allowedOrigins });
const bridgeHealthUrl = new URL(desktopManifest.bridge.healthUrl);
const bridgeRuntime = createBridgeRuntime({
  app,
  bridgeHealthUrl,
  desktopManifest,
  startDir: path.resolve(__dirname, "..", "..", ".."),
  getEnvOverrides: () => composeBridgeEnv() || {},
});

async function ensureProviderConfigured() {
  // First-run check — open the 3-step wizard if either (a) no provider
  // key is stored locally OR (b) no bridge_pairing exists yet. The
  // wizard's pair step (Step 1) handles the second case; provider key
  // (Step 2) handles the first. Skipping straight to the dashboard
  // works in either state, but the wizard makes the missing pieces
  // obvious so the operator doesn't end up wondering why chat 412s.
  //
  // Post-2026-05-17 refresh: replaced the single-screen provider form
  // with the 3-step pair → AI → health wizard. CC's product goal is
  // "clients never touch a terminal" — pairing used to require
  // `bravo setup` in a shell; now it's a paste-the-9-char-code field.
  // Path knowledge lives in src/bridge-paths.js (shared with the
  // wizard) so neither file can drift from where bravo_cli writes.
  const providerConfigured = listConfiguredProviders().length > 0;
  if (bridgePaired() && providerConfigured) return { result: "already_configured" };
  try {
    return await openFirstRunWindow({
      desktopManifest,
      commandCenterUrl,
      bridgeHealthUrl: desktopManifest?.bridge?.healthUrl,
    });
  } catch (err) {
    return { result: "error", error: err instanceof Error ? err.message : String(err) };
  }
}

async function showUpdateDialog(report) {
  if (!report.ok) return;
  if (!report.is_newer) {
    dialog.showMessageBox({
      type: "info",
      title: "OASIS AI is up to date",
      message: `You're on v${report.current}. Latest release is v${report.latest}.`,
    });
    return;
  }
  const buttons = report.asset
    ? ["Download for this OS", "Open release page", "Later"]
    : ["Open release page", "Later"];
  const choice = await dialog.showMessageBox({
    type: "info",
    title: "OASIS AI update available",
    message: `A newer build is available: v${report.latest} (you're on v${report.current}).`,
    detail: report.asset
      ? `Asset: ${report.asset.name} (${(report.asset.size / 1024 / 1024).toFixed(1)} MB)`
      : "No platform-specific asset detected on the release.",
    buttons,
    defaultId: 0,
    cancelId: buttons.length - 1,
  });
  if (report.asset && choice.response === 0) {
    void shell.openExternal(report.asset.url);
  } else if (report.asset && choice.response === 1) {
    void shell.openExternal(report.html_url);
  } else if (!report.asset && choice.response === 0) {
    void shell.openExternal(report.html_url);
  }
}

async function runStartupUpdateProbe() {
  if (process.env.OASIS_DESKTOP_DISABLE_UPDATE_CHECK === "true") return;
  try {
    const report = await checkForUpdate();
    if (report.ok && report.is_newer) void showUpdateDialog(report);
  } catch (err) {
    // Update probe must NEVER block boot or leak to the UI. Just write
    // to console; the menu's manual "Check for Updates" surfaces errors.
    console.warn("[update-check] startup probe failed:", err instanceof Error ? err.message : err);
  }
}

function isAllowedNavigation(targetUrl) {
  try {
    const parsed = new URL(targetUrl);
    const allowed = allowedOrigins.has(parsed.origin);
    if (allowed) authNavigation.noteAllowedAppNavigation(targetUrl);
    return allowed;
  } catch {
    return false;
  }
}

function shouldAllowInDesktop(targetUrl) {
  return isAllowedNavigation(targetUrl) || authNavigation.shouldAllowAuthNavigation(targetUrl);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fallbackHtml(errorMessage) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OASIS AI</title>
  <style>
    :root { color-scheme: dark; --bg: #05070d; --panel: #0d131f; --line: #1b2a3f; --text: #edf6ff; --muted: #9fb1c7; --accent: #12d8ff; --warn: #ffca65; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: radial-gradient(circle at 18% 12%, rgba(18,216,255,.18), transparent 24rem), linear-gradient(145deg, #05070d, #08101b 58%, #04060b);
      color: var(--text);
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { width: min(760px, calc(100vw - 40px)); border: 1px solid rgba(18,216,255,.28); background: rgba(13,19,31,.86); border-radius: 24px; padding: 30px; box-shadow: 0 24px 90px rgba(0,0,0,.42); }
    .eyebrow { color: var(--accent); text-transform: uppercase; letter-spacing: .18em; font-size: 11px; font-weight: 800; }
    h1 { margin: 8px 0 10px; font-size: 32px; letter-spacing: -.04em; }
    p { color: var(--muted); margin: 0 0 16px; }
    .error { border: 1px solid rgba(255,202,101,.32); background: rgba(255,202,101,.08); color: var(--warn); border-radius: 14px; padding: 12px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }
    a { color: var(--text); text-decoration: none; border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; background: rgba(255,255,255,.03); }
    a.primary { border-color: rgba(18,216,255,.45); background: rgba(18,216,255,.12); color: var(--accent); font-weight: 800; }
    ul { color: var(--muted); padding-left: 18px; }
    code { color: var(--accent); }
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">OASIS AI Desktop</div>
    <h1>Command Center is temporarily unreachable</h1>
    <p>The desktop shell is running, but it could not load the hosted Command Center. API-key mode and sign-in need the web app; Desktop diagnostics are still available from the app menu.</p>
    <div class="error">${escapeHtml(errorMessage || "Unknown load failure")}</div>
    <div class="actions">
      <a class="primary" href="${escapeHtml(commandCenterUrl.toString())}">Retry Command Center</a>
      <a href="https://agent-dashboard-cc90210.vercel.app">Open hosted dashboard</a>
    </div>
    <ul>
      <li>Use <code>OASIS AI -> Desktop Diagnostics</code> for bridge and package health.</li>
      <li>Use <code>OASIS AI -> Create Support Bundle</code> for a redacted support report.</li>
      <li>If this is a local dev build, set <code>OASIS_COMMAND_CENTER_URL=http://localhost:3100</code>.</li>
    </ul>
  </main>
</body>
</html>`;
}

function showFallbackPage(errorMessage) {
  if (!mainWindow) return;
  const html = fallbackHtml(errorMessage);
  allowLocalFallbackNavigation = true;
  mainWindow.webContents.once("did-finish-load", () => {
    allowLocalFallbackNavigation = false;
  });
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`).catch((error) => {
    allowLocalFallbackNavigation = false;
    dialog.showErrorBox("OASIS AI could not load", error.message);
  });
}

// OAuth provider hosts we never want to load inside Electron. Supabase auth
// URLs are included because Supabase OAuth flows REDIRECT to provider URLs
// (accounts.google.com etc.) and the user's session-bearing browser is what
// makes them work. Magic-link verify URLs are NOT on this list — those we
// DO want loaded in Electron because they set the desktop's session cookie.
const EXTERNAL_AUTH_HOSTS = new Set([
  "accounts.google.com",
  "oauth2.googleapis.com",
  "appleid.apple.com",
  "github.com",
  "login.microsoftonline.com",
]);

function isExternalAuthUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return false;
    if (EXTERNAL_AUTH_HOSTS.has(parsed.hostname)) return true;
    // Supabase OAuth init endpoints: /auth/v1/authorize?provider=google.
    // The /auth/v1/verify path is the magic-link verifier — we KEEP that
    // in-window so it can set our session cookie.
    if (parsed.pathname === "/auth/v1/authorize" && parsed.hostname.endsWith(".supabase.co")) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

function surfaceSignInLanding() {
  // When the dashboard view bounces to /login (session expired, pairing
  // revoked, etc.) we close the main window and re-open the sign-in
  // landing. The user reverts to the same turnkey path: open browser,
  // sign in, deep-link back.
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.close();
    mainWindow = null;
  }
  openSignInLanding();
}

function openSignInLanding() {
  signinWindow.openSignInWindow({
    commandCenterUrl,
    onPaired: (info) => {
      // Renderer-side manual code submit → close sign-in, swap in main.
      pendingMagicLinkUrl = info?.magic_link_url || null;
      handlePostPair(info);
    },
  });
}

function handlePostPair(info) {
  // Give the renderer a beat to show "Connected" so the swap doesn't
  // look like a glitch. The actual cookie write happens via loadURL ->
  // magic-link below; pendingMagicLinkUrl was set by the caller.
  setTimeout(() => {
    signinWindow.closeSignInWindow();
    void bridgeRuntime.startIfAvailable();
    createWindow();
  }, 900);
}

async function handleDeepLink(rawUrl) {
  const parsed = parseDeepLink(rawUrl);
  if (!parsed) return;
  if (parsed.action !== "pair") return;
  const code = parsed.params?.code || "";
  const result = await redeemPairCode({ code, commandCenterUrl });
  if (!result?.ok) {
    if (signinWindow.isOpen()) signinWindow.notifyError(result || { message: "Pair failed" });
    return;
  }
  pendingMagicLinkUrl = result.magic_link_url || null;
  if (signinWindow.isOpen()) {
    signinWindow.notifyPaired(result);
    handlePostPair(result);
  } else if (mainWindow && !mainWindow.isDestroyed()) {
    // Already in main view (e.g. user re-paired) — reload via the magic
    // link to refresh the session cookie.
    if (pendingMagicLinkUrl) {
      mainWindow.loadURL(pendingMagicLinkUrl).catch(() => mainWindow.webContents.reloadIgnoringCache());
      pendingMagicLinkUrl = null;
    } else {
      mainWindow.webContents.reloadIgnoringCache();
    }
  }
}

function loadCommandCenter() {
  if (!mainWindow) return;
  // Pending magic-link wins: after pairing via the oasis:// deep-link the
  // redeem endpoint returns a one-time Supabase magic-link. Loading it
  // here lets the Supabase verify route set the session cookie on the
  // Electron browser's domain BEFORE we land on the dashboard. The
  // /auth/callback then redirects us to `/` already authenticated. If
  // the magic-link minting failed server-side (network blip, generateLink
  // disabled), we fall through to the bare dashboard URL — degraded but
  // not broken; the dashboard will redirect to /login which our nav
  // listener catches + bounces back to the sign-in landing.
  const target = pendingMagicLinkUrl || commandCenterUrl.toString();
  pendingMagicLinkUrl = null;
  mainWindow.loadURL(target).catch((error) => {
    showFallbackPage(error.message);
  });
}

function isDashboardLoginPath(url) {
  try {
    const parsed = new URL(url);
    return allowedOrigins.has(parsed.origin) && parsed.pathname === "/login";
  } catch {
    return false;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 720,
    title: "OASIS AI",
    backgroundColor: "#05070d",
    show: false,
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
      allowRunningInsecureContent: false,
      devTools: !app.isPackaged
    }
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // window.open from the dashboard — OAuth providers, magic links etc.
    // OAuth in Electron is the "incognito browser" UX the user complained
    // about, so we route every Google/Supabase auth URL straight to the
    // user's real browser. They already have an authenticated Supabase
    // session there (or can sign in via Google SSO normally).
    if (isExternalAuthUrl(url)) {
      void shell.openExternal(url);
      return { action: "deny" };
    }
    if (shouldAllowInDesktop(url)) {
      mainWindow.loadURL(url).catch((error) => {
        showFallbackPage(error.message);
      });
      return { action: "deny" };
    }
    void shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (allowLocalFallbackNavigation && url.startsWith("data:text/html")) {
      return;
    }
    // Pre-empt OAuth-in-Electron navigations before the network even
    // starts. Without this guard, clicking "Sign in with Google" inside a
    // dashboard view loaded in the Electron window would navigate to
    // accounts.google.com inside this Chromium — where the user has no
    // Google session because Electron's cookie jar is isolated from the
    // OS Chrome.
    if (isExternalAuthUrl(url)) {
      event.preventDefault();
      void shell.openExternal(url);
      return;
    }
    // If the dashboard tries to redirect us to /login (Supabase session
    // expired, magic-link verification failed, etc.) we abort the main
    // window and re-open the sign-in landing instead of letting Electron
    // host the broken OAuth UX.
    if (isDashboardLoginPath(url)) {
      event.preventDefault();
      surfaceSignInLanding();
      return;
    }
    if (!shouldAllowInDesktop(url)) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });

  mainWindow.webContents.on("did-fail-load", (_event, _errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame || validatedURL.startsWith("data:")) return;
    showFallbackPage(errorDescription);
  });

  loadCommandCenter();
}

function installSecurityDefaults() {
  const allowedPermissions = new Set(desktopManifest.security.allowedBrowserPermissions || []);
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(allowedPermissions.has(permission));
  });
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "X-Content-Type-Options": ["nosniff"],
        "Referrer-Policy": ["strict-origin-when-cross-origin"]
      }
    });
  });
}

function installMenu() {
  const diagnosticsContext = () => ({
    allowedOrigins: [...allowedOrigins],
    bridgeHealthUrl,
    commandCenterUrl,
    desktopManifest,
    getBridgeCwd: bridgeRuntime.getBridgeCwd,
    getBridgeLogPath: bridgeRuntime.getBridgeLogPath,
    getBridgeProcessState: bridgeRuntime.getProcessState,
    isBridgeHealthy: bridgeRuntime.isBridgeHealthy
  });

  const template = [
    {
      label: "OASIS AI",
      submenu: [
        { role: "about" },
        { type: "separator" },
        {
          label: "Reload Command Center",
          accelerator: "CmdOrCtrl+R",
          click: () => loadCommandCenter()
        },
        {
          label: "Open Command Center in Browser",
          click: () => shell.openExternal(commandCenterUrl.toString())
        },
        { type: "separator" },
        {
          label: "Connect / Update Provider Key…",
          click: async () => {
            const result = await openFirstRunWindow({ parent: mainWindow });
            if (result.result === "saved") {
              dialog.showMessageBox({
                type: "info",
                title: "Provider key saved",
                message: `Saved ${result.provider} key. Restart the bridge to pick up the new credential.`,
                buttons: ["Restart bridge now", "Later"],
                defaultId: 0,
              }).then((choice) => {
                if (choice.response === 0) {
                  bridgeRuntime.stop();
                  void bridgeRuntime.startIfAvailable();
                }
              });
            }
          }
        },
        {
          label: "Reset Provider Keys…",
          click: async () => {
            const configured = listConfiguredProviders();
            if (configured.length === 0) {
              dialog.showMessageBox({
                type: "info",
                title: "No provider keys configured",
                message: "Nothing to reset — open Connect Provider Key to add one.",
              });
              return;
            }
            const choice = await dialog.showMessageBox({
              type: "warning",
              title: "Reset all provider keys?",
              message: `This deletes saved keys for: ${configured.join(", ")}. The desktop bridge will fall back to cloud-only mode until a new key is configured.`,
              buttons: ["Reset all", "Cancel"],
              defaultId: 1,
              cancelId: 1,
            });
            if (choice.response === 0) {
              for (const p of PROVIDERS) clearProviderKey(p);
              bridgeRuntime.stop();
              dialog.showMessageBox({
                type: "info",
                title: "Provider keys cleared",
                message: "Run Connect Provider Key to add a new one.",
              });
            }
          }
        },
        { type: "separator" },
        {
          label: "Bridge Log",
          click: () => shell.openPath(bridgeRuntime.getBridgeLogPath())
        },
        {
          label: "Desktop Diagnostics",
          click: () => {
            void openDiagnosticsWindow(diagnosticsContext());
          }
        },
        {
          label: "Sidecar Bundle Info",
          click: () => {
            const manifest = bridgeRuntime.getBundleManifest();
            if (!manifest) {
              dialog.showMessageBox({
                type: "info",
                title: "No bundled sidecar",
                message: "This build is running from a repo clone (dev mode) — no bundle manifest available.",
              });
              return;
            }
            dialog.showMessageBox({
              type: "info",
              title: "Sidecar Bundle",
              message: `Source SHA: ${manifest.bundled_from_sha}${manifest.bundled_from_clean ? "" : " (dirty)"}`,
              detail: `Bundled at: ${manifest.bundled_at}\nFiles: ${manifest.file_count}\nTotal size: ${(manifest.total_bytes / 1024).toFixed(1)} KiB\nSchema: v${manifest.schema_version}`,
            });
          }
        },
        {
          label: "Check for Updates…",
          click: async () => {
            try {
              const report = await checkForUpdate();
              await showUpdateDialog(report);
            } catch (err) {
              dialog.showErrorBox(
                "Update check failed",
                `Could not reach GitHub (${RELEASE_REPO}): ${err instanceof Error ? err.message : String(err)}`
              );
            }
          }
        },
        {
          label: "Create Support Bundle",
          click: async () => {
            try {
              const bundlePath = await createSupportBundle(diagnosticsContext());
              shell.showItemInFolder(bundlePath);
            } catch (error) {
              dialog.showErrorBox(
                "OASIS AI support bundle failed",
                error instanceof Error ? error.message : String(error)
              );
            }
          }
        },
        { type: "separator" },
        { role: "quit" }
      ]
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// Register oasis:// as a default protocol handler. On macOS this enables
// the `open-url` event below (LaunchServices routes to us); on Windows it
// writes a registry key so explorer.exe knows we own the scheme. In dev
// mode under `electron .` we have to pass argv so Squirrel/Electron knows
// which exe to register — packaged builds get it from electron-builder's
// protocols entry in package.json. Idempotent on subsequent boots.
if (process.defaultApp) {
  if (process.argv.length >= 2) {
    app.setAsDefaultProtocolClient(OASIS_PROTOCOL, process.execPath, [path.resolve(process.argv[1])]);
  }
} else {
  app.setAsDefaultProtocolClient(OASIS_PROTOCOL);
}

// macOS hands deep-links to the running app via the open-url event. It can
// fire BEFORE `whenReady` (cold-launch via Finder click), so we buffer the
// URL and drain after the boot path is ready.
app.on("open-url", (event, url) => {
  event.preventDefault();
  deepLinkBuffer.push(url);
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, argv) => {
    // Windows/Linux deep-links arrive via argv on a second-instance event.
    // Find the oasis:// URL in the argv (its position depends on packaged
    // vs dev mode + how the OS shell forwarded the args) and push it onto
    // the buffer. Then surface whichever window is current.
    const deepLink = (argv || []).find((arg) => typeof arg === "string" && arg.startsWith(`${OASIS_PROTOCOL}://`));
    if (deepLink) deepLinkBuffer.push(deepLink);
    if (signinWindow.isOpen()) {
      // The sign-in landing is the foreground window before pairing.
      // (no explicit handle exported — focusing is best-effort via OS)
    } else if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    installSecurityDefaults();
    installMenu();

    // Drain deep-links the moment app boots. handleDeepLink resolves
    // the pair-code, mints the magic-link, and either notifies the
    // sign-in renderer or swaps in the main window — depending on
    // what's open at the time.
    deepLinkBuffer.onReady((url) => { void handleDeepLink(url); });

    if (bridgePaired()) {
      // Paired machine — start the bridge daemon and open the dashboard.
      // The first-run wizard remains accessible from the OASIS AI menu
      // for provider-key changes or re-pairing.
      await bridgeRuntime.startIfAvailable();
      createWindow();
    } else {
      // Unpaired — turnkey path: open the sign-in landing window. The
      // user clicks "Open sign-in in my browser" → real Chrome / Safari
      // handles the OAuth or email/password normally → dashboard fires
      // oasis://pair?code=... → handleDeepLink picks it up → main window
      // opens, loading the magic-link so the dashboard renders signed-in.
      openSignInLanding();
    }
    // Update probe in the background — non-blocking, never raises.
    void runStartupUpdateProbe();
  });

  app.on("activate", () => {
    // Dock-icon click on macOS. Restore the appropriate window for the
    // current pairing state.
    if (BrowserWindow.getAllWindows().length === 0) {
      if (bridgePaired()) createWindow();
      else openSignInLanding();
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("before-quit", () => {
    bridgeRuntime.stop();
  });
}
