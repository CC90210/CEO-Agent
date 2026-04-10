---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
triggers: [bug, error, failure, crash, broken, not working, debug, stack trace]
tier: core
dependencies: []
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Manager wants it fixed NOW (systematic is faster than thrashing)

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings
   - They often contain the exact solution
   - Read stack traces completely
   - Note line numbers, file paths, error codes

2. **Reproduce Consistently**
   - Can you trigger it reliably?
   - What are the exact steps?
   - Does it happen every time?
   - If not reproducible → gather more data, don't guess

3. **Check Recent Changes**
   - What changed that could cause this?
   - Git diff, recent commits
   - New dependencies, config changes
   - Environmental differences

4. **Gather Evidence in Multi-Component Systems**

   **WHEN system has multiple components (CI → build → signing, API → service → database):**

   **BEFORE proposing fixes, add diagnostic instrumentation:**
   ```
   For EACH component boundary:
     - Log what data enters component
     - Log what data exits component
     - Verify environment/config propagation
     - Check state at each layer

   Run once to gather evidence showing WHERE it breaks
   THEN analyze evidence to identify failing component
   THEN investigate that specific component
   ```

   **Example (multi-layer system):**
   ```bash
   # Layer 1: Workflow
   echo "=== Secrets available in workflow: ==="
   echo "IDENTITY: ${IDENTITY:+SET}${IDENTITY:-UNSET}"

   # Layer 2: Build script
   echo "=== Env vars in build script: ==="
   env | grep IDENTITY || echo "IDENTITY not in environment"

   # Layer 3: Signing script
   echo "=== Keychain state: ==="
   security list-keychains
   security find-identity -v

   # Layer 4: Actual signing
   codesign --sign "$IDENTITY" --verbose=4 "$APP"
   ```

   **This reveals:** Which layer fails (secrets → workflow ✓, workflow → build ✗)

5. **Trace Data Flow**

   **WHEN error is deep in call stack:**

   See `root-cause-tracing.md` in this directory for the complete backward tracing technique.

   **Quick version:**
   - Where does bad value originate?
   - What called this with bad value?
   - Keep tracing up until you find the source
   - Fix at source, not at symptom

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find Working Examples**
   - Locate similar working code in same codebase
   - What works that's similar to what's broken?

2. **Compare Against References**
   - If implementing pattern, read reference implementation COMPLETELY
   - Don't skim - read every line
   - Understand the pattern fully before applying

3. **Identify Differences**
   - What's different between working and broken?
   - List every difference, however small
   - Don't assume "that can't matter"

4. **Understand Dependencies**
   - What other components does this need?
   - What settings, config, environment?
   - What assumptions does it make?

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form Single Hypothesis**
   - State clearly: "I think X is the root cause because Y"
   - Write it down
   - Be specific, not vague

2. **Test Minimally**
   - Make the SMALLEST possible change to test hypothesis
   - One variable at a time
   - Don't fix multiple things at once

3. **Verify Before Continuing**
   - Did it work? Yes → Phase 4
   - Didn't work? Form NEW hypothesis
   - DON'T add more fixes on top

4. **When You Don't Know**
   - Say "I don't understand X"
   - Don't pretend to know
   - Ask for help
   - Research more

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Create Failing Test Case**
   - Simplest possible reproduction
   - Automated test if possible
   - One-off test script if no framework
   - MUST have before fixing
   - Use the `superpowers:test-driven-development` skill for writing proper failing tests

2. **Implement Single Fix**
   - Address the root cause identified
   - ONE change at a time
   - No "while I'm here" improvements
   - No bundled refactoring

3. **Verify Fix**
   - Test passes now?
   - No other tests broken?
   - Issue actually resolved?

4. **If Fix Doesn't Work**
   - STOP
   - Count: How many fixes have you tried?
   - If < 3: Return to Phase 1, re-analyze with new information
   - **If ≥ 3: STOP and question the architecture (step 5 below)**
   - DON'T attempt Fix #4 without architectural discussion

5. **If 3+ Fixes Failed: Question Architecture**

   **Pattern indicating architectural problem:**
   - Each fix reveals new shared state/coupling/problem in different place
   - Fixes require "massive refactoring" to implement
   - Each fix creates new symptoms elsewhere

   **STOP and question fundamentals:**
   - Is this pattern fundamentally sound?
   - Are we "sticking with it through sheer inertia"?
   - Should we refactor architecture vs. continue fixing symptoms?

   **Discuss with your human partner before attempting more fixes**

   This is NOT a failed hypothesis - this is a wrong architecture.

## Red Flags - STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals new problem in different place**

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (see Phase 4.5)

