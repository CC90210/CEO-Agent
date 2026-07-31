---
tags: [template]
last_updated: 2026-05-21
---

# `_templates/` — Obsidian Note Templates

Markdown templates the operator pastes from when creating new Obsidian
notes (daily logs, decisions, mistakes, sessions). These are **inert
templates** — never executed, never imported, just copy-pasted.

This directory is **distinct from** `templates/`, which holds the
**agent-scaffold** template tree used by `scripts/scaffold.py` to forge new
client/sibling agents. Different purpose, different consumer.

**Heuristic:**
- Personal note templates (daily notes, decision entries, etc.) → `_templates/`
- Programmatic scaffolds for forging new agents → `templates/`

## Current contents

| File | Used in |
|---|---|
| `agent-template.md` | Defining a new sub-agent in `agents/` |
| `daily-note.md` | Obsidian daily note hotkey |
| `decision-entry.md` | `memory/DECISIONS.md` row |
| `mistake-entry.md` | `memory/MISTAKES.md` row |
| `session-log-entry.md` | Manual hand-edit to `memory/SESSION_LOG.md` (when state_manager isn't running) |
| `skill-template.md` | Bootstrap a `skills/<name>/SKILL.md` |

## Cross-reference
- [[templates/agent-scaffold/README]] — the OTHER templates directory (full agent scaffold)
