---
name: evolve
description: Extract session patterns and promote them to skills, SOPs, or CLAUDE.md rules. The self-improvement engine that makes Bravo smarter over time.
user-invocable: true
---

# /evolve — Self-Improvement Pipeline

## Steps

1. Read recent session data:
   - `memory/SESSION_LOG.md` — last 5-10 sessions
   - `memory/MISTAKES.md` — recent mistakes
   - `memory/PATTERNS.md` — probationary patterns
   - `memory/SELF_REFLECTIONS.md` — failure reflections

2. **Pattern Extraction:**
   - Identify repeated behaviors (positive or negative)
   - Positive pattern 3+ times → candidate for promotion
   - Negative pattern 2+ times → candidate for prevention rule

3. **Promotion Decisions:**
   - Repeated task sequence → create SOP in `memory/SOP_LIBRARY.md`
   - Proven debugging technique → add to `skills/systematic-debugging/SKILL.md`
   - New capability discovered → update `brain/CAPABILITIES.md`
   - Recurring mistake → add prevention rule to CLAUDE.md

4. **Probationary Validation:**
   - Check `[PROBATIONARY]` patterns — any used 3+ times successfully?
   - Yes → promote to `[VALIDATED]`
   - No evidence → keep probationary or retire

5. Report what was evolved, promoted, or retired.

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
