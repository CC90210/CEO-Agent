---
name: architecture-migration-gate
description: "Fires during any architectural migration (DB, hosting, framework swap). Generates a documentation impact manifest pre-migration and enforces a doc sweep post-migration so no brain/memory file is left with stale references."
tier: core
owner: bravo
risk: normal
tags: [architecture, migration, documentation, integrity, gate]
# `triggers` (plural, keyword list) is what build_capability_graph indexes and
# capability_query resolves against. This skill shipped with `trigger:` — singular,
# one prose sentence — which the graph does not read, so harness_eval flagged
# "skill has no triggers — agent can't route to it". A gate nobody can discover is
# a gate that never fires: the same failure this skill exists to prevent, one
# level up.
# KEEP THIS ON ONE LINE. _read_frontmatter is line-based (splitlines +
# partition(":"), not a YAML parser), so a wrapped list silently loses every line
# after the first — which is how the first attempt at this fix still read as zero
# triggers.
triggers: [migrate, migration, cut over, cutover, switch backend, replace database, decommission, deprecate component, swap framework, change hosting, doc sweep, documentation drift, stale references, architecture change]
---

# Architecture Migration Gate

> **Purpose:** Prevent documentation debt from accumulating during architectural migrations. Every migration that replaces a named system component (database, hosting, framework, service) MUST run this gate before being marked "complete."

## Why This Exists

The Supabase-to-Turso migration (completed 2026-08) was executed correctly at the infrastructure/code level but left 40+ documentation files referencing "Supabase" as the primary backend. This caused agents to mis-route DB queries for weeks. Root causes:

1. No doc-sweep step in the migration skill (`turso-patterns`)
2. No automated detection for semantic staleness (frontmatter dates don't catch factual errors)
3. Multi-session drift: each session updated its own files but never swept the broader corpus
4. Additive-only edits: new references added, old ones never removed

## Pre-Migration: Documentation Impact Manifest

Before starting any migration, run:

```bash
python scripts/core/doc_sweep.py --term "<old-component>" --brain --memory --dry-run
```

This produces a manifest of every file referencing the component being replaced. Save this manifest — it's the checklist for post-migration cleanup.

**Manual checklist (if doc_sweep.py doesn't exist yet):**

```bash
# Example: migrating from Supabase to Turso
grep -rin "supabase" brain/ memory/ --include="*.md" | grep -v "_archive" | grep -v "RETROSPECTIVE" > tmp/migration_doc_manifest.txt
wc -l tmp/migration_doc_manifest.txt
```

Review the manifest. Files in `brain/` and `memory/` that are NOT historical (retrospectives, research notes) MUST be updated post-migration.

## Post-Migration: Documentation Sweep

After the migration code is verified and live:

1. **Re-run the manifest:**
   ```bash
   python scripts/core/doc_sweep.py --term "<old-component>" --brain --memory --dry-run
   ```

2. **For each hit, classify:**
   - **STALE (must fix):** File presents the old component as current/primary
   - **HISTORICAL (leave):** Retrospectives, research notes, changelogs — add `[HISTORICAL]` annotation if missing
   - **TRANSITIONAL (annotate):** File correctly describes a dual-state (e.g., "legacy Supabase retained for event bus")

   **How to annotate, concretely.** Put the marker `legacy-ok` inline on the line,
   or in an HTML comment on the line directly above — the second form is the one
   to use inside a markdown table, where an inline marker would render as visible
   text in the cell:

   ```markdown
   <!-- legacy-ok: event bus stays on Postgres LISTEN/NOTIFY, libSQL has no pub/sub -->
   | Event bus | Supabase `agent_events` | LISTEN/NOTIFY |
   ```

   `doc_sweep.py` then counts that hit under `annotated` and stops holding the
   gate closed on it. Say WHY in the comment — an unexplained marker is just a
   silencer, and the next person cannot tell a decision from a snooze.

   THIS MATTERS MORE THAN IT LOOKS. Without annotation the gate exits 1 forever,
   because plenty of correct sentences must keep naming the old component — 108
   Tier-1/2 hits on the day the tool shipped, most of them true. A gate that can
   never pass gets bypassed, and a bypassed gate still reads as coverage.

3. **Fix all STALE hits.** The edit pattern:
   - Replace old-component-as-primary with new-component-as-primary
   - If the old component is still running in any capacity, add a `DEPRECATED — legacy only` annotation with the specific remaining dependencies
   - Update frontmatter `last_updated` and `verified` dates

4. **Update these critical files (always):**
   - `brain/CAPABILITIES.md` — Tech Stack section, SDK Integrations, App Registry
   - `brain/STATE.md` — Infrastructure counts
   - `brain/QUICK_REFERENCE.md` — Tool routing tables
   - `brain/APP_REGISTRY.md` — Per-app DB/hosting column
   - `brain/CREDENTIALS_SCAFFOLD.md` — Required vs Legacy credentials
   - `memory/LONG_TERM.md` — High-confidence facts table
   - `brain/C_SUITE_ARCHITECTURE.md` — Shared data layer
   - `brain/AGENT_INDEX.md` — Cross-agent data references

5. **Verify zero Tier 1/2 hits remain:**
   ```bash
   python scripts/core/doc_sweep.py --term "<old-component>" --brain --dry-run
   ```

## Completion Gate

A migration is NOT complete until:
- [ ] Infrastructure code is verified live
- [ ] `doc_sweep.py --dry-run` returns zero Tier 1/2 hits
- [ ] `LONG_TERM.md` migration row updated from "in flight" to "COMPLETE"
- [ ] `brain/STATE.md` infrastructure counts updated
- [ ] `brain/CAPABILITIES.md` Tech Stack section updated
- [ ] `brain/CREDENTIALS_SCAFFOLD.md` credentials priority updated

## Related Skills
- `skills/turso-patterns/SKILL.md` — Turso-specific migration patterns
- `skills/self-healing/SKILL.md` — Automated drift detection

## References
- `memory/MISTAKES.md` — The Supabase doc staleness incident (2026-08-19)
- `scripts/core/doc_sweep.py` — CLI tool for term-based doc scanning
