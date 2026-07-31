---
name: agent-permissions
description: "Claims-based access control for multi-agent coordination. Defines what each agent can read, write, execute, and spawn. Enforces least-privilege. Use when spawning agents, multi-agent tasks, security-sensitive operations. Skip for single-agent inline work or trivial tasks."
tags: [security, orchestration, agents]
triggers: ["agent permissions", "use agent permissions", "run agent permissions"]
tier: standard
last_updated: 2026-07-09
---

# Agent Permissions — Claims-Based Access Control

> **Purpose:** Not every agent should touch every file. The permissions system enforces
> least-privilege so agents can only access what their role requires.

## Claim Types

| Claim | Description | Example |
|-------|-------------|---------|
| **read** | View file contents | Explorer reads any file |
| **write** | Create or modify files | Writer edits `.ts` files |
| **execute** | Run shell commands | Debugger runs test suites |
| **spawn** | Create sub-agents | Architect spawns writer agents |
| **memory** | Access shared memory files | Debugger reads MISTAKES.md |
| **network** | Make external API/web calls | Researcher browses with Playwright |
| **admin** | All permissions + config changes | Only Bravo lead agent |

## Permission Levels

Levels are cumulative — each includes all claims from the level below:

| Level | Claims | Agents |
|-------|--------|--------|
| **minimal** | read | explorer, researcher, revenue-hunter |
| **standard** | read, write, execute | writer, reviewer, chief-of-staff, git-ops, documenter |
| **elevated** | standard + spawn, memory | architect, debugger, workflow-builder, meta-agent |
| **admin** | all claims | Bravo lead agent only |

## Scope Restrictions

Each agent's write access is limited to specific file patterns:

| Agent | Writable Scopes | Rationale |
|-------|----------------|-----------|
| **writer** | `**/*.ts`, `**/*.tsx`, `**/*.js`, `**/*.py`, `**/*.css`, `**/*.json` | Code files only |
| **reviewer** | `**/*` (read) + auto-fix on code files | Can read everything, write only for mechanical fixes |
| **documenter** | `**/*.md`, `brain/**`, `memory/**`, `skills/**` | Markdown and intelligence files |
| **explorer** | (none — read-only by design) | Never writes, edits, or deletes |
| _(Maven sub-agents:_ `content-creator`, `social-publisher`, `video-editor` _)_ | _Live in `../CMO-Agent/agents/` — delegate via Maven, not invoked locally_ | Maven owns content/posting/video pipelines |
| **git-ops** | `.git/**`, staging area | Git operations only |
| **architect** | `**/*.md` (plans, docs) | Designs only, never writes code directly |

## Blocked Patterns (Universal)

**NO agent** — regardless of permission level — can access:

```
.env*                    # Credentials
*.pem, *.key             # Certificates
credentials*.json        # Service accounts
.obsidian/**             # Obsidian config (managed by app)
```

These are enforced by both this skill AND the Claude Code hooks in `.claude/settings.local.json`.

## How to Check Permissions

Before an agent performs an action, validate:

```
PERMISSION CHECK:
  Agent: [agent name]
  Action: [read | write | execute | spawn | memory | network]
  Target: [file path or resource]
  Level: [minimal | standard | elevated | admin]

  Result: [ALLOWED | DENIED — reason]
```

**If DENIED:**
1. Log the denied action (for audit trail)
2. Check if a different agent has the required permission
3. If no agent can do it, escalate to CC

## Permission Escalation

When an agent needs to exceed its permissions:

1. **Temporary escalation** — Agent requests elevated access for a specific action
2. The request must include: what action, why it's needed, which files
3. CC approves or denies
4. If approved, the escalation is logged and expires after the task completes

This should be RARE. If an agent frequently needs escalation, its base permission level is wrong — update `.agents/config.toml` [permissions.agents].

## Integration with Task Routing

When the task routing skill assigns agents:
1. Check each assigned agent's permission level
2. Verify the agent can access all files in the routing decision
3. If permission gap exists, either:
   - Add a higher-permission agent to the team
   - Request temporary escalation from CC

## Config Reference

All permission settings are in `.agents/config.toml`:
- `[permissions.agents]` — Per-agent permission levels
- `[permissions.scopes]` — Per-agent file glob restrictions
- `[permissions.blocked]` — Universal blocked patterns


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[brain/AGENTS]] | [[skills/task-routing/SKILL.md]]
- [[skills/security-protocol/SKILL.md]] | [[brain/CAPABILITIES]]
