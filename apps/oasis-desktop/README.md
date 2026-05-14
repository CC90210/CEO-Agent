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

```bash
npm run release:check
npm run build:win
npm run portable:win
npm run release:metadata
npm run signing:check
```

Windows builds can be produced on Windows. macOS signing/notarization requires macOS and Apple credentials. Linux packages should be built on Linux CI.

For the current unsigned alpha, `npm run pack` creates a runnable unpacked app folder at `dist/win-unpacked/`.
`npm run release:metadata` writes `dist/release-metadata.json` and `dist/SHA256SUMS.txt` for generated installer/archive artifacts.

For production Windows distribution, configure Authenticode signing in CI with `WINDOWS_CSC_LINK` and `WINDOWS_CSC_KEY_PASSWORD`, then set `OASIS_REQUIRE_WINDOWS_SIGNING=true`. Without a trusted publisher signature, locked-down Windows machines can block the app even when the package is built correctly.

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
