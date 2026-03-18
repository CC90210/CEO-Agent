# Lesson 2: Multi-Agent Orchestration — Specialized Agents Working Together

> **Course:** Agent Command Centers
> **XP Reward: +350 XP** | Running Total: 650 XP
> **Level: Architect (L3)** — One agent is a tool. Ten working together is a system.

---

## Why Specialized Agents Beat One General Agent

The instinct when building an AI system is to make one extremely capable agent that handles everything. This works fine at small scale. It breaks down as soon as the task complexity increases.

### The Single Agent Problem

A general agent handling everything suffers from three compounding issues:

**1. Context window dilution.** Every capability you add to a single agent's instructions consumes context window space. A 500-line CLAUDE.md leaves less room for the actual task than a 100-line one. The more general the agent, the less focused it is on any specific task.

**2. Conflicting instructions.** "Be creative when writing content" and "Be precise when writing code" are genuinely contradictory. A general agent reconciles these instructions on every task instead of picking the right mode for the job.

**3. No quality enforcement.** When the same agent writes code, reviews code, and deploys code, there's no independent check. A specialist Reviewer sees the Coder's output with fresh context and different criteria.

### The Specialist Model

```
User task: "Build a client dashboard for ABC Corp"

Single agent approach:
  One agent → researches, plans, codes, reviews, deploys
  → Context diluted across all phases
  → No independent quality check
  → Sequential, slow

Multi-agent approach:
  Architect  → system design (Opus model — worth the cost here)
  Planner    → implementation breakdown
  Coder      → writes the code
  Reviewer   → independent quality gate
  Git Ops    → commits and creates PR
  → Parallel where possible, specialized always
  → Independent review catches what the Coder misses
```

The time savings come from parallelism. The quality improvement comes from specialization.

---

## The Agent Roster

A complete agency command center needs these specialist types. You don't need all of them on day one — start with the ones that match your current workload and add more as you scale.

### Tier 1: Core (Build First)

| Agent | Primary Function | Model Tier |
|-------|-----------------|------------|
| **Architect** | System design, schema decisions, cross-service planning | Opus — expensive, use sparingly |
| **Planner** | Translates features into phased numbered steps | Sonnet |
| **Coder** | High-speed TDD implementation of approved plans | Sonnet |
| **Reviewer** | Pre-commit security and quality audit | Sonnet |
| **Debugger** | Root cause analysis and minimal fixes | Sonnet |

### Tier 2: Operational (Add When You Have Clients)

| Agent | Primary Function | Model Tier |
|-------|-----------------|------------|
| **Chief of Staff** | Client communication, email drafting, follow-up | Sonnet |
| **Revenue Hunter** | Sales outreach, lead nurturing, pricing strategy | Sonnet |
| **Documenter** | Keeps brain/ and memory/ files current after sessions | Haiku |
| **Git Ops** | Commits, PRs, branch management | Haiku |

### Tier 3: Specialized (Add When Needed)

| Agent | Primary Function | Model Tier |
|-------|-----------------|------------|
| **Content Creator** | Social posts, scripts, marketing copy | Sonnet |
| **Researcher** | Web research via Playwright, API documentation lookup | Sonnet / Haiku |
| **Workflow Builder** | n8n automation creation and management | Sonnet |
| **Explorer** | Read-only codebase navigation and analysis | Haiku |

### Model Tier Selection

The model tier decision is a cost-performance tradeoff. Most tasks don't need the most expensive model.

| Tier | Use When | Cost |
|------|----------|------|
| **Opus** | Architectural decisions, complex cross-system planning, anything where a wrong decision has large downstream consequences | High — 5-10x Sonnet |
| **Sonnet** | Standard implementation, code review, content creation, most operational tasks | Medium — the default |
| **Haiku** | Simple lookups, formatting tasks, logging, routing decisions | Low — 10x cheaper than Sonnet |

💡 **PRO TIP:** The Architect uses Opus for initial system design — worth the cost because architecture mistakes compound. The Coder uses Sonnet because most implementation tasks are well-defined once the plan exists. The Documenter uses Haiku because it's literally just formatting and writing what happened. Match the model to the cognitive demand of the task.

---

## The Delegation Matrix

