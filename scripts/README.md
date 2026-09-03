---
tags: [scripts]
last_updated: 2026-05-21
---

# scripts/ — Categorized Tool Directory

> **STRICT DIRECTIVE:** This directory is migrating from a flat structure to a categorized layout to prevent context bloat for smaller AI models.

## Structure

| Directory | Purpose |
|-----------|---------|
| `scripts/core/` | Core empire operations (state management, event routing, memory, sync) |
| `scripts/integrations/` | External service connectors (Turso, Stripe, n8n, Google Workspace, email) |
| `scripts/browser/` | Browser harness, scraping, cloaking, web automation |
| `scripts/state/` | V6 state substrate (state_manager, guards, bridges, heartbeats) |
| `scripts/hooks/` | Pre-commit, session-start, and automation hooks |

## Rules for AI Agents

1. **DO NOT drop new `.py` files in the `scripts/` root.** Place them in the appropriate subdirectory.
2. **If unsure which category fits**, use `scripts/core/` and add a comment at the top of the file explaining what it does.
3. **Existing root-level scripts** are being migrated incrementally. Do not break imports — update any `import` or `subprocess` references when moving a file.
4. **All scripts must** read credentials from `.env.agents` via `lib/secret_loader.py` — never hardcode secrets.
5. **All scripts must** support `--json` for machine-readable output where applicable.

## Legacy Root Scripts

Scripts still living at the root level are pending migration. They remain fully functional. Do not delete or rename them without CC approval.

## Obsidian Links
- [[brain/CAPABILITIES]]
- [[brain/QUICK_REFERENCE]]
