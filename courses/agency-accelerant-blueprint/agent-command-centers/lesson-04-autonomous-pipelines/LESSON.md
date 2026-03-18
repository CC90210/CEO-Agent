# Lesson 4: Autonomous Decision Pipelines — Agents That Act Without You

> **Course:** Agent Command Centers
> **XP Reward: +450 XP** | Running Total: 1,500 XP
> **Level: Architect (L3)** — Course complete. You now build systems that work while you sleep.

---

## The Autonomy Spectrum

Not all agent actions should require your approval. Not all agent actions should be unsupervised. The goal is knowing the difference.

```
MANUAL ←————————————————————————————→ FULLY AUTONOMOUS

Manual           Semi-automated      Supervised         Fully autonomous
  |                    |             autonomous               |
"Do X"          "Draft X,          "Do X, show me       "Do X on schedule,
(user          I'll approve"        the result"         alert me only if
initiates)                                               something fails"

Examples:
  Write a       Draft an email,     Run daily report,   Daily backup,
  report        I'll send it        show me summary     heartbeat check
```

Most tasks live in the middle. The goal is to push routine, low-risk operations toward full autonomy so you spend your time on judgment calls, not execution.

---

## Confidence-Based Autonomy

The key to safe autonomy is confidence gating: the agent's level of autonomy scales with how confident it is about the right action.

### The Three-Tier Model

| Confidence | Range | Agent Behavior |
|-----------|-------|----------------|
| **High** | >0.8 | Act without prompting. Log the action. |
| **Medium** | 0.5–0.8 | Act, then show CC the result immediately. |
| **Low** | <0.5 | Stop. Present the plan. Wait for CC approval before executing. |

### Applying Confidence Gates in Practice

```
Task: "Send the weekly report to Client ABC"

Agent thinks:
  - I have the report template (confidence: 0.9 — used 12 times successfully)
  - I have the client's email address (confidence: 0.95 — verified in LONG_TERM.md)
  - I know the correct tone for this client (confidence: 0.85 — 3 prior successful sends)
  Overall confidence: 0.88 → HIGH → Execute autonomously

Task: "Update the pricing on the OASIS website"

Agent thinks:
  - I can edit the website (confidence: 0.9)
  - I know the current prices (confidence: 0.7 — last verified 45 days ago)
  - I know what the new prices should be (confidence: 0.3 — CC mentioned this casually)
  Overall confidence: 0.45 → LOW → Stop and ask CC to confirm the new prices
```

The formula isn't mathematical — it's a thinking discipline. Before acting on anything consequential, ask: "How confident am I that this is the right action with the right parameters?"

💀 **COMMON MISTAKE:** Using confidence gating as a reason to be maximally cautious and always ask before acting. That defeats the purpose. The goal is to push routine actions to full autonomy and free CC's attention for genuine judgment calls — not to create a system that asks permission for every file read.

---

## The Brain Loop: 10-Step Reasoning Protocol

The Brain Loop is the reasoning framework your agent applies to every significant task. It is not a checklist you consciously run through — it is the structure of how the agent thinks.

```
Step 1: ORIENT     Load context — SOUL.md, USER.md, STATE.md
Step 2: RECALL     Search memory — mistakes, patterns, SOPs, prior decisions
Step 3: ASSESS     Evaluate — what's known, what's uncertain, what's risky
Step 4: PLAN       Multi-hypothesis — generate 2-3 approaches, rank them
Step 5: VERIFY     Cross-check — does this violate any constraints?
Step 6: EXECUTE    One step at a time, log each action
Step 7: REFLECT    What happened? What went wrong? What should change?
Step 8: STORE      Update memory — mistakes, patterns, facts, session log
Step 9: EVOLVE     New capability? → update skills. Repeated task? → create SOP
Step 10: HEAL      Clean up, verify state, git commit, sync Supabase
```

### Trivial vs. Complex Tasks

The full loop is heavyweight. Apply it proportionally:

| Complexity | Steps Used |
|-----------|------------|
| Trivial — typo fix, lookup | 1, 2, 6 |
| Simple — single file edit | 1-3, 5-6 |
| Moderate — feature, bug fix | 1-8 |
| Complex — multi-file, architecture | All 10 |
| Architectural — system redesign | All 10 + CC approval at step 4 |

