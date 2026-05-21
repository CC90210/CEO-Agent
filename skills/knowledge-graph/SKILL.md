---
name: knowledge-graph
description: Query the Obsidian vault as a live knowledge graph — PageRank, community detection, semantic search, path-finding, and vault writes via MCP.
tags: [skill, mcp, knowledge, obsidian, graph, search]
triggers: ["knowledge graph", "use knowledge graph", "run knowledge graph"]
---

# Knowledge Graph — Vault as Queryable Graph

> MCP server: `knowledge-graph`
> Source: `C:\Users\User\tools\knowledge-graph`
> Vault: `C:\Users\User\Business-Empire-Agent` (2,117 nodes / 3,725 edges / 696 communities at last index)
> Data dir: `C:\Users\User\tools\knowledge-graph\data`

## What This Gives You

The Obsidian vault is parsed into a SQLite-backed graph with:
- **PageRank centrality** — which notes are most structurally important
- **Betweenness centrality (bridge nodes)** — which notes connect otherwise separate clusters
- **Louvain community detection** — automatically grouped topic clusters (696 detected)
- **Semantic search** — transformer embeddings (lazy-loaded on first use)
- **Full-text search** — BM25-style keyword search, instant
- **Path-finding** — shortest connecting path between any two nodes
- **Vault writes** — create new nodes, annotate existing ones, add wiki-links

## Tools Reference

### Read Tools

| Tool | When to Use | Key Params |
|------|-------------|------------|
| `kg_search` | Find relevant notes by meaning or keyword | `query`, `fulltext` (bool), `limit` |
| `kg_node` | Inspect a single note — metadata, links, content | `name` (fuzzy), `brief` (bool), `maxContentLength` |
| `kg_neighbors` | Explore what connects to a note | `name`, `depth` (default 1) |
| `kg_subgraph` | Get a local neighborhood as a self-contained graph | `name`, `depth` |
| `kg_paths` | Find connecting route between two notes | `from`, `to`, `maxDepth` |
| `kg_common` | Find shared connections between two notes | `nodeA`, `nodeB` |
| `kg_central` | Top notes by PageRank (most linked-to) | `limit`, `community` (optional filter) |
| `kg_bridges` | Top bridge nodes by betweenness centrality | `limit` |
| `kg_communities` | List all Louvain community clusters | — |
| `kg_community` | Get members of a specific community | `id` (number or label) |

### Write Tools

| Tool | When to Use | Key Params |
|------|-------------|------------|
| `kg_index` | Re-index vault after large changes | `resolution` (Louvain, default 1.0) |
| `kg_create_node` | Create a new markdown file in the vault | `title`, `directory`, `content`, `frontmatter` |
| `kg_annotate_node` | Append content to an existing note | `name`, `content` |
| `kg_add_link` | Add a wiki-link from one note to another | `source`, `target`, `context` |

## When to Use Knowledge Graph vs Other Tools

| Task | Use |
|------|-----|
| "What notes relate to PropFlow revenue?" | `kg_search` (semantic) |
| "Find all notes tagged [skill]" | `kg_search fulltext` with tag query, or Grep |
| "What does STATE.md link to?" | `kg_node "STATE"` |
| "How does SOUL.md connect to ACTIVE_TASKS?" | `kg_paths` |
| "Which notes are most central to the vault?" | `kg_central` |
| "Which notes bridge disconnected clusters?" | `kg_bridges` |
| "What topic cluster does client-health belong to?" | `kg_node` → check `community` in frontmatter result |
| Find a specific string in a file | Grep (exact match is faster than graph) |
| Read a specific file's content | Read tool (direct, no overhead) |
| Search mem0 knowledge graph | Memory MCP `search_nodes` (different graph — personal facts, not vault) |

## Decision: Knowledge Graph vs Memory MCP vs Grep

```
Query is about vault STRUCTURE or RELATIONSHIPS?
  YES → knowledge-graph MCP

Query is about CC's personal facts, preferences, or past decisions?
  YES → Memory MCP (search_nodes)

Query is a known string/pattern in a known file?
  YES → Grep (faster, exact)

Query is "find notes conceptually similar to X"?
  YES → kg_search (semantic, no fulltext flag)

Query is "find notes containing the word X"?
  YES → kg_search (fulltext: true) OR Grep
```

## Example Queries

```
# What notes are semantically related to MRR growth?
kg_search { query: "MRR growth revenue pipeline", limit: 10 }

# Show me STATE.md with its connections
kg_node { name: "STATE", brief: true }

# How does the SOUL connect to ACTIVE_TASKS?
kg_paths { from: "SOUL", to: "ACTIVE_TASKS", maxDepth: 4 }

# What are the most central notes in the vault?
kg_central { limit: 10 }

# Which notes bridge disconnected clusters?
kg_bridges { limit: 10 }

# What are the main topic communities?
kg_communities {}

# Find shared context between two skills
kg_common { nodeA: "codex-delegation", nodeB: "task-routing" }

# Create a new decision record
kg_create_node {
  title: "Decision — Pricing Model 2026-Q3",
  directory: "memory",
  content: "## Context\n...",
  frontmatter: { tags: ["decision"], date: "2026-04-06" }
}

# Re-index after adding many new files
kg_index { resolution: 1.0 }
```

## Re-indexing

Run `kg_index` via the MCP tool whenever:
- A significant batch of new files was added to the vault
- Wiki-links were restructured across many files
- Community assignments look stale

Or from CLI:
```bash
cd /c/Users/User/tools/knowledge-graph
KG_VAULT_PATH="C:/Users/User/Business-Empire-Agent" KG_DATA_DIR="C:/Users/User/tools/knowledge-graph/data" npx tsx src/cli/index.ts index
```

## Notes

- **Semantic search** lazy-loads a transformer model on first use — expect ~5s delay for the first semantic call per session. Subsequent calls are fast.
- **Full-text search** (`fulltext: true`) is instant — use it when the query is a known term, not a concept.
- **Node names** are fuzzy-matched. Use a distinctive substring if the full path is long (e.g., `"ACTIVE_TASKS"` not `"memory/ACTIVE_TASKS.md"`).
- **`kg_index` resolution**: Lower values (0.5) produce fewer, larger communities. Higher values (2.0) produce more granular clusters. Default 1.0 works well for this vault size.
- Index is stored at `C:\Users\User\tools\knowledge-graph\data\kg.db` — persists across sessions.

## Obsidian Links
- [[brain/CAPABILITIES]] | [[brain/STATE]] | [[skills/memory-management/SKILL.md]]
