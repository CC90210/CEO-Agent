# OASIS Desktop Alpha Handover

Date: 2026-05-13
Updated: 2026-05-14
Primary repo: `Business-Empire-Agent`
Working product: `apps/oasis-desktop`
Authoring agent: Codex

## Objective

Turn the OASIS Agent Command Center into a downloadable desktop product that preserves the same client-specific Command Center layout while adding a trusted local runtime underneath it.

The product direction is:

- one Command Center UI
- different business/client shells through manifests and tenant profiles
- provider connection through OAuth/account sign-in, API key, or OASIS subscription billing
- runtime access through cloud workspace or this desktop
- desktop access for approved local files, tools, bridge, browser actions, automations, and local model providers

Important boundary: Hermes/Nous was used as a reference pattern for provider/runtime separation, not as source material to copy. Do not scrape or reuse their docs, assets, branding, or website text.

## Current Status

An internal Windows desktop alpha now exists.

Runnable local alpha artifact:

- `apps/oasis-desktop/dist/OASIS-AI-0.1.0-win-x64-unpacked.zip`

Artifact metadata:

- version: `0.1.0`
- channel: `alpha`
- bytes: `136571615`
- SHA-256: `8c5669d6c06bff89448814f10d17e4e28cc518c8582548b62da6ea1484f7da39`

Metadata files generated locally:

- `apps/oasis-desktop/dist/release-metadata.json`
- `apps/oasis-desktop/dist/SHA256SUMS.txt`

Note: `dist/` is ignored by git, so the artifact exists locally but is not meant to be committed.

Public download route added:

- `https://agent-dashboard-cc90210.vercel.app/download`

Published GitHub prerelease tags:

- `https://github.com/CC90210/CEO-Agent/releases/tag/oasis-desktop-v0.1.0-alpha.1`
- `https://github.com/CC90210/CEO-Agent/releases/tag/oasis-desktop-v0.1.0-alpha.2`
- `https://github.com/CC90210/CEO-Agent/releases/tag/oasis-desktop-v0.1.0-alpha.3`
- `https://github.com/CC90210/CEO-Agent/releases/tag/oasis-desktop-v0.1.0-alpha.4`

Direct alpha.4 asset URLs:

- Windows portable zip: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-win-x64-portable.zip`
- Windows installer: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-win-x64.exe`
- macOS Apple Silicon dmg: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-mac-arm64.dmg`
- Linux AppImage: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-linux-x86_64.AppImage`
- Linux deb: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-linux-amd64.deb`

Release verification:

- Alpha.1 GitHub release asset returns `200 OK`.
- Alpha.1 uploaded asset size is `136569906` bytes.
- Alpha.1 uploaded asset digest is `sha256:0061c90ea95fffd3c6b413dcbe18a103880e858f9096ced49505e30fba377404`.
- Alpha.2 cross-platform CI run succeeded for Windows, macOS, and Linux: `https://github.com/CC90210/CEO-Agent/actions/runs/25824129241`.
- Alpha.2 selected asset hashes were generated locally in `tmp/oasis-ci-25824129241/SHA256SUMS-release.txt`.
- Alpha.3 desktop OAuth hotfix committed as `fa46e24 Fix desktop Google OAuth navigation`.
- Alpha.3 cross-platform CI run succeeded for Windows, macOS, and Linux: `https://github.com/CC90210/CEO-Agent/actions/runs/25834820092`.
- Alpha.3 selected asset hashes were generated locally in `tmp/oasis-desktop-alpha3-25834820092/SHA256SUMS-release.txt`.
- Alpha.4 Windows Security hotfix committed as `46f3d87 Fix Windows desktop packaging path`.
- Alpha.4 cross-platform CI run succeeded for Windows, macOS, and Linux: `https://github.com/CC90210/CEO-Agent/actions/runs/25836054826`.
- Alpha.4 selected asset hashes were generated locally in `tmp/oasis-desktop-alpha4-25836054826/SHA256SUMS-release.txt`.
- Stable production `/download` route returns `200 OK` and references alpha.4 after Vercel deployment verification.

Important product note:

- This is a native desktop app, not a Chrome extension. A browser extension can be a later companion for browser capture, but it is not the primary OASIS runtime.

## What Was Built

### Command Center Provider/Access Selector

File:

- `apps/command-center/components/ChatWidget.tsx`

Behavior added:

