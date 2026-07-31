---
tags: [docs]
last_updated: 2026-04-27
---

# AI Workstation Roadmap

This machine is the Windows production node for the agent stack. The goal is a powerful, symbiotic AI workstation: fast enough for heavy browser automation now, ready for GPU-accelerated local models later, and guarded enough to avoid accidental destructive control.

## Current Baseline

- CPU: AMD Ryzen 5 5600GT, 6 cores / 12 threads.
- RAM: 16 GB installed.
- RAM speed observed from Windows: 2133 MHz, despite 3200-series DIMMs.
- Storage: 500 GB Kingston NVMe SSD, healthy.
- GPU: AMD integrated graphics only; no NVIDIA CUDA stack yet.
- Power plan: High performance active.
- Security: Defender real-time protection and Controlled Folder Access active.
- AI tools: Claude Code, Gemini CLI, Node, Python, uv, Bun, PM2 installed.
- Missing for future local AI: WSL 2, Ollama/local model runner, NVIDIA GPU/driver.

## What This Workstation Should Become

- Windows stays the production automation node.
- PM2 owns long-running business daemons.
- Telegram remains the remote control plane.
- PowerShell gets clean operator aliases, not blanket YOLO aliases.
- Local model serving becomes available after GPU/RAM upgrades.
- Defender stays active, with targeted allow-listing only when a real automation needs it.

## Immediate Software Enhancements

Run:

```powershell
npm run ai:doctor
npm run ai:services
npm run ai:logs
```

Optional admin baseline:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\User\Business-Empire-Agent\scripts\admin_enable_ai_workstation_features.ps1
```

That admin script:

- Enables Windows Long Paths.
- Keeps High performance power plan active.
- Does not weaken Defender, firewall, or Controlled Folder Access.

## BIOS / Hardware Actions

These cannot be done safely from Windows:

- Enable DOCP/XMP in BIOS so the RAM runs closer to its rated 3200 MHz.
- Upgrade to 32 GB minimum, 64 GB preferred.
- Add an NVIDIA RTX GPU with at least 12 GB VRAM; 16-24 GB is the better local-AI range.
- Add a second 1-2 TB NVMe SSD for model weights, recordings, browser profiles, and datasets.
- Confirm PSU and cooling are sized for sustained GPU workloads.

## After GPU Install

- Install the NVIDIA driver.
- Verify:

```powershell
nvidia-smi
```

- Install a local model runner such as Ollama or LM Studio.
- Add local-model routing for private/offline tasks.
- Store models on a dedicated SSD path, not inside the repo.
- Add health checks for VRAM, model server, and GPU temperature.

## Control Philosophy

Powerful does not mean reckless:

- Default AI commands should be guarded.
- Destructive desktop/system actions should require explicit approval.
- Raw shell passthrough should stay disabled in Telegram.
- Production daemons should have single-instance locks.
- Security events should be visible through `ai-operator security-events`.

## Related
- [[docs/INDEX]]
- [[brain/CAPABILITIES]]
