# Computer Store Upgrade Brief

Generated: 2026-04-21

Please use this as the parts and service brief for upgrading this desktop into a stronger AI workstation.

## Current Machine

- Motherboard: ASUS PRIME B550M-A WIFI II
- CPU: AMD Ryzen 5 5600GT with Radeon Graphics, 6 cores / 12 threads
- RAM: 16 GB total, 2 x 8 GB Patriot 3200-series, currently running at 2133 MHz
- GPU: integrated AMD Radeon graphics only, no NVIDIA GPU
- Storage: Kingston SNV3S500G 500 GB NVMe
- Network: Wi-Fi 6 board, Tailscale used for private remote access
- Goal: Windows AI workstation for coding agents, browser automation, content creation, Telegram/PM2 services, and local AI model work

## Technician Checklist

Before selling/installing parts:

- Confirm PSU brand, model, wattage, age, and PCIe/12V-2x6 connector support.
- Confirm case GPU clearance, including power cable bend clearance.
- Confirm airflow and whether extra case fans are needed.
- Update BIOS to the latest stable ASUS release for PRIME B550M-A WIFI II.
- After BIOS update, enable DOCP/XMP for the RAM.
- Confirm Secure Boot can be enabled cleanly.
- Do not enable BitLocker until the recovery key is backed up.

## Priority 1: RAM

Install 64 GB RAM if possible.

Recommended target:

- 2 x 32 GB DDR4 kit
- DDR4-3200 or DDR4-3600
- Prefer a kit on the ASUS QVL or a mainstream reliable kit the store can validate
- Enable DOCP/XMP in BIOS
- Verify Windows reports the memory running near rated speed, not 2133 MHz

Why: 16 GB is already tight for Antigravity/Chrome/Bun/Claude/Playwright plus agents. 64 GB is the practical sweet spot for this machine.

## Priority 2: NVIDIA GPU

For local AI, VRAM matters more than almost everything else. Do not buy an 8 GB GPU if the goal is local AI.

Options:

1. Budget AI option: NVIDIA RTX 5060 Ti 16 GB.
   - Good entry point for CUDA, local LLM experiments, image tools, and creator apps.
   - Make sure it is the 16 GB model, not the 8 GB model.

2. Strong middle option: NVIDIA RTX 5070 Ti 16 GB or RTX 5080 16 GB.
   - Better for local AI, video workflows, and heavier multitasking.
   - Expect an 850 W quality PSU for many cards.
   - Check card length and slot thickness.

3. Best consumer local-AI option: NVIDIA RTX 5090 32 GB.
   - Best fit if the goal is serious local models and maximum longevity.
   - Requires a serious PSU and careful case clearance.
   - NVIDIA lists RTX 5090 Founders Edition at 575 W total graphics power and 1000 W required system power.

## Priority 3: Storage

Add a dedicated NVMe SSD for AI work.

Recommended target:

- 2 TB NVMe SSD preferred
- 1 TB minimum if budget is tight
- Keep the current 500 GB Kingston NVMe as the OS/app drive if it is healthy
- Put models, datasets, generated media, browser automation profiles, and recordings on the new drive

The board has two M.2 slots. With non-G Ryzen 5000 desktop CPUs, ASUS lists the first M.2 slot as PCIe 4.0 x4 capable; with G-series APUs, PCIe behavior is lower.

## Priority 4: CPU

The current Ryzen 5 5600GT can stay if budget is focused on RAM/GPU first.

If upgrading CPU while staying on AM4:

- Productivity/core-heavy option: Ryzen 9 5900X or 5950X, with proper cooling.
- Gaming/efficient high-performance option: Ryzen 7 5700X3D or 5800X3D, if available and priced fairly.

Important: ASUS lists the current 5600GT as a 5000 G-series/Cezanne CPU. The motherboard specs list Ryzen 5000 G-series expansion at PCIe 3.0 x16, while non-G Ryzen 5000 desktop CPUs get PCIe 4.0 x16. For local AI this is not fatal, but with a high-end GPU it is worth knowing.

## Priority 5: PSU And Cooling

Ask the store to size this based on the actual GPU chosen.

- RTX 5060 Ti 16 GB: PSU depends on exact card and current PSU quality.
- RTX 5070 Ti / RTX 5080: plan around a high-quality 850 W Gold-class PSU unless the card vendor says otherwise.
- RTX 5090: plan around 1000 W or better, with the correct modern GPU power connector and cable clearance.
- Add or upgrade cooling if CPU/GPU thermals will be tight.

## After Install Validation

Have the store show or document:

- BIOS updated.
- DOCP/XMP enabled and RAM running correctly.
- GPU physically fits and power cable is not sharply bent.
- NVIDIA driver installed from NVIDIA or the GPU vendor.
- `nvidia-smi` works.
- Windows Device Manager has no unknown/problem devices.
- Short CPU/GPU stress test passed.
- Idle and load temperatures are reasonable.
- Secure Boot enabled if confirmed safe.
- BitLocker left off unless recovery key handling is done with you present.

## Sources Checked

- ASUS PRIME B550M-A WIFI II tech specs: https://www.asus.com/us/motherboards-components/motherboards/prime/prime-b550m-a-wifi-ii/techspec/
- ASUS PRIME B550M-A WIFI II CPU support: https://www.asus.com/us/supportonly/prime%2520b550m-a%2520wifi%2520ii/helpdesk_cpu/
- NVIDIA RTX 5060 family specs: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5060-family/
- NVIDIA RTX 5080 specs: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5080/
- NVIDIA RTX 5090 specs: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/
- ASUS TUF RTX 5070 Ti 16 GB specs: https://www.asus.com/us/motherboards-components/graphics-cards/tuf-gaming/tuf-rtx5070ti-16g-gaming/techspec/


## Related
- [[docs/INDEX]]
- [[brain/CAPABILITIES]]
