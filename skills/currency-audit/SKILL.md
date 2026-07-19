---
name: currency-audit
description: System currency sweep — find prose that contradicts live reality (retired products, stale counts, old versions/locations/domains) that freshness gates cannot see; 3-lens audit + fix + verify
tier: meta
owner: bravo
risk: low
triggers: ["currency audit", "staleness sweep", "out of date", "stale docs", "semantic staleness"]
tags: [audit, hygiene, meta, documentation]
status: '[NEW]'
created_at: 2026-07-19T20:04:51.210794+00:00
---

# Currency Audit

> Freshness gates catch OLD files; they cannot catch WRONG files. This skill finds **semantic staleness** — prose with a valid `last_updated` whose content contradicts current reality (retired products still routed to, stale counts, superseded versions/locations/domains). First run: 2026-07-19 (6 HIGH / 14 MED / 10 LOW) — full method + findings: `docs/audits/2026-07-19-currency-audit.md`.

## When to use

- After any rename / retirement / relocation / rebrand (product, brand, domain, residency, model standard) — the change never propagates everywhere on its own.
- After a major version ships (the "what version am I" surfaces rot fastest).
- On CC's ask: "is anything out of date?", "make sure we're at the cutting edge".

## How it works

1. **Build the ground-truth list first** (never audit against memory): `architecture_version` from `brain/STATE.md` frontmatter; counts from `brain/CAPABILITY_GRAPH.json` totals; live rosters (agent catalog, `brain/APP_REGISTRY.md`); canonical domain; operator facts from the FRESHEST `brain/USER.md`; env-mode from `.claude/settings.json`; model standard from `scripts/lib/model_registry.py`.
2. **Three parallel read-only lenses** (Explore agents): (a) brain/ + docs/ + root prose vs ground truth; (b) knowledge/ + registries/indexes cross-surface consistency — the same fact materialized in 3 places WILL disagree; (c) config/automation claims vs live behavior (hooks, crons, CI triggers, package scripts).
3. **Targeted greps for known-retired tokens**: retired product names, old domain, old location, hardcoded counts ("N skills", "N MCP"), old model names. Exclude `_archive/**`, dated CHANGELOG/ADR/retro entries (correctly historical), and rollback instructions that legitimately reference old values.
4. **Verify every auditor claim before fixing** (RULE 10) — run #1 had one wrong claim: the "wrong repo URL" was actually the real push remote.
5. **Fix with the grain**: entry-point lines via `PERSONAL.md` + `genome_sync.py` (mirrors must re-stamp); generated files via their emitter, never by hand; hardcoded counts become graph-deferred phrasing ("live count: CAPABILITY_GRAPH totals") — pointing beats copying.
6. **Verify**: re-run the greps to zero · `pytest scripts/tests/ -q` · `genome_sync.py --check` · `build_capability_graph.py --check` · retriever rebuild · `harness_eval.py`.
7. **Record**: dated report in `docs/audits/`, CHANGELOG line, memory sync.

## Tools used

- `scripts/build_capability_graph.py` / `scripts/capability_query.py` — ground-truth counts + rosters
- `scripts/genome_sync.py` — entry-point + mirror stamping after seed edits
- `scripts/core/memory_retriever.py` — rebuild after doc changes
- `scripts/update_readme_stats.py` — README count enforcement (wired into pre-commit 2026-07-19)
- `scripts/core/memory_aging.py` — the complementary TIME-based gate (this skill covers what it can't)

## Related skills

- [[skills/knowledge-compilation/SKILL]] — the wiki pages this audit refreshes
- [[skills/retro/SKILL]] — post-mortem discipline the audit report follows
- [[brain/V68_AGENT_OS_PATTERNS]] — propagation contract for cross-agent fixes