- Access selector with `Auto`, `Cloud`, and `This desktop`.
- Cloud access always uses `/api/chat` and does not touch the local bridge.
- This desktop access requires the bridge/local desktop runtime.
- Auto access uses the desktop bridge when available, otherwise falls back to cloud workspace.
- Local-only providers such as `ollama` are treated as Desktop-only instead of failing mysteriously in Vercel cloud chat.
- UI copy distinguishes provider connection from local file/tool access.

Security intent:

- Client cloud chat and local machine access are visibly and behaviorally separated.
- The app no longer silently routes to local bridge when the operator explicitly chooses cloud workspace.
- Important correction after the first alpha: API keys are provider credentials, not a limited runtime mode. Target product model is `provider connection + runtime access = agent capability`.

### Desktop App Shell

Directory:

- `apps/oasis-desktop`

Key files:

- `apps/oasis-desktop/package.json`
- `apps/oasis-desktop/package-lock.json`
- `apps/oasis-desktop/src/main.js`
- `apps/oasis-desktop/src/manifest.js`
- `apps/oasis-desktop/src/bridge-runtime.js`
- `apps/oasis-desktop/src/diagnostics.js`
- `apps/oasis-desktop/src/secure-store.js`
- `apps/oasis-desktop/desktop.manifest.json`
- `apps/oasis-desktop/README.md`
- `apps/oasis-desktop/RELEASE.md`

Behavior:

- Electron desktop shell loads the hosted Command Center at `https://agent-dashboard-cc90210.vercel.app`.
- Optional local development URL can be supplied with `OASIS_COMMAND_CENTER_URL=http://localhost:3100`.
- Bridge sidecar is started automatically when the repo is available and `bravo_cli.local_bridge` can be found.
- Bridge remains loopback-only through `http://127.0.0.1:9100/health`.
- Bridge logs go to Electron user-data storage and obvious key/token patterns are redacted.
- App has a branded fallback page if the hosted Command Center cannot load.
- Fallback page navigation is explicitly scoped and does not allow arbitrary `data:` navigation.

Desktop security defaults:

- `nodeIntegration: false`
- `contextIsolation: true`
- Chromium sandbox enabled
- `webSecurity: true`
- external links open in the system browser
- browser permissions denied by default except notifications
- allowed origins are manifest-driven and wildcard origins are rejected
- bridge health URL must be loopback-only

### Desktop Manifest And Release Gates

File:

- `apps/oasis-desktop/desktop.manifest.json`

Defines:

- product identity
- alpha channel
- hosted Command Center URL
- provider connection options
- runtime access options
- bridge sidecar settings
- allowed origins
- browser permission allowlist
- release gates

Manifest validation:

- `apps/oasis-desktop/src/manifest.js`
- rejects wildcard origins
- requires hosted URL to be HTTPS
- permits localhost/127.0.0.1 only for local development
- keeps bridge URL loopback-only
- enforces sandbox/context isolation/nodeIntegration security settings

### Bridge Runtime Module

File:

- `apps/oasis-desktop/src/bridge-runtime.js`

Owns:

- repo-root detection
- bridge health check
- bridge startup
- bridge shutdown
- bridge log path
- bridge log redaction
- Windows hidden child process behavior

Reason for split:

- keeps `main.js` from becoming an unmaintainable blob
- makes local runtime behavior testable and release-checkable
- isolates sidecar risk from browser shell code

### Diagnostics And Support Bundles

File:

- `apps/oasis-desktop/src/diagnostics.js`

App menu items added:

- `Desktop Diagnostics`
- `Create Support Bundle`

Diagnostics include:

- product name/version/channel
- OS/arch/Electron/Chrome/Node versions
- Command Center URL and allowed origins
- bridge health, repo root, process state, and log path
- Python/npm availability
- secure-store encryption availability
- release gates

Support bundle behavior:

- writes a local JSON support report under Electron user-data
- includes a redacted bridge-log tail
- does not serialize environment variables
- redacts obvious API key/token/secret/password/Bearer/sk-style values

### Secure Store Foundation

File:

- `apps/oasis-desktop/src/secure-store.js`

Behavior:

- wraps Electron `safeStorage`
- encrypts string values before writing
- decrypts values for future local runtime use
- exposes status for diagnostics
- does not log secrets

Current state:

- foundation only
- no API-key entry UI yet
- no hosted web page gets direct Node or secure-store access

### Release Metadata

File:

- `apps/oasis-desktop/scripts/write-release-metadata.js`

Behavior:

- scans `apps/oasis-desktop/dist`
- writes `release-metadata.json`
- writes `SHA256SUMS.txt`
- skips `win-unpacked`
- skips `.nsis.7z`
- rejects suspiciously small installer artifacts

