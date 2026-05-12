---
name: Quarterly Business Review
trigger: /qbr
schedule: quarterly (last week of quarter)
description: Grade this quarter's OKRs, compile a QBR report, and draft next quarter's OKRs for CC's approval
---

# Quarterly Business Review Workflow

## When to Run
- Last week of each quarter (late March, June, September, December)
- After completing a `/strategic-review`
- When CC asks "let's do a QBR" or "grade our OKRs"

## Prerequisites
- `/strategic-review` should be run first (or the data is stale)
- Current quarter's OKRs should be in `memory/ACTIVE_TASKS.md`

## Announce at Start
"Running QBR — grading Q[X] OKRs, compiling quarterly review, and drafting Q[X+1] targets."

---

## Step 1: Run Strategic Review

If not already done this week:
```
Run /strategic-review workflow first — provides all financial and pipeline data needed for QBR.
```

If already run, load the output and proceed.

---

## Step 2: Pull Quarterly Financial Data

```bash
python scripts/revenue_engine.py history --months 3 --json
python scripts/financial_model.py unit-economics --json
python scripts/financial_model.py concentration --json
```

Calculate for the quarter:
- Starting MRR vs ending MRR
- Total revenue collected
- Total expenses (3 × monthly overhead)
- Net quarterly profit
- MRR growth rate (% change over 90 days)

---

## Step 3: Grade OKRs (0.0 – 1.0 scale)

Read current OKRs from `memory/ACTIVE_TASKS.md` or wherever CC stores them.

For each Key Result:
1. What was the target?
2. What is the actual result?
3. Grade = Actual ÷ Target (cap at 1.0)
4. Write a 1-sentence note on why it hit or missed

Grade scale:
```
0.0-0.3 → Failed
0.4-0.6 → Partial progress
0.7-0.9 → Success (this is the goal)
1.0     → Exceeded (or target was too easy)
```

Objective score = average of its KR grades.
Overall OKR score = average of all Objective scores.

Present grades in this format:
```
## OKR Grades — Q[X] [YEAR]

### O1: [Objective title]
  KR1: [target] → [actual] → [X.X/1.0] — [note]
  KR2: [target] → [actual] → [X.X/1.0] — [note]
  Objective score: X.X/1.0

### O2: [Objective title]
  ...

Overall: X.X/1.0
```

---

## Step 4: Identify Top 3 Wins and Top 3 Misses

From the quarter's activity (SESSION_LOG.md, revenue data, pipeline data):

**Top 3 Wins:**
- What shipped that you're proud of?
- What deal or revenue milestone was hit?
- What system or automation saved the most time?

**Top 3 Misses:**
- What OKR missed and why?
- What task stayed in ACTIVE_TASKS.md all quarter without moving?
- What opportunity wasn't captured?

---

## Step 5: Compile QBR Report

Using `skills/strategic-planning/SKILL.md` QBR template, generate the full report:

```markdown
## QBR — Q[X] [YEAR] — [Date]

### Financial Performance
[Revenue table: start MRR, end MRR, growth %, expenses, net profit]

### Pipeline Performance
[Conversion rates, deal sizes, leads generated vs converted]

### Client Health
[Per-client status table]

### OKR Grades
[Full graded OKR table from Step 3]

### Top 3 Wins
1.
2.
3.

### Top 3 Misses
1.
2.
3.

### Competitive Position
[Key competitive developments this quarter]

### Strategic Adjustments
Continue: [what worked]
Stop: [what didn't]
Start: [what to add]
```

---

## Step 6: Draft Next Quarter OKRs

Based on:
- Missed OKRs that still matter → carry forward or revise
- Strategic gaps identified → new objectives
- MRR target progress → quantify the revenue objective precisely

Draft using the OKR template from `skills/strategic-planning/SKILL.md`:

```markdown
## DRAFT OKRs — Q[X+1] [YEAR] ([Start Month] – [End Month])

### O1: [Objective]
KR1: [Target with number]
KR2: [Target with number]
KR3: [Target with number]

### O2: [Objective]
...
```

Present draft to CC with: "Here are the proposed Q[X+1] OKRs based on this quarter's performance. Do these match your priorities? What should change?"

---

## Step 7: Store and Sync

After CC approves the OKR draft:

1. Write approved OKRs to `memory/ACTIVE_TASKS.md` under a new section
2. Update `brain/STATE.md` with new quarterly focus
3. Archive this QBR report to `memory/ARCHIVES/qbr-YYYY-Q[X].md`
4. Log the QBR completion to the V6.0 state DB (auto-mirrors to `memory/SESSION_LOG.md`):

```bash
python scripts/state_manager.py log --agent bravo \
  --note "Q[X] QBR complete — OKR score X.X/1.0, top win: [win], key miss: [miss], Q[X+1] OKRs approved"
```

---

## Output

CC should leave the QBR session with:
1. Clear OKR grades for the quarter (no ambiguity)
2. An archived QBR document
3. Approved OKRs for next quarter written into ACTIVE_TASKS.md
4. Clear #1 priority for the week to start next quarter strong

---

## Rules
- Never grade an OKR above 1.0 in the record, even if exceeded (note the excess separately)
- Never present next quarter's OKRs without also sharing what's being retired from this quarter
- Always present OKR grades BEFORE drafting next quarter's — grading reveals what to carry forward

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
