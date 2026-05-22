# Desktop Code Signing — CLI Cheat Sheet

Mac Gatekeeper and Windows SmartScreen both warn loudly on unsigned
binaries downloaded from the internet. To distribute the desktop app
without those warnings:

- **Mac:** an Apple Developer ID Application certificate **+** Apple
  notarization round-trip.
- **Windows:** an Authenticode code-signing certificate (EV preferred
  — gets through SmartScreen reputation faster).

This document is the canonical "what to set, what to run" reference.
Source of truth: `scripts/build-platform.js`.

---

## Mode matrix

| Command | Signed? | Notarized? | Distribution-ready? |
|---|---|---|---|
| `npm run build:mac:unsigned` | No | No | Local testing only |
| `npm run build:mac` *(no env)* | No | No | Local testing only |
| `npm run build:mac` *(CSC_LINK + CSC_KEY_PASSWORD)* | Yes | No | Mac launches but Gatekeeper still warns |
| `npm run build:mac` *(all env vars)* | Yes | Yes | Ship it |
| `npm run build:win:unsigned` | No | n/a | Local testing only — SmartScreen warns |
| `npm run build:win` *(no env)* | No | n/a | Local testing only — SmartScreen warns |
| `npm run build:win` *(CSC_LINK + CSC_KEY_PASSWORD)* | Yes | n/a | Ship it (EV cert clears SmartScreen faster) |

The build wrapper prints which mode it ran in. Read that line.

---

## Mac — full signed + notarized build

### One-time setup

1. **Apple Developer Program membership** (US$99/year): https://developer.apple.com/programs/
2. **Create the cert.** Apple Developer → Certificates → "+" → "Developer ID Application" → follow the CSR steps. Download the .cer, double-click to install into Keychain Access.
3. **Export the .p12.**
   - Keychain Access → "login" keychain → Certificates tab.
   - Find your "Developer ID Application: <your name> (<team id>)" cert.
   - Right-click → Export → File format `.p12` → save → set a password.
   - The password you set IS your `CSC_KEY_PASSWORD`.
4. **App-specific password.** https://appleid.apple.com → Sign-In and Security → App-Specific Passwords → "+" → label "OASIS notary" → copy the value.

### Per-build env vars

```bash
export CSC_LINK="/absolute/path/to/oasis-developer-id.p12"
export CSC_KEY_PASSWORD="the-p12-password-you-set"
export APPLE_ID="conaugh@oasisai.work"
export APPLE_APP_SPECIFIC_PASSWORD="aaaa-bbbb-cccc-dddd"
export APPLE_TEAM_ID="ABCD123456"   # 10-char Team ID from Apple Developer
```

### Install the notarize dep + build

```bash
cd apps/oasis-desktop
npm install --save-dev @electron/notarize
npm run build:mac
```

The build wrapper boots `electron-builder --mac`, signs with the
Developer ID cert, then calls `scripts/notarize.js` (afterSign hook)
which submits to Apple's notary service via `notarytool`. Typical
notarize round-trip: 2–10 minutes.

Output: `dist/OASIS-AI-<version>-mac-universal.dmg` (and a `.zip`).
Both notarized, both Gatekeeper-clean on first launch.

---

## Windows — Authenticode signed build

### One-time setup

1. **Buy a code-signing certificate.** EV (Extended Validation) is preferred — it gets through Microsoft Defender SmartScreen reputation immediately. OV (Organization Validation) works but new publishers face a "warm-up period" where SmartScreen still warns until enough end-users have run the binary.
   - Recommended vendors: DigiCert (EV ~US$400/yr), Sectigo, SSL.com.
   - EV certs ship on a physical token (USB) or via cloud HSM (Azure Trusted Signing, SSL.com eSigner). Cloud HSMs are easier on CI.
2. **Export to .pfx** (for local use) or configure HSM access (for CI).

### Per-build env vars

```bash
# .pfx file path:
export CSC_LINK="C:\path\to\oasis-codesign.pfx"
export CSC_KEY_PASSWORD="the-pfx-password"
# OR https URL to an HSM-fronted cert blob:
# export CSC_LINK="https://example.com/cert.pfx"
```

### Build

```bash
cd apps/oasis-desktop
npm run build:win
```

Output: `dist/OASIS-AI-<version>-win-x64.exe` (NSIS installer) and
`dist/OASIS-AI-<version>-portable.exe` (single-file portable). Both
Authenticode-signed when env vars are present.

### SmartScreen warm-up note

Even with a valid EV cert, brand-new publisher identities can hit a
short reputation-warmup window where SmartScreen displays "Unknown
publisher" once or twice. The fastest fix is **distribute the
artifact to a few real users** — Microsoft's reputation engine
clears the warning after a few installs.

---

## Unsigned local builds — for fast iteration

```bash
# Mac
npm run build:mac:unsigned

# Windows
npm run build:win:unsigned
```

Both produce launchable binaries you can install + run locally.
Operators downloading these will see:

- **Mac:** Gatekeeper modal — "OASIS AI cannot be opened because the developer cannot be verified." Right-click → Open → confirm. Or run `xattr -dr com.apple.quarantine /Applications/OASIS\ AI.app` from Terminal.
- **Windows:** SmartScreen modal — "Windows protected your PC." More info → Run anyway.

These warnings are EXPECTED for unsigned builds. Don't ship unsigned
artifacts to paying clients — they'll think it's malware.

---

## Verifying a signature after the fact

### Mac
```bash
codesign -dv --verbose=4 "/Applications/OASIS AI.app"
spctl -a -t exec -vv "/Applications/OASIS AI.app"
```
A notarized build prints `accepted` + `source=Notarized Developer ID`.

### Windows
```powershell
Get-AuthenticodeSignature "C:\Program Files\OASIS AI\OASIS AI.exe"
# Or via signtool:
signtool verify /pa /v "C:\Program Files\OASIS AI\OASIS AI.exe"
```
A valid signature prints `Status: Valid` + the certificate chain.

---

## Troubleshooting

- **Mac `errSecInternalComponent`:** Keychain access denied to
  `codesign` — open Keychain Access, right-click the cert, "Get
  Info", expand "Access Control", add `codesign` to "Always Allow".
- **Mac notarize "Invalid Credentials":** APPLE_APP_SPECIFIC_PASSWORD
  has gone stale (90-day rotation) — regenerate at appleid.apple.com.
- **Win `Unable to sign` despite CSC_LINK set:** path must use double
  backslashes in JSON env files (PowerShell `$env:CSC_LINK` handles
  it correctly).
- **Win SmartScreen still warns with valid EV cert:** reputation
  warm-up. Ship to 5–10 users, wait 24h, retest.
