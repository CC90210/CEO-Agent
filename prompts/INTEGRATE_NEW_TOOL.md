---
tags: [prompts]
last_updated: 2026-05-25
---

# INTEGRATE_NEW_TOOL — paste this whole block as your prompt

> **Works in** Claude Code, Antigravity, OpenCode, Codex CLI, Cursor, Gemini CLI, or any tool that opens one of CC's agent repos.
> **Use it when** CC drops a GitHub URL, a research doc, an open-source tool, a Hacker News thread, a competitor repo, a YouTube transcript, a Twitter thread, or any external resource and says "integrate this" / "audit this against our setup" / "what would we steal from this."
> **Why this exists:** the mattpocock/skills audit (2026-05-16, see `~/.claude/plans/i-found-a-really-parallel-pascal.md`) became the canonical pattern for external-resource integration in CC's empire. Every future integration follows the same shape so nothing gets silently dropped, half-finished, or imported-for-the-sake-of-importing.

---

## Identity probe (FIRST move — don't skip)

Detect which agent you are by repo path:

- `Business-Empire-Agent/` → you are **Bravo** (CEO). Architecture, business ops, CC's strategic voice.
- `CMO-Agent/` → you are **Maven** (CMO). Content, brand, ads, funnels.
- `APPS/CFO-Agent/` → you are **Atlas** (CFO). Tax, research, financial advisory.
- `APPS/<client>/` → you are a **client agent** running on `skills/agent-forge` harness. Domain depends on the client.
- Any other repo → identify by `CLAUDE.md` top section, default to read-only mode if unclear, ASK CC.

Identity is model-driven, not tool-driven. Running Claude → Bravo/Maven/Atlas. Running GPT → Codex (backend executor). Running anything else → name yourself honestly and default to read-only.

---

## Inputs you'll receive

CC will give you ONE of:

1. **A GitHub URL** — `https://github.com/<owner>/<repo>`. Fetch via WebFetch / curl.
2. **A raw paste** — README content, code snippet, blog post, transcript.
3. **A file path** — path to a local repo, a research PDF, a markdown doc.
4. **A research request** — "go find me what's out there for X." You research, then integrate.
5. **A vague pointer** — "this thing I saw on Twitter." Ask one clarifying question, then proceed.

If CC doesn't tell you which agent to integrate into, **classify it yourself** in Phase 1 below.

---

## Phase 1 — Identify (under 60 seconds)

Answer these three in plain English before doing anything else:

1. **What is it?** Repo / research doc / open-source tool / framework / prompt library / pattern / methodology.
2. **What problem does it solve that we currently have?** If you can't name a real problem of CC's that this addresses, **STOP and tell CC** — don't import for the sake of importing.
3. **Which agent does it belong to?**
   - Architecture / multi-agent / governance / infrastructure → **Bravo**
   - Content / brand / video / ad / social / funnel → **Maven**
   - Tax / accounting / equity research / macro → **Atlas**
   - Client-specific (SunBiz / PropFlow / etc) → that client's agent in `apps/` or `APPS/`
   - Universal (could benefit all C-suite) → land in **Bravo** first, propagate per V6.8.1 contract

If the answer to #2 is "looks cool" or "everyone's using it" — that's a red flag. Push back on CC: *"What would this actually replace or improve in our current setup?"*

---

## Phase 2 — Cross-reference audit (parallel, spawn agents)

**Spawn two agents IN PARALLEL** (single message, two Agent tool calls):

**Agent A (researcher)** — fetch and analyze the external resource:
- WebFetch the URL / read the paste / read the local repo
- Identify: architecture, skill format, plugin/distribution mechanism, hooks, agent definitions, governance, distinctive patterns
- Report (under 600 words): top 5 things worth stealing, top 3 things we already do better, file-path-level recommendations

**Agent B (Explore)** — inventory OUR current state in the relevant area:
- Read our `CONTEXT.md`, `brain/CAPABILITY_GRAPH.json`, relevant `skills/`, `scripts/`, hooks
- Report (under 700 words): what we already have, where the gap is, what would conflict, what already does the same job better

Wait for both. Then YOU (the main agent) do the synthesis — never delegate synthesis. Read both reports, then write the cross-reference table.

**Cross-reference table shape:**

| Their pattern | Our equivalent | Action | Why |
|---|---|---|---|
| `<their thing>` | `<our thing or none>` | Import / Skip / Already-better | One sentence |

---

