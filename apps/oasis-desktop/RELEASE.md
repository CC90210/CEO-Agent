# OASIS Desktop Release Playbook

This playbook turns the desktop alpha into repeatable release work. It is intentionally practical: every gate either passes locally or becomes a visible blocker.

## Local Alpha Gate

Run from the repository root:

```bash
npm run desktop:doctor
npm run desktop:release-check
npm --prefix apps/oasis-desktop audit --audit-level=high
npm run desktop:pack
```

Expected local artifact:

```text
apps/oasis-desktop/dist/win-unpacked/OASIS AI.exe
```

Optional handoff zip:

```powershell
Compress-Archive -Path apps/oasis-desktop/dist/win-unpacked/* -DestinationPath apps/oasis-desktop/dist/OASIS-AI-0.1.0-win-x64-unpacked.zip -Force
npm run desktop:release-metadata
```

## Client Beta Gate

Before a client receives the app:

- App opens the hosted Command Center.
- Sign-in works inside the desktop shell.
- Provider connection options are explained separately from runtime access.
- Cloud workspace can chat without starting the bridge.
- This desktop shows offline when the bridge is unavailable.
- This desktop routes to the local bridge when available.
- Bridge log opens from the app menu.
- Desktop Diagnostics opens from the app menu.
- Support bundle generation creates a redacted JSON report.
- Command Center load failure shows the local fallback page.
- Secure store reports encryption availability in diagnostics.
- External links open in the system browser.
- Untrusted navigation is blocked from replacing the Command Center.
- No API keys, tokens, or secrets appear in logs.

## Production Gate

Before broad distribution:

- Windows code-signing certificate configured.
- macOS Developer ID signing configured.
- macOS notarization configured.
- Linux AppImage/deb artifacts generated in CI.
- Auto-update channel configured and tested.
- OS keychain storage implemented for local provider keys.
- Bundled sidecar/runtime shipped so clients do not need a repo clone.
- Per-agent local permission prompts implemented.
- Crash/support bundle command implemented.
- Release artifact checksums published.

## Known Alpha Limitations

- The current local Windows artifact is an unpacked app folder, not a signed installer.
- The sidecar starts from this repo when it can find `bravo_cli.local_bridge`; it is not bundled yet.
- macOS and Linux artifacts should be generated through CI or native builders.
- The app icon still needs final branded `.ico`, `.icns`, and `.png` assets.