## your human partner's Signals You're Doing It Wrong

**Watch for these redirections:**
- "Is that not happening?" - You assumed without verifying
- "Will it show us...?" - You should have added evidence gathering
- "Stop guessing" - You're proposing fixes without understanding
- "Ultrathink this" - Question fundamentals, not just symptoms
- "We're stuck?" (frustrated) - Your approach isn't working

**When you see these:** STOP. Return to Phase 1.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Identify differences |
| **3. Hypothesis** | Form theory, test minimally | Confirmed or new hypothesis |
| **4. Implementation** | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

If systematic investigation reveals issue is truly environmental, timing-dependent, or external:

1. You've completed the process
2. Document what you investigated
3. Implement appropriate handling (retry, timeout, error message)
4. Add monitoring/logging for future investigation

**But:** 95% of "no root cause" cases are incomplete investigation.

## Supporting Techniques

These techniques are part of systematic debugging and available in this directory:

- **`root-cause-tracing.md`** - Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** - Add validation at multiple layers after finding root cause
- **`condition-based-waiting.md`** - Replace arbitrary timeouts with condition polling

**Related skills:**
- **superpowers:test-driven-development** - For creating failing test case (Phase 4, Step 1)
- **superpowers:verification-before-completion** - Verify fix worked before claiming success

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common

---

## 5 Whys — Root Cause Analysis Template

Use for any bug where the immediate cause is obvious but the underlying cause is not. The goal is to reach the system-level failure, not the surface symptom.

```
Problem statement: [Describe the bug in one specific sentence]

Why 1: Why did [problem] occur?
Answer: [First-level cause]

Why 2: Why did [answer to Why 1] occur?
Answer: [Second-level cause]

Why 3: Why did [answer to Why 2] occur?
Answer: [Third-level cause]

Why 4: Why did [answer to Why 3] occur?
Answer: [Fourth-level cause — often reveals the real system issue]

Why 5: Why did [answer to Why 4] occur?
Answer: [Root cause — this is what we fix]

Root cause: [Restate clearly in one sentence]
Fix: [The change that addresses the root cause, not any of the intermediate causes]
Prevention: [What process or check prevents this class of bug in the future?]
```

**Rules:**
- Each answer must be a fact, not a hypothesis. If you're unsure, gather evidence before proceeding.
- Stop at 5 Whys or when you reach a process or architecture failure (rather than a code bug).
- If two Why chains diverge at the same level — you may have two root causes. Document both.

---

## Binary Search (Bisect) Strategy for Regression Bugs

When you know something used to work and now doesn't, but you don't know which change broke it.

### Step 1 — Establish Bounds

```
Known good: [commit hash or date when it worked]
Known bad: [commit hash or date when it broke]
```

### Step 2 — Find the Midpoint

```bash
# If using git bisect (most reliable)
git bisect start
git bisect bad HEAD
git bisect good [known-good-commit]
# Git will checkout the midpoint commit automatically
```

### Step 3 — Test at Midpoint

Run the minimal reproduction case at the midpoint commit. Mark it:

```bash
git bisect good   # if it works at this commit
git bisect bad    # if it's broken at this commit
# Repeat until git bisect identifies the first bad commit
git bisect reset  # when done
```

### Step 4 — Manual Binary Search (No git bisect)

If git bisect isn't available, bisect manually:

```
Total changes: [N changes between good and bad]
Round 1: Disable the top 50% of changes. Does the bug still appear?
  Yes → Bug is in the bottom 50%
  No  → Bug is in the top 50%

Round 2: Narrow by 50% again. Repeat until you find the single change that introduced the bug.

Typical rounds needed: log₂(N)
  10 changes → ~4 rounds
  100 changes → ~7 rounds
  1,000 changes → ~10 rounds
```

---

## Log Analysis Patterns

When the bug doesn't reproduce locally and you must debug from logs.

### Error Correlation Pattern

Look for events that cluster around the failure timestamp:

```
Step 1: Find the error timestamp (T)
Step 2: Extract all log lines from T-60s to T+10s
Step 3: Scan for:
  - Warnings or errors immediately BEFORE T (these are candidate causes)
  - Any unusual volume spikes (10x+ normal rate = something upstream changed)
  - Any missing expected log lines (if expected log A doesn't appear before T, A is the failure)
  - Multiple error types at the same timestamp = shared upstream dependency failing
```

### Timing Analysis

For performance bugs and intermittent failures, timing tells the story:

