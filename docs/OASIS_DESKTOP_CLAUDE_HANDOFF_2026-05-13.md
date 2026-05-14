# OASIS Desktop + SunBiz Portal Handoff

Date: 2026-05-13
Repo: `Business-Empire-Agent`
Branch: `main`
Authoring agent: Codex
Audience: Claude Code / Bravo

## Executive Summary

Two production-facing pushes were completed after the previous desktop alpha handoff:

1. SunBiz now has a public review portal that renders demo-only data without requiring a login.
2. OASIS Desktop downloads are now OS-aware, with Windows users routed to the portable ZIP instead of accidentally opening a Mac `.dmg` or launching an unsigned installer from Temp.

Current production dashboard URL:

```text
https://agent-dashboard-cc90210.vercel.app
```

Current desktop download page:

```text
https://agent-dashboard-cc90210.vercel.app/download
```

Current SunBiz public demo:

```text
https://agent-dashboard-cc90210.vercel.app/demo/sun
```

## Latest Commits Pushed

### `42df249` — Add public SunBiz demo portal

Files changed:

- `apps/command-center/app/api/demo/sun/route.ts`
- `apps/command-center/app/demo/sun/page.tsx`
- `apps/command-center/app/layout.tsx`
- `apps/command-center/middleware.ts`
- `docs/INDEX.md`
- `docs/SUNBIZ_CLOUD_PORTAL_ARCHITECTURE.md`

Behavior:

- `/demo/sun` is now public and renders the SunBiz Command Center shell using demo-only data.
- `/api/demo/sun` no longer requires auth; it sets the Sun demo cookie and redirects back to `/demo/sun`.
- The root layout infers the Sun demo shell directly from paths starting with `/demo/sun`, so direct visits render the Sun Biz sidebar even before a cookie exists.
- Middleware explicitly allows `/demo/sun` and `/api/demo/sun` without allowing broader private app routes.
- SunBiz cloud/API guidance was later consolidated into this handoff during the 2026-05-14 Markdown cleanup.

Production verification:

```text
https://agent-dashboard-cc90210.vercel.app/demo/sun
```

Verified live production HTML contains:

- `Welcome to your Command Center`
- `Sun Biz Funding`
- `Solara`

Verified it does not contain a login redirect.

### `adcb4e6` — Make desktop downloads OS-aware

Files changed:

- `apps/command-center/app/api/download/desktop/route.ts`
- `apps/command-center/app/download/page.tsx`
- `apps/command-center/middleware.ts`
- `apps/oasis-desktop/RELEASE.md`
- `apps/oasis-desktop/scripts/artifact-check.js`
- `docs/INDEX.md`
- `docs/OASIS_DESKTOP_DISTRIBUTION_PATHS.md`

Behavior:

- Added public route `/api/download/desktop`.
- Browser OS is inferred from `User-Agent`.
- Windows browsers redirect to the Windows portable ZIP.
- Mac browsers redirect to the macOS DMG.
- Linux browsers redirect to the AppImage.
- Explicit `platform=` query params are supported:
  - `platform=windows`
  - `platform=windows-installer`
  - `platform=mac`
  - `platform=linux`
  - `platform=linux-deb`
  - `platform=checksums`
- `/download` now has a primary `Download for this computer` button.
- Windows copy now clearly says not to open a Mac `.dmg` on Windows.
- `artifact-check.js` was hardened:
  - portable ZIP is the alpha release gate
  - tiny local NSIS installer stubs warn instead of blocking the working ZIP path
  - any `.exe` included in release metadata must still pass the non-stub size gate
- Desktop distribution guidance was later consolidated into this handoff during the 2026-05-14 Markdown cleanup.

Production verification:

```text
https://agent-dashboard-cc90210.vercel.app/download
```

Verified live production HTML contains:

- `Download for this computer`
- `Windows portable zip`
- `will make Windows ask you to pick an app`

Verified live production redirect:

