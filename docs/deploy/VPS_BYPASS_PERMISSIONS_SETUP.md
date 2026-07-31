---
tags: [docs, deploy]
last_updated: 2026-06-09
---

# VPS AI-CLI Bypass-Permissions Setup

> Paste everything between the triple-dashes into your VPS Claude Code
> chat. The agent installs/configures Claude Code, Codex CLI, and
> Gemini CLI to default to auto-approve so future AI sessions can do
> extensive work without pausing for permissions. No SSH-from-Windows
> needed.
>
> Idempotent: re-run any time. Safe — config-only, no production state.

---

You are a Claude Code agent on CC's SunBiz Funding VPS
(Ubuntu 22.04, srv1723601, root). Your job: make the three AI CLIs
installed here default to "auto-approve / bypass permissions" mode so
CC's future agentic sessions on this host don't pause to ask for
permission. CC owns the risk — this VPS is a single-tenant sandbox he
controls and is not multi-user.

## Scope

In:
- `/root/.claude/settings.json` (Claude Code)
- `/root/.codex/config.toml` (OpenAI Codex CLI)
- `/root/.gemini/settings.json` (Google Gemini CLI)
- `/root/.bashrc` (shell aliases — so plain `claude` / `codex` / `gemini` invoke bypass-mode by default)

Out:
- Anything outside the root user's home directory
- The actual agent workloads (sequence-runner, lender classifier, etc.)
- The bridge daemon
- Anything in `/srv/sunbiz/*`

## Step 1 — Claude Code

### 1.1 Install if not present

```
which claude || (npm install -g @anthropic-ai/claude-code && claude --version)
```

Expected: claude command exists, version printed.

### 1.2 Write `/root/.claude/settings.json`

Create the file if missing, otherwise merge. The canonical content:

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions"
  }
}
```

Use `mkdir -p /root/.claude && cat > /root/.claude/settings.json <<'JSON'` then the JSON above. Set perms `chmod 600 /root/.claude/settings.json`.

### 1.3 Authenticate Claude Code (one-time if not already)

```
claude --version
# If not logged in: claude login (this opens a browser URL — CC must complete it)
```

Skip this step if `~/.claude/.credentials.json` already exists.

### 1.4 Verify bypass works

Launch claude with a trivial task. Expected: it executes Read/Bash without prompting.

```
echo "List files in /tmp" | claude --print --dangerously-skip-permissions
```

If exit code 0 → bypass works. If it returns "permission denied" → defaultMode didn't take; fall back to alias (Step 4).

## Step 2 — Codex CLI

### 2.1 Install if not present

```
which codex || npm install -g @openai/codex
codex --version
```

### 2.2 Configure auto-approve

Write `/root/.codex/config.toml`:

```toml
# Auto-approve every operation. Single-tenant sandbox; CC owns the risk.
approval_policy = "never"

# Use sandboxed shell for any FS-mutating action — last line of defense.
sandbox_mode = "workspace-write"
```

```
mkdir -p /root/.codex
chmod 600 /root/.codex/config.toml  # after writing
```

If the installed Codex CLI version uses a different key name (older versions used `approval_mode = "full-auto"`), check with `codex --help` and update accordingly. Report the version + final TOML in your output.

### 2.3 Authenticate

```
# If not already logged in, codex will prompt on first run
codex auth status || codex login
```

Skip if already authenticated.

### 2.4 Verify

```
codex exec --auto-approve "echo verified > /tmp/codex-test && cat /tmp/codex-test"
```

Expected: prints "verified" without prompting.

## Step 3 — Gemini CLI

### 3.1 Install if not present

```
which gemini || npm install -g @google/gemini-cli
gemini --version
```

### 3.2 Write `/root/.gemini/settings.json`

```json
{
  "selectedAuthType": "oauth-personal",
  "yolo": true
}
```

```
mkdir -p /root/.gemini
chmod 600 /root/.gemini/settings.json   # after writing
```

`"yolo": true` makes Gemini auto-approve every tool call.

### 3.3 Authenticate

```
gemini --version
# If not authed: run `gemini` once and follow the OAuth prompt
```

### 3.4 Verify

```
echo "Print 'gemini-verified'" | gemini --yolo
```

Expected: prints "gemini-verified" without prompting.

## Step 4 — Shell aliases (belt-and-suspenders)

Even with the settings files above, also add explicit `--bypass` flags as aliases. This protects against config-file drift and gives CC a clear signal in his shell history.

Append to `/root/.bashrc` if not already present:

```bash
# AI-CLI bypass aliases — single-tenant VPS, CC owns the risk
alias claude='claude --dangerously-skip-permissions'
alias codex='codex --auto-approve'
alias gemini='gemini --yolo'
```

Then:

```
source /root/.bashrc
```

Check each alias:

```
type claude
type codex
type gemini
```

Each should print the aliased form.

## Step 5 — Sanity check

Run each CLI's verification command from Steps 1.4 / 2.4 / 3.4 again to confirm aliases compose cleanly with the settings files (no double-flag errors).

## Step 6 — Report

Print to stdout:

```
=== AI CLI Bypass Setup — {ISO timestamp} ===

[1] Claude Code  : INSTALLED v{version} | settings.json: WRITTEN | alias: SET | verify: PASS/FAIL
[2] Codex CLI    : INSTALLED v{version} | config.toml: WRITTEN | alias: SET | verify: PASS/FAIL
[3] Gemini CLI   : INSTALLED v{version} | settings.json: WRITTEN | alias: SET | verify: PASS/FAIL
[4] .bashrc      : aliases present
[5] All three verify: YES/NO

Notes:
- {anything that needed a key-name adjustment for a newer CLI version}
- {anything that required CC to complete an OAuth flow in the browser}
- {anything you DIDN'T do and why}
```

Then a one-paragraph plain-English summary for CC: which CLIs are now bypass-default, which still need his action (e.g., browser OAuth), and what to test next.

## Constraints

1. **Never** install something that isn't an official Anthropic/OpenAI/Google CLI. No third-party AI tooling.
2. **Never** write the settings files with `chmod 644` or world-readable perms — always 600.
3. **Never** log into accounts that aren't CC's (you may need to skip OAuth steps and flag for him).
4. If a CLI is already installed and configured, **skip** that step — don't reinstall over a working setup.
5. If any verify step fails three times in a row, stop and report — do not loop.
