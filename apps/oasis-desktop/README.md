---
tags: [apps]
last_updated: 2026-05-22
---

# OASIS AI Desktop

OASIS AI Desktop is the installable shell for the Agent Command Center. It loads the existing Command Center UI and, when available, starts the local bridge sidecar so This desktop access can use approved local tools and files.

## Product Axes

OASIS Desktop separates the model/provider connection from computer access.

Provider connection:

- Sign in with a provider or local authenticated CLI where supported, such as Claude Code.
- Paste an API key from providers such as OpenRouter, Anthropic, OpenAI, Google, or compatible local endpoints.
- Use OASIS subscription billing and platform-managed model credentials.

Runtime access:

- Cloud workspace uses the hosted Command Center without local files, browser, or desktop tools.
- This desktop uses the local bridge sidecar for approved local tools, files, browser actions, and automations.
- Auto chooses this desktop when the bridge is available, otherwise it stays in the cloud workspace.

Target product contract:

```text
Provider connection + Runtime access = agent capability
```

An API key should be able to power desktop automations once the desktop provider adapter is implemented. The current alpha still uses Claude Code CLI for non-local desktop bridge execution and uses provider API keys through the hosted `/api/chat` cloud path.

## Development

```bash
npm install
npm run doctor
npm run release:check
npm start
```

Use a custom Command Center URL during development:

```bash
$env:OASIS_COMMAND_CENTER_URL="http://localhost:3100"
npm start
```

## Packaging

Two entry points — both go through `scripts/build-platform.js` which
auto-detects signing readiness from env vars and prints a clear
banner showing which mode it ran in (signed / signed+notarized /
unsigned). See [SIGNING.md](./SIGNING.md) for the full env-var
matrix + per-platform cert-provisioning walkthrough.

```bash
# Local testing — produces a launchable artifact without certs:
npm run build:win:unsigned    # NSIS .exe + portable .exe (unsigned)
npm run build:mac:unsigned    # universal .dmg + .zip (unsigned)

# Production — auto-signs when env vars are present:
npm run build:win             # Authenticode-signed when CSC_LINK + CSC_KEY_PASSWORD set
npm run build:mac             # signed + notarized when CSC_LINK + APPLE_* set
```

Supporting scripts:

```bash
npm run release:check
npm run portable:win
npm run release:metadata
npm run signing:check
```

Windows builds can be produced on Windows. macOS signing/notarization requires macOS and Apple credentials. Linux packages should be built on Linux CI.

`npm run pack` creates a runnable unpacked app folder at `dist/win-unpacked/` for fast iteration.
`npm run release:metadata` writes `dist/release-metadata.json` and `dist/SHA256SUMS.txt` for generated installer/archive artifacts.

For production CI, set `OASIS_REQUIRE_WINDOWS_SIGNING=true` (or `OASIS_REQUIRE_MAC_SIGNING=true`) — the build wrapper REFUSES to produce an unsigned artifact when either is set, unless `--unsigned` is passed explicitly. CI secrets in `.github/workflows/oasis-desktop.yml` map `WINDOWS_CSC_LINK` → `WIN_CSC_LINK` (electron-builder's platform-specific override); the wrapper honors both that and the cross-platform `CSC_LINK` fallback.

## Security Defaults

- `nodeIntegration` is disabled.
- `contextIsolation` and Chromium sandboxing are enabled.
- Navigation is restricted to the configured Command Center origin and localhost dev origins.
- External links open in the system browser.
- Browser permissions are denied by default except notifications.
- Bridge logs are written to the Electron user-data folder and redact obvious token/key patterns.
- Desktop Diagnostics and Create Support Bundle are available from the app menu for support/debugging.
- Support bundles include diagnostic state and a redacted bridge-log tail; they do not serialize environment variables.
- If the hosted Command Center cannot load, the app shows a local fallback page with retry/support instructions instead of a blank window.
- `src/secure-store.js` provides an OS-backed encrypted local store for future local API-key and desktop-runtime secrets.

This is the first desktop shell, not the final production installer. Before broad client release, add code signing, auto-updates, OS keychain storage, bundled sidecar runtime, and per-agent local permission prompts.

See `RELEASE.md` for the alpha, beta, and production gates.

## Obsidian Links
- [[brain/APP_REGISTRY]]
- [[docs/INDEX]]
