# Workstation Deep Audit

Generated: 2026-04-21

Machine audited: `CCPC`
Repo/workstation root: `C:\Users\User\Business-Empire-Agent`

## Executive Read

The machine is now much safer than it was when "YOLO mode" was active. Terminal AI commands are guarded, Windows Defender is active, Controlled Folder Access is on, Attack Surface Reduction rules are configured, Long Paths are enabled, the High Performance power plan is active, and public inbound firewall exposure has been reduced heavily.

The biggest remaining risks are not subtle:

- Secure Boot is disabled.
- BitLocker is disabled on `C:`.
- The main local user account reports `PasswordRequired=False`.
- No recent full Defender scan is recorded.
- The Node dependency tree still has critical audit findings.
- The workstation is hardware-bottlenecked for serious local AI: 16 GB RAM, RAM running at 2133 MHz, no NVIDIA GPU, no WSL.

## Actions Applied

- Removed unsafe AI terminal defaults from the PowerShell profile.
- Replaced Claude/Gemini YOLO aliases with guarded commands.
- Enabled Windows Long Paths.
- Activated the High Performance power plan.
- Hardened public inbound firewall rules for AI/dev tools, old driver installers, games, Zoom, Teams, TikTok Live Studio, ASUS/Razer utilities, browser discovery, and old Office entries.
- Restricted the SSH firewall rule to Tailscale plus localhost.
- Confirmed Tailscale remains available.
- Confirmed PM2 AI services are online.
- Added repeatable diagnostics:
  - `scripts\ai_workstation_doctor.ps1`
  - `scripts\ai_operator.ps1`
  - `scripts\admin_secure_network_surface.ps1`
  - `scripts\admin_collect_security_snapshot.ps1`

## Security Findings

### Critical

1. Secure Boot is off.

   Admin snapshot: `secure_boot=false`.

   Fix: enable UEFI Secure Boot in BIOS after confirming the boot mode, disk layout, and GPU firmware are compatible. This is best done during the store upgrade visit or by someone comfortable with BIOS recovery.

2. BitLocker is off.

   Admin snapshot: `ProtectionStatus=0`, `EncryptionPercentage=0` on `C:`.

   Fix: enable device encryption or BitLocker only after the recovery key is backed up to the Microsoft account and/or printed/stored safely. Do not enable blindly before a BIOS/CPU/GPU upgrade.

3. The main Windows user does not require a password.

   Finding: local user `User` is enabled with `PasswordRequired=False`.

   Fix: set a strong Windows password and Windows Hello PIN. For a machine running agent automations, this is a real risk.

4. Node dependency audit has critical issues.

   Current `npm audit --audit-level=high` reports critical issues in `form-data` and `protobufjs`, plus transitive issues under `node-telegram-bot-api`.

   Fix order:
   - Run the safe `npm audit fix` path for `protobufjs`.
   - Replace or upgrade the Telegram bot library carefully; the audit force fix changes `node-telegram-bot-api` in a breaking direction, so it needs testing.

### High

- Defender is healthy: realtime protection, behavior monitoring, Tamper Protection, Controlled Folder Access, PUA protection, and ASR are active.
- Full Defender scan has no recent valid age recorded. Run one after the upgrade or overnight.
- SSH is listening, but firewall access is now restricted to Tailscale plus localhost. Do not disable SSH password auth until `authorized_keys` is installed and tested.
- Controlled Folder Access and ASR have exclusions for Antigravity, OBS, and VLC. That keeps your workflow usable, but it means those apps have extra trust. Keep extensions and plugins tight.
- AnyDesk service is disabled, but an AnyDesk startup entry still exists. If you do not use it, uninstall it or remove the startup entry.

### Medium

- 18 app upgrades are available via `winget`, including Git, GitHub CLI, Obsidian, Malwarebytes, Node.js LTS, VC++ Redistributables, FFmpeg, Telegram Desktop, Teams, and AnyDesk.
- Do not batch-upgrade Node/Python blindly; update developer tooling in a controlled pass and rerun tests.
- Local Codex/Claude health scored `12/13`; local hooks are still false while global hooks are true.

## Performance Findings

- CPU: AMD Ryzen 5 5600GT, 6 cores / 12 threads.
- Motherboard: ASUS PRIME B550M-A WIFI II.
- RAM: 16 GB installed as 2 x 8 GB Patriot 3200-series sticks, but currently configured at 2133 MHz.
- GPU: integrated AMD Radeon graphics only, plus a USB HDMI adapter. No NVIDIA CUDA device.
- Storage: Kingston 500 GB NVMe, healthy, but small for local models, recordings, and agent browser profiles.
- WSL is not installed. This blocks the cleanest Linux AI tooling path.
- Heavy live memory users include Antigravity, Bun, Chrome, Claude, Phone Link, Playwright/headless Chrome, and Wispr Flow.

## AI Agent Health

- `atlas-telegram`: online.
- `bravo-scheduler`: online.
- `bravo-telegram`: online.
- `python scripts\test_send_gateway.py`: 41 tests passed.
- `node --check telegram_agent.js`: passed.
- `python scripts\codex_health.py --json`: `12/13`, grade `B`.

## Recommended Fix Order

1. Reboot once. Long Paths and TPM state both indicate a restart is pending or useful.
2. Set a real Windows account password and Windows Hello PIN.
3. Run a full Defender scan overnight.
4. During the hardware upgrade visit, enable Secure Boot after BIOS/firmware checks.
5. Enable BitLocker only after saving the recovery key.
6. Upgrade RAM/GPU/storage.
7. Install NVIDIA drivers, verify `nvidia-smi`, then install WSL 2 and local AI tools.
8. Clean up npm audit findings in a tested dependency pass.
9. Remove AnyDesk if it is not intentionally used.

## Useful Commands

```powershell
npm run ai:doctor
npm run ai:services
npm run ai:logs
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\admin_collect_security_snapshot.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\admin_secure_network_surface.ps1
```


## Related
- [[docs/INDEX]]
- [[brain/CAPABILITIES]]


## Related (graph)

- [[docs/INDEX]]
- [[docs/AGENT_REPO_CROSS_ANALYSIS_2026-04-22]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
