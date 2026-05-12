---
description: "Delegate a task to Codex for investigation, fix, or background execution. Use /codex:rescue"
---

Delegate a task to Codex via the companion runtime.

Raw user request:
`$ARGUMENTS`

**Setup:** Set the plugin root first:
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/Business-Empire-Agent/.claude/plugins/codex"
```

Execution mode:
- `--background` → run in background. `--wait` → foreground. Default: foreground.
- `--resume` → continue latest Codex thread. `--fresh` → start new thread.
- `--model <model>` → specific model. `spark` maps to `gpt-5.3-codex-spark`.
- `--effort <level>` → reasoning effort (none/minimal/low/medium/high/xhigh).
- If neither `--resume` nor `--fresh`, check for resumable thread:

```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task-resume-candidate --json
```

If `available: true`, ask user whether to continue or start fresh.

Task execution (foreground):
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task --write $ARGUMENTS
```

Task execution (background):
Run with `Bash(run_in_background: true)`:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task --write $ARGUMENTS
```
Tell user: "Codex rescue task started in the background. Check `/codex:status` for progress."

Return Codex output verbatim. Do not paraphrase or add commentary.

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