```text
curl -I -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" https://agent-dashboard-cc90210.vercel.app/api/download/desktop
```

Returns `307` to:

```text
https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-win-x64-portable.zip
```

## Current Desktop Release Assets

GitHub release:

```text
https://github.com/CC90210/CEO-Agent/releases/tag/oasis-desktop-v0.1.0-alpha.4
```

Release status:

- tag: `oasis-desktop-v0.1.0-alpha.4`
- name: `OASIS Desktop v0.1.0 alpha.4`
- draft: `false`
- prerelease: `true`

Assets:

- `OASIS-AI-0.1.0-win-x64-portable.zip`
  - size: `136631188`
  - sha256: `07dea7cf78ce4ae36321dbdebb0e0c246dbf0c173699c2bd31e3fa9fa88e9c76`
  - URL: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-win-x64-portable.zip`
- `OASIS-AI-0.1.0-win-x64.exe`
  - size: `95667041`
  - sha256: `18e09eb6efd275d06c6b2f8f1e116f3edfe9635e888b0d6fb04cf069f3db23cd`
  - URL: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-win-x64.exe`
- `OASIS-AI-0.1.0-mac-arm64.dmg`
  - size: `109795648`
  - sha256: `3119cdd4f3e6b7e7f61e715375fa980937964abedc8a393d9d8273bc120d6d63`
  - URL: `https://github.com/CC90210/CEO-Agent/releases/download/oasis-desktop-v0.1.0-alpha.4/OASIS-AI-0.1.0-mac-arm64.dmg`
- `OASIS-AI-0.1.0-linux-x86_64.AppImage`
  - size: `115390258`
  - sha256: `7df499a4fe4d0f9746d41ff6e13b85bcc6368ec59287820f288fa1508f5ef777`
- `OASIS-AI-0.1.0-linux-amd64.deb`
  - size: `90338512`
  - sha256: `0fc038c210e54b331169f8d443d12fa423eb0a43c5a900ec051e66e36bce33ab`
- `SHA256SUMS-release.txt`
  - size: `495`

Important: Windows users should start with the portable ZIP. The `.exe` installer exists on GitHub and is a real-size artifact, but it is unsigned and may trigger endpoint security. The local `apps/oasis-desktop/dist/OASIS-AI-0.1.0-win-x64.exe` is currently a tiny stale stub and must not be used.

## Verification Completed This Session

Command Center:

```bash
npm run build
npm run typecheck
```

Results:

- Build passed.
- Typecheck passed.

Desktop:

```bash
npm run desktop:doctor
npm run desktop:release-check
npm run desktop:auth-check
npm run desktop:artifact-check
npm --prefix apps/oasis-desktop audit --audit-level=high
npm run desktop:signing-check
```

Results:

- Doctor passed.
- Release check passed.
- Auth navigation check passed.
- Artifact check passed with warning about the local stale installer stub.
- Audit reported `0` high-severity vulnerabilities in `apps/oasis-desktop`.
- Signing check reported Windows artifacts are unsigned, allowed because this is still alpha.

Live deployment:

```bash
npx vercel ls
```

Latest production deployment after `adcb4e6`:

```text
https://agent-dashboard-a9k9gyzh0-cc90210.vercel.app
```

Status: `Ready`

## Known Limitations / Blockers

### Windows distribution

Windows is available now through the portable ZIP, but it is not yet a seamless public production install.

Why:

- The app executable is unsigned.
- Strict Windows security, Defender, SmartScreen, or company endpoint policy can still block it.
- The portable ZIP avoids the Temp-launched installer problem, but it does not replace OS trust.

Production-grade options:

- Microsoft Store / MSIX, where Microsoft signs Store packages after certification.
- Direct-download Authenticode signing with a Windows code-signing certificate.
- Enterprise allowlist / MDM distribution for controlled client environments.

### Mac distribution

Mac alpha DMG exists and downloads, but production-grade Mac release still needs:

