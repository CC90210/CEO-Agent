---
name: agent-forge
description: Use when CC asks to create a new agent, scaffold a new agent repo, or clone Bravo's architecture for a new domain (client agent, sibling agent, specialized agent). Generates a new AI-agent repo from templates, wires it into C_SUITE_ARCHITECTURE.md and brain/APP_REGISTRY.md, preserves the V5.6 outbound chokepoint, and gives the new agent a doctor command on day one.
triggers: ["agent forge", "use agent forge", "run agent forge", "use when cc asks to create a new agent"]
tier: specialized
tags: [skill, agent-forge]
last_updated: 2026-07-09
---

# Agent Forge

Bravo's moat is that it can create **new agents** with the same architecture (brain + memory + skills + scripts + safety rules) in minutes, not weeks. This is the command set that implements that.

## When to Use

Trigger when CC says any of:
- "Create a new agent for..."
- "Clone Bravo for..."
- "Scaffold an agent that does..."
- "Make an agent for [client name]"
- "Build me an Atlas-style agent for X"

**Do not use** for: one-off scripts, temporary workers, Claude Code sub-agents that already fit `agents/` or `.claude/agents/`.

## Commands

```bash
# List everything Forge knows about
bravo agent list

# Create a new agent from template
bravo agent create <name> [--template <template>] [--role "<role>"] [--path <target-path>]

# Validate an existing agent's structure
bravo agent doctor <name>
```

Templates live in `templates/agent-scaffold/`. The default template produces the minimum viable agent: `AGENTS.md`, `CLAUDE.md`, `brain/SOUL.md`, `brain/STATE.md`, `memory/SESSION_LOG.md`, `memory/ACTIVE_TASKS.md`, `scripts/core/self_audit.py`, a `doctor` command, and a README.

**Template files (read by `bravo agent create`):**
- [[templates/agent-scaffold/README]] — generated agent's user-facing README
- [[templates/agent-scaffold/AGENTS|AGENTS]] — universal entry point for all AI clients
- [[templates/agent-scaffold/CLAUDE|CLAUDE]] — Claude Code instructions stub
- [[templates/agent-scaffold/brain/SOUL|brain/SOUL]] · [[templates/agent-scaffold/brain/STATE|brain/STATE]] · [[templates/agent-scaffold/brain/USER|brain/USER]]
- [[templates/agent-scaffold/memory/ACTIVE_TASKS|memory/ACTIVE_TASKS]] · [[templates/agent-scaffold/memory/SESSION_LOG|memory/SESSION_LOG]]
- [[templates/agent-scaffold/skills/INDEX|skills/INDEX]]

## What a Forged Agent Gets on Day One

| Layer | File(s) | Purpose |
|---|---|---|
| Identity | `AGENTS.md`, `CLAUDE.md`, `brain/SOUL.md` | Who the agent is, voice, values, prime directive |
| Memory | `brain/STATE.md`, `memory/ACTIVE_TASKS.md`, `memory/SESSION_LOG.md` | Live operational state + task backlog + session history |
| User context | `brain/USER.md` | Who they work for and that person's priorities |
| Safety | `scripts/integrations/send_gateway.py` (stub) + `skills/security-protocol/` | V5.6 outbound chokepoint; no bypass paths |
| Health | `scripts/core/self_audit.py` | Same 100-point audit Bravo uses |
| Skills | `skills/INDEX.md` | Registry of capabilities |
| Docs | `README.md` | One-page explanation of what this agent does |

## Templating Tokens

Template files support these tokens (replaced during `bravo agent create`):

- `{{AGENT_NAME}}` → literal name (e.g., `Hermes`)
- `{{agent_name}}` → lowercase slug (e.g., `hermes`)
- `{{AGENT_ROLE}}` → role description (e.g., `client operations agent`)
- `{{AGENT_TEMPLATE}}` → template slug used for this generation
- `{{DATE}}` → creation date (YYYY-MM-DD)

## Conventions (NON-NEGOTIABLE)

1. **Every forged agent preserves the V5.6 send_gateway chokepoint.** Outbound email/DM/post/publish routes through `scripts/integrations/send_gateway.py` or an explicit approval gate.
2. **Every forged agent has a `doctor` command on day one.** It doesn't need to be rich; it just needs to be runnable so the agent can self-check.
3. **Every forged agent has a clear Prime Directive.** `brain/SOUL.md` must state what this agent exists to do.
4. **Forged agents get registered in Bravo's world.** The Forge updates `brain/C_SUITE_ARCHITECTURE.md` and `brain/APP_REGISTRY.md` so Bravo can route to them.
5. **Forged agents never store credentials in their own repo.** Read from a shared `.env.agents` or the parent operator's environment.

## Default Template Slots (v1)

The default scaffold ships with placeholders for:

- Name + role
- Business context (who they work for, what they optimize)
- Safety gates (what requires CC approval)
- Capability list (what tools this agent can use)

## Relationship to Existing Agents

- **Atlas** (CFO) — finance/tax/trading. Created manually; will be re-aligned to Agent Forge scaffold on its next refresh.
- **Maven** (CMO) — content/ads/brand. Same — planned migration.
- **Aura** (Life/Home) — ambient/habits. Same.
- **Hermes** (client-side commerce agent for Emmanuel Lowinger) — first agent intentionally forged with this template pattern.

## Post-Creation Checklist

After `bravo agent create <name>` finishes:

1. `cd` into the forged repo.
2. Fill in `.env.agents` with only the keys this agent actually needs.
3. Run `bravo agent doctor <name>` (or `python scripts/core/self_audit.py` from inside the new repo).
4. Edit `brain/SOUL.md` to tune voice and Prime Directive.
5. Commit and push.
6. Add a line to `brain/C_SUITE_ARCHITECTURE.md` under the appropriate role slot.

## Safety Notes

- Forge NEVER writes to `.env.agents` in either the source or target.
- Forge NEVER force-pushes or deletes existing files at the target path.
- Forge refuses to overwrite non-empty target directories.
- Forge logs every creation to `memory/SESSION_LOG.md`.

## Related
- [[brain/C_SUITE_ARCHITECTURE]] — where new agents slot in
- [[brain/APP_REGISTRY]] — routing table for named agents
- [[brain/AGENTS]] — sub-agent roster
- [[skills/security-protocol/SKILL.md]] — safety defaults
- `runtime/profile_home.py` — profile substrate for multi-agent isolation
