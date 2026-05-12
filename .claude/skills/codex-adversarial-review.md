---
description: "Run a Codex adversarial review that challenges implementation and design choices. Use /codex:adversarial-review"
---

Run an adversarial Codex review that challenges the chosen implementation, design choices, tradeoffs, and assumptions.

Raw slash-command arguments:
`$ARGUMENTS`

**Setup:** Set the plugin root first:
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/Business-Empire-Agent/.claude/plugins/codex"
```

Core constraint:
- Review-only. Do not fix issues or apply patches.
- Focus on whether the current approach is the right one, what assumptions it depends on, and where the design could fail.

Execution mode rules:
- `--wait` → foreground. `--background` → background task.
- Otherwise estimate size and recommend background for anything beyond 1-2 files.
- Unlike `/codex:review`, this command accepts extra focus text after the flags.

Foreground flow:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" adversarial-review "$ARGUMENTS"
```
Return stdout verbatim.

Background flow:
Run with `Bash(run_in_background: true)`:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" adversarial-review "$ARGUMENTS"
```
Tell user: "Codex adversarial review started in the background. Check `/codex:status` for progress."

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-cancel]]
- [[.claude/skills/codex-rescue]]
