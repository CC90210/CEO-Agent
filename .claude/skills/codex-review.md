---
description: "Run a Codex code review against local git state. Use /codex:review"
---

Run a Codex review through the shared built-in reviewer.

Raw slash-command arguments:
`$ARGUMENTS`

**Setup:** Set the plugin root first:
```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/Business-Empire-Agent/.claude/plugins/codex"
```

Core constraint:
- This command is review-only.
- Do not fix issues, apply patches, or suggest that you are about to make changes.
- Your only job is to run the review and return Codex's output verbatim to the user.

Execution mode rules:
- If the raw arguments include `--wait`, run the review in the foreground.
- If the raw arguments include `--background`, run the review in a Claude background task.
- Otherwise, estimate the review size:
  - `git status --short --untracked-files=all`
  - `git diff --shortstat --cached` and `git diff --shortstat`
  - For base-branch review: `git diff --shortstat <base>...HEAD`
  - Recommend background for anything beyond 1-2 files.

Foreground flow:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" review "$ARGUMENTS"
```
Return the command stdout verbatim.

Background flow:
Run with `Bash(run_in_background: true)`:
```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" review "$ARGUMENTS"
```
Tell user: "Codex review started in the background. Check `/codex:status` for progress."

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