The delegation matrix is the routing table that maps task signals to agents. It lives in AGENTS.md and is referenced by CLAUDE.md.

When a task comes in, the agent looks for signal words that indicate which specialist to engage:

| Task Signal | Agent | Trigger Words |
|-------------|-------|---------------|
| System design, new feature architecture | Architect | "design", "architecture", "schema", "how should we structure" |
| Feature breakdown into steps | Planner | "/plan-feature", "break down", "implementation plan" |
| Writing code, bug fixes | Coder | "/execute", "implement", "write the code for", "fix" |
| Code quality, security | Reviewer | "/review", before any commit |
| Error investigation | Debugger | "bug", "error", "not working", "broken" |
| Client emails, professional communication | Chief of Staff | "email to", "draft", "respond to", client name |
| Sales, pricing, lead follow-up | Revenue Hunter | "lead", "prospect", "pricing", "close" |
| Social media | Content Creator | "post", "tweet", "content for" |
| Web browsing, research | Researcher | "research", "what does", "find information about" |
| n8n workflows | Workflow Builder | "workflow", "automation", "n8n" |
| Git operations | Git Ops | "commit", "push", "PR", "branch" |

The routing is not automatic in Claude Code — you read the signal words and adopt the relevant agent's mindset and principles. The agent file (`agents/reviewer.md`, `agents/debugger.md`, etc.) defines exactly how that specialist thinks.

---

## Agent Communication Patterns

Agents coordinate through shared files — the same files that form the intelligence layer of your command center.

### Pattern 1: The Handoff Document

One agent produces a structured artifact that the next agent consumes.

```
Planner produces: .agents/plans/2026-03-18-client-dashboard.md
  → Numbered steps, file paths, code examples, test criteria

Coder reads: .agents/plans/2026-03-18-client-dashboard.md
  → Executes step by step
  → Marks steps complete as it goes

Reviewer reads: git diff origin/main...HEAD
  → Runs code review skill
  → Produces code-review-report.md

Git Ops reads: code-review-report.md
  → If APPROVED: commits and creates PR
  → If BLOCKED: surfaces issues to CC
```

### Pattern 2: Shared State Files

Multiple agents read from and write to the same state files. The discipline here is important: every write must be complete and consistent, because the next agent to read may be a different AI on a different device.

```
SESSION_LOG.md structure:
  ### [DATE] — [AGENT] via [INTERFACE]
  **Focus:** [Task]
  **Done:** [Specific actions]
  **Files:** [Changed files]
  **Next:** [What should happen next]

Any agent picking up reads this and knows exactly where to start.
```

### Pattern 3: Database Coordination

For cross-session, cross-device state that can't live in files (real-time updates, concurrent access, structured queries), agents write to and read from Supabase.

```sql
-- agent_traces: every significant action logged
INSERT INTO agent_traces (session_id, action, resource, outcome, metadata)
VALUES ('session-abc', 'db_read', 'client_records', 'success', '{"rows": 15}');

-- agent_state: current operational state
INSERT INTO agent_state (agent_id, status, current_task, last_updated)
VALUES ('bravo', 'active', 'building dashboard', now())
ON CONFLICT (agent_id) DO UPDATE SET
  status = EXCLUDED.status,
  current_task = EXCLUDED.current_task,
  last_updated = now();
```

---

## Cross-AI Sync: Making Three AIs Work Together

You have three AI interfaces available: Claude Code (Bravo), Gemini CLI, and Anti-Gravity IDE. They run in separate processes with separate context windows. Left unmanaged, they will contradict each other, repeat work, and diverge on ground truth.

The sync protocol prevents this.

### What "Sync" Actually Means

Sync means: after every session in any AI, the shared state files (STATE.md, ACTIVE_TASKS.md, SESSION_LOG.md) are updated so any AI starting a new session has perfect current context.

```
Session flow:
  1. CC opens Claude Code, asks Bravo to build a feature
  2. Bravo builds the feature, updates STATE.md + SESSION_LOG.md
  3. CC closes Claude Code, opens Gemini for a quick question
  4. Gemini reads STATE.md — knows exactly what Bravo just did
  5. Gemini answers the question, notes it in SESSION_LOG.md
  6. CC opens Anti-Gravity to review a file
  7. Anti-Gravity reads SESSION_LOG.md — sees both previous sessions
```