## Phase 3 — Plan (write to `~/.claude/plans/<slug>.md`)

For each pattern marked Import, write:
- **Files to create** (full paths)
- **Files to modify** (full paths, with diff hint)
- **Dependency classification per ADR-0001** — hard (declare `requires:` in frontmatter) or soft (degrade gracefully)
- **Effort estimate** — human-team time / agent time
- **Completeness score 0-10** (boil-the-lake principle from CLAUDE.md)

Rank by ROI. Items <2h with ≥8 completeness score go first. Anything <5 completeness — push back on CC before implementing.

Identify **propagation needs**:
- Does this cross to siblings? (Bravo ↔ Maven ↔ Atlas ↔ client agents)
- Does this need `CONTEXT.md` updates? (new domain terms)
- Does this warrant an ADR? (architectural, irreversible, opinion-shaping)

If the plan is non-trivial, **call `ExitPlanMode`** and wait for CC's approval before touching code.

---

## Phase 4 — Execute (single coherent commit per layer)

Ship in this order — substrate first, conventions next, vocabulary last:

1. **Substrate** — scripts, hooks, daemons. Make new behavior actually happen.
2. **Conventions** — frontmatter keys, ADR(s), capability graph fields. Make the new shape consumable.
3. **Vocabulary** — `CONTEXT.md` entries, sibling entry-point sync. Make the language canonical across agents.
4. **Distribution** — `.claude-plugin/plugin.json` updates, `skills/agent-forge` template updates (if forking-relevant).

After each layer: `python scripts/build_capability_graph.py` + `python scripts/core/memory_retriever.py build`. Commit per layer.

**Anti-slop guardrails (mandatory):**

- ❌ Never claim "Proposed future tooling" in an ADR unless CC explicitly accepted "we'll do it later." Soften wording.
- ❌ Never create stub functions that just `pass` or return mock data.
- ❌ Never duplicate logic — if `scripts/foo.py` already does it, extend it; don't write `foo_v2.py`.
- ❌ Never touch substrate (state DB, guards, hooks) without explicit need.
- ❌ Never import a frontend pattern (gradients, 3-column grids, icon menus) — see AI Slop Detection in CLAUDE.md.
- ✅ Soften your own claims. If you ship something half-implemented, say so in the commit message AND in any ADR/docs that reference it.

---

## Phase 5 — Verify symbiosis (4-test pattern)

After execution, run **at least these four tests** to prove the integration is load-bearing, not additive:

1. **Capability graph rebuilds clean**: `python scripts/build_capability_graph.py --check` (exit 0, no drift)
2. **Memory retriever picks up new content**: `python scripts/core/memory_retriever.py query "<new term or new skill name>"` returns the new file at rank ≤3
3. **New frontmatter consumed by resolver**: `python scripts/capability_query.py resolve "<intent that matches new skill>"` includes/excludes correctly
4. **End-to-end behavior changed**: spin up a fresh-shape prompt the new pattern is supposed to handle, prove the system handles it without re-deriving from scratch

If any of the 4 fails, you didn't actually ship a load-bearing change — you shipped paperwork. Loop back to Phase 4.

---

## Phase 6 — Commit + propagate + document

**Commit message shape** (V6.X.Y semantic-versioning):

