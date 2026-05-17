---
name: V68_AGENT_OS_PATTERNS
description: V6.8 propagation contract — vocabulary layer (CONTEXT.md), ADR layer (docs/adr/), skill-invocation discipline (disable_model_invocation / argument_hint), skill lifecycle directories (in-progress/, _archive/), distribution manifest (.claude-plugin/plugin.json). What every CC agent (Bravo, Maven, Atlas, Hermes) must inherit and what each adapts per domain.
last_updated: 2026-05-16
freshness_threshold_days: 365
---

# V6.8 — Agent-OS Vocabulary Layer

> Adopted 2026-05-16. Source audit: [mattpocock/skills](https://github.com/mattpocock/skills) cross-referenced against the Bravo V6.7 substrate.
>
> V6.0–V6.7 built the *substrate* (state DB, retrieval, guards, hooks, capability graph, Prep Table). V6.8 makes it **self-documenting** and **externally distributable** without touching substrate code.

## What V6.8 adds

| Layer | Pattern | Purpose | Universal? |
|---|---|---|---|
| Vocabulary | `CONTEXT.md` at project root | Canonical domain glossary all skills + entry points reference | YES — every agent |
| Governance | `docs/adr/NNNN-<slug>.md` | Numbered architectural decisions, distinct from tactical `memory/DECISIONS.md` | YES — every agent |
| Skill invocation | `disable_model_invocation: true` in frontmatter | Skill never auto-loads via semantic match; fires only on explicit `/command` | YES — applies wherever a capability graph + resolver exist |
| Skill invocation | `argument_hint: "<question>"` in frontmatter | Surfaces invocation prompt at runtime | YES |
| Skill lifecycle | `skills/in-progress/` (staging) + `skills/_archive/` (retired) | Excluded from graph + distribution manifest | YES |
| Distribution | `.claude-plugin/plugin.json` | Listing of skills shippable to other Claude Code installs via `npx skills@latest add` | Bravo only initially; Maven/Atlas adopt if they ever distribute |

## Propagation contract per sibling

### Bravo (this repo) — fully applied 2026-05-16

- ✅ `/CONTEXT.md` (40+ terms, empire-wide vocabulary)
- ✅ `/docs/adr/0001-skill-dependency-classification.md` (hard vs soft)
- ✅ `/docs/adr/0002-context-md-canonical-vocabulary.md` (this layer)
- ✅ Frontmatter flags applied to `hyperthink`, `sparc-methodology`, `retro` (disable_model_invocation), `writing-plans`, `outreach-send` (argument_hint)
- ✅ `/skills/in-progress/.gitkeep` + `SKIP_SKILL_DIRS` in `build_capability_graph.py`
- ✅ `/.claude-plugin/plugin.json` — 47 shippable skills
- ✅ Cross-sync: CLAUDE.md / GEMINI.md / ANTIGRAVITY.md / AGENTS.md / OPENCODE.md all reference CONTEXT.md as boot item #5
- ✅ `memory_retriever.py` SCOPES extended (`context`, `adr`) — CONTEXT.md and ADRs indexed alongside `brain/`, `memory/`, `skills/`
- ✅ `register.py adr-new <slug>` scaffolds new ADRs
- ✅ `skills/skill-creator/SKILL.md` opens with 4-step pre-flight (CONTEXT.md + ADR-0001 + invocation discipline + register.py scaffold)

### Maven (`~/CMO-Agent`) — propagated 2026-05-16

- ✅ `/CONTEXT.md` (content/brand/social vocabulary — pillars, platforms, NEPQ, voice rules)
- ✅ `/docs/adr/0001-context-md-canonical-vocabulary.md` (references Bravo's ADR-0002 as the empire-wide parent)
- ⏭ Skill frontmatter audit — deferred. Maven adopts `disable_model_invocation` + `argument_hint` skill-by-skill as the skill set is audited.
- ⏭ `skills/in-progress/` + `.claude-plugin/plugin.json` — deferred. Maven's skills don't yet have a distribution use case.
- ⏭ Sibling entry-point sync — Maven owns its own CLAUDE/AGENTS/GEMINI/ANTIGRAVITY/OPENCODE; update those when Maven next has a clean session. The pattern is documented; not enforced now.

### Atlas (`~/APPS/CFO-Agent`) — propagated 2026-05-16

- ✅ `/CONTEXT.md` (finance/tax/research vocabulary — T2125, FHSA/TFSA/RRSP, conviction score, IRR/MOIC, CRA rules)
- ✅ `/docs/adr/0001-context-md-canonical-vocabulary.md` (references Bravo's ADR-0002)
- ⏭ Skill frontmatter audit — deferred (same reason as Maven)
- ⏭ Distribution manifest — deferred

### Hermes (future) — propagated via agent-forge

- ⏭ Not yet deployed. When Hermes ships, `skills/agent-forge` + `skills/agent-runtime-packaging` must scaffold the V6.8 layout by default: CONTEXT.md template + `docs/adr/` directory + frontmatter conventions in `skill-creator/SKILL.md`.
- TODO: `skills/agent-forge/SKILL.md` should be updated to include the V6.8 patterns in the harness. Tracked in `memory/ACTIVE_TASKS.md`.

## Why this version exists

The mattpocock/skills audit (2026-05-16, see `~/.claude/plans/i-found-a-really-parallel-pascal.md`) confirmed:

- Our substrate (state DB, retrieval, guards, multi-agent, event bus) is **orders of magnitude** more sophisticated than any public Claude Code skill repo.
- Public skill repos have **better vocabulary discipline** and **better external distribution mechanics** — both small, both fixable in <2 hours, both compounding in value.

V6.8 closes that specific gap without touching substrate. No new daemons. No new DB tables. No new hooks. Just:
- A glossary every agent already needed.
- ADRs to keep architectural decisions distinct from tactical/business decisions.
- Two frontmatter keys the resolver already honored.
- A staging lane every long-lived skill repo eventually needs.
- A manifest making our work redistributable.

## How to propagate to a NEW client agent (post-V6.8)

1. `skills/agent-forge` scaffolds the agent's repo (existing flow).
2. Harness automatically copies the V6.8 file shapes:
   - Empty `/CONTEXT.md` template with section headers (people / brands / vocab / state / North Star)
   - Empty `/docs/adr/0001-context-md-canonical-vocabulary.md` referencing the empire ADR
   - `skills/in-progress/.gitkeep`
   - `skill-creator/SKILL.md` with the 4-step pre-flight checklist
3. First operator turn after fork: agent reads its own CONTEXT.md (still empty), prompts the operator for domain terms, fills it in. Self-bootstraps.

## Anti-patterns to avoid during propagation

- **Don't copy Bravo's CONTEXT.md verbatim to siblings.** The glossary is per-agent. Maven's vocabulary is content/brand/social; Atlas's is finance/tax/research. Each writes its own.
- **Don't add skills/in-progress/ to siblings until they have ≥5 active skills.** Empty staging lanes are noise.
- **Don't ship `.claude-plugin/plugin.json` from a sibling until the sibling has skills worth distributing.** Bravo's is the only one for now.
- **Don't enforce `disable_model_invocation` retroactively on every existing skill.** Audit skill-by-skill; flag only the ones where false-positive routing has been observed.

## Verification (run from each sibling repo)

```bash
# 1. CONTEXT.md exists and parses as markdown
test -f CONTEXT.md && head -5 CONTEXT.md

# 2. memory_retriever (if exists) returns CONTEXT.md for a domain query
python scripts/memory_retriever.py query "what is <domain term>" --lexical-only 2>/dev/null | head -5

# 3. ADR-0001 references the empire canonical
grep -q "Bravo.*ADR-0002\|Business-Empire-Agent" docs/adr/0001*.md

# 4. (Bravo only) Capability graph rebuilds cleanly + new frontmatter surfaces
python scripts/build_capability_graph.py --check
```

## Source

- Audit plan: `~/.claude/plans/i-found-a-really-parallel-pascal.md`
- External source: https://github.com/mattpocock/skills
- Probationary pattern: `memory/PATTERNS.md` § "Surgical Import from External Skill Repos"
- Related architecture decisions: `docs/adr/0001-skill-dependency-classification.md`, `docs/adr/0002-context-md-canonical-vocabulary.md`
