---
description: "Check Codex CLI readiness and toggle review gate. Use /codex:setup"
---

Check whether the local Codex CLI is ready and optionally toggle the stop-time review gate.

Raw arguments:
`$ARGUMENTS`

**Setup:** Set the plugin root first:
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/Business-Empire-Agent/.claude/plugins/codex"
```

Run:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" setup --json $ARGUMENTS
```

If Codex is unavailable and npm is available, offer to install:
```bash
npm install -g @openai/codex
```
Then rerun setup.

If Codex is installed but not authenticated, tell user to run: `codex login`

Supports: `--enable-review-gate` / `--disable-review-gate`

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