Important catch:

- A failed NSIS build left a tiny `OASIS-AI-0.1.0-win-x64.exe` stub in `dist`.
- Release metadata caught it because it was too small to be a real installer.
- The stub and failed `.nsis.7z` were removed locally.
- The current metadata now includes only the real unpacked zip artifact.

### Release Check

File:

- `apps/oasis-desktop/scripts/release-check.js`

Checks:

- stable package name and main entry
- package lock exists
- manifest, README, RELEASE doc are included in packaged app
- no wildcard origins
- navigation deny-by-default
- sandbox/context isolation/nodeIntegration/webSecurity settings
- permission handler exists
- new-window and top-level navigation handlers exist
- external links leave desktop shell
- diagnostics and support-bundle menu items exist
- fallback page exists and fallback navigation is scoped
- diagnostics/support redaction exists
- support bundle does not serialize env vars
- secure store uses `safeStorage` and does not log secrets
- manifest validation exists
- bridge runtime module exists and keeps Windows child process hidden
- release metadata writes checksums and skips partial installer stubs

### CI Workflow

File:

- `.github/workflows/oasis-desktop.yml`

Behavior:

- manual and path-triggered desktop packaging workflow
- matrix targets:
  - Windows
  - macOS
  - Linux
- runs:
  - `npm ci`
  - `npm run doctor`
  - `npm run release:check`
  - `npm audit --audit-level=high`
  - platform build
  - `npm run release:metadata`
  - artifact upload

Production caveat:

- signing/notarization credentials are not configured yet
- CI workflow is a foundation, not a final public release pipeline

### Docs

Files:

- `docs/OASIS_DESKTOP_PRODUCT_STRATEGY.md`
- `docs/INDEX.md`
- `apps/oasis-desktop/README.md`
- `apps/oasis-desktop/RELEASE.md`

Docs cover:

- product goal
- Hermes reference pattern and non-copying boundary
- provider/runtime access axes
- multi-client manifest direction
- security boundaries
- current alpha foundation
- delivery timeline
- local alpha gate
- beta gate
- production gate

Root package commands added:

- `npm run desktop:doctor`
- `npm run desktop:release-check`
- `npm run desktop:release-metadata`
- `npm run desktop:dev`
- `npm run desktop:pack`
- `npm run desktop:build:win`

## Verification Completed

Desktop validation commands run:

- `node --check apps/oasis-desktop/src/main.js`
- `node --check apps/oasis-desktop/src/diagnostics.js`
- `node --check apps/oasis-desktop/src/secure-store.js`
- `node --check apps/oasis-desktop/src/manifest.js`
- `node --check apps/oasis-desktop/src/bridge-runtime.js`
- `node --check apps/oasis-desktop/scripts/doctor.js`
- `node --check apps/oasis-desktop/scripts/release-check.js`
- `node --check apps/oasis-desktop/scripts/write-release-metadata.js`
- `npm run desktop:release-check`
- `npm run desktop:doctor`
- `npm --prefix apps/oasis-desktop audit --audit-level=high`
- `npm run desktop:pack`
- `npm run desktop:release-metadata`
- ASAR content checks for packaged files

Command Center validation after access selector:

- `npm run typecheck` from `apps/command-center`
- `npm run build` from `apps/command-center`

Results:

- Desktop syntax checks passed.
- Desktop release check passed.
- Desktop doctor passed.
- Desktop npm audit found `0` high-severity vulnerabilities.
- Desktop unpacked Windows app built successfully.
- Desktop alpha zip generated successfully.
- Release metadata and SHA-256 checksums generated successfully.
- Command Center typecheck passed.
- Command Center Next.js production build passed.

Known warning:

- `electron-builder --dir` emits a Node deprecation warning from a dependency path involving `shell option true`. This appears to come from builder internals, not the desktop app's own doctor/release scripts.

## Current Artifact

Primary alpha artifact:

```text
apps/oasis-desktop/dist/OASIS-AI-0.1.0-win-x64-unpacked.zip
```

Checksum:

```text
0061c90ea95fffd3c6b413dcbe18a103880e858f9096ced49505e30fba377404  OASIS-AI-0.1.0-win-x64-unpacked.zip
```

Metadata:

```json
{
  "version": "0.1.0",
  "channel": "alpha",
  "artifacts": [
    {
      "file": "OASIS-AI-0.1.0-win-x64-unpacked.zip",
      "bytes": 136569906,
      "sha256": "0061c90ea95fffd3c6b413dcbe18a103880e858f9096ced49505e30fba377404"
    }
  ]
}
```