Without sync: Gemini doesn't know what Bravo built. Anti-Gravity doesn't know what Gemini said. Three separate realities.

With sync: one shared reality, three interchangeable interfaces.

### The RULE 0 Pattern

The most critical rules in CLAUDE.md — the ones that prevent cross-AI desync — are designated as RULE 0 because they are non-negotiable and apply to every single interaction:

```markdown
### RULE 0: CONTINUOUS STATE SYNC (NON-NEGOTIABLE)

After EVERY inquiry or action, update:
  - brain/STATE.md
  - memory/ACTIVE_TASKS.md
  - memory/SESSION_LOG.md

You cannot wait until the end of the session.
If CC switches to Gemini on the next prompt, they must have
up-to-the-second context.
```

This rule is enforced before any other consideration.

---

## The AGENTS.md Registry

AGENTS.md is the complete registry of all agents in your system. Every AI interface references it. It serves three functions:

1. **Discovery** — what agents exist and what they do
2. **Routing** — which tasks map to which agents
3. **Principles** — how each agent thinks and what constraints it operates under

### Agent Definition Format

```markdown
### [N]. [Agent Name] ([Role])

- **Model Tier:** [Opus/Sonnet/Haiku] — [usage guidance]
- **File:** `agents/[agent-name].md`
- **Purpose:** [One sentence — what this agent does]
- **Principles:** [3-5 bullet points — how it thinks, what it never does]
```

The agent file (`agents/[name].md`) contains the full system prompt for that specialist. When you adopt that agent's mindset, you're loading that file's principles into your operating mode.

---

## Conflict Resolution

What happens when two agents produce contradictory outputs, or when an agent disagrees with what a previous agent did?

### Rule 1: Recency Wins for State

The most recently written state file is ground truth. If SESSION_LOG.md says a task is complete and ACTIVE_TASKS.md still shows it as in-progress, the SESSION_LOG.md entry is more current — update ACTIVE_TASKS.md to match.

### Rule 2: Hierarchy for Decisions

```
CC's explicit instruction > Architect's recommendation > Bravo's judgment
```

No agent overrides a direct CC instruction. The Architect's decisions (documented in DECISIONS.md) take precedence over any single agent's in-session judgment. Individual agent judgment fills the gaps.

### Rule 3: Human Gate for Genuine Conflicts

When two agents reach opposite conclusions on a judgment call (architecture, business logic, security tradeoff), surface the conflict to CC with a clear statement of each position. Don't resolve it unilaterally.

```
"Bravo recommends approach A because [reason].
Gemini recommended approach B because [different reason].
This is a judgment call. Which do you prefer?"
```

---

## 🔥 EXERCISE: Create an AGENTS.md Registry

Build out your own AGENTS.md registry with 5 specialized agents tailored to your business.

**Step 1:** Choose your 5 agents from the roster above. Pick the ones most relevant to your current operations.

**Step 2:** For each agent, define:
- Model tier and when to use it
- Purpose (one sentence)
- 3-5 principles (how it thinks)
- The trigger signals that activate it

**Step 3:** Build the delegation matrix — a table mapping task signals to agents.

**Step 4:** Write a RULE 0 for your CLAUDE.md that enforces state sync across all three of your AI interfaces.

**Deliverable:** A complete AGENTS.md file with 5 agents, a delegation matrix, and a RULE 0 in your CLAUDE.md. This file should be operable — another AI reading it should be able to route tasks correctly without additional explanation.

---

## 🧠 KEY TAKEAWAY

Specialized agents beat general agents because specialization produces better output, parallel execution produces faster output, and independent review produces more reliable output. The delegation matrix is the router. The shared state files (STATE.md, SESSION_LOG.md, ACTIVE_TASKS.md) are the communication bus. Cross-AI sync turns three separate tools into one coordinated system. The AGENTS.md registry is the governance document that makes all of it work across interfaces, sessions, and team members.

---

**Next:** [Lesson 3 — Real-Time Monitoring & Dashboards](../lesson-03-monitoring/LESSON.md)
