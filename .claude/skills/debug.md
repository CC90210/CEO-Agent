---
name: debug
description: Systematic debugging using root-cause-first methodology. Never guesses — reads errors, reproduces, traces data flow, forms hypotheses, tests minimally.
user-invocable: true
---

# /debug — Systematic Debugging

Load `skills/systematic-debugging/SKILL.md` for the full protocol.

## The Iron Law
```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

## Quick Steps

1. **Phase 1: Root Cause Investigation**
   - Read error messages carefully (don't skip stack traces)
   - Reproduce consistently
   - Check recent changes (`git diff`, recent commits)
   - Gather evidence at component boundaries
   - Trace data flow backward to find the source

2. **Phase 2: Pattern Analysis**
   - Find working examples in the same codebase
   - Compare against references
   - Identify differences

3. **Phase 3: Hypothesis and Testing**
   - Form single hypothesis: "I think X because Y"
   - Make the SMALLEST possible change to test
   - One variable at a time

4. **Phase 4: Implementation**
   - Create failing test case
   - Implement single fix addressing root cause
   - Verify fix (all tests pass)
   - If 3+ fixes fail → question the architecture, escalate to CC

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
