# OASIS Desktop Product Strategy

Date: 2026-05-13

## Goal

Turn the Agent Command Center into a downloadable desktop product for macOS, Windows, and Linux. The desktop app should keep the same Command Center layout, but package it with a trusted local runtime so each client can use API keys, optional subscriptions, and local computer access without needing a terminal-first setup wizard.

## Reference Pattern

Hermes is useful as a product reference because it separates the visible app experience from provider configuration and runtime execution. OASIS should copy that pattern, not their documentation, branding, source text, or assets.

Reference links:

- https://github.com/nousresearch/hermes-agent
- https://hermes-ai.net/desktop/
- https://hermes-agent.nousresearch.com/docs/getting-started/quickstart
- https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- https://hermes-agent.nousresearch.com/docs/developer-guide/architecture

## Product Shape

The Command Center is the product shell. It should look and behave the same in web and desktop, with the desktop app adding local capabilities underneath.

The app should separate two product axes.

Provider connection:

- OAuth or account sign-in where supported, such as Claude Code or future provider OAuth.
- API key entry for OpenRouter, Anthropic, OpenAI, Google, compatible local endpoints, and future providers.
- OASIS subscription billing for clients who want OASIS-managed model access.

Runtime access:

- Cloud workspace: hosted Command Center only, without local files, browser, or desktop tools.
- This desktop: local bridge/sidecar with approved local files, browser actions, automations, and skills.

The target product contract is:

```text
Provider connection + Runtime access = agent capability
```

An API key should be able to power desktop automations once the desktop provider adapter exists. The current alpha still uses Claude Code CLI for non-local desktop bridge execution and uses provider API keys through the hosted `/api/chat` cloud path.

## Multi-Client Experience Layer

The same infrastructure should render different products per client. The durable pieces are auth, provider config, bridge pairing, device identity, encrypted keys, tool execution, audit logs, and deployments.

The client-specific pieces should come from manifests:

- Brand shell: name, logo, colors, route labels, homepage hero, onboarding language.
- Agent family: enabled agents, primary agent, welcome messages, suggested prompts, model/provider defaults.
- Integration pack: business-specific connectors such as JotForm, Text Torrent, Gmail, Stripe, CRM, n8n, or file folders.
- Permission pack: which local paths, tools, and automations the desktop runtime may access.
- Playbook pack: business-specific docs such as Sun Biz's Unified Onboarding Manual.

## Recommended Desktop Architecture

Use a small desktop shell around the existing Command Center UI and pair it with a local sidecar process.

- UI shell: Tauri is the recommended first path because it is cross-platform and has a smaller default footprint than Electron. Electron is acceptable if JavaScript-only speed becomes more important than app size.
- Local sidecar: reuse the existing bridge concepts, but productize them as OASIS Desktop instead of asking users to run CLI commands.
- Key wallet: store local provider keys in the operating system keychain where possible. Cloud-saved keys should remain encrypted through the existing server-side config path.
- Device pairing: desktop app signs into the Command Center account and registers as a device. Pairing should be a normal login flow, not a terminal ceremony.
- Update path: signed installers and signed auto-updates are required before broad client distribution.

## Security Boundaries

Provider credentials and local computer permissions must stay visibly separate.

- Provider connection decides what model account/key powers the agent.
- Runtime access decides whether the agent may use cloud workspace only or this desktop computer.
- Cloud workspace must never read local files, spawn local tools, or call the bridge.
- This desktop must require the local app to be running and paired to the tenant.
- Local file access must be allowlisted by path and agent profile.
- Tool execution must be allowlisted by command capability, not arbitrary shell by default.
- Local bridge traffic must stay loopback-only unless a signed desktop transport replaces it.
- Browser-to-local requests must require origin checks, a local session token, and tenant/device binding.
- Raw API keys must never be logged, returned to the browser, or written into repo config files.
- Each tool run should create an audit event visible in the Command Center.

## Current Foundation

The repo already has the important beginnings:

- `agent_model_config` stores per-agent provider/model/key configuration.
- `/api/chat` supports cloud API-key chat through provider abstraction.
- The local bridge supports full local context when it is online.
- Client profiles already change the Command Center experience by tenant.
- Pairing routes and device settings already point toward a desktop-device model.

## Implementation Plan

Phase 1 is product clarity. The chat UI must expose provider connection separately from Cloud/This Desktop access so operators understand both what powers the model and what computer access is allowed.

Phase 2 is desktop packaging. Build the first OASIS Desktop shell, embed or load the Command Center, launch the bridge sidecar automatically, and replace terminal setup with app login.

Phase 3 is secure key management. Add local keychain storage, cloud encrypted key sync, provider test buttons, and explicit per-agent runtime defaults.

Phase 4 is marketplace packaging. Turn each client/business use case into a signed agent manifest with brand shell, integrations, permissions, playbooks, and default prompts.

Phase 5 is installer quality. Ship macOS, Windows, and Linux installers, signed updates, uninstall cleanup, startup registration, crash reporting, and support diagnostics.

Phase 6 is production acceptance. Test first-run signup, login, API key setup, desktop pairing, bridge health, local permission prompts, agent chat, integration credentials, and audit logs for each client shell.

## Current Alpha Foundation

The first desktop foundation now lives in `apps/oasis-desktop`.

- `desktop.manifest.json` defines the product channel, provider connection options, runtime access options, allowed origins, bridge sidecar settings, and release gates.
- `src/main.js` is the hardened Electron shell that loads the hosted Command Center and starts the bridge sidecar when this repo is available.
- If the hosted Command Center cannot load, the desktop shell shows a local fallback page instead of a blank app window.
- `src/secure-store.js` is the first OS-backed encrypted local store foundation for future local API-key and runtime secrets.
- `scripts/doctor.js` checks local desktop prerequisites.
- `scripts/release-check.js` blocks unsafe desktop drift such as wildcard origins or disabled sandbox settings.
- `scripts/write-release-metadata.js` writes artifact checksums and release metadata so every downloadable build can be verified.
- The app menu exposes Desktop Diagnostics and a redacted support bundle generator for alpha/beta support.
- `.github/workflows/oasis-desktop.yml` is the first CI path for Windows, macOS, and Linux desktop artifacts.
- `RELEASE.md` documents the alpha, beta, and production gates.

## Delivery Timeline

The practical schedule is:

- Same day: internal Windows desktop shell that loads the Command Center and can start the local bridge from this repo.
- 1-2 focused days: alpha build with cleaner first-run states, downloadable Windows zip/installer, and bridge health surfaced in the UI.
- 3-5 focused days: macOS and Linux build pipeline, branded icons, app metadata, and repeatable release artifacts.
- 1-2 focused weeks: production-safe local permission prompts, bundled sidecar/runtime, keychain storage, crash logs, support diagnostics, and update channel.
- 2-4 focused weeks: production distribution quality with code signing, macOS notarization, auto-updates, marketplace-style agent manifests, and acceptance testing per client shell.

The only honest shortcut is the internal alpha. A client-safe downloadable product needs signing, updater, support logs, and permission boundaries before it is treated as production.

## Product Decision

The setup wizard should become an internal fallback and recovery tool. The client-facing path should be:

1. Download OASIS Desktop.
2. Sign in or create account.
3. Choose business profile or accept assigned profile.
4. Connect a provider through OAuth/account sign-in, API key, or OASIS subscription billing.
5. Choose cloud workspace or this desktop and approve optional local permissions.
6. Land in the branded Command Center.

That keeps the Hermes-style simplicity while preserving OASIS's advantage: a marketplace command center where every business can receive a different agent workforce on the same secure foundation.
