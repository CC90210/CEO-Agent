---
name: growth-engine
description: Self-learning and evolution system. Tracks capability expansion, extracts patterns from experience, promotes patterns to SOPs, identifies skill gaps, and produces evolution reports. Triggers after complex tasks, failures, and monthly audits.
triggers: [MRR, revenue, growth, evolution, capability, skill gap, pattern promotion]
tier: core
dependencies: [memory-management, sop-breakdown]
---

# Growth Engine — Self-Learning System

## Overview

Bravo doesn't just execute — it learns. The Growth Engine tracks what Bravo can do, identifies what it should learn next, and systematically expands capabilities over time.

## Growth Cycle

```
EXPERIENCE → REFLECT → EXTRACT → STORE → APPLY → GROW
     ↑                                              |
     └──────────────────────────────────────────────┘
```

### 1. EXPERIENCE
Every task execution generates experience data:
- Task type and complexity
- Tools and skills used
- Outcome (success/partial/failure)
- Time taken
- Errors encountered
- CC's feedback (explicit or implicit)

### 2. REFLECT
After significant tasks (Brain Loop Step 7), assess:
- What went well? Why?
- What failed? Root cause?
- Was there a more efficient approach?
- Did I use the right tools?
- Would CC be satisfied with the quality?

### 3. EXTRACT
Derive actionable insights:
- **New Pattern:** A repeatable approach that works (→ PATTERNS.md)
- **New Mistake:** An error to never repeat (→ MISTAKES.md)
- **New Capability:** Something Bravo can now do (→ brain/GROWTH.md)
- **New SOP Candidate:** A process done 3+ times (→ SOP_LIBRARY.md)
- **Skill Gap:** A task that failed due to missing capability

### 4. STORE
Store with appropriate confidence scores:
- Patterns: minimum 0.7 confidence (2+ observations)
- Mistakes: minimum 0.9 confidence (verified root cause)
- Capabilities: minimum 0.8 confidence (successfully executed)
- SOP candidates: tracked in pattern-to-SOP pipeline

### 5. APPLY
Use stored knowledge in future tasks:
- Brain Loop Step 2 (RECALL) searches all memory stores
- Brain Loop Step 5 (VERIFY) checks against known patterns/mistakes
- SOP execution follows stored procedures

### 6. GROW
Expand the capability frontier:
- New tools mastered
- New task types completed successfully
- New integrations established
- Higher success rates on existing capabilities

## Capability Categories

| Category | Examples |
|----------|----------|
| **Communication** | Social posting, content writing, email drafting |
| **Development** | Bug fixing, feature building, code review, testing |
| **Research** | Market analysis, competitive intelligence, trend spotting |
| **Automation** | n8n workflows, cron jobs, triggered pipelines |
| **Operations** | Client onboarding, invoicing, deployment |
| **Analysis** | Data analysis, performance profiling, SEO audit |
| **Creative** | Visual design, video editing, brand content |
| **Strategic** | Business planning, pricing strategy, growth hacking |

## Skill Gap Detection

When a task fails or is routed away because Bravo lacks capability:

1. Log the gap: "Could not [action] because [reason]"
2. Research: Is there a skill, tool, or MCP that could fill this gap?
3. Propose: Suggest to CC how to acquire the capability
4. Track: Add to "Evolution Goals" in brain/GROWTH.md

## Evolution Reports

### Weekly Summary (Auto-generated if 5+ sessions)
```
BRAVO WEEKLY EVOLUTION REPORT
Period: [date range]
Sessions: [count]
Tasks Completed: [count] | Success Rate: [%]
New Capabilities: [list]
Mistakes Prevented: [count] (from learned patterns)
SOPs Created: [count]
Top Growth Area: [category]
Biggest Challenge: [description]
```

### Monthly Report (Via /monthly-audit command)
- Full capability frontier review
- Confidence score decay processing
- SOP success rate analysis
- Skill gap inventory
- Growth velocity trends
- Recommendations for CC

## Self-Learning Triggers

| Trigger | Action |
|---------|--------|
| Task completed successfully | Log capability if new |
| Task failed | Log mistake, identify gap |
| Same task done 3rd time | Draft SOP candidate |
| CC provides feedback | Calibrate communication/approach |
| Monthly audit | Full growth review |
| New MCP/tool added | Log new capability, test integration |
| Pattern confidence > 0.9 | Promote to SOP if actionable |

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
