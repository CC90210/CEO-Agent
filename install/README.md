# Install And Onboarding

This directory is the landing zone for Bravo's product installer.

The immediate goal is to turn the repo into a Hermes-grade installable product without weakening the existing business logic.

## Current Safe Diagnostics

Run:

```powershell
python scripts/onboarding_diagnostics.py
```

Browser Harness only:

```powershell
python scripts/browser_harness_doctor.py
```

## Installer Roadmap

Planned commands:

```text
bravo setup
bravo doctor
bravo status
bravo browser setup
bravo browser doctor
bravo skills list
bravo tools list
bravo agent create
```

Planned files:

```text
install/install.ps1
install/install.sh
bravo_cli/main.py
config/bravo-config.example.toml
runtime/session_store.py
runtime/tool_manifest.py
```

## Install Principles

- Windows-first because CC's primary workstation is Windows.
- POSIX/WSL support second.
- No installer should overwrite `.env.agents`.
- No installer should run destructive database, Stripe, git, or file operations.
- Setup should generate templates, check tools, and explain next actions.
- Doctor should be read-only.