- Apple Developer ID signing.
- Notarization.

### Desktop runtime

The desktop app shell exists and loads the hosted Command Center. It has:

- secure Electron defaults
- OAuth navigation handling
- diagnostics
- support bundle foundation
- secure-store foundation
- bridge sidecar startup when repo-local bridge is available

Still not final:

- local API-key entry UI is not finished
- bundled sidecar/runtime is not shipped
- per-agent local permission prompts are not finished
- auto-update channel is not configured
- final branded desktop icons are not added
- manual Windows download/extract/open/sign-in test still needs a human pass
- Google sign-in inside the desktop shell has an automated navigation check but still needs a fresh manual end-to-end pass

### SunBiz

SunBiz public demo is live and reviewable. Real SunBiz production path still needs:

- fresh real SunBiz account provisioning test
- tenant `custom_fields.command_center_profile_slug = "sun"`
- profile `primary_agent = "sunbiz"`
- staging SunBiz Agent API/worker
- live or sandbox JotForm/Text Torrent/email credentials
- pulse checks against those credentials

## Current Worktree Notes

After the pushed commits, the repo still has unrelated/inherited dirty files. Do not revert these unless CC explicitly asks.

Current dirty files:

- `apps/command-center/app/applications/page.tsx`
- `apps/command-center/app/commissions/page.tsx`
- `apps/command-center/app/contacts/page.tsx`
- `apps/command-center/app/email-blast/page.tsx`
- `apps/command-center/app/embed/page.tsx`
- `apps/command-center/app/funded-deals/page.tsx`
- `apps/command-center/app/import/page.tsx`
- `apps/command-center/app/leads/page.tsx`
- `apps/command-center/app/lenders/page.tsx`
- `apps/command-center/app/offers/page.tsx`
- `apps/command-center/app/renewals/page.tsx`
- `apps/command-center/app/templates/page.tsx`
- `apps/command-center/components/sunbiz/ComingSoon.tsx`
- `brain/STATE.md`
- `data/email_suppressions.csv`
- `scripts/email_engine.py`
- `scripts/send_gateway.py`
- `scripts/test_send_gateway.py`
- `final_analysis.txt`
- `scripts/test_email_engine.py`
- `tmp_templates.txt`

The dirty `brain/STATE.md` entry was updated by `state_sync.py` logging.

## Suggested Next Claude Code Push

Priority 1: make the Windows portable ZIP self-explanatory.

Add `START_HERE_WINDOWS.txt` into `apps/oasis-desktop/dist/win-unpacked/` before zipping. The file should explain:

- extract the ZIP first
- open `OASIS AI.exe`
- do not open the Mac `.dmg` on Windows
- alpha is unsigned
- production clients require trusted distribution

Likely file:

- `apps/oasis-desktop/scripts/create-windows-portable.js`

Priority 2: add a live release asset check.

Add a script that HEAD-checks the GitHub release URLs and validates:

- HTTP 200 after redirects
- expected filenames
- minimum file sizes

Likely files:

- `apps/oasis-desktop/scripts/check-release-assets.js`
- `apps/oasis-desktop/package.json`
- root `package.json`
- `apps/oasis-desktop/scripts/release-check.js`
- `apps/oasis-desktop/RELEASE.md`

Suggested command:

```bash
npm run desktop:release-asset-check
```

Priority 3: publish alpha.5 only after the ZIP includes the start-here file.

Suggested release tag:

```text
oasis-desktop-v0.1.0-alpha.5
```

After publishing alpha.5:

- update `RELEASE_TAG` in `apps/command-center/app/download/page.tsx`
- update `/api/download/desktop` release tag
- update checksums displayed on `/download`
- run build/typecheck
- push to `main`
- verify Vercel production redirect

Priority 4: run human E2E on Windows.

Acceptance pass:

