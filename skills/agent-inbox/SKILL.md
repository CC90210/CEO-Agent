---
name: agent-inbox
description: Async agent-to-agent messaging protocol. Use when Bravo, Atlas, Maven, Aura, or Codex needs to pass a structured message to another agent without blocking the orchestrator. Replaces synchronous-only delegation with a checkpoint-based pickup pattern. CLI backed by scripts/core/agent_inbox.py.
triggers: [agent inbox, inter-agent message, async delegation, agent notification, cross-agent handoff]
tier: standard
dependencies: []
---

# Agent Inbox — Async Inter-Agent Messaging

> Pattern from Dicklesworthstone/mcp_agent_mail (FastMCP + SQLite + Git). Adapted to Bravo's stack as a lightweight file-based inbox under `tmp/agent_inbox/`. Closes the gap named in brain/ORCHESTRATION.md: *"Bravo's inter-agent communication is entirely synchronous — Codex can't notify Bravo when a background task finishes without a poll."*

## When to Use

- **Codex finishes a background task** → Codex posts a message to bravo's inbox; Bravo picks it up at its next checkpoint instead of polling
- **Maven needs Atlas's spend-gate approval** → Maven posts a request; Atlas picks it up on next activation, replies
- **Aura detects a habit pattern Bravo should know about** → Aura posts a `priority: normal` note; Bravo picks it up next session start
- **Long-running multi-agent workflows** where one agent waits on another's milestone

## When NOT to Use

- Synchronous in-session delegation (use Task tool directly — faster, simpler)
- CC ↔ Bravo conversation (that's the normal chat channel)
- State that should be durable beyond a message (use Supabase, pulse files, or brain/ files)

## Message Schema

Every message is one JSON file in `tmp/agent_inbox/inbox/` (unread) or `read/` (acknowledged):

```json
{
  "message_id": "12-char hex",
  "from": "bravo | atlas | maven | aura | codex | cc | <agent-name>",
  "to":   "bravo | atlas | maven | aura | codex | broadcast",
  "timestamp": "ISO 8601 UTC",
  "subject": "<one-line>",
  "body": "<full message>",
  "priority": "low | normal | high | urgent",
  "requires_response": true|false,
  "in_reply_to": "<message_id> or null",
  "thread_id": "<root message_id>"
}
```

Filenames sort by priority-then-time: `{priority_prefix}_{ts}_{to}_{id}.json` — so urgent messages surface first when listing.

## Commands (scripts/core/agent_inbox.py)

```bash
# Post a message
python scripts/core/agent_inbox.py post --from codex --to bravo \
  --subject "Task complete" \
  --body "Refactor of send_gateway landed in commit abc123. Tests green." \
  --priority normal

# List unread messages for a recipient
python scripts/core/agent_inbox.py list --to bravo

# Read (and acknowledge — moves to read/)
python scripts/core/agent_inbox.py read <message_id>

# Reply in-thread
python scripts/core/agent_inbox.py reply --from bravo --in-reply-to <message_id> \
  --body "Received. Deploying."

# Machine-readable
python scripts/core/agent_inbox.py list --to bravo --json
```

## Integration Points

### Bravo session start
Add to boot sequence: `python scripts/core/agent_inbox.py list --to bravo --json` — if any urgent/high messages, surface in briefing.

### Codex task completion
When Codex finishes a background task via `codex-companion.mjs`, have the script post a completion message:
```bash
python scripts/core/agent_inbox.py post --from codex --to bravo \
  --subject "Codex task <id> complete" \
  --body "$(cat result.md)" --priority normal
```

### Cross-agent pulse updates
When any sibling agent writes to `data/pulse/<agent>_pulse.json` with a significant change, it should also post a broadcast message so others pick it up on next activation:
```bash
python scripts/core/agent_inbox.py post --from atlas --to broadcast \
  --subject "Spend gate threshold lowered to $50/day" \
  --body "..." --priority high
```

## Priority Semantics

| Priority | When to use | Bravo behavior |
|----------|-------------|----------------|
| **urgent** | Security breach, outage, blocked ship | Surface immediately at next tool call, interrupt work |
| **high** | Sibling agent needs decision within hours | Surface at next checkpoint, before new major work |
| **normal** | Status updates, completions, FYIs | Surface at session start + end |
| **low** | Archival, logs, long-term notes | List on explicit request only |

## Hard Rules

- **Storage is tmp/ (gitignored)** — never commit messages. They're ephemeral coordination, not durable state.
- **Never use the inbox for CC-facing content** — CC reads chat, not inbox files.
- **Read = acknowledged** — the `read` command moves the file. Don't use inbox as a database; move true durable info into pulse files or brain/.
- **No auto-actions on inbox reads** — messages inform, they don't authorize destructive operations. Still goes through send-gateway / review / CC approval.

## Why This Exists (Anthropic gap)

From the researcher's 2026 findings (session 2026-04-21): *"Bravo's inter-agent communication is entirely synchronous and orchestrator-mediated — Bravo spawns, waits, receives. The mcp_agent_mail pattern gives each agent an identity and inbox so agents can post results, questions, and escalations to each other without blocking the orchestrator."*

Current state before this skill: if Codex finishes a background task, Bravo only knows by manual status check. Now: Codex posts to inbox, Bravo picks up on next checkpoint. Zero polling, zero blocking.

## Obsidian Links
- [[brain/ORCHESTRATION]] §The Observability Gap
- [[brain/AGENTS]] §Cross-Agent Integration
- [[scripts/agent_inbox]] — the CLI
