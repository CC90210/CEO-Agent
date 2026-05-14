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
npm run desktop:portable:win
npm run desktop:release-metadata
```

The public Windows alpha should point clients to `OASIS-AI-0.1.0-win-x64-portable.zip` first. That archive extracts to a normal folder and avoids the NSIS installer launching from a blocked Temp path on locked-down Windows machines.

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

- Windows code-signing certificate configured through `WINDOWS_CSC_LINK` and `WINDOWS_CSC_KEY_PASSWORD`.
- GitHub repository variable `OASIS_REQUIRE_WINDOWS_SIGNING=true` enabled so unsigned Windows artifacts fail CI.
- macOS Developer ID signing configured.
- macOS notarization configured.
- Linux AppImage/deb artifacts generated in CI.
- Auto-update channel configured and tested.
- OS keychain storage implemented for local provider keys.
- Bundled sidecar/runtime shipped so clients do not need a repo clone.
- Per-agent local permission prompts implemented.
- Crash/support bundle command implemented.
- Release artifact checksums published.

## Windows Signing Gate

The alpha can build unsigned artifacts, but a seamless Windows install requires a trusted Authenticode signature.

For production:

1. Buy or provision a Microsoft Authenticode code-signing certificate for OASIS AI Solutions.
2. Store the certificate in GitHub Actions as `WINDOWS_CSC_LINK`.
3. Store the certificate password as `WINDOWS_CSC_KEY_PASSWORD`.
4. Set the GitHub repository variable `OASIS_REQUIRE_WINDOWS_SIGNING=true`.
5. Run the `OASIS Desktop` workflow.
6. Confirm `npm run signing:check` reports a valid Windows installer and app executable signature.

If the signing variable is off, CI reports signature status but allows unsigned alpha artifacts.

## Known Alpha Limitations

- Windows artifacts are unsigned until the production certificate is configured.
- Locked-down Windows machines may block unsigned alpha builds even when the archive downloads correctly.
- Windows users should not download the macOS `.dmg`; Windows will ask which app should open it.
- The sidecar starts from this repo when it can find `bravo_cli.local_bridge`; it is not bundled yet.
- macOS and Linux artifacts should be generated through CI or native builders.
- The app icon still needs final branded `.ico`, `.icns`, and `.png` assets.