## Known Limitations

This is an alpha, not a public production installer.

Current limitations:

- Windows artifact is an unpacked zip, not a signed installer.
- `npm run desktop:build:win` failed on this Windows account during NSIS/winCodeSign steps because Windows blocked symlink/installer execution privileges.
- macOS and Linux artifacts have not been built locally.
- Code signing is not configured.
- macOS notarization is not configured.
- Auto-update channel is not configured.
- Final OASIS branded icons are not added.
- Bridge/runtime is not bundled; alpha starts the bridge from this repo when available.
- Secure store exists, but no user-facing local API-key entry UI exists yet.
- Per-agent local permission prompts are not implemented yet.
- Desktop app has not been manually opened and browser-smoked in this session.

## Recommended Next Build Steps

Highest-value next tasks:

1. Add branded desktop icons:
   - `apps/oasis-desktop/build/icon.ico`
   - `apps/oasis-desktop/build/icon.icns`
   - `apps/oasis-desktop/build/icon.png`

2. Add a real first-run screen:
   - sign in
   - select or confirm business profile
   - choose provider connection through OAuth/account sign-in, API key, or OASIS subscription
   - choose cloud workspace or this desktop access
   - show bridge/device status

3. Add local API-key UX:
   - use `secure-store.js`
   - never expose keys to hosted web content
   - decide whether local keys power only this desktop access or can sync encrypted cloud config

4. Bundle the sidecar/runtime:
   - stop depending on a repo clone for client machines
   - package Python bridge or replace sidecar with a signed local service
   - keep bridge loopback-only

5. Fix Windows installer path:
   - enable Windows Developer Mode or run packaging in CI
   - configure signing later
   - avoid sharing unsigned installer with clients

6. Build CI artifacts:
   - trigger `.github/workflows/oasis-desktop.yml`
   - inspect Windows/macOS/Linux artifacts
   - confirm metadata and checksums are uploaded

7. Add production release infrastructure:
   - Windows code signing
   - Apple Developer ID signing
   - macOS notarization
   - auto-updates
   - crash/support logs
   - release channel separation: alpha, beta, stable

8. Add desktop acceptance tests:
   - app launches
   - hosted dashboard loads
   - fallback page appears when URL is unreachable
   - external navigation opens system browser
   - diagnostics page opens
   - support bundle creates redacted JSON
   - bridge starts when repo exists
   - bridge stays offline gracefully when repo is absent

## Suggested Resume Commands

From repo root:

```bash
npm run desktop:doctor
npm run desktop:release-check
npm --prefix apps/oasis-desktop audit --audit-level=high
npm run desktop:pack
npm run desktop:release-metadata
```

For local development against local Command Center:

```powershell
cd apps/command-center
npm run dev
```

Then in another shell:

```powershell
$env:OASIS_COMMAND_CENTER_URL="http://localhost:3100"
npm run desktop:dev
```

For hosted alpha:

```powershell
npm run desktop:dev
```

## Git / Worktree Notes

Desktop-related uncommitted work includes:

- `.github/workflows/oasis-desktop.yml`
- `apps/oasis-desktop/**`
- `docs/OASIS_DESKTOP_PRODUCT_STRATEGY.md`
- `docs/INDEX.md`
- `package.json`
- `apps/command-center/components/ChatWidget.tsx`

Existing unrelated or inherited dirty files are also present in the worktree. Do not revert them without CC approval:

- SunBiz copy polish in multiple `apps/command-center/app/*/page.tsx` files
- `apps/command-center/components/sunbiz/ComingSoon.tsx`
- `brain/STATE.md`
- `scripts/send_gateway.py`
- `final_analysis.txt`
- `tmp_templates.txt`

The desktop artifact and dependencies are intentionally ignored:

- `apps/oasis-desktop/dist/`
- `apps/oasis-desktop/node_modules/`

## Product Judgment

The direction is sound.

The immediate product should not be "a wizard with a window." It should be:

- Command Center as the stable UI shell
- desktop app as the trusted local runtime
- API-key mode as the default simple client path
- This desktop as an explicit permission boundary for local files/tools
- client-specific experiences driven by manifests/profiles rather than forks

Do not blur provider credentials with local computer permissions. API keys should be able to power desktop automations once the desktop provider adapter is implemented; the security boundary is whether the agent has cloud workspace access or this desktop access.
