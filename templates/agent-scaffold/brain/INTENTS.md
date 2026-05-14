---
name: INTENTS
description: Verb-by-verb playbook for {{AGENT_NAME}}. For each kind of operator request, the exact sequence the agent should run.
mutability: SEMI-MUTABLE
tags: [brain, agent-only, playbook]
last_updated: 2026-05-14
canonical_pattern: ../../Business-Empire-Agent/brain/INTENTS.md (Bravo master)
---

# INTENTS — {{AGENT_NAME}} Verb-by-Verb Playbook

> First-person playbooks the agent reads when a recurring intent fires. Keep each section ≤ 15 lines.

---

## "Generate a status briefing"

1. Read `state/snapshots/latest_briefing.json` if it exists and `ts` < 24h old. Use it as the spine.
2. If stale or missing, run `python scripts/snapshots/briefing_snapshot.py` (once that script exists for this agent), then read.
3. Add what isn't in the snapshot (open tasks, blocked items, today's #1 priority).
4. Format per the agent's briefing template. Keep concise — operator should consume in 30 seconds.
5. End with the #1 priority.

---

## "Sync an external data source"

1. Read `skills/integrations-sync/SKILL.md` for the canonical refresh patterns.
2. Identify the source. Pull the delta (`--since <iso>`); full re-sync requires explicit operator approval.
3. Verify with the per-source verification command.
4. Rebuild affected Prep Table snapshots.
5. Log to `state/integrations_sync.log` JSONL.
6. Confirm in chat: source, mode, row delta, audit log path.

---

## "Log a decision or pattern"

1. Classify: Decision → `memory/DECISIONS.md`. Pattern → `memory/PATTERNS.md` (`[P]` → `[V]` at 3 uses). Mistake → `memory/MISTAKES.md` (Failure / Why / Prevention / Tag).
2. Compose per the matching shape. Compute today's date — never quote from context.
3. Cross-link ≥ 2 related files via `[[wiki-link]]`.
4. Append at TOP of target file (newest first), below frontmatter.
5. Bump `last_updated:` on the target file.
6. The `skills/memory-journaling/SKILL.md` skill is the guided form.

---

## "Audit my data readiness" / "/silver-platter"

1. Invoke `skills/silver-platter/SKILL.md`.
2. Skill reads `brain/DATA_TAXONOMY.md` + scans `state/snapshots/`, `scripts/snapshots/`, `memory/`.
3. Outputs HTML report at `tmp/silver-platter-{{agent_name}}-YYYY-MM-DD.html`.
4. Surface the top 3 quick-wins in chat.

---

## Domain-Specific Intents (fill in per agent)

Add intents that recur for {{AGENT_NAME}}'s specific domain. Examples a real-estate agent might add:

- "Pull MLS listings for area X"
- "Run comp analysis on property Y"
- "Generate showing report for client Z"

Each gets its own section. ≤ 15 lines. First-person. Specific.

---

## How to extend this file

Add new sections when an intent recurs. First-person playbooks, ≤ 15 lines each. The whole point is so the agent doesn't re-discover the same sequence on every operator request.

## Obsidian Links
- [[brain/AGENTIC_OS_REFERENCE]] | [[brain/DATA_TAXONOMY]]
- [[skills/silver-platter/SKILL]] | [[skills/integrations-sync/SKILL]] | [[skills/memory-journaling/SKILL]]
