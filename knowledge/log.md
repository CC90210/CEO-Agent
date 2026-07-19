---
tags: [knowledge, log, ingest-history]
last_updated: 2026-04-06
---

# KNOWLEDGE LOG — Chronological Ingest History

> Every ingest operation appends an entry here. Never edit past entries — append only.
> [[knowledge/SCHEMA]] | [[knowledge/index]] | [[skills/knowledge-compilation/SKILL]]

## Format

Each entry records: date, source, pages created or updated, agent that ran the ingest, and any notes.

```
### YYYY-MM-DD — [operation type]
**Source:** `raw/filename.md` or inline
**Pages affected:** ``wiki/page-name`` (created | updated)
**Agent:** [who ran it]
**Notes:** [anything relevant — gaps, conflicts with existing knowledge, follow-ups]
```

---

## Ingest History

### 2026-04-06 — Initial knowledge compilation
**Source:** Compiled from `brain/STATE.md`, `brain/USER.md`, `brain/CAPABILITIES.md`, `memory/ACTIVE_TASKS.md`
**Pages created:**
- [[knowledge/wiki/ai-automation-agency]] — OASIS AI services, positioning, ICP, differentiation
- [[knowledge/wiki/revenue-model]] — [ARCHIVED 2026-05-18] Full MRR breakdown pre-2026-05-18; preserved as historical context
- [[knowledge/wiki/tech-stack]] — Complete technology inventory across all tools and integrations
- [[knowledge/wiki/client-playbook]] — Client acquisition, onboarding, retention, health scoring
**Agent:** Bravo (Claude Sonnet 4.6) via Claude Code
**Notes:** Initial seed compilation. All four pages created from existing brain/ and memory/ files.
No raw/ documents existed at the time of first compilation. All knowledge sourced from agent
brain files. Confidence set at 0.90–0.92 reflecting high-fidelity first-party sources.

---

_Append new entries above this line as new ingests are performed._

## 2026-04-08 — frontier-models ingest
Added `wiki/frontier-models.md` (model landscape snapshot). Recorded retroactively 2026-07-19 — this entry was missed at ingest time.

## 2026-05-18 — revenue-model archived
`wiki/revenue-model.md` archived after the primary-retainer end reshaped the revenue model. Recorded retroactively 2026-07-19.

## 2026-07-19 — currency sweep refresh
`tech-stack.md` rewritten against live sources (graph totals 151/116/32/35/14, 9+4 MCPs, fable-5 standard, CLI-first model calls, CC Funnel retired, Atlas post-trading). Index confidences decayed per SCHEMA (0.05/30d).
