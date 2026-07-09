---
name: hooks-automation
description: "Enhanced pre/post operation hooks with learning capabilities. Extends Claude Code's native hooks with task-aware pre-validation, post-execution learning, memory coordination, and session lifecycle management. Use when configuring hooks, debugging hook failures, adding new automation triggers. Skip when hooks are already working correctly."
tags: [automation, hooks, orchestration]
triggers: ["hooks automation", "use hooks automation", "run hooks automation"]
tier: core
---

# Hooks Automation — Intelligent Operation Lifecycle

> **Purpose:** Claude Code hooks are powerful but limited to simple regex matching.
> This skill defines the full hook lifecycle: what happens before, during, and after
> every operation type, including learning and pattern extraction.

## Current Hooks (`.claude/settings.local.json`)

These are the native Claude Code hooks already active:

| Event | Matcher | Action |
|-------|---------|--------|
| PreToolUse (Edit/Write) | `.env*` files | BLOCK — credentials are manual-only |
| PreToolUse (Bash) | destructive commands | BLOCK — rm -rf, force push, DROP TABLE |
| PostToolUse (Bash) | git/npm/vercel commands | AUDIT LOG → tmp/hook_audit.log |
| Notification | all | Windows desktop alert on input needed |

## Enhanced Hook Definitions

Beyond the native hooks, these are the logical hooks that agents should follow:

### Pre-Operation Hooks

**pre-edit: File Validation**
Before modifying any file:
1. Check agent permissions (see `skills/agent-permissions/SKILL.md`)
2. Verify file is not in blocked patterns list
3. Read the file first (mandatory — never edit blind)
4. If file is in `brain/` — check mutability level (SOUL.md = IMMUTABLE)

**pre-bash: Command Safety**
Before executing any shell command:
1. Check against blocked command patterns
2. Verify the command doesn't expose secrets (no `echo $API_KEY`)
3. For destructive commands (rm, git reset) — require CC confirmation
4. Log command intent to session context

**pre-task: Context Loading**
Before starting any non-trivial task:
1. Run task routing (see `skills/task-routing/SKILL.md`)
2. Load relevant memory (BRAIN_LOOP Step 2: RECALL)
3. Check ACTIVE_TASKS.md for conflicts or related work
4. Verify agent has required permissions

**pre-commit: Quality Gate**
Before any git commit:
1. Run `git diff --staged` — review all changes
2. Check for hardcoded secrets (grep for API keys, tokens, passwords)
3. Verify no `.env` files are staged
4. For MODERATE+ changes: run code review skill
5. Verify commit message follows conventional format

**pre-deploy: Build Verification**
Before pushing to remote:
1. `npm run build` must pass with zero errors
2. All tests must pass
3. No CRITICAL code review issues outstanding
4. CHANGELOG.md updated (for feature/fix commits)

### Post-Operation Hooks

**post-edit: Change Tracking**
After modifying any file:
1. Track which files were modified (for anti-drift scope monitoring)
2. If a markdown file in `brain/` or `memory/` was edited — update timestamps
3. If the edit introduced a new pattern — flag for PATTERNS.md consideration

**post-bash: Execution Logging**
After executing any shell command:
1. If command failed — log to session context for debugging
2. If command was git push/commit — log to SESSION_LOG.md
3. If command was npm build/test — note pass/fail status
4. Append to `tmp/hook_audit.log` for audit trail

**post-task: Learning Extraction**
After completing any non-trivial task:
1. Did the task succeed? Log outcome to SESSION_LOG.md
2. Did anything unexpected happen? Flag for PATTERNS.md or MISTAKES.md
3. Update ACTIVE_TASKS.md with completion status
4. If task used a new approach — tag as `[PROBATIONARY]` pattern
5. Run anti-drift final check (actual scope vs. planned scope)

**post-commit: State Sync**
After any git commit:
1. Update SESSION_LOG.md with commit hash and summary
2. Update brain/STATE.md if operational state changed
3. Notify via desktop notification (already handled by native hook)

**post-deploy: Smoke Test**
After deployment completes:
1. Visit production URL with Playwright
2. Check for console errors
3. Verify the deployed feature works
4. If smoke test fails — create hotfix branch immediately

### Session Lifecycle Hooks

**session-start:**
1. Load brain/ files (SOUL, STATE, USER)
2. Read ACTIVE_TASKS.md for pending work
3. Check MCP server connectivity
4. Run memory health check (SESSION_LOG.md size, stale tasks)
5. Load `.agents/config.toml` for current settings

**session-end:**
1. Update brain/STATE.md with final operational state
2. Update memory/ACTIVE_TASKS.md with task status
3. Append session summary to memory/SESSION_LOG.md
4. Flush traces to Supabase (if available)
5. Git commit if uncommitted changes exist: `bravo: sync — session YYYY-MM-DD`

### Memory Coordination Hooks

**memory-write:**
Before writing to any memory file:
1. Check the Five-Gate Knowledge Filter (see `skills/memory-management/SKILL.md`)
2. Verify no duplicate entry exists
3. Add confidence score and timestamp
4. If writing to brain/ file — verify mutability permits the change

**memory-read:**
When accessing memory files:
1. Log access for activation scoring (recency bump)
2. Check freshness — flag stale entries (>30 days without verification)
3. Cross-reference with Supabase for any newer data from other agents

### Learning Hooks

**train-on-success:**
After a task completes successfully:
1. Extract the approach as a candidate pattern
2. Check if this pattern already exists in PATTERNS.md
3. If new — add as `[PROBATIONARY]` with confidence 0.6
4. If existing — increment usage count, bump confidence

**train-on-failure:**
After a task fails:
1. Generate Reflexion entry (BRAIN_LOOP Step 7)
2. Check MISTAKES.md for similar failures
3. If repeat failure — escalate to SOP creation
4. Store failure context for future RECALL

## Adding New Hooks

To add a new native Claude Code hook, edit `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "pattern to match",
        "hook": "command to run",
        "timeout": 10000
      }
    ]
  }
}
```

For logical hooks (enforced by agent behavior, not Claude Code runtime):
1. Add the hook definition to this skill file
2. Reference it in the relevant skill that should trigger it
3. Update `.agents/config.toml` [hooks] section

## Config Reference

Hook settings in `.agents/config.toml`:
- `[hooks.pre]` — Which pre-operation hooks are enabled
- `[hooks.post]` — Which post-operation hooks are enabled
- `[hooks.learning]` — Learning trigger settings


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[brain/CAPABILITIES]] | [[skills/task-routing/SKILL.md]]
- [[skills/anti-drift/SKILL.md]] | [[skills/memory-management/SKILL.md]]
- [[skills/code-review/SKILL.md]] | [[skills/security-protocol/SKILL.md]]
