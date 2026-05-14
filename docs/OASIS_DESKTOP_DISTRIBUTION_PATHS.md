# OASIS Desktop Distribution Paths

Date: 2026-05-13
Status: desktop release planning

## Bottom Line

Windows is available now for internal alpha testing through the portable ZIP. The Mac build is not the only option.

For public production distribution, OASIS needs one trusted path:

- Microsoft Store / MSIX submission, where Microsoft signs the Store package after certification.
- Authenticode code-signing certificate for direct website downloads.
- Enterprise allowlist / MDM distribution for a controlled client environment.

Unsigned direct-download `.exe` installers are not production-grade for broad Windows clients because SmartScreen, Defender, or company endpoint policy can block them.

## Current Alpha Path

Use the Windows portable ZIP:

```text
OASIS-AI-0.1.0-win-x64-portable.zip
```

Why this is the current preferred Windows alpha path:

- It downloads as a normal archive.
- The user extracts it to a normal folder.
- The app runs from the extracted folder instead of an installer trying to execute from Temp.
- It avoids confusing Windows with a macOS `.dmg`.

Known limitation:

- The executable inside the ZIP is still unsigned, so strict company endpoint controls can still block it.

## What Not To Do

Do not send Windows users the macOS `.dmg`. Windows will ask the user to pick an app because `.dmg` is an Apple disk image format.

Do not position the unsigned NSIS installer as the main Windows path. It can trigger the exact blocked-content behavior seen during alpha testing.

## Recommended Production Path

1. Keep the portable ZIP for internal alpha.
2. Add MSIX packaging in CI.
3. Submit the MSIX package to Microsoft Store / Partner Center for a trusted install experience.
4. In parallel, decide whether OASIS still wants a direct-download installer.
5. If yes, buy/provision an Authenticode code-signing certificate and turn on `OASIS_REQUIRE_WINDOWS_SIGNING=true`.

## Mac Path

Mac distribution should use Developer ID signing and Apple notarization before client release. Unsigned/not-notarized Mac builds are acceptable for internal alpha, but they are not the final client experience.

## Release Rule

Alpha can be unsigned if clearly labeled and tested internally.

Beta and production must be trusted by the OS distribution path.
