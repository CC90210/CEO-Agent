---
description: "Central index for the 4-agent ecosystem (Bravo/Atlas/Maven/Aura): maps governance, cross-agent workflows, shared DB, and app registry"
tags: [index, agents, hub, graph]
last_updated: 2026-07-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# Agent Index — The 4-Agent Graph Hub

> The central hub connecting Bravo, Atlas, Maven, and Aura. Open this file in Obsidian to see the full agent graph. Every agent doc in every repo should eventually link back here.

## The 4 Agents

- [[brain/C_SUITE_ARCHITECTURE]] — governance, decision rights, pulse protocol, shared DB
- [[brain/CROSS_AGENT_AWARENESS]] — how pulses pass the baton + multi-resident privacy (Aura)
- [[brain/HOW_TO_USE_THE_4_AGENTS]] — decision tree, per-agent use cases, cross-agent workflows
- [[brain/APP_REGISTRY]] — all apps + agents mapped to local paths and GitHub repos

### 🏛️ Bravo (CEO — you are here)
- Identity: [[brain/SOUL]]
- State: [[brain/STATE]]
- Active tasks: [[memory/ACTIVE_TASKS]]
- Skill routing: [[AGENTS]]
- Revenue + OKRs: [[brain/OKRs]], [[brain/CEO_OPERATING_SYSTEM]]
- Dashboard: [[brain/DASHBOARD]]

### 💰 Atlas (CFO) — cross-repo
Atlas lives at `C:\Users\User\APPS\CFO-Agent`. Its docs aren't in Bravo's vault by default; open Atlas as a separate Obsidian vault for full graph access.
- Key docs (browse via Obsidian vault picker): SOUL, USER, STATE, STRUCTURE, AGENT_ORCHESTRATION, 60+ tax playbooks under `docs/`
- Data Bravo reads from Atlas: `data/pulse/cfo_pulse.json` — runway, liquid, spend gate, tax reserve

### 🎨 Maven (CMO) — cross-repo
Maven lives at `C:\Users\User\CMO-Agent`. Open as separate vault for full graph.
- Key docs: SOUL, CLAUDE, START_HERE, ENV_STRUCTURE, SHARED_DB, brain/clients/ (5 profiles)
- Campaigns: `campaigns/pulse-lead-gen/` (4-hook playbook)
- Data Bravo reads: `data/pulse/cmo_pulse.json` — content pipeline, ad performance, funnel metrics

### 🏠 Aura (Life/Home) — cross-repo
Aura lives at `C:\Users\User\AURA`. Raspberry Pi 5 hub. Open as separate vault.
- Key docs: CLAUDE, ROOMMATE_AGENT_PROTOCOL (multi-resident privacy), voice-agent/, dashboard/
- Data Bravo reads: `data/pulse/aura_pulse.json` — CC presence, energy, habit streaks, apartment status

## How the Graph Works Across Vaults

Obsidian's graph view shows wikilinks inside the current vault only. To see the full 4-agent picture:

1. **In Bravo's vault** (this one): see all Bravo brain/memory/skills + references to other agents via this index
2. **Switch vault** (Obsidian → ⌘/Ctrl+O → Open another vault): pick Atlas, Maven, or Aura from the vault picker
3. All 4 vaults registered at `C:\Users\User\AppData\Roaming\obsidian\obsidian.json`

Each agent's brain/ is its own sovereign space — this is intentional. Cross-agent synthesis happens via:
- [[brain/CROSS_AGENT_AWARENESS]] — pulse file reads
- [[brain/SHARED_DB]] (in Maven's vault) — Supabase `phctllmtsogkovoilwos`, 38 tables, all 4 agents read/write

## The Shared Data Layer

- **Pulse files** (JSON, per-agent sovereign path): fast "now-state" — runway, MRR, content pipeline, presence
- **Shared Supabase** (`phctllmtsogkovoilwos`): long-term memory — `agent_traces`, `skill_activation`, `session_logs`, `agent_state`, `content_calendar`, `leads`, `funnels`, etc. (38 tables)
- **Each app's own DB**: Turso for PULSE, OASIS Supabase, Nostalgic Supabase, etc.

## When You Need To Find Something

| I need... | Where |
|-----------|-------|
| Current strategy / OKRs | [[brain/OKRs]] + [[data/pulse/ceo_pulse.json]] |
| Runway / money / tax | Atlas vault → `cfo_pulse.json` + `USER.md` |
| Current ad performance | Maven vault → `cmo_pulse.json` + `campaigns/` |
| My habits / presence / energy | Aura vault → `aura_pulse.json` |
| Any app (PULSE, PropFlow, etc.) | [[brain/APP_REGISTRY]] |
| How to decide which agent to ask | [[brain/HOW_TO_USE_THE_4_AGENTS]] |
| What's happening right now across all 4 | Ask Bravo directly — I synthesize the pulses |

## Related Hub Docs

- [[brain/SOUL]] | [[brain/STATE]] | [[brain/USER]]
- [[brain/BRAIN_LOOP]] | [[brain/INTERACTION_PROTOCOL]]
- [[AGENTS]] | [[brain/CAPABILITIES]] | [[brain/QUICK_REFERENCE]]
- [[brain/ORCHESTRATION]] | [[brain/CROSS_MACHINE_SYNC]]
- [[brain/DAILY_SCHEDULE]] | [[brain/CLIENT_READY]] | [[brain/RISK_REGISTER]]
