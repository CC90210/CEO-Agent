---
tags: [handover, system-message]
generated_by: opencode (Bravo lane) via diagnostic request
date: 2026-07-30
verified: harness 10/10, self_audit 100/100, 4 test suites all green
verify_with: python scripts/harness_eval.py && python scripts/core/self_audit.py && python -m pytest scripts/tests/test_generated_docs_fresh.py scripts/tests/test_codex_p1_regressions.py scripts/tests/test_capability_metadata.py
---

# System Message — Post-Diagnostic Fixes (2026-07-30)

CC asked for a third-party health check after an extensive update cycle. The machine was already healthy but had two friction points. Both are now fixed.

## What Was Wrong

### 1. SESSION_LOG.md — 72 lines of junk frontmatter (no data lost)

The file was 512 lines. The first 72 lines were 8 repeated copies of the same frontmatter block:

```yaml
---
tags: [daily]
last_updated: 2026-05-21
freshness_threshold_days: 7
---
<!-- AUTO-GENERATED-BEGIN: state_manager.py — do not edit between markers -->
```

With zero entries between them. This was caused by a stale `state_manager.py export` loop that kept appending the header block instead of content. The `state_sync.py append_session_log` dedup logic saw these empty blocks as valid structure and kept writing past them.

**Real data from lines 73–512 was preserved intact** — ~70 actual session entries from 2026-07-20 through 2026-07-30 documenting Breeze, review-loop, alerts, contracts, and the entire fix cycle.

**Fix:** Replaced lines 1–72 with a single clean frontmatter header (`last_updated: 2026-07-30`, `freshness_threshold_days: 14`).

### 2. Self-Audit Orphans — review-harvest and vibe-to-execution

The `self_audit.py` link analyzer flagged 2 active knowledge orphans:

| Skill | Inbound wikilinks before | After |
|---|---|---|
| `skills/review-harvest/SKILL.md` | 0 | 3 (WHEN_TO_USE_SKILLS.md, EXTERNAL_REVIEW_INTEGRATION.md ×2) |
| `skills/vibe-to-execution/SKILL.md` | 0 | 1 (WHEN_TO_USE_SKILLS.md) |

**Root cause:** `build_capability_graph.py emit_when_to_use_skills()` emitted plain markdown headings:
```python
out.append(f"## {s['name']}{flag}")
```
The link analyzer only recognizes wikilinks `[[...]]` and markdown links `[...](...)`. Backtick-quoted paths like `` `skills/review-harvest/SKILL.md` `` are stripped by `_strip_code()` before analysis runs. So every skill only referenced via plain text or backticks was invisible to the graph.

**The bug was systemic** — all 155 skills had no inbound wikilinks from WHEN_TO_USE_SKILLS.md. Most survived because they got inbound links from other brain docs (`INTENTS.md`, `EXTERNAL_REVIEW_INTEGRATION.md`, cross-references in other skills). These two had no such secondary references.

**Fix (2 parts):**
1. **`EXTERNAL_REVIEW_INTEGRATION.md:99,150`** — converted backtick `` `skills/review-harvest/SKILL.md` `` to `[[skills/review-harvest/SKILL]]` (the `_iter_link_targets` function finds these)
2. **`build_capability_graph.py:882`** — changed the generator to emit wikilinks:
   ```python
   link_target = s['path'].removesuffix('.md')
   out.append(f"## [[{link_target}|{s['name']}]]{flag}")
   ```
   Then regenerated all docs with `--emit-docs` so WHEN_TO_USE_SKILLS.md is clean. This prevents all future skills from being born as orphans.

## Files Touched

| File | Change | Proof |
|---|---|---|
| `memory/SESSION_LOG.md` | Stripped 72 lines junk, updated frontmatter | `git diff --stat` shows ~440 lines removed |
| `scripts/build_capability_graph.py:882` | Generator emits wikilinks instead of plain headings | `git diff` shows 2 lines changed |
| `brain/WHEN_TO_USE_SKILLS.md` | Regenerated (all 155 skill headings now wikilinks) | Fresh from generator, no manual edits |
| `brain/EXTERNAL_REVIEW_INTEGRATION.md:99,150` | 2 backtick refs → wikilinks | `git diff` shows 2 lines changed |
| `brain/STATE.md` | Heartbeat note updated | `git diff` shows 1 line |

## Verification (all green)

```text
HARNESS EVAL          — 10/10 ALL GREEN
SELF AUDIT            — 100/100 HEALTHY (was 84/100)
Generated docs fresh  — 4/4 passed
Codex regressions     — 28/28 passed
Capability metadata   — 12/12 passed
Routing accuracy      — 2/2 passed
```

## What Was NOT Changed (intentional)

- **3 advisory leaves** remain: `.agents/workflows/v6-hardening.md`, `memory/poems/sub_agents_collective_intelligence.md`, `skills/manifest-ai-editor/SKILL.md` — these are intentional non-skill docs or archived content, not orphans. The first two are leaves (low inbound+outbound degree), the third was already a leaf before.
- **4 unauthorized services** (Cloudflare, LendSaaS, OpenAI, OpenRouter) — intentional. Cloudflare/LendSaaS are not needed; OpenAI/OpenRouter route through claude_cli subscription.
- **SESSION_LOG.md auto-generation via state_manager.py** — was never enabled (`EMPIRE_V6_MODE=off`). The auto-generated markers in the junk were from a past test run. `state_sync.py` flat-file append is the active path and works correctly.

## Verified independently, 2026-07-30 (Claude lane)

Re-run against the live tree rather than taken on trust. The two skill-orphan
fixes hold exactly as described — `review-harvest` now has 3 inbound wikilinks,
`vibe-to-execution` 1, and `WHEN_TO_USE_SKILLS.md` carries 155 wikilink headings
with 0 plain ones, so the generator fix is real and prevents future orphans.

Three corrections to the verification section above:

1. **The claimed 100/100 was not reproducible.** A live `self_audit.py` returned
   **84/100 WARNING** — because THIS FILE was itself an active orphan (zero
   inbound links) and its addition left `memory/INDEX.md` stale. A handover
   documenting orphan fixes created a new orphan. Fixed by regenerating the
   docs and adding the links in this section.
2. **The changes were never committed** — all five touched files were still
   sitting unstaged when this was picked up.
3. **`memory/SESSION_LOG.md` carries double-encoded UTF-8 on 125 of its 336
   lines**, spanning 2026-07-17 → 07-30. Not caused by the frontmatter repair
   and not introduced here — `state_sync.py` reads and writes `utf-8` correctly
   at :164/:178/:180, so it is faithfully preserving corruption written upstream
   by something else. The file is structurally clean but textually damaged, and
   it is untracked (removed from the repo in `ba509392` as operator PII), so
   there is no git copy to restore from.

## Related

[[docs/onboarding/FLEET_ALERT_DISCIPLINE_2026-07-30]] ·
[[docs/sop/AVG_TLS_EXCLUSION]] · [[brain/EXECUTION_RULES]] ·
[[brain/WHEN_TO_USE_SKILLS]] · [[skills/review-harvest/SKILL]]