```
Step 1: Extract timestamps for the start and end of each operation
Step 2: Compute duration for each step in the pipeline
Step 3: Compare to baseline (prior successful run or documented expectations)
Step 4: Find the step where duration suddenly increased → that step is the bottleneck

Example:
  Auth: 12ms (normal)
  DB query: 4,200ms (baseline: 80ms) ← HERE
  Response: 4ms (normal)
  
  Finding: DB query is 52x slower than baseline. Investigate query plan, indexes, connection pool.
```

### Log Analysis CLI Commands

```bash
# Extract lines around a timestamp (logs with ISO timestamps)
grep "2026-04-06T14:3[0-9]" app.log

# Count error frequency by type
grep "ERROR" app.log | sed 's/.*ERROR: //' | sort | uniq -c | sort -rn | head -20

# Find the first occurrence of an error
grep -n "TypeError" app.log | head -1

# Correlate two log files by timestamp
comm -12 <(grep "14:32" api.log | awk '{print $1}') <(grep "14:32" worker.log | awk '{print $1}')
```

---

## Hypothesis-Driven Debugging

Structured scientific method for bugs that resist the standard 4-phase process.

### Template

```
## Debugging Session — [Bug Description] — [Date]

### Observed Behavior
[What actually happens — specific, not paraphrased]

### Expected Behavior
[What should happen — from spec, tests, or prior behavior]

### Evidence Gathered So Far
- [Log line or error message]
- [Screenshot or test output]
- [Relevant code path or data state]

### Hypotheses (generate 2–3 before testing any)

Hypothesis A: [Clear statement of what might be wrong]
  - Confidence: Low / Medium / High
  - Test: [Minimal action to confirm or deny — ideally one line or one flag change]
  - Prediction: [If A is correct, we will see X]

Hypothesis B: [Different candidate cause]
  - Confidence: Low / Medium / High
  - Test: [Minimal action]
  - Prediction: [If B is correct, we will see Y]

Hypothesis C: [Third candidate — often the non-obvious one]
  - Confidence: Low / Medium / High
  - Test: [Minimal action]
  - Prediction: [If C is correct, we will see Z]

### Testing Order
Test highest-confidence hypothesis first. If it fails, test B. Never test multiple simultaneously.

### Results
Hypothesis A tested: [Confirmed / Denied]
  - Evidence: [What we saw]
  - Next: [Proceed to fix / Test B]

### Root Cause
[Final determination — one sentence]

### Fix Applied
[Exact change made — file, line, what changed]

### Verification
[Test or behavior that confirms the fix worked]
```

---

## Post-Mortem Template

For any bug that caused production impact, a post-mortem is required before the session ends. Post-mortems are blameless — they target systems and processes, not people.

```markdown
## Post-Mortem — [Incident Title] — [Date]

### Summary
[2-3 sentences: what broke, how long it was broken, what the impact was]

### Timeline

| Time | Event |
|------|-------|
| [T+0:00] | Incident detected |
| [T+X:XX] | [Key diagnostic step] |
| [T+X:XX] | Root cause identified |
| [T+X:XX] | Fix deployed |
| [T+X:XX] | Confirmed resolved |

**Total time to resolution:** X minutes / hours

### Root Cause
[The 5 Whys answer — the actual system failure, not the symptom]

### Contributing Factors
- [Factor 1 — e.g., "No test covered this edge case"]
- [Factor 2 — e.g., "The error was swallowed silently"]
- [Factor 3 — e.g., "No alerting on this metric"]

### What Went Well
- [Something the response did right — build on this]

### Action Items

| Action | Owner | By When |
|--------|-------|---------|
| [Add test for this case] | Bravo | Next session |
| [Add error alerting] | Bravo | This week |
| [Update runbook] | Bravo | Before next deploy |

### Logged To
- [ ] memory/MISTAKES.md (root cause + 1-line prevention)
- [ ] Supabase agent_traces (if applicable)
```

---

## Sub-Guides
- [[skills/systematic-debugging/root-cause-tracing]] — Backward tracing technique through call stacks
- [[skills/systematic-debugging/defense-in-depth]] — Validation at multiple layers after root cause
- [[skills/systematic-debugging/condition-based-waiting]] — Replace timeouts with condition polling
- [[skills/systematic-debugging/CREATION-LOG]] — Creation history and rationale

## Tests
- [[skills/systematic-debugging/test-academic]] — Academic understanding test
- [[skills/systematic-debugging/test-pressure-1]] — Pressure scenario 1
- [[skills/systematic-debugging/test-pressure-2]] — Pressure scenario 2
- [[skills/systematic-debugging/test-pressure-3]] — Pressure scenario 3

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]] | [[skills/test-driven-development/SKILL]]
