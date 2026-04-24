---
name: semantic-memory
description: Use this skill when storing or retrieving preferences, facts, or context that should be searchable by meaning rather than exact keyword. Activates when CC says "remember that", "what do I prefer", or any query requiring fuzzy recall across sessions.
triggers: [remember, recall, preferences, semantic search, mem0, memory search, what does CC prefer, cross-session context]
tier: standard
dependencies: [memory-management, knowledge-management]
tags: [skill, memory, semantic, mem0, vector, embeddings]
---

# Semantic Memory Skill

Bravo maintains two complementary memory systems. This skill governs the **semantic layer** (mem0ai).
The two systems are designed to work together, not replace each other.

## The Two Memory Systems

| Dimension | Markdown Memory | Semantic Memory (mem0) |
|-----------|----------------|------------------------|
| Tool | brain/, memory/ .md files | `scripts/mem0_tool.py` |
| Search | Exact keyword / grep | Natural language / vector similarity |
| Storage | Git-tracked files | Local Qdrant (data/mem0_qdrant/) |
| Human-readable | Yes — Obsidian-integrated | No — binary vector store |
| Auto-deduplication | No — manual | Yes — LLM merges similar facts |
| Cross-session | Yes | Yes |
| Best for | Structured state, logs, plans, decisions | Preferences, facts, context retrieval |
| When to use | STATE.md, ACTIVE_TASKS.md, SESSION_LOG.md | Preferences, client facts, CC's style |

They are **complementary, not competing**. Structural state goes in markdown. Semantic facts go in mem0.

## When to Use mem0 (This Skill)

- CC says "remember that I prefer X" or "don't forget Y"
- Retrieving CC's preferences, working style, or past decisions for a task
- Injecting relevant context at the start of a complex session
- Any recall query that would require reading 10+ markdown files to answer manually
- Cross-session preference persistence that doesn't belong in STATE.md

## When to Use Markdown Memory Instead

- Task status, progress, next steps → `memory/ACTIVE_TASKS.md`
- Session events, what was done → `memory/SESSION_LOG.md`
- Current operational state → `brain/STATE.md`
- Decisions with rationale → `memory/DECISIONS.md`
- Mistakes + prevention → `memory/MISTAKES.md`
- Patterns + validated approaches → `memory/PATTERNS.md`

## CLI Commands

```bash
# Store a fact (mem0 auto-extracts and deduplicates)
python scripts/mem0_tool.py add "CC prefers direct communication, no filler"

# Semantic search — returns by relevance score
python scripts/mem0_tool.py search "what does CC prefer about communication"

# List all stored memories
python scripts/mem0_tool.py list --limit 20

# Retrieve a specific memory by UUID
python scripts/mem0_tool.py get <memory_id>

# Delete a memory
python scripts/mem0_tool.py delete <memory_id>

# View update history for a memory (deduplication log)
python scripts/mem0_tool.py history <memory_id>

# Statistics
python scripts/mem0_tool.py stats

# Machine-readable output (for agent consumption)
python scripts/mem0_tool.py --json search "CC preferences"
python scripts/mem0_tool.py --json list
```

Note: `--json` and `--user-id` / `--agent-id` flags must come BEFORE the subcommand.

## Architecture

```
mem0_tool.py
  ├── LLM: Claude Haiku (fact extraction + deduplication)
  ├── Embedder: fastembed thenlper/gte-large (1024-dim, local ONNX)
  └── Vector store: Qdrant embedded → data/mem0_qdrant/
                    (upgrade: set BRAVO_SUPABASE_DB_PASSWORD for pgvector)
```

**First-run note:** The fastembed model (~120 MB) downloads once on first use from HuggingFace.
Subsequent runs use the cached model at `C:\Users\User\AppData\Local\Temp\fastembed_cache\`.

## Integration with Session Protocol

At the start of a COMPLEX task, optionally inject semantic context:

```bash
python scripts/mem0_tool.py --json search "relevant topic" | head -5
```

At session end (RULE 0 sync), store any new preferences CC expressed:

```bash
python scripts/mem0_tool.py add "CC decided to use X approach for Y tasks"
```

## Upgrade Path: Supabase pgvector

When CC's Supabase DB password is available, add to `.env.agents`:

```
BRAVO_SUPABASE_DB_PASSWORD=<actual_db_password_not_service_role_key>
```

The script auto-detects this variable and switches from local Qdrant to Supabase pgvector.
The Supabase DB password is found in: Supabase Dashboard > Project Settings > Database > Connection string.

## Obsidian Links
- [[brain/CAPABILITIES]] | [[skills/memory-management/SKILL]] | [[skills/knowledge-management/SKILL]]
- [[brain/STATE]] | [[memory/ACTIVE_TASKS]]
