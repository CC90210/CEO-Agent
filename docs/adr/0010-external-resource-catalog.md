---
adr: 10
title: "External-resource catalog: Free-Tier Radar rows as capability-graph resource nodes"
status: accepted
date: 2026-07-17
deciders: [bravo, cc]
supersedes: null
superseded_by: null
tags: [docs, adr, decision]
last_updated: 2026-07-17
---

# ADR-0010 — External-resource catalog: Free-Tier Radar rows as capability-graph resource nodes

## Context

The 2026-07-17 six-repo audit (free-for-dev, public-apis, free-programming-books, LLMs-from-scratch, ML-From-Scratch, Made-With-ML — plan: `~/.claude/plans/i-m-dropping-you-a-elegant-truffle.md`) surfaced a structural gap: knowledge about external services and free APIs lived nowhere machine-queryable. `brain/TOOL_SHED.md` was hand-prose invisible to the capability graph; the graph had no node kind for external resources and never ingested `brain/` docs; the empire already carried THREE drifting inventories of overlapping facts (TOOL_SHED, `knowledge/wiki/tech-stack.md`, `brain/APP_REGISTRY.md`). Meanwhile the upstream "awesome lists" themselves are un-importable as data: free-for-dev has **no license** and churns daily; public-apis ships zero data files and its widely-cited query API (api.publicapis.org) is dead (DNS `ENOTFOUND`, verified 2026-07-17).

## Decision

External-resource knowledge is cataloged as **structured table rows in `brain/TOOL_SHED.md` § "Free-Tier Radar"**, which `scripts/build_capability_graph.py` `discover_resources()` parses into first-class `resource:` nodes — making the catalog resolvable at runtime via `capability_query.py resolve --kind resource`. Rules this codifies:

1. **One catalog.** TOOL_SHED is the single external-resource catalog. No parallel docs; never under `knowledge/` (not in `memory_retriever` SCOPES — anything there is invisible to FTS5/semantic retrieval).
2. **Row contract.** `Slug | Capability | Service | Free Tier | Auth | Status | Conflicts/Replaces | Verified`, with `Status ∈ {candidate, adopted, rejected, policy}` (enum enforced as graph drift). Slugs are stable IDs.
3. **Link, don't vendor.** Upstream lists are fetched on demand (raw README + TOC anchors via `research_fetch.py`); mirroring or bulk-indexing them is prohibited (license, churn, no schema).
4. **Keyed-adoption path.** Radar row → `docs/ENV_KEYS_TEMPLATE.md` entry → CC signs up and hand-adds the key to `.env.agents` (agents never handle keys) → `scripts/integrations/<name>_tool.py` wrapper via `lib.secret_loader` → `integration_health.ping()` → SEED_JOBS health row. No-auth APIs skip the key steps but keep the wrapper contract (reference implementation: `email_validate_tool.py` / Disify).
5. **Closed slots.** A Radar consultation must respect the closed-slot list (DNS/hosting/DB/payments/email/SMS/scraping/TTS/vector/CI) — consolidation over addition; email is send_gateway-locked.
6. **Test taxonomy note** (from Made-With-ML): test intent separates into code-correctness vs data-quality vs behavior tests. Recorded here as a naming/authoring convention for future `scripts/tests/` additions; the existing test tree is deliberately NOT reorganized.

## Consequences

**Positive:**
- "Is there a free service for X?" resolves from the graph in one call instead of re-researching upstream every time.
- Rejected options (e.g. caldays) stay rejected with the reason attached — decisions don't get re-litigated.
- Radar rows with bad status enums surface as graph drift, so the catalog can't silently rot into free text.

**Negative:**
- The Radar table is markdown parsed by regex — column reordering breaks `discover_resources()` (mitigated: row contract documented in the section header itself, drift check catches vanishing nodes).
- Free-tier limits go stale; `Verified` dates are per-row but nothing auto-probes them. Refresh is manual, on-consultation.

**Neutral:**
- 11 candidate rows (uptime, error tracking, dead-man pings, coverage, SAST, etc.) await CC's per-service signup decisions; nothing is auto-adopted.
- `resource:` nodes add a kind to `CAPABILITY_GRAPH.json`; consumers that filter by kind are unaffected.

## Enforcement

- `python scripts/build_capability_graph.py --check` — node-set drift including resources; status-enum violations appear in `drift[]` (fails `harness_eval` check "capability graph fresh").
- `python scripts/capability_query.py resolve "<need>" --kind resource` — runtime consumption path; `skills/resource-radar/SKILL.md` routes agents to it.
- Review-time: new Radar rows follow the row contract; new keyed adoptions follow rule 4 (secret_guard blocks the shortcut paths anyway).

## References

- Sources: <https://github.com/ripienaar/free-for-dev> · <https://github.com/public-apis/public-apis> · <https://github.com/GokuMohandas/Made-With-ML>
- Related: [ADR-0001 — skill dependency classification](0001-skill-dependency-classification.md) (resource-radar declares all-soft deps) · [ADR-0002 — CONTEXT.md canonical vocabulary](0002-context-md-canonical-vocabulary.md)
- Code: `scripts/build_capability_graph.py` (`discover_resources`, `RADAR_STATUSES`) · `scripts/integrations/email_validate_tool.py` · `brain/TOOL_SHED.md` § Section 9

## Obsidian Links
- [[docs/adr/INDEX]]
- [[CONTEXT]]
