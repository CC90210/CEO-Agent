---
tags: [memory, hub, index]
---

# memory/ — Operational Memory Hub

> Index for `memory/`. Links active task tracking, session log, decision log, and the historical archives.
>
> Parent: [[brain/INDEX]] · Companion: [[brain/STATE]] (current ephemeral state)

## Active state (updated every session)
- [[brain/STATE]] — stable identity / North Star / capability architecture (30-day threshold)
- [[memory/OPERATIONAL_STATE]] — ephemeral infra status, known issues, last-heartbeat (7-day threshold; split from STATE.md 2026-05-07)
- [[memory/ACTIVE_TASKS]] — current task queue with owners + ETAs (7-day threshold)
- [[memory/SESSION_LOG]] — chronological log of every session (compacted via context_manager)
- [[memory/MEMORY_INDEX]] — older memory-system index pointer
- [[memory/LONG_TERM]] — durable cross-session memory snapshots
- [[memory/PERSONAS]] — role-flavored GWS workflow aliases (consolidated from archived persona-* skills, 2026-05-07)

## Decision + learning records
- [[memory/DECISIONS]] — architectural and product decisions with rationale
- [[memory/MISTAKES]] — root-caused failures + prevention rules (Rule 9)
- [[memory/PATTERNS]] — validated approaches promoted from probationary
- [[memory/SOP_LIBRARY]] — standard operating procedures
- [[memory/PROPOSED_CHANGES]] — semi-mutable file change staging
- [[memory/CLAUDE_HANDOVER]] — multi-session handoff notes
- [[memory/SELF_REFLECTIONS]] — Reflexion-pattern post-failure analyses

## Reference + research
- [[memory/DISCOVERY_PLAYBOOK]] — NEPQ discovery questions for sales calls
- [[memory/research/2026-04-06-deep-research-intelligence]] — research-engine deep dive
- [[memory/content/scripts_v1]] — historical content scripts (now Maven-canonical at ../CMO-Agent)

## Daily notes
- [[memory/daily/INDEX]] — daily-note hub
- [[memory/daily/2026-03-01_content_scripts]] · [[memory/daily/2026-04-19]]

## Outreach archive (historical campaigns)
- [[memory/outreach_archive/INDEX]] — outreach archive hub
- [[memory/outreach_archive/SUMMARY_2026_03_02]]
- [[memory/outreach_archive/2026-03-02_dj_outreach]] · [[memory/outreach_archive/2026-03-02_leads_batch2]] · [[memory/outreach_archive/2026-03-02_outreach_drafts]] · [[memory/outreach_archive/2026-03-02_outreach_manifest]]
- [[memory/outreach_archive/2026-03-03_leads_batch1]] · [[memory/outreach_archive/2026-03-11_linkedin_blitz]]

## Archives (compacted older sessions + retired material)
- [[memory/ARCHIVES/README]] — what lives in archives + how to read it
- [[scratch/oneshots-2026-04/README]] — 2026-04 one-shot scripts archive (post_call_update, tremont, warm-revival batch)
- [[memory/ARCHIVES/sessions-2026-02]] · [[memory/ARCHIVES/sessions-2026-03]] · [[memory/ARCHIVES/sessions-2026-04]]
<!-- (untracked 2026-05-09) historical primary-retainer proposal — preserved locally in memory/ARCHIVES/ (gitignored) -->
- [[memory/ARCHIVES/WHATSAPP_BRIDGE_SOP]] — retired WhatsApp bridge SOP
- [[memory/ARCHIVES/lead_system/README]] — early lead-system reference dump
- [[memory/ARCHIVES/references-setup/Claude_Setup_Guide]]
- [[memory/ARCHIVES/references-setup/awesome-claude-skills/README]]

## NOTE on auto-memory (separate from this directory)
Some files referenced in chat history (e.g., `feedback_system_philosophy.md`, `project_alejandro_andrade.md`, `project_v6_architecture.md`, `codex_integration.md`, `zernio_rebrand.md`, `atlas_cfo_upgrade.md`, `singlekey_research.md`, `content_pipeline_vision.md`) live in Claude Code's **auto-memory store** at `~/.claude/projects/c--Users-User-Business-Empire-Agent/memory/` — NOT in this vault. They're outside Obsidian's reach by design (per-conversation persistence). See system-prompt auto-memory section for the pointer pattern.

## Files in this directory

- [[memory/ACTIVE_TASKS.template]]
- [[memory/HANDOFF]]
- [[memory/SESSION_LOG.template]]
- [[memory/WORKING]]

## Related leaves
- [[memory/poems/sub_agents_collective_intelligence]]
