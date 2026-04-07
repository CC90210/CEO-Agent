---
description: "Show active and recent Codex jobs. Use /codex:status"
---

Show active and recent Codex jobs for this repository.

**Setup:**
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/Business-Empire-Agent/.claude/plugins/codex"
```

Run:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" status $ARGUMENTS
```

If no job ID passed: render as a compact Markdown table with job ID, kind, status, phase, elapsed, summary.
If job ID passed: present full output without summarizing.