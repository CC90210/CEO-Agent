---
name: sequential-reasoning
description: Enhanced multi-step reasoning protocol for complex problems. Combines Sequential Thinking MCP with structured analysis frameworks. Use for architecture decisions, root cause analysis, strategic planning, and multi-variable optimization.
triggers: [complex reasoning, multi-step analysis, architecture decision, strategic planning]
tier: standard
dependencies: []
---

# Sequential Reasoning Skill

## Overview

Not every problem needs deep reasoning, but for the ones that do, this skill provides structured frameworks that go beyond simple step-by-step thinking. It integrates with the Sequential Thinking MCP for formal chain-of-thought.

## When to Use

| Complexity | Framework | Example |
|------------|-----------|---------|
| **Simple** | Direct execution | Fix a typo, read a file |
| **Moderate** | Brain Loop (10 steps) | Bug fix, feature addition |
| **Complex** | Sequential Reasoning | Architecture design, root cause analysis |
| **Strategic** | Full Analysis Framework | Business decisions, multi-system planning |

## Framework 1: OODA Loop (Fast Decisions)

For time-sensitive decisions where speed matters:

```
OBSERVE → ORIENT → DECIDE → ACT
```

1. **Observe:** What are the raw facts? No interpretation yet.
2. **Orient:** What context matters? Past experience? Current constraints?
3. **Decide:** What's the best action given observations and context?
4. **Act:** Execute the decision. Then observe the result → loop.

**Use when:** Quick decisions, incident response, real-time problem solving.

## Framework 2: Root Cause Analysis (Debugging)

For problems where the symptom isn't the cause:

```
SYMPTOM → HYPOTHESES → EVIDENCE → ROOT CAUSE → FIX → VERIFY
```

1. **Symptom:** What exactly is broken? Reproduce the issue.
2. **Hypotheses:** Generate 3+ possible causes. Rank by likelihood.
3. **Evidence:** For each hypothesis, what evidence would confirm/deny it?
4. **Root Cause:** Which hypothesis has the strongest evidence?
5. **Fix:** Apply minimal fix targeting the root cause (not the symptom).
6. **Verify:** Does the fix resolve the symptom? Any regressions?

**Use when:** Debugging, error investigation, system failures.

## Framework 3: Architecture Decision Record (ADR)

For decisions that affect system structure:

```
CONTEXT → CONSTRAINTS → OPTIONS → ANALYSIS → DECISION → CONSEQUENCES
```

1. **Context:** What is the current situation? Why does a decision need to be made?
2. **Constraints:** What are the hard limits? (Time, money, tech stack, CC's preferences)
3. **Options:** List 3+ viable approaches. Include "do nothing."
4. **Analysis:** For each option: pros, cons, effort, risk, alignment with CC's goals.
5. **Decision:** Choose the best option with clear reasoning.
6. **Consequences:** What changes as a result? What new constraints are introduced?

**Use when:** Architecture changes, technology choices, process redesign.

## Framework 4: Strategic Planning Matrix

For business and growth decisions:

```
GOAL → CURRENT STATE → GAP → STRATEGIES → PRIORITIZE → EXECUTE
```

1. **Goal:** What does CC want to achieve? (Revenue target, capability, market position)
2. **Current State:** Where are we now? What do we have?
3. **Gap:** What's the delta between goal and current state?
4. **Strategies:** How can we close the gap? (3+ approaches)
5. **Prioritize:** Impact vs. effort matrix. Pick highest ROI actions first.
6. **Execute:** Break into actionable tasks with owners and deadlines.

**Use when:** Business planning, quarterly goals, growth strategy.

## Framework 5: Multi-Variable Optimization

For problems with competing objectives:

```
VARIABLES → WEIGHTS → CONSTRAINTS → TRADE-OFFS → OPTIMAL SOLUTION
```

1. **Variables:** What factors are we optimizing? (Speed, cost, quality, maintainability)
2. **Weights:** How important is each variable to CC? (1-10 scale)
3. **Constraints:** What are the hard limits for each variable?
4. **Trade-offs:** Map the trade-off curves. Where do variables conflict?
5. **Optimal Solution:** Find the point that maximizes weighted value.

**Use when:** Technology selection, pricing decisions, resource allocation.

## Integration with Sequential Thinking MCP

For problems requiring formal chain-of-thought:

```javascript
// Use the MCP for structured step-by-step reasoning
sequentialthinking({
  thought: "Step N analysis...",
  thoughtNumber: N,
  totalThoughts: estimated_total,
  nextThoughtNeeded: true/false,
  isRevision: false,  // Set true if revising a previous thought
  revisesThought: N,  // Which thought is being reconsidered
  branchFromThought: N,  // If exploring an alternative path
})
```

**Best Practices:**
- Start with an estimated total, but adjust as you learn more
- Don't be afraid to revise earlier thoughts when new information emerges
- Branch when two viable approaches exist — explore both briefly before committing
- Each thought should advance understanding, not just restate the problem
- Final thought should be a clear, actionable conclusion

## Output Format

After sequential reasoning, present results as:

```
ANALYSIS COMPLETE
Framework: [which framework was used]
Confidence: [HIGH/MEDIUM/LOW]
Key Finding: [1-2 sentence summary]
Recommendation: [clear action]
Reasoning: [brief chain of logic]
Risks: [what could go wrong]
```

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
