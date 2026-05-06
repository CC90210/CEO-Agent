---
name: memory-compression
description: claude-mem plugin — automatic cross-session memory compression and injection via SQLite + semantic search. Captures tool usage, compresses observations, and injects relevant context at session start.
tags: [skill, memory, plugin, claude-mem]
triggers: ["memory compression", "use memory compression", "run memory compression"]
---

# Memory Compression (claude-mem)

## What It Is

claude-mem is a Claude Code plugin (v11.0.0) installed at `~/.claude/plugins/marketplaces/thedotmack/`. It provides **automatic** cross-session memory that is distinct from our manual brain/memory/ file system.

- **Storage:** SQLite at `~/.claude-mem/claude-mem.db` (auto-created on first use)
- **Vector search:** Chroma embeddings at `~/.claude-mem/chroma/` (semantic similarity)
- **Viewer UI:** `http://localhost:37777` (available when worker is running)
- **Runtime:** Requires Bun (auto-installed on first session start via `smart-install.js`)

## How It Coexists With Our Memory System

| Layer | System | What It Stores | Managed By |
|-------|--------|----------------|------------|
| brain/ + memory/ | Bravo's file-based memory | Business context, tasks, decisions, patterns | Bravo (manual writes) |
| `@modelcontextprotocol/server-memory` | MCP knowledge graph | Named entities and relations | Bravo via MCP tools |
| claude-mem SQLite | Plugin automated memory | Tool usage observations, session summaries | claude-mem hooks (automatic) |

These three layers are complementary, not conflicting. claude-mem captures low-level tool activity automatically — it does not replace the structured business memory in brain/ and memory/.

## Activation — Fully Automatic

5 lifecycle hooks run without any action from Bravo or CC:

| Hook | Trigger | What It Does |
|------|---------|--------------|
| `Setup` | Session with "startup/clear/compact" | Runs `smart-install.js` — installs Bun/uv if missing, starts worker |
| `SessionStart` | Session with "startup/clear/compact" | Starts worker service, injects relevant past context |
| `UserPromptSubmit` | Every prompt | Initializes session-level observation tracking |
| `PostToolUse` | Every tool call | Records observation (file edits, bash commands, etc.) |
| `Stop` | End of response | Compresses session into summary observation |
| `SessionEnd` | Session end | Marks session complete in DB |

**Privacy:** Wrap sensitive content in `<private>...</private>` tags to prevent storage.

## Available Skills (Auto-Loaded by Plugin)

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/mem-search` | Use when asking "did we already solve this?" | 3-layer search: index → timeline → fetch |
| `/make-plan` | Plan a multi-phase feature | Orchestrator + subagent phased planning |
| `/do` | Execute a plan from `/make-plan` | Subagent-driven plan execution |
| `/smart-explore` | Explore codebase structure | Guided codebase discovery |
| `/timeline-report` | Generate activity timeline | Chronological work history |

## Search Workflow (When CC Asks About Past Work)

Always use the 3-layer approach — never fetch full observations without filtering first (10x token savings):

```
Step 1 — search(query="...", limit=20, project="Business-Empire-Agent")
Step 2 — timeline(anchor=<id>, depth_before=3, depth_after=3)
Step 3 — get_observations(ids=[...])   # Only for IDs that look relevant
```

## Worker Service

The worker (Express on port 37777) handles AI processing asynchronously. It requires Bun.

```bash
# Start worker (required for search and viewer UI)
npx claude-mem start

# Check status
npx claude-mem status

# Stop
npx claude-mem stop

# View memories in browser
open http://localhost:37777
```

The worker auto-starts when a session begins with "startup", "clear", or "compact" in the first prompt. For other sessions, tool hooks still record observations — but search requires the worker to be running.

## Interaction With Our Existing Memory System

**claude-mem reads, Bravo writes.** claude-mem passively records what Bravo does. Bravo continues writing to brain/STATE.md, memory/ACTIVE_TASKS.md, etc. as per Rule 0.

**No conflicts with MCP memory server.** `@modelcontextprotocol/server-memory` stores named entities (knowledge graph). claude-mem stores time-series observations (what happened, when, what files). Different data models, different use cases.

**When to use claude-mem search vs. reading memory files:**
- Reading `memory/SESSION_LOG.md` → current session's structured decisions and task status
- `/mem-search` → tool-level observations from any past session (what files were touched, what commands ran)

## Configuration

Settings auto-created at `~/.claude-mem/settings.json` on first run. No manual configuration required for basic operation.

## Installation Record

- **Installed:** 2026-04-06
- **Version:** 11.0.0
- **Method:** `npx claude-mem@11.0.0 install --ide claude-code`
- **Plugin dir:** `~/.claude/plugins/marketplaces/thedotmack/`
- **Registered in:** `~/.claude/settings.json` under `enabledPlugins`
- **Bun status:** Not yet installed — auto-installs on first session with "startup" prompt

## Obsidian Links
- [[skills/memory-management/SKILL]] | [[brain/CAPABILITIES]] | [[memory/SESSION_LOG]]
