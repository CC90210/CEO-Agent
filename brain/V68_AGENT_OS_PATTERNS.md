---
name: V68_AGENT_OS_PATTERNS
description: V6.8 propagation contract — vocabulary layer (CONTEXT.md), ADR layer (docs/adr/), skill-invocation discipline (disable_model_invocation / argument_hint), skill lifecycle directories (in-progress/, _archive/), distribution manifest (.claude-plugin/plugin.json). What every CC agent (Bravo, Maven, Atlas, Hermes) must inherit and what each adapts per domain.
last_updated: 2026-06-09
freshness_threshold_days: 365
verified: 2026-06-09
tags: [brain]
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

### Bravo (this repo) — V6.8 + V6.8.1 fully applied 2026-05-16

**V6.8 (static patterns, commit 5aeb5fb):**
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

**V6.8.1 (load-bearing wiring, commit bec2fcc):**
- ✅ `scripts/hooks/user_prompt_submit.py` — Pass 1 auto-injects CONTEXT.md definitions when prompt mentions a glossary term. Runs on every tier including T1 (greetings with domain terms still get vocab). Cached on CONTEXT.md mtime.
- ✅ `scripts/capability_query.py check-deps <node_id>` — verifies declared `requires:` against env / daemon pid mtime / state files. Returns structured report; exits 1 on miss. Makes ADR-0001 enforceable.
- ✅ `scripts/build_capability_graph.py` — `_parse_requires()` surfaces `requires: [env:X, daemon:Y, state:Z]` into every skill node. Field is now first-class in the graph.
- ✅ `scripts/register.py skill` — wizard emits V6.8 frontmatter by default. Flags: `--argument-hint`, `--disable-model-invocation`, `--requires-env`, `--requires-daemon`, `--requires-state`. New skills inherit V6.8 conventions without author discipline.
- ✅ Module docstrings updated (`capability_query.py`, `register.py`, `user_prompt_submit.py`) to reflect V6.8.1 behaviors.

**V6.8.2 (docs catch up, commit 5335556):**
- ✅ ADR-0001 Enforcement section updated to mark `check-deps` shipped.
- ✅ Module docstrings in `capability_query.py`, `register.py`, `user_prompt_submit.py` updated to describe V6.8.1 behavior.
- ✅ CLAUDE.md V6.8 section + this file updated to reflect V6.8.1 load-bearing state.