```
V6.X.Y: <one-line summary of what behavior changed>

<2-3 lines of context — what audit prompted this, what gap closed>

<bulleted list of imports, with file paths>

<verification block — 3-5 lines of "verified live" evidence>

Source: <external URL or path>
Plan: <~/.claude/plans/<slug>.md>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

**Propagation steps:**

1. **If cross-sibling** → also commit in Maven (`~/CMO-Agent`) and Atlas (`~/APPS/CFO-Agent`) with their own domain-tailored versions. Reference Bravo's canonical commit hash in each sibling commit.
2. **Log a probationary pattern** in `memory/PATTERNS.md`: `[P] <pattern name> — <one-line>. Promote to [V] after 3 re-uses.`
3. **Update PATTERNS.md `last_updated:` frontmatter** to today's date.
4. **Update `brain/STATE.md` or `brain/V6X_<NAME>.md`** if the integration is structural (a new substrate layer, a new convention).
5. **State sync** — `python scripts/state/state_sync.py --note "<one-line summary>"`.
6. **Memory sync line** — finish your turn with: *"Memory synced. [X] commits, [Y] files, [Z] retriever chunks added."*

---

## What to do if CC dropped a vague pointer

If CC said something like "I saw this cool repo, here's the URL" with no context:

1. Fetch the URL.
2. Apply Phase 1 yourself (classify it, name the gap it closes).
3. Tell CC in ≤3 sentences: *"This is X. It would land in [agent]. The gap it closes is [Y]. Top 3 things worth importing: [list]. Top thing to skip: [item, with reason]. Want me to run the full audit pattern?"*
4. Wait for go/no-go before spawning Phase 2 agents.

**Never spend >3 minutes researching without first checking with CC.** Token cost compounds; CC's attention compounds harder.

---

## What to do if CC asks for a one-shot integration (no audit)

Some integrations are obvious and small ("add this CLI tool to scripts/"). In that case:

1. Skip Phase 2 (no parallel audit needed).
2. Still write a plan file (1-page minimum).
3. Still classify dependencies per ADR-0001.
4. Still run the 4-test verification.
5. Still write a structured commit message.

The audit is skippable. The discipline isn't.

---

## Quick-reference checklist (TL;DR)

```
[ ] Identity probe — which agent am I?
[ ] Phase 1 — name the problem this solves (not "looks cool")
[ ] Phase 2 — parallel audit (researcher + Explore agents)
[ ] Phase 3 — plan file + ADR-0001 dep classification + ExitPlanMode
[ ] Phase 4 — substrate → conventions → vocabulary → distribution
[ ] Phase 5 — 4 symbiosis tests (graph / retriever / resolver / e2e behavior)
[ ] Phase 6 — commit per layer + propagate + state_sync + memory sync line
```

If you skipped any step, your integration is paperwork, not progress. Loop back.

---

**Canonical example #1** of this prompt being applied end-to-end:
- External resource: https://github.com/mattpocock/skills
- Plan file: `~/.claude/plans/i-found-a-really-parallel-pascal.md`
- Bravo commits: 5aeb5fb (V6.8 patterns) → bec2fcc (V6.8.1 load-bearing) → 5335556 (V6.8.2 docs catch up)
- Maven commits: da1e5aa (V6.8 propagation) → 00d8e14 (V6.8.1 entry sync)
- Atlas commits: 1699c9e (V6.8 propagation) → 18e89af (V6.8.1 entry sync)
- Pattern logged: `memory/PATTERNS.md` § "Surgical Import from External Skill Repos"
- Result: vocabulary auto-injection live in production, dependency enforcement live, V6.8 conventions inherited by every new skill via `register.py`.

**Canonical example #2** — five-layer substrate import, larger surface, single-agent-owned:
- External resource: https://github.com/twentyhq/twenty (AGPLv3 — patterns only, no code copied)
- Plan file: `~/.claude/plans/i-m-dropping-you-a-magical-cat.md`
- Bravo commits: 057dcb1 (V6.9.0 object/field metadata) → a951850 (V6.9.1 views) → 289f6d8 (V6.9.2 workflow engine) → 410354c (V6.9.3 ADRs 0003+0004)
- oasis-command-center commits: b5b8c5a (V6.9.0 introspector) → fd6d25d (V6.9.1 views loader+API) → 5fabfb1 (V6.9.2 step registry+5 steps) → e86822e (V6.9.3 ai-agent step + field perms)
- ADRs added: 0003 (typed workflow step registry), 0004 (field-level permission model)
- Vocabulary: `CONTEXT.md` § "V6.9 CRM Substrate" — 6 new glossary entries (Object Metadata, Field Metadata, Saved View, Workflow Step, AI Agent Step, Field Permission)
- Skill added: `skills/manifest-ai-editor/` (V6.9.4 — operator-facing AI manifest editor surface)
- Sibling propagation: **none** — CRM is Bravo-owned (oasis-command-center); Maven and Atlas don't have CRM dashboards. Universal vocabulary entries still land in `CONTEXT.md` for cross-agent term coherence.
- Distribution: `.claude-plugin/plugin.json` deliberately NOT updated — manifest-ai-editor is CC-internal multi-tenant tooling, not universally useful (matches the plugin's own "excluding CRM" exclusion rule).
- Pattern logged: `memory/PATTERNS.md` § "Substrate-Layer-First Import from AGPL Reference Repos" (V6.9 confirms the V6.8 pattern at larger surface — 3 migrations + 6 step types + 2 ADRs + 6 glossary entries shipped across 8 commits).

This is the bar. Match it.

## Obsidian Links
- [[brain/INDEX]]
- [[brain/CAPABILITIES]]