The most impactful steps for autonomous pipelines are RECALL (don't repeat mistakes), PLAN (generate multiple approaches), and REFLECT (learn from every execution).

---

## Multi-Hypothesis Planning

Single-track thinking is fragile. If the one approach you planned hits a blocker, you're stuck. Multi-hypothesis planning generates 2-3 approaches and ranks them before execution.

### The LATS Pattern (Language Agent Tree Search)

Before executing a complex task, generate candidate approaches:

```
Task: "Set up automated lead follow-up for new OASIS contacts"

Approach A: n8n workflow with email sequences
  Feasibility: 0.9 (we have n8n, we have email integration)
  Risk: Low (reversible, no financial consequences)
  Effort: ~45 min with Bravo
  Ranked: #1

Approach B: Supabase trigger + Edge Function + Resend
  Feasibility: 0.8 (more components, more failure points)
  Risk: Medium (new infrastructure to maintain)
  Effort: ~90 min
  Ranked: #2

Approach C: Manual + SOP
  Feasibility: 1.0 (always works)
  Risk: Lowest (no automation failure possible)
  Effort: Ongoing manual time
  Ranked: #3 (only if A and B fail)
```

During execution, if Approach A fails after two attempts, switch to Approach B. If Approach B fails, stop and surface the issue to CC with both failure reports.

### The Three-Attempt Rule

If an approach fails three times:
- Stop — do not attempt a fourth fix on the same approach
- Generate a new hypothesis (or promote Approach B)
- If all approaches exhausted: escalate to CC with a Reflexion entry explaining what was tried and why it failed

This prevents the trap of applying the same failed fix repeatedly because it "should work."

---

## Reflexion Protocol: Structured Failure Analysis

Reflexion (from the 2023 research paper by Shinn et al.) is a structured method for making AI agents learn from failure. Instead of failing silently and retrying, the agent generates a written analysis of what went wrong and why.

### The Reflexion Template

```
### [DATE] — Reflexion Entry

**Task attempted:** [What was being done]
**Approach taken:** [How it was attempted]
**Failure point:** [Exactly where and how it failed]
**Root cause:** [Why it failed — not what failed]
**What should have been done differently:** [Concrete alternative]
**Confidence in this analysis:** [0.0-1.0]
```

### Why This Matters for Autonomous Systems

A Reflexion entry is stored in `memory/SELF_REFLECTIONS.md` and retrieved at the start of the next similar task (Brain Loop Step 2: RECALL). This means the agent starts the next similar task with the lesson from the last failure already loaded.

Without Reflexion: agent repeats the same approach, fails the same way.
With Reflexion: agent reads the previous failure analysis, generates a different approach first.

Over time, a system with Reflexion accumulates a library of "what not to do" that is as valuable as its library of "what works."

---

## Cron-Triggered Pipelines

The highest-leverage autonomous pipelines run on a schedule — they don't require a human to initiate them.

### Pipeline 1: Daily Business Report

```
Schedule: Every day at 7am

Steps:
  1. Query Supabase for yesterday's metrics
     - New leads
     - Active tasks completed
     - MRR movement (Stripe API)
     - Agent activity summary (agent_traces count)

  2. Query n8n for workflow executions yesterday

  3. Check ACTIVE_TASKS.md for anything blocked >2 days

  4. Generate report using template in skills/daily-report/SKILL.md

  5. Send via Telegram
     Format:
     📊 Daily Report — {DATE}
     Revenue: ${MRR} MRR
     New leads: {N}
     Tasks completed: {N}
     Blocked: {N items needing attention}

  6. Log to SESSION_LOG.md
```

### Pipeline 2: Weekly Retro

```
Schedule: Every Sunday at 9am

Steps:
  1. Run /retro command — full retrospective analysis
  2. Read git logs from all app repos (last 7 days)
  3. Read SESSION_LOG.md entries for the week
  4. Calculate 4 scores (Velocity, Quality, Memory, Coordination)
  5. Generate improvement actions for any score <7
  6. Append to memory/PATTERNS.md if new patterns found
  7. Send Telegram summary
  8. Commit: bravo: retro — week of YYYY-MM-DD
```

### Pipeline 3: Monthly Credential Rotation Reminder

```
Schedule: 1st of every month

Steps:
  1. Read credentials-rotation-log.md
  2. Find any keys with last_rotated older than 30 days (DB passwords)
     or 90 days (API keys)
  3. For each overdue key: create task in ACTIVE_TASKS.md
  4. Send Telegram message listing all overdue rotations
  5. Log to SESSION_LOG.md
```

---

## Human-in-the-Loop Gates

Autonomy is not unlimited. Some actions should always require human approval, regardless of how confident the agent is.

### Hard Gates — Always Require Approval

| Category | Examples |
|----------|---------|
| **Destructive operations** | DELETE queries, file deletions, database migrations that drop columns |
| **Financial transactions** | Initiating payments, creating invoices, modifying subscription plans |
| **Client-facing communications** | Emails sent as CC, social posts under client accounts |
| **Infrastructure changes** | New Vercel deployments for production, new Supabase projects |
| **Credential operations** | Key rotation, creating new API keys |

The agent can prepare everything — write the email, draft the migration, stage the deployment — but it must stop at the gate and wait for explicit CC approval before executing.

### Soft Gates — Require Approval When Uncertain

| Condition | Gate |
|-----------|------|
| Confidence < 0.5 on any parameter | Present plan, wait for approval |
| No prior successful completion of this task type | Show approach, ask for confirmation |
| Task affects >5 files across multiple repos | Present scope, ask for confirmation |
| Task touches billing or client data | Additional confirmation regardless of confidence |

```
Gate implementation in CLAUDE.md:

RULE: Before any destructive operation, financial transaction, or
client-facing communication, STOP and write:
"GATE: I'm about to [action]. This requires your approval.
Reason: [why this is gated]
Action I'll take: [exact steps]
Approve? (Yes/No)"

Do not proceed until CC explicitly says yes.
```

---

## Skill Evolution: How Agents Learn New Capabilities

An agent that doesn't grow is an agent that becomes obsolete. The Voyager-inspired skill evolution model (from the 2023 Minecraft agent research) applies to your command center.

### The Skill Promotion Ladder

```
Observation (session)
  ↓ (after 2 similar tasks)
PROBATIONARY pattern in PATTERNS.md
  ↓ (after 3 successful sessions using it)
VALIDATED pattern
  ↓ (if used 5+ times with a standard sequence)
SOP in SOP_LIBRARY.md
  ↓ (if complex enough to warrant dedicated guidance)
SKILL.md in skills/ directory
```

Every task is an opportunity to notice whether what you did should be codified. The threshold is simple: if you did it the same way three times, write it down. If you wrote it down three more times and it worked, promote it.

### Compositionality Check

Before creating a new skill, ask: can this be built from existing simpler skills?

```
New need: "How do I handle client offboarding?"

Existing skills:
  skills/memory-management/SKILL.md      ← archive client data
  skills/systematic-debugging/SKILL.md   ← investigate any outstanding issues
  skills/sop-breakdown/SKILL.md          ← create the offboarding SOP

Client offboarding is not a new skill — it is a composition of existing ones.
Create an SOP, not a skill.
```

Build new skills only for genuinely novel capabilities. Compose existing skills for everything else.

---

## The Safety Net: Kill Switches and Rollback

Autonomous pipelines need safety mechanisms. When something goes wrong at 3am with no human watching, the system must be able to contain the damage.

### Kill Switches

For any automated pipeline, define a kill switch — a mechanism to stop it immediately.

```
n8n pipeline kill switch:
  1. In n8n: set workflow to "inactive" (stops cron execution immediately)
  2. Manual override webhook: POST /agent/kill → sets agent_state.status='suspended'
  3. ACTIVE_TASKS.md entry: "SUSPENDED — pipeline stopped due to [reason]"

Claude Code kill switch:
  Ctrl+C stops the current session immediately
  Destructive operations always gated (never autonomous)
```

### Rollback Procedures

For any autonomous action that modifies state, define the rollback:

| Action | Rollback |
|--------|---------|
| Git commit | `git revert [commit-hash]` |
| Database write | Transaction with rollback on error |
| Vercel deployment | Previous deployment is preserved — redeploy from dashboard |
| File write | Keep backup in `tmp/` before overwriting |
| API call | Cannot be rolled back — prevent with approval gates |

### Blast Radius Containment

Design autonomous actions so failure is contained:

```
Bad: One workflow that reads leads → enriches → emails → updates Stripe → logs everything
     (one failure at step 4 has already sent emails and you can't unsend them)

Good: Separate workflows for each phase
     Phase 1: Read + enrich → success? → trigger Phase 2
     Phase 2: Email → success? → trigger Phase 3
     Phase 3: Update Stripe → success? → trigger Phase 4
     Each phase fails independently, earlier phases already complete
```

---

## 🔥 EXERCISE: Autonomous Pipeline with Full Safety Architecture

Build a complete autonomous pipeline. This is the capstone exercise for the course.

**The Pipeline:** Daily lead enrichment for OASIS AI

```
Cron: Every day at 6am

Step 1: Query Supabase for leads added in last 24 hours
  → Gate: if >20 leads (unusual), STOP and alert CC before proceeding

Step 2: For each new lead, check if enrichment data exists
  → If missing company info: note for manual research queue
  → If exists: proceed to Step 3

Step 3: Score lead based on criteria (company size, industry, keywords)
  → Scoring logic documented in skills/lead-scoring/SKILL.md

Step 4: IF lead score > 7/10
  → Gate: Draft email sequence, STOP here
  → Telegram message with draft to CC for approval before sending
  → Do NOT send automatically — this is client-facing communication

Step 5: Update Supabase leads table with enrichment data and score

Step 6: Log run summary to SESSION_LOG.md and agent_traces
```

**Build this with:**
1. The confidence gate at Step 1 (>20 leads = unusual → alert)
2. A human-in-the-loop gate at Step 4 (draft + wait for approval)
3. A Reflexion entry if any step fails
4. A kill switch (n8n workflow set to inactive)
5. A rollback procedure (transaction for Supabase writes)

**Deliverable:** A working n8n workflow implementing all 6 steps, with confidence gates at Steps 1 and 4, Reflexion logging on failure, and a documented kill switch procedure.

---

## 🧠 KEY TAKEAWAY

Autonomous pipelines are what make an AI agency scalable. The work that would take a human team 40 hours per week runs in the background while you focus on clients and growth. The keys to safe autonomy are: confidence-based gating (act alone when confident, ask when uncertain), human-in-the-loop gates for financial and client-facing actions, the Brain Loop for structured reasoning, Reflexion for learning from failure, and a safety net of kill switches and rollback procedures. The system that works while you sleep is the system that knows exactly when not to act without you.

---

**Course Complete: Agent Command Centers**

You've designed the architecture, built the multi-agent roster, implemented monitoring, and created autonomous pipelines. The command center is yours. Now run it.
