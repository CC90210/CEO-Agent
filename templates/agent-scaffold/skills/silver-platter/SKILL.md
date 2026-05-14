---
name: silver-platter
description: Per-agent data-readiness audit for {{AGENT_NAME}}. Produces an HTML report mapping Pantry (raw sources), Prep Table (deterministic snapshots), and Plate (consumers) with a Mermaid data-flow diagram and ranked quick-win list. V6.7 default skill.
tags: [skill, audit, data, agentic-os, foundation]
triggers: ["silver platter", "data audit", "data readiness audit", "audit my data", "pantry prep table plate", "where does my data live"]
owner: {{agent_name}}
tier: T2
risk: low
canonical_pattern: ../../../Business-Empire-Agent/skills/silver-platter/SKILL.md
---

# Silver Platter — {{AGENT_NAME}} Data-Readiness Audit

## Overview

"Put the core data on a silver platter so agents spend their session analyzing, not retrieving." (brain/AGENTIC_OS_REFERENCE.md §3)

This skill audits {{AGENT_NAME}}'s data layer and produces an HTML report at `tmp/silver-platter-{{agent_name}}-YYYY-MM-DD.html` with Pantry / Prep Table / Plate sections, a Mermaid data-flow diagram, and a ranked quick-win list.

**When to invoke:**
- New agent forge (Day 0 self-knowledge doc)
- Quarterly review
- After adding a major integration
- When the operator asks "where does my data live"

**Trigger:** `silver platter`, `data audit`, `/silver-platter`

## What the audit produces

1. **Pantry** — every raw source. Status active/dead/stale.
2. **Prep Table** — every deterministic pre-aggregation with refresh cadence + last-refresh timestamp.
3. **Plate** — every consumer (skills, agents, dashboards) and what they read.
4. **Data flow** — Mermaid diagram. Arrows from Pantry → Prep Table → Plate. Flag direct Pantry → Plate paths as quick-wins.
5. **Quick-wins** — Ranked list. Each entry: gap description, affected components, estimated effort, estimated savings.

## Execution Protocol

1. **Read inputs:** `brain/DATA_TAXONOMY.md`, `ls scripts/snapshots/`, `brain/CAPABILITY_GRAPH.json` (if present).
2. **Trace each Plate consumer** back through the chain. Flag any consumer reading a Pantry source directly without Prep Table in between.
3. **Score quick-wins:** `score = (session_savings_sec / build_minutes) * agents_affected`. Sort descending.
4. **Render** single-file HTML, no external deps. Mermaid via CDN.
5. **Confirm in chat:** N pantry sources, M prep tables (K stale), P plate consumers, Q quick-wins. Report path.

## Anti-Patterns

- ❌ Producing the audit without quick-wins ranking. The prioritized action list is the point.
- ❌ Auditing without verifying snapshot freshness. Stale snapshots are a finding, not a free pass.

## Integration

- **brain/AGENTIC_OS_REFERENCE.md** — the principle
- **brain/DATA_TAXONOMY.md** — the manifest
- **scripts/snapshots/** — Prep Table implementations
- **state/snapshots/** — snapshot outputs

## Cross-Agent Consistency

Bravo's `~/Business-Empire-Agent/skills/silver-platter/SKILL.md` is the master. When it updates, mirror here.

## Obsidian Links
- [[brain/AGENTIC_OS_REFERENCE]] | [[brain/DATA_TAXONOMY]]
- [[skills/integrations-sync/SKILL]] | [[skills/memory-journaling/SKILL]]