**V6.8.3 (INTEGRATE_NEW_TOOL prompt + dashboard wiring, commit 484b6e0):**
- ✅ `prompts/INTEGRATE_NEW_TOOL.md` — canonical 6-phase pasteable system message for any external-resource integration. Generalized from the mattpocock/skills audit.
- ✅ `oasis-command-center:lib/prompts-library.ts` — new `system_integration` category + foundational `integrate-new-tool` PromptEntry.
- ✅ PLAYBOOK.md top-5-moves table — new row pointing operators to the dashboard prompt.
- ✅ `scripts/core/memory_retriever.py` SCOPES extended with `prompt` scope — prompts/*.md are now retriever-indexable.

**V6.8.4 (self-review fixes for V6.8.3, commit a2e58d2):**
- ✅ `oasis-command-center:app/playbook/prompts/page.tsx` — `system_integration` added to `OPERATOR_CATEGORIES` so the new category actually renders.
- ✅ `oasis-command-center:lib/prompts-library.ts` — prompt entry refactored from `+` concatenation to template literal for pattern consistency with existing entries.
- ✅ `brain/INTENTS.md` — added "Integrate a new tool / GitHub repo / open-source code / research" routing section so the agent fires the prompt automatically on intent match, without CC having to find it.

**V6.8.5 (sidebar nav fix, commit cc4fbbd):**
- ✅ `oasis-command-center:lib/nav-config.ts` `CC_NAV` — restored `/playbook` as the 5th Operations item. Phase 2 nav trim had claimed `/playbook` was folded into `/settings/playbook`, but that route was never built. V6.8.3 made `/playbook/prompts` daily-use; hiding it broke the flow. Other tenants (`SUN_NAV`, `SUGA_NAV`) already had this nav slot — only CC's own empire nav was missing it. After deploy, click path is: Sidebar → Playbook → Prompts Library card → /playbook/prompts → System integration section → Integrate-a-new-tool prompt.

**V6.8.6 (consistency sweep, commit forthcoming):**
- ✅ `oasis-command-center:lib/nav-config.ts` — updated stale comments. Previously claimed `/integrations → /settings/integrations` and `/feed → /operations` folds; verified `/settings/integrations` doesn't exist and `/feed` is still a separate page from `/operations`. Comment now honestly lists routes-reachable-by-URL-but-not-in-sidebar (with reason) so the next operator doesn't waste a session diagnosing the same nav-vs-route mismatch this V6.8.5 cycle did.

### Maven (`~/CMO-Agent`) — V6.8 + V6.8.1 propagated 2026-05-16

**V6.8 (commit da1e5aa):**
- ✅ `/CONTEXT.md` (content/brand/social vocabulary — pillars, platforms, NEPQ, voice rules)
- ✅ `/docs/adr/0001-context-md-canonical-vocabulary.md` (references Bravo's ADR-0002 as the empire-wide parent)

**V6.8.1 (commit 00d8e14):**
- ✅ All 5 sibling entry points (CLAUDE / GEMINI / ANTIGRAVITY / AGENTS / OPENCODE) reference `CONTEXT.md` on operational turns

**Still deferred:**
- ⏭ Skill frontmatter audit — Maven adopts `disable_model_invocation` + `argument_hint` + `requires:` skill-by-skill as the skill set is audited.
- ⏭ `skills/in-progress/` + `.claude-plugin/plugin.json` — Maven's skills don't yet have a distribution use case.
- ⏭ Hook-side vocab injection — Maven's runtime doesn't yet have a `user_prompt_submit.py` equivalent. If it adds one, the same V6.8.1 pattern applies.

### Atlas (`~/APPS/CFO-Agent`) — V6.8 + V6.8.1 propagated 2026-05-16

**V6.8 (commit 1699c9e):**
- ✅ `/CONTEXT.md` (finance/tax/research vocabulary — T2125, FHSA/TFSA/RRSP, conviction score, IRR/MOIC, CRA rules)
- ✅ `/docs/adr/0001-context-md-canonical-vocabulary.md` (references Bravo's ADR-0002)

**V6.8.1 (commit 18e89af):**
- ✅ All 5 sibling entry points (CLAUDE / GEMINI / ANTIGRAVITY / AGENTS / OPENCODE) reference `CONTEXT.md` on operational turns. Particularly load-bearing for Atlas because CRA-rule drift has direct dollar consequences.

**Still deferred:**
- ⏭ Skill frontmatter audit
- ⏭ Distribution manifest
- ⏭ Hook-side vocab injection

### Forked agents — propagated via agent-forge (scaffold gap CLOSED 2026-07-19)

- ✅ `templates/agent-scaffold/` now ships the V6.8 shapes: `CONTEXT.md` template (section headers + update rules), `docs/adr/0001-context-md-canonical-vocabulary.md` stub (references the empire ADR-0002), and `skills/in-progress/.gitkeep`. Closed during the V7.3.5 currency sweep — the "How to propagate" section below was aspirational until this date (the scaffold did NOT ship these files from 2026-05-16 to 2026-07-19).
- ⏭ Remaining nice-to-have: `skill-creator/SKILL.md` with the 4-step pre-flight is still not part of the scaffold's 3 canonical skills — forks adopt it when they add their first custom skill.

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
python scripts/core/memory_retriever.py query "what is <domain term>" --lexical-only 2>/dev/null | head -5

# 3. ADR-0001 references the empire canonical
grep -q "Bravo.*ADR-0002\|Business-Empire-Agent" docs/adr/0001*.md

# 4. (Bravo only) Capability graph rebuilds cleanly + new frontmatter surfaces
python scripts/build_capability_graph.py --check
```

---

# V7.5 — Guard & Continuity (davidondrej/skills import, 2026-08-03)

Third application of this contract (after mattpocock V6.8 and Twenty V6.9). Source: [davidondrej/skills](https://github.com/davidondrej/skills) (MIT — patterns studied, no code copied). Plan: `~/.claude/plans/integrate-davidondrej-skills.md`.

45 external skills audited; 5 imported, 14 marked already-better, 26 skipped. The full table with per-item reasoning is in the plan file.

| Layer | What shipped | Commit |
|---|---|---|
| Substrate | `exec_guard.py` HARD_BLOCKS: `gh` destruction + credential exfil, remote-branch deletion, reflog/gc destruction, mkfs/dd/raw-disk, chmod-chown-root. Plus `scripts/tests/test_exec_guard.py` (99 cases) — the guard had no test file at all. | `7afe35c3` |
| Conventions | `skills/handoff/`, `skills/setup-help/`, `skills/decisions/` — all manual-only, all SOFT per ADR-0001. | `c3e9e9ee` |
| Vocabulary | `CONTEXT.md` § V7.5 — 5 terms, verified auto-injecting via `user_prompt_submit.py` Pass 1. | `2c7dd37f` |
| Distribution | This section + `.claude-plugin/plugin.json` (+3 skills). | this commit |

## Sibling propagation — REQUIRED for the guard, OPEN pending CC

**The `gh` gap is fleet-wide, not Bravo-only.** Maven (`~/CMO-Agent`) and Atlas (`~/APPS/CFO-Agent`) each run their own `exec_guard.py` and each have `gh` available. `gh auth token` prints a live OAuth token to stdout on every one of those repos today, and `secret_guard.py` does not stop it there either — it is path-based and the token never touches a guarded file.

This is the one case where the usual "each sibling writes its own" rule does **not** apply. A denylist is not domain vocabulary; the same command is exactly as destructive in Maven's repo as in Bravo's. The patterns should land byte-identical.

Not executed here — editing sibling repos is a separate authorization, and Rule 10 forbids one agent silently rewriting shared substrate another chassis reads. **Flagged OPEN for CC.** The patch is the `gh` / `git-push-delete` / `reflog` / `gc` / `mkfs` / `dd` / `chmod-chown` block in `scripts/state/exec_guard.py` plus `scripts/tests/test_exec_guard.py`, applied verbatim.

The three skills are universal and portable — propagate on the normal per-sibling schedule, no urgency.

## What this import confirms about the contract

V6.8 established that an external audit yields vocabulary and conventions. V6.9 confirmed it at larger surface. **V7.5 adds a case the first two did not cover: the most valuable import was not a skill at all — it was a diff.** Reading another repo's denylist against ours surfaced a live credential-exfil hole that no amount of reading our own code would have found, because the gap was defined by absence. Nothing in our repo pointed at the missing `gh` rules.

Practical consequence for future audits: when an external repo ships a **denylist, an allowlist, a schema, or a test table**, diff it against ours before evaluating any of its skills. A list of things someone else decided to guard against is a map of our blind spots, and it is cheaper to read than the whole repo.

Corollary, also from this import: `scripts/tests/` had 40+ test files and none for the single most safety-critical script in the substrate. The external repo's `test-guard.sh` is unremarkable on its own — its value was making that absence visible. When auditing, check what the other repo tests that we don't.

## Source

- Audit plan: `~/.claude/plans/i-found-a-really-parallel-pascal.md`
- External source: https://github.com/mattpocock/skills
- Probationary pattern: `memory/PATTERNS.md` § "Surgical Import from External Skill Repos"
- Related architecture decisions: `docs/adr/0001-skill-dependency-classification.md`, `docs/adr/0002-context-md-canonical-vocabulary.md`
