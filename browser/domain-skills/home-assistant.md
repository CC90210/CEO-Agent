# Home Assistant

## Site

- URL patterns: local Home Assistant dashboard URLs
- Auth assumptions: Aura may be logged in locally.
- Agent owner: Aura
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect device state, automations, dashboards, logs.
- Draft-only: prepare automation YAML or troubleshooting steps.
- Approval required: locks, cameras, alarms, network devices, resets, scenes affecting people, destructive config changes.

## Traps

- Local network state can be stale.
- Device actions may affect the home immediately.
- Do not inspect cameras or privacy-sensitive streams unless CC asks.

## Approval Gates

Approval required before any action that changes physical devices, privacy state, network state, alarms, locks, cameras, or home access.
