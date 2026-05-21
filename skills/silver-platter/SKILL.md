---
name: silver-platter
description: Per-agent data-readiness audit. Produces an HTML report mapping Pantry (raw sources), Prep Table (deterministic snapshots), and Plate (agent consumers) with a Mermaid data-flow diagram and ranked quick-win list. The audit deliverable from brain/AGENTIC_OS_REFERENCE.md §5.
tags: [skill, audit, data, agentic-os, foundation]
triggers: ["silver platter", "data audit", "data readiness audit", "audit my data", "pantry prep table plate", "where does my data live"]
owner: bravo
tier: T2
risk: low
---

# Silver Platter — Data-Readiness Audit

## Overview

"Put the core data on a silver platter so agents spend their session analyzing, not retrieving." (brain/AGENTIC_OS_REFERENCE.md §3)

This skill runs the data-readiness audit the reference doc calls for. Input: the agent's repo. Output: a single HTML report at `tmp/silver-platter-<agent>-YYYY-MM-DD.html` with three sections (Pantry / Prep Table / Plate), a data-flow Mermaid diagram, and a ranked list of quick-wins.

**When to invoke:**
- New agent provisioning (Day 0 self-knowledge doc)
- Quarterly reviews ("are we still pre-aggregating the right things?")
- After adding a major integration ("does our Prep Table cover the new source?")
- When CC asks "where does my data live" / "what's our data audit"

**Trigger:** `silver platter`, `data audit`, `/silver-platter`

## What the audit produces

A single-page HTML report with these tabs/sections:

1. **Pantry** — every raw source the agent can reach. Columns: domain, source, access method (CLI/MCP/API), owner, status (active/dead/stale). Sourced from `brain/DATA_TAXONOMY.md` + scan of `scripts/*_tool.py` + `.env.agents` keys.

2. **Prep Table** — every deterministic pre-aggregation. Columns: snapshot name, script path, schedule, output JSON path, last-refresh timestamp (from the JSON `ts` field), staleness flag. Sourced from `brain/DATA_TAXONOMY.md` + scan of `scripts/snapshots/` + `state/snapshots/`.

3. **Plate** — every consumer (agents, skills, dashboards) and which Prep Table they read. Columns: consumer, source it reads, delivery channel.

4. **Data flow** — Mermaid diagram. Arrows from Pantry → Prep Table → Plate, plus any direct Pantry → Plate paths (these are the anti-patterns the audit is meant to surface).

5. **Quick-wins** — ranked list. Each entry: gap description, affected agents/skills, estimated effort (Bravo time), estimated savings (sec/session). Sorted by savings/effort ratio.

## Execution Protocol

### Step 1: Resolve the agent

Default: Bravo (current repo). If CC says "audit Maven" / "audit Atlas" / "audit Hermes", switch repo root to the matching path:
- Maven: `C:\Users\User\CMO-Agent`
- Atlas: `C:\Users\User\APPS\trading-agent`
- Hermes: `C:\Users\User\APPS\hermes`

If the sibling repo lacks `brain/DATA_TAXONOMY.md`, surface that as the first quick-win and run a partial audit from `scripts/snapshots/`, `scripts/core/cron_engine.py`, and `.env.agents` only.

### Step 2: Collect inputs

Read in this order (each step's output feeds the next):

1. `brain/DATA_TAXONOMY.md` — authoritative manifest
2. `ls scripts/snapshots/` + `ls state/snapshots/` — what Prep Table actually exists
3. `grep -l "snapshot" scripts/core/cron_engine.py` — what's scheduled
4. `scripts/build_capability_graph.py` output — what skills/agents exist
5. `ls .env.agents | grep -i "_API_KEY\|_TOKEN"` (via the CLI wrapper, not direct read — secret_guard will block direct read) — what integrations are credentialed

### Step 3: Compute the gap list

For each consumer in the Plate section, walk back through the chain. Flag any consumer that reads a Pantry source directly without a Prep Table in between as a candidate quick-win.

Quick-win scoring formula:
```
score = (estimated_session_savings_seconds / estimated_bravo_minutes_to_build) * agents_affected
```

Sort descending. Top 5 surface in the report's hero section.

### Step 4: Render

Write `tmp/silver-platter-<agent>-<YYYY-MM-DD>.html`. Single-file HTML, no external deps. Tabs implemented as anchor links + `:target` CSS (no JS frameworks). Mermaid diagram via the CDN `<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js">` (works offline if cached).

Inline CSS: monospace headings, dark-on-light, table rows striped. Match `brain/STATE.md` aesthetic.

### Step 5: Confirm in chat

One line: `silver-platter audit for <agent>: <N> pantry sources, <M> prep tables (<K> stale), <P> plate consumers, <Q> quick-wins identified. Report at tmp/silver-platter-<agent>-<date>.html.`

If the agent has > 0 stale Prep Table snapshots, surface the top one with its age.

## Anti-Patterns

- ❌ Running this skill against the wrong repo (e.g. auditing Maven from inside Bravo without switching). Always confirm the repo path in step 1 output.
- ❌ Producing the HTML without the quick-wins ranking. The whole point is the prioritized action list — without it the audit is decorative.
- ❌ Treating `memory_index.db` as a Prep Table. It's a retrieval index over Pantry/Plate text — categorically different from a summary aggregation. Note this in the diagram if it appears.
- ❌ Reporting "everything is fine" when 3+ Pantry → Plate direct arrows exist. Those are always quick-wins.

## Integration

- **brain/AGENTIC_OS_REFERENCE.md** — the principle this skill operationalizes
- **brain/DATA_TAXONOMY.md** — the manifest this skill reads
- **scripts/snapshots/** — the Prep Table implementations
- **state/snapshots/** — where snapshot outputs live
- **scripts/capability_query.py** — for agent/skill enumeration
- **brain/CAPABILITY_GRAPH.json** — for capability metadata

## Cross-Agent Propagation

Once this skill is proven on Bravo, the same SKILL.md (with adjusted paths) should be ported to Maven, Atlas, Hermes per CLAUDE.md Rule 4. Each sibling agent should be able to invoke its own silver-platter audit.

## Obsidian Links
- [[brain/AGENTIC_OS_REFERENCE]] | [[brain/DATA_TAXONOMY]] | [[brain/CAPABILITIES]]
- [[skills/ceo-briefing/SKILL.md]] | [[skills/integrations-sync/SKILL.md]]
