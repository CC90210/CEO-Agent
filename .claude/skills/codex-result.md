---
description: "Show final output for a finished Codex job. Use /codex:result"
---

Show the stored final output for a finished Codex job.

**Setup:**
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/Business-Empire-Agent/.claude/plugins/codex"
```

Run:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" result $ARGUMENTS
```

Present the FULL command output. Preserve all details: verdict, summary, findings, file paths, line numbers, next steps. Do not summarize.