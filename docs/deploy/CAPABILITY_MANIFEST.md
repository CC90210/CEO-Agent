---
tags: [parity, plugins, mcp, setup, multi-machine]
purpose: Reproducible snapshot of the machine-level capability surface (plugins, marketplaces, Codex, global config, system bins) that does NOT sync via git, so any new machine can reach full parity.
owner: CC (Conaugh McKenna)
generated_from: Windows production box
last_updated: 2026-06-26
---

# Capability Manifest — what a new machine needs beyond `git pull`

`git pull` syncs the repo (skills/, scripts/, brain/, hooks scripts, `.claude/mcp.json`,
the committed hooks **template**). It does NOT sync the machine-level surface below. Run
`python3 scripts/machine_parity.py --fix` first (installs hooks + checks deps), then close the
remaining gaps from this manifest. Re-run `--check` until GREEN.

## 1. Marketplace plugins (installed at `~/.claude/plugins/`, NOT in the repo)

Snapshot of the 24 installed plugins across 3 marketplaces (from
`~/.claude/plugins/installed_plugins.json` + `known_marketplaces.json` on the Windows box).

**Add the marketplaces (in Claude Code, interactive):**
```
/plugin marketplace add anthropics/claude-plugins-official
/plugin marketplace add anthropics/financial-services        # registers as "claude-for-financial-services"
/plugin marketplace add thedotmack/claude-mem
```

**Install the plugins:**
```
# claude-plugins-official
/plugin install superpowers@claude-plugins-official
/plugin install github@claude-plugins-official
/plugin install context7@claude-plugins-official
/plugin install frontend-design@claude-plugins-official
/plugin install skill-creator@claude-plugins-official
/plugin install feature-dev@claude-plugins-official
/plugin install pyright-lsp@claude-plugins-official
/plugin install vercel@claude-plugins-official
/plugin install claude-code-setup@claude-plugins-official
/plugin install supabase@claude-plugins-official
/plugin install agent-sdk-dev@claude-plugins-official
/plugin install shopify-ai-toolkit@claude-plugins-official
/plugin install shopify@claude-plugins-official
/plugin install twilio-developer-kit@claude-plugins-official
/plugin install code-review@claude-plugins-official
/plugin install claude-md-management@claude-plugins-official
/plugin install code-simplifier@claude-plugins-official

# claude-for-financial-services (Atlas/CFO surfaces)
/plugin install financial-analysis@claude-for-financial-services
/plugin install equity-research@claude-for-financial-services
/plugin install wealth-management@claude-for-financial-services
/plugin install private-equity@claude-for-financial-services

# thedotmack
/plugin install claude-mem@thedotmack
```

> The empire's OWN skills (150 in `skills/`) sync via git and need no install. The list above
> is only the third-party marketplace layer. `superpowers` (brainstorming, TDD, systematic-
> debugging, writing/executing-plans) and `code-review` are the highest-value for Bravo's loop.

## 2. Codex dual-AI plugin (the review/delegation backend — Rule 8)

Lives at `~/.claude/codex-plugin/` (NOT a marketplace plugin, NOT in this repo). Required so
`node ~/.claude/codex-plugin/scripts/codex-companion.mjs …` works and end-of-task audits run.

- Confirm present + authed: `node ~/.claude/codex-plugin/scripts/codex-companion.mjs status`
- If the directory is missing, install/copy the codex-plugin to `~/.claude/codex-plugin` on this
  machine (same on Windows + macOS), then run the OpenAI login the `status` command prints.

## 3. Global config

- `~/.claude/CLAUDE.md` — canonical copy committed at `docs/deploy/global-CLAUDE.md`. If missing:
  `cp docs/deploy/global-CLAUDE.md ~/.claude/CLAUDE.md` (macOS: adjust the Codex path note inside).

## 4. MCP servers

- `.claude/mcp.json` syncs via git but has Windows-specific entries: the `github`/`firecrawl`/
  `obsidian` shims use `scripts\mcp_shims\*.js` (backslashes) and `knowledge-graph` points at
  `C:\Users\User\tools\knowledge-graph\...`. On macOS those break. MCP is **secondary** to the
  CLI tools (project Rule 2), so this is non-blocking — fix the paths in a machine-local
  `~/.claude/mcp.json` only if you actually use those MCP servers on the Mac.

## 5. System binaries + environment

- `python3` (3.12+), `node` (20+ LTS), `npm`, `git` — required.
- `ffmpeg`, `gh`, `pm2` — needed for content pipeline / GitHub CLI / daemon orchestration.
- `caffeinate` (macOS built-in) — keep the laptop awake while it hosts daemons.
- Python venv + `pip install -r requirements.txt`; `npm install`. (`.env.agents` is per-machine,
  updated manually by CC; the doctor audits it by KEY NAME only.)

```bash
brew install python@3.12 node@20 ffmpeg gh && npm install -g pm2   # macOS one-liner
```

## How to refresh this manifest

On the source machine: re-read `~/.claude/plugins/installed_plugins.json` +
`known_marketplaces.json` and regenerate the lists above. (A future `machine_parity.py
--export-manifest` could automate this.)
