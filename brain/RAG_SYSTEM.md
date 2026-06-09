---
tags: [rag, memory, infrastructure, obsidian]
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# RAG System — How Memory Works Across the 4 Agents

> What "remembering" means in this architecture, where each layer lives, and how Obsidian fits in.

## The 4 Memory Layers

All 4 agents share the same memory stack. Different data, same pipes.

### 1. Markdown files (human-readable, git-versioned)
- **Location**: each agent's `brain/`, `memory/`, `knowledge/`, `docs/` directories
- **Purpose**: curated, editable knowledge — docs, playbooks, SOPs, session logs
- **Accessed by**: Obsidian (graph view), Claude Code (direct file reads), other agents (cross-repo reads)
- **Current size**: Bravo has 435 markdown files, 1,714 `[[wikilinks]]` across them

### 2. Obsidian graph
- **Binary**: `C:\Program Files\Obsidian\Obsidian.exe`
- **4 vaults registered** (vault picker on launch):
  - Bravo: `C:\Users\User\Business-Empire-Agent`
  - Atlas: `C:\Users\User\APPS\CFO-Agent`
  - Maven: `C:\Users\User\CMO-Agent`
  - Aura: `C:\Users\User\AURA`
- **Graph scope**: per-vault (Obsidian doesn't cross vaults by default)
- **Cross-vault hub**: [[brain/AGENT_INDEX]] lives in Bravo and references all agents

### 3. Shared Supabase (`phctllmtsogkovoilwos`)
- **Tables that make this a RAG**:
  - `memories` — categorized memory entries (mistake, pattern, decision, preference)
  - `agent_traces` — every material action with agent + span_id + trace_id + timestamp
  - `skill_activation` — pattern scoring (recency × 0.3 + frequency × 0.4 + confidence × 0.3)
  - `session_logs` — cross-agent session summaries
- **RPC helpers**:
  - `search_memories(query)` — semantic search across memory entries
  - `log_trace(agent, action, payload)` — append to traces
  - `calculate_activation_score(skill_id)` — refresh a pattern's score
- **Tagging convention**: every row has `agent` ('bravo' | 'atlas' | 'maven' | 'aura'); Aura adds `resident` ('cc' | 'adon' | 'shared')

### 4. Claude-mem plugin (11.0.1)
- **Location**: `/c/Users/User/.claude/plugins/cache/thedotmack/claude-mem/`
- **Purpose**: cross-session conversation memory, searchable
- **Tools exposed** (via Claude Code skills):
  - `mem-search` — query prior session content
  - `smart-explore` — tree-sitter AST codebase search
  - `smart-outline` / `smart-unfold` — navigate structure
  - `timeline-report` — project history narrative
- **Shared across all 4 agents**: same plugin install, per-project cache

## How Bravo Uses All 4 Layers In One Answer

When you ask *"what happened in marketing last week?"*:

1. **Markdown** (instant): read `../CMO-Agent/memory/SESSION_LOG.md`
2. **Obsidian graph** (only if I need context on linked docs): follow backlinks from cmo_pulse references
3. **Supabase** (queryable history): `SELECT * FROM agent_traces WHERE agent='maven' AND created_at > now() - interval '7 days'`
4. **Claude-mem** (fuzzy, conversational): `mem-search "ad campaign last week"` for prior chats about it

I typically query layers 1 + 3 for structured answers; layers 2 + 4 for harder narrative questions.

## Why "Symbiotic"

Each layer feeds the others:
- Obsidian notes get indexed by claude-mem on edit
- Agent actions write to Supabase `agent_traces` + update `skill_activation`
- Supabase `memories` can be surfaced in Obsidian via dataview queries (wire this up later if needed)
- Every session, Bravo's `ceo_pulse.json` + `brain/STATE.md` update — which shows up in the graph next session

If you write something in a markdown file, it's also available as structured data (via Supabase if tagged) and as conversational memory (via claude-mem). Three entry points to the same knowledge.

## Fix Checklist (run if Obsidian misbehaves)

1. **Won't open** → clear cache: `del /q "%APPDATA%\obsidian\Cache\*"` (Windows) or use vault picker (⌘/Ctrl+O)
2. **Graph stuck / empty** → Settings → Community plugins → rebuild cache; or just close and reopen the vault
3. **Broken links** → run `python scripts/obsidian_link_check.py` (if it exists) or scan with grep
4. **Vault not in picker** → edit `C:\Users\User\AppData\Roaming\obsidian\obsidian.json` and add the vault entry
5. **Stuck "Ops, can't open vault"** → remove the `workspace.json` in that vault's `.obsidian/` dir; Obsidian will rebuild fresh
6. **Post-refactor cleanup** → after big renames/migrations, scan for broken wikilinks across the vault

## Obsidian Config Files (per vault)

Every vault has `.obsidian/`:
- `app.json` — general settings
- `appearance.json` — theme, fonts
- `core-plugins.json` — which built-ins are on (graph, backlinks, tag-pane, etc.)
- `community-plugins.json` — array of enabled 3rd-party plugins
- `plugins/` — plugin code
- `graph.json` — graph view filters
- `hotkeys.json` — custom shortcuts
- `workspace.json` — current layout (tabs, sidebar, last-open file). If corrupted, deleting this is safe — Obsidian rebuilds.

## Related

- [[brain/AGENT_INDEX]] — cross-vault hub
- [[brain/C_SUITE_ARCHITECTURE]] — overall governance
- [[brain/CROSS_AGENT_AWARENESS]] — pulse-file passing
- [[brain/SHARED_DB]] (in Maven's vault) — Supabase schema detail
