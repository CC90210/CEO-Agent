---
tags: [docs, adr, decision, index, hub]
last_updated: 2026-08-15
---

# Architecture Decision Records — Index

> Every structural decision that locks in behaviour across services, tables, agents, or
> repos lives here. An ADR is **immutable once accepted** — supersede it with a new one,
> never rewrite it. This file is the hub: every ADR links back here, and here links out
> to all of them, so the decision layer shows up as a connected cluster in the graph
> instead of 14 isolated nodes.

Related hubs: [[CONTEXT]] · [[brain/STATE]] · [[brain/CAPABILITIES]] · [[brain/V6_ARCHITECTURE]]

---

## ⚠️ Numbering collision — needs CC's call

Two pairs of ADRs share a number. Both members of each pair are `accepted` and both are
referenced elsewhere, so renumbering is **not** a safe unilateral edit (it would break
inbound references — e.g. `CLAUDE.md` cites `docs/adr/0002-context-md-canonical-vocabulary.md`).

| Number | Claimant A | Claimant B |
|---|---|---|
| **0003** | [[docs/adr/0003-agent-first-identity-pattern]] (2026-05-23) | [[docs/adr/0003-typed-workflow-step-registry]] (2026-05-25) |
| **0004** | [[docs/adr/0004-entry-file-lockstep-policy]] (2026-05-23) | [[docs/adr/0004-field-level-permission-model]] (2026-05-25) |

Recommended fix: renumber the **later** member of each pair (typed-workflow-step-registry →
0013, field-level-permission-model → 0014), leave a stub at the old filename pointing at the
new one, then `grep -rn "0003-typed\|0004-field"` and update inbound references. Needs a yes
from CC before anyone touches it — see [[brain/EXECUTION_RULES]] § shared-substrate rule.

**0013 and 0014 stay reserved for that fix.** ADR-0015 (2026-08-07) deliberately skipped
them rather than claim a number this plan has already spoken for; numbering forward is
free, and un-reserving these would silently break the remediation above.

---

## Accepted

| # | Decision | Date | Scope |
|---|---|---|---|
| 0001 | [[docs/adr/0001-skill-dependency-classification]] — hard vs soft skill dependencies | 2026-05-16 | capability graph |
| 0002 | [[docs/adr/0002-context-md-canonical-vocabulary]] — `CONTEXT.md` is the empire glossary | 2026-05-16 | vocabulary |
| 0003 | [[docs/adr/0003-agent-first-identity-pattern]] — one identity (Bravo) across all CLI entry files | 2026-05-23 | entry points |
| 0003 | [[docs/adr/0003-typed-workflow-step-registry]] — typed workflow step registry | 2026-05-25 | workflows |
| 0004 | [[docs/adr/0004-entry-file-lockstep-policy]] — entry files stay byte-identical in lockstep blocks | 2026-05-23 | entry points |
| 0004 | [[docs/adr/0004-field-level-permission-model]] — field-level permission model | 2026-05-25 | permissions |
| 0005 | [[docs/adr/0005-bridge-path-enrichment]] — PATH enrichment for GUI-launched subprocess CLIs | 2026-05-23 | bridge |
| 0006 | [[docs/adr/0006-multi-employee-tenant-bridge-access]] — multi-employee access to a shared admin bridge | 2026-05-23 | tenancy |
| 0007 | [[docs/adr/0007-breeze-separate-repo]] — Breeze ships as its own repo + Supabase project | 2026-06-08 | topology |
| 0010 | [[docs/adr/0010-external-resource-catalog]] — Free-Tier Radar rows as capability-graph resource nodes | 2026-07-17 | capability graph |
| 0011 | [[docs/adr/0011-typed-memory-taxonomy]] — typed memory with declared update semantics | 2026-07-18 | memory |
| 0012 | [[docs/adr/0012-agent-fleet-contract]] — one agent schema, two dialects, scoped by default | 2026-07-19 | agent fleet |
| 0015 | [[docs/adr/0015-evidence-gated-harness-refinement]] — evidence is an executed command, not a rationale | 2026-08-07 | self-improvement |
| 0016 | [[docs/adr/0016-20-point-vibe-code-security-standard]] — 20-point vibe-security matrix, single-sourced with a tested defense mapping | 2026-08-15 | security |

## Proposed

| # | Decision | Date | Scope |
|---|---|---|---|
| 0008 | [[docs/adr/0008-leads-tenant-email-unique-constraint]] — `(tenant_id, lower(email))` unique + atomic upsert | 2026-06-09 | database |
| 0009 | [[docs/adr/0009-tenant-safe-bridge-catalog]] — tenant-safe bridge-tool catalog for non-admin operators | 2026-06-09 | bridge |

---

## Writing a new ADR

1. Next free number — check this table first, not `ls` (the collision above happened
   because two sessions both ran `ls | tail -1` and picked the same number).
2. Filename `NNNN-kebab-case-title.md`; frontmatter `status`, `date`, `tags`, `last_updated`.
3. Body: **Context** (the forcing function) → **Decision** (what we chose) → **Consequences**
   (what this now costs us). No "Alternatives considered" theatre unless one was genuinely close.
4. Add a row here and a `[[docs/adr/INDEX]]` backlink in the ADR itself.

## Obsidian Links
- [[CONTEXT]] | [[brain/STATE]] | [[brain/CAPABILITIES]] | [[brain/EXECUTION_RULES]]
