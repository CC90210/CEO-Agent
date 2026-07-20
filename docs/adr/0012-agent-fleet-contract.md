---
adr: 12
title: "Canonical agent contract: one schema, two dialects, scoped-by-default"
status: accepted
date: 2026-07-19
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0012 — Canonical agent contract: one schema, two dialects, scoped-by-default

## Context

The V7.4 fleet audit (CC directive: "fresh update that ties everything together, makes the wiring better") found the agent layer a generation behind the rest of the AOS: the 13 core personas were V5.5-era while the V7.2 imports beside them followed a modern contract; **four frontmatter dialects** coexisted (`.claude/agents` inline, `agents/` block-list, voltagent, outliers aura/codex-agent); three personas were **duplicated across both dirs** (shadowed dead files since the V7.2 stem-dedup); **three separate "reviewer" personas** existed; agent nodes carried no `triggers`/`tags`/`model`/`tools` into the capability graph (the resolver scored them on description alone); the delegation matrix was hand-maintained (three copies already disagreed per the currency audit); `register.py agent` scaffolded **full write tools by default** — inverting least-privilege; and `--kind any` in the resolver silently collapsed to skills-only.

## Decision

**1. One schema, every agent definition:** `name` · `description` (with a use-when clause — it IS the routing signal) · `model` (registry alias) · `tools` (explicit — scoping is part of the definition) · `tier` (`core | specialized | meta | safety | tool | strategic`) · `owner` · `triggers` (inline list — resolver scores these at 2×) · `tags`.

**2. Two dialects, one contract (serialization only):**
- `.claude/agents/` — **native dialect**: `tools:` as inline comma string (Claude Code's runtime parser requires it). These are the runtime-spawnable definitions and WIN stem collisions in the graph.
- `agents/` — **bench dialect**: `tools:` as YAML block-list. Graph-visible, cross-runtime, spawn-registered where the harness supports it.
- Same keys, same meanings. The graph parses both.

**3. Canonical-home rule — no duplicates.** One file per persona. The V5.5 duplicates (`agents/{architect,debugger,researcher}.md`, plus `agents/reviewer.md` vs `code-reviewer`) are merged into their `.claude/agents/` natives and **deleted** — a shadowed definition is drift waiting to be read by the wrong runtime. `agents/voltagent/code-reviewer.md` stays as import-record (shadowed, documented). `agents/aura.md` is a **peer-agent profile, not a spawnable persona** — marked as such.

**4. Routing is generated, not hand-written.** `--emit-docs` now produces `brain/WHEN_TO_USE_AGENTS.md` from agent frontmatter (freshness-tested like the skills doc). `brain/AGENTS.md`'s hand matrix keeps ONLY what frontmatter can't express (cross-agent delegation to Maven/Atlas/Codex/apps, veto rules); per-persona rows defer to the generated doc.

**5. Scoped-by-default scaffolding.** `register.py agent` emits the canonical schema with **read-only tools** (`Read, Grep, Glob`) — authors widen deliberately, with the reason in "What this agent must NOT do." The meta-agent persona emits this contract too.

**6. Resolver honesty:** `capability_query.py resolve --kind any` now genuinely searches all kinds (was silently skills-only); agents are scoreable via their new `triggers`.

**7. Fleet propagation (V6.8 contract):** the SCHEMA propagates to Maven/Atlas/client scaffolds; the PERSONAS don't (per-agent content). Siblings adopt on their own audit cadence; `templates/agent-scaffold` inherits via the modernized meta-agent + register path.

## Consequences

**Positive:** the resolver routes to agents as well as it routes to skills; scoping is visible in the graph before a spawn decision; one persona = one file = one truth; the routing doc can't drift (regenerated + freshness-tested); new agents are born least-privilege.
**Negative:** two serializations of `tools:` persist (runtime constraint — documented here so nobody "fixes" it into breakage); deleting the shadowed files breaks any stale `[[agents/architect]]`-style wiki-links (swept in this change).
**Neutral:** `strategic` tier legitimized in VALID_TIERS (hyperthink already used it); 32 agent-node count unchanged by the merges (shadowed copies were never counted).

## Enforcement

- `build_capability_graph.py --check` + `test_generated_docs_fresh.py` (now covers WHEN_TO_USE_AGENTS.md).
- `test_wiki_links.py` catches dangling links from the deletions.
- Review-time: new personas via `register.py agent` (canonical scaffold) or the V7.2 cherry-pick contract for imports.

## References

- [ADR-0001](0001-skill-dependency-classification.md) (dependency declarations) · [ADR-0011](0011-typed-memory-taxonomy.md) (update-semantics registry pattern this follows)
- Code: `scripts/build_capability_graph.py` (`discover_agents`, `emit_when_to_use_agents`) · `scripts/capability_query.py` (any-kind fix) · `scripts/register.py` (`create_agent`)
- Plan/history: V7.2 persona bench (cherry-pick contract) · `docs/audits/2026-07-19-currency-audit.md` (the drift evidence)
