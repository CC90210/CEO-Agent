---
tags: [mac, sync, antigravity, deprecated-pointer]
purpose: Backward-compat pointer. The Mac-specific prompt has been generalized to support N machines (Mac + Linux + Windows-as-secondary). Body moved to docs/deploy/MULTI_MACHINE_PAIRING_PROMPT.md.
last_updated: 2026-05-09
superseded_by: docs/deploy/MULTI_MACHINE_PAIRING_PROMPT.md
---

# MAC COMMAND CENTER — Moved

> **The Mac-specific prompt has been generalized.** It used to live here
> as a Mac-only paste-ready setup; the same pattern now applies to
> macOS, Linux, and Windows-as-secondary machines.

## What changed (2026-05-09)

The 12-step pairing playbook didn't actually have anything Mac-specific
once we looked at it — `bravo bridge install` already supports launchd
(macOS), systemd user units (Linux), and schtasks/Startup-folder
(Windows). The Mac-only framing was just historical.

The generalized version:
- **`docs/deploy/MULTI_MACHINE_PAIRING_PROMPT.md`** — paste-ready prompt
  with OS-detection in STEP 0 and per-OS branches in STEPS 5/7/8/10
  for the install / verify steps. Same 12-step structure CC's Mac
  side already verified.

## What still lives here

This file is preserved as a **thin pointer for backward compatibility**.
Existing bookmarks / Obsidian links to `MAC_COMMAND_CENTER_PROMPT`
won't break — they just land here, see this notice, and follow the
link.

## Why we kept the file

CC's saved Antigravity prompts may reference this filename. Deleting
it would silently break those references; keeping a 30-line pointer
costs nothing and preserves the audit trail (the verified field below
documents the Mac-side stress test that originally proved out the
generalized pattern).

## Original Mac-side verification (preserved for record)

Stress-tested end-to-end on 2026-05-09 against commit dd0044f+. Battery:
T1 idempotent install · T2 KeepAlive respawn · T3 token wipe + re-pair ·
T4 stale-token (401) recovery · T5 network failure modes (DNS / timeout /
503) · T6 100-concurrent /warm-status · T7 reboot proxy · T8 stale-PID +
port-collision. 8/8 passed. Two cmd_install bugs (py-undef + missing
WorkingDirectory) fixed in 894585b; Linux parity confirmed via the
shared `bravo bridge install` code path.

## Obsidian Links
- [[docs/deploy/MULTI_MACHINE_PAIRING_PROMPT]] (canonical — paste this)
- [[brain/CROSS_MACHINE_SYNC]] (the rules)
- [[brain/SECURITY_MODEL]] (how pairing actually works under the hood)