1. Open `https://agent-dashboard-cc90210.vercel.app/download`
2. Click `Download for this computer`
3. Confirm the downloaded file is `OASIS-AI-0.1.0-win-x64-portable.zip`
4. Extract it
5. Open `START_HERE_WINDOWS.txt`
6. Double-click `OASIS AI.exe`
7. Confirm app opens
8. Try Google sign-in
9. Confirm dashboard session sticks inside desktop shell
10. Open Desktop Diagnostics
11. Create Support Bundle

## Architecture Guidance For SunBiz

Use a cloud-first portal for SunBiz.

Recommended shape:

- Vercel-hosted Command Center remains the client-facing control plane.
- `SunBiz-Agent` should run as a hosted API/worker on a real VPS/container platform.
- Hostinger is acceptable only if it is a VPS with HTTPS, process supervision, logs, and secret handling.
- Do not make the production web app drive an interactive CLI over SSH.
- Keep CLI for admin/debug only.
- Dashboard should call authenticated HTTPS APIs.
- Provider keys/OAuth tokens should be encrypted server-side and never sent to the browser.
- Desktop bridge is only needed when the client explicitly needs local computer files/tools.

Minimum hosted API contract:

- `GET /health`
- `GET /integrations/status`
- `POST /forms/jotform`
- `POST /lead/intake`
- `POST /sms/send`
- `POST /agent/run`
- `POST /documents/search`

Production gates:

- public SunBiz demo route uses demo-only data
- real SunBiz provisioning sets `command_center_profile_slug = "sun"`
- real profile sets `primary_agent = "sunbiz"`
- Command Center to SunBiz API uses HMAC or signed bearer auth
- JotForm webhooks are signature-checked
- Text Torrent/Twilio sends are rate-limited and audited
- provider keys are encrypted and never exposed to browser sessions

## Consolidated Desktop Product Decisions

This is the only active OASIS Desktop + SunBiz handoff after the 2026-05-14 Markdown cleanup.

Desktop product shape:

- Command Center is the shared product shell for web and desktop.
- Provider connection and runtime access stay separate.
- Provider connection can be OAuth/account sign-in, API key, or OASIS-managed subscription.
- Runtime access can be cloud workspace or this desktop.
- Client-specific behavior should come from manifests: brand shell, enabled agents, integrations, permissions, playbooks, and default prompts.

Desktop security boundaries:

- cloud workspace must not read local files, spawn local tools, or call the local bridge
- desktop access requires the paired local app to be running
- local file/tool access must be explicitly allowlisted
- local bridge traffic stays loopback-only until replaced by a signed desktop transport
- browser-to-local requests need origin checks, local session tokens, tenant binding, and device binding
- raw API keys must never be logged, returned to the browser, or written into repo config

Distribution decisions:

- internal alpha can use unsigned artifacts if clearly labeled
- Windows alpha users should start with the portable ZIP, not the NSIS installer
- Windows beta/production needs MSIX/Microsoft Store, Authenticode signing, or enterprise allowlist/MDM
- Mac beta/production needs Developer ID signing and Apple notarization
- beta/production releases need trusted installers, signed updates, uninstall cleanup, crash reporting, support diagnostics, and acceptance testing per client shell

## Source Docs Consolidated

The following one-off docs were deleted on 2026-05-14 after their durable decisions were folded into this handoff:

- `docs/SUNBIZ_CLOUD_PORTAL_ARCHITECTURE.md`
- `docs/OASIS_DESKTOP_DISTRIBUTION_PATHS.md`
- `docs/OASIS_DESKTOP_PRODUCT_STRATEGY.md`
- `docs/handovers/2026-05-12-sunbiz-experience-layer-handover.md`
- `docs/handovers/2026-05-13-oasis-desktop-alpha-handover.md`

## State Sync Notes Written

`state_sync.py` notes were written for:

- public SunBiz demo portal deployment
- OS-aware desktop download deployment

Do not hand-edit auto-generated state sections if V6 mode/state guards are enabled later.
