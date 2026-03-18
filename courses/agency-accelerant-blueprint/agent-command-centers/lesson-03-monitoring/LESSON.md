# Lesson 3: Real-Time Monitoring & Dashboards

> **Course:** Agent Command Centers
> **XP Reward: +400 XP** | Running Total: 1,050 XP
> **Level: Architect (L3)** — You can't improve what you can't see.

---

## What to Monitor

Running an AI agent system without monitoring is like running a business without a bank account statement — you hope it's working, but you don't actually know.

Monitoring answers four questions:

1. **Is the system healthy?** (MCPs responding, APIs returning, no auth failures)
2. **Is work actually getting done?** (task completion rate, session frequency)
3. **Is anything breaking?** (error rate, repeated failures, stale memory)
4. **What did the agents do?** (audit trail for clients, debugging, billing reconciliation)

### The Monitoring Hierarchy

| Layer | What to Monitor | Tool |
|-------|----------------|------|
| **Infrastructure** | MCP server health, API auth status, dependency errors | Heartbeat checks |
| **Operations** | Task completion, session activity, agent switching | SESSION_LOG.md + Supabase |
| **Intelligence** | Memory freshness, confidence score decay, pattern validation | Memory audit |
| **Outputs** | Error rates, failed tool calls, repeated mistakes | MISTAKES.md + agent_traces |

---

## The Heartbeat Pattern

A heartbeat is a periodic self-check — a cron job that runs your agent's health checks automatically and alerts you to problems before they become incidents.

The pattern comes from server monitoring. A server "heartbeat" pings `/health` every 60 seconds and fires an alert if it doesn't respond. Agent heartbeats do the equivalent for your AI infrastructure.

### What a Heartbeat Checks

```
HEARTBEAT — runs on schedule (daily minimum, hourly preferred)

Infrastructure Checks:
  [ ] MCP servers: Playwright, Supabase, n8n, Late — each callable?
  [ ] Database: can we read from agent_state table?
  [ ] Authentication: tokens not expired?
  [ ] Git: no unexpected uncommitted changes?

Memory Checks:
  [ ] STATE.md updated within last 24 hours?
  [ ] SESSION_LOG.md has entries from last active session?
  [ ] ACTIVE_TASKS.md has no tasks stale >7 days?
  [ ] No credential rotation overdue in rotation log?

Intelligence Checks:
  [ ] MISTAKES.md — any new entries needing pattern promotion?
  [ ] PATTERNS.md — any PROBATIONARY patterns ready for validation?
  [ ] memory/ files under size thresholds? (SESSION_LOG <200 lines, etc.)
```

### Implementing Heartbeat in n8n

```
n8n Workflow: Agent Heartbeat

Trigger: Cron — every day at 9am

Step 1: HTTP Request → Supabase health check
  URL: {SUPABASE_URL}/rest/v1/agent_state?select=*&limit=1
  Headers: { Authorization: Bearer {ANON_KEY} }

Step 2: IF Supabase request fails
  → Telegram message: "⚠️ Supabase health check failed"
  → Stop

Step 3: Read STATE.md via File Read or Git
  Check: last_updated timestamp

Step 4: IF STATE.md older than 24 hours
  → Telegram message: "⚠️ STATE.md not updated in 24h — agent may be inactive"

Step 5: Check credentials rotation log
  Parse next_rotation_date for each key
  IF any key within 14 days of rotation
  → Telegram message: "📅 Key rotation due: {KEY_NAME} in {N} days"

Step 6: Log heartbeat result to Supabase agent_traces
  action: 'heartbeat', outcome: 'pass' or 'partial', metadata: {checks: [...]}
```

💡 **PRO TIP:** Don't alert on every check failure — you'll start ignoring the alerts. Alert on things that require action. Infrastructure failures require immediate action. Memory freshness warnings can wait until morning. Tune the severity to the response time required.

---

## Session Logging as the Source of Truth

SESSION_LOG.md is the single most valuable file in your intelligence layer. It is the answer to: "what did every agent do, in what order, and what was the outcome?"

### What Makes a Good Session Log Entry

```markdown
### 2026-03-18 — Bravo via Claude Code
**Focus:** PropFlow — checkout bug fix
**Done:**
  - Identified root cause: missing null check on subscription.current_period_end
  - Fixed in /app/api/checkout/route.ts line 47
  - Wrote failing test, confirmed fix passes
  - Committed: bravo: fix — null check on subscription period end
**Files:** app/api/checkout/route.ts, __tests__/checkout.test.ts
**Next:** PR needs review — CC to approve merge
```

A bad session log entry:
```markdown
### 2026-03-18
Did some work on PropFlow.
```

The good entry is something another agent can pick up and continue from. The bad entry is useless for coordination.

### Compressing the Log

SESSION_LOG.md bloats over time. The rule: when it exceeds 200 lines, compress entries older than 14 days into `memory/ARCHIVES/sessions-YYYY-MM.md` and remove them from the active file.

This keeps the context cost of loading the log low while preserving the full history in cold storage.

---

## Supabase as the Monitoring Backend

File-based monitoring works for single-agent systems. When you have multiple agents, multiple interfaces, and potentially multiple people working in the system, you need a database.

Supabase provides the persistent, queryable, real-time monitoring backend.

### Schema: The Monitoring Tables

```sql
-- Every significant agent action
CREATE TABLE agent_traces (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id  TEXT,
    agent       TEXT,                    -- 'bravo', 'gemini', 'antigravity'
    action      TEXT NOT NULL,           -- 'db_read', 'api_call', 'file_write', 'mcp_call'
    resource    TEXT,                    -- table, endpoint, file path
    outcome     TEXT,                    -- 'success', 'error', 'skipped'
    duration_ms INTEGER,                 -- how long the action took
    metadata    JSONB DEFAULT '{}',      -- flexible additional context
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Current state of each agent
CREATE TABLE agent_state (
    agent_id      TEXT PRIMARY KEY,
    status        TEXT,                  -- 'active', 'idle', 'error'
    current_task  TEXT,
    session_id    TEXT,
    last_updated  TIMESTAMPTZ DEFAULT now()
);

-- Heartbeat results
CREATE TABLE heartbeat_logs (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    checks_run   INTEGER,
    checks_passed INTEGER,
    alerts       JSONB DEFAULT '[]',
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Performance over time
CREATE TABLE performance_metrics (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    metric_name  TEXT NOT NULL,          -- 'task_completion_rate', 'mcp_latency_ms'
    metric_value NUMERIC NOT NULL,
    period       TEXT,                   -- 'daily', 'weekly'
    recorded_at  TIMESTAMPTZ DEFAULT now()
);
```

### Querying Your Agent Activity

```sql
-- What did my agents do today?
SELECT agent, action, resource, outcome, created_at
FROM agent_traces
WHERE created_at > now() - interval '24 hours'
ORDER BY created_at DESC;

-- Error rate by action type this week
SELECT action, outcome, count(*) as count
FROM agent_traces
WHERE created_at > now() - interval '7 days'
GROUP BY action, outcome
ORDER BY count DESC;

-- Average action duration by type
SELECT action, avg(duration_ms) as avg_ms, count(*) as total
FROM agent_traces
WHERE duration_ms IS NOT NULL
GROUP BY action
ORDER BY avg_ms DESC;
```

---

## Building a Monitoring Dashboard

A simple dashboard transforms raw Supabase data into a visual overview of your command center's health.

### Stack

```
Next.js (App Router) — the dashboard application
Supabase — data source (direct queries from server components)
Recharts or Chart.js — visualizations
Tailwind CSS — styling
```

### Key Components to Build

**1. Health Status Bar**
```
MCP Health: ● Supabase ● n8n ● Playwright ● Late
```
A row of green/red indicators based on the last heartbeat check.

**2. Activity Feed**
```
14:32 — Bravo wrote 3 files in PropFlow
14:15 — n8n workflow "Lead Follow-up" triggered (success)
09:00 — Heartbeat passed (8/8 checks)
```
A real-time stream of agent_traces entries, most recent first.

**3. Task Completion Gauge**
```
This Week: 8/11 tasks completed (73%)
```
Query ACTIVE_TASKS.md or a tasks table for completion rate.

**4. Error Rate Chart**
```
[7-day sparkline of error count per day]
```
A simple line chart from agent_traces grouped by day and outcome.

**5. Memory Health**
```
STATE.md: Updated 2h ago ✓
SESSION_LOG.md: 147 lines (OK)
MISTAKES.md: 12 entries (OK)
ACTIVE_TASKS.md: 4 in-progress, 2 blocked
```

### Data Fetching Pattern

```typescript
// app/dashboard/page.tsx — Server Component
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export default async function DashboardPage() {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies }
  )

  const { data: recentTraces } = await supabase
    .from('agent_traces')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(20)

  const { data: errorRate } = await supabase
    .from('agent_traces')
    .select('created_at, outcome')
    .gte('created_at', new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString())

  return (
    <main>
      <ActivityFeed traces={recentTraces ?? []} />
      <ErrorRateChart data={errorRate ?? []} />
    </main>
  )
}
```

---

## Alert Patterns in n8n

Three alert workflows cover 90% of what you need to know.

### Alert 1: Failed MCP Detection

```
Trigger: Webhook — fired when agent logs error with action='mcp_call'
Condition: outcome='error' AND same mcp_server 3+ times in 1 hour
Action: Telegram message
  "🔴 MCP failure: {mcp_server} has failed {count} times in the last hour.
   Last error: {metadata.error}
   Check .env.agents for expired credentials."
```

### Alert 2: Stale Memory Warning

```
Trigger: Cron — daily at 8am
Action:
  1. Read STATE.md last_updated timestamp
  2. IF older than 48 hours:
     Telegram: "⚠️ STATE.md is {N} hours stale. Was the last session logged?"
```

### Alert 3: Repeated Error Pattern

```
Trigger: Cron — every 6 hours
Action:
  1. Query MISTAKES.md for entries added in last 7 days
  2. Group by root_cause
  3. IF any root_cause appears 2+ times:
     Telegram: "🔁 Repeated mistake: '{root_cause}' has occurred {N} times this week.
     Consider creating an SOP or automated check."
```

---

## The Weekly Retro: Systematic Review

The weekly retro is the highest-leverage monitoring activity. It runs once per week and produces four scores with improvement actions:

| Dimension | Measures | Score Scale |
|-----------|----------|------------|
| **Shipping Velocity** | Features deployed, commits to app repos | 0-10 |
| **Code Quality** | Build passes, security issues, TypeScript errors | 0-10 |
| **Memory Health** | STATE.md freshness, log completeness, file sizes | 0-10 |
| **Agent Coordination** | Cross-AI sync, duplicate work, contradictory outputs | 0-10 |

Any dimension scoring below 7 generates mandatory improvement actions for the following week. The retro data feeds back into the intelligence layer — patterns become SOPs, repeated mistakes become automated checks.

---

## Self-Healing: Agents That Fix Their Own Problems

Monitoring tells you something is wrong. Self-healing is the agent's ability to detect and fix problems without human intervention.

Five dimensions of self-healing:

| Dimension | Detects | Auto-Fixes |
|-----------|---------|-----------|
| **Memory** | Contradictions, stale facts, bloated files | Compresses logs, removes duplicates |
| **Context** | Outdated APPS_CONTEXT files, stale references | Flags for review |
| **Skill** | Skills with high error rates | Flags for improvement |
| **Infrastructure** | MCP failures, expired tokens | Reports error, suggests fix |
| **Relationship** | CC frustration signals, repeated redirections | Logs reflection, recalibrates |

### The Self-Healing Checklist

Run at end of every session:

```
[ ] Junk files cleaned (no tmp/ files left over)
[ ] Git status clean (no unexpected uncommitted changes)
[ ] Memory consistent (no contradictions between files)
[ ] MCP health noted (failures logged in MISTAKES.md)
[ ] Tasks current (ACTIVE_TASKS.md reflects reality)
[ ] Session logged (SESSION_LOG.md updated)
[ ] Patterns extracted (new patterns/mistakes captured)
[ ] STATE.md updated (reflects post-session reality)
```

💀 **COMMON MISTAKE:** Treating self-healing as a nice-to-have. The value of self-healing compounds — a system that catches and fixes drift weekly accumulates less technical debt than one that only fixes problems when they cause visible failures. Add the checklist to your CLAUDE.md session end protocol.

---

## 🔥 EXERCISE: Set Up Heartbeat and a Basic Dashboard

**Part 1: Heartbeat in n8n**

Build the heartbeat workflow described in this lesson. Include:
1. Supabase health check
2. STATE.md freshness check (>24h triggers alert)
3. Credential rotation check (14-day warning)
4. Telegram notification for any failures
5. Log the heartbeat result to agent_traces

Test it by manually triggering the workflow and verifying the Telegram message arrives.

**Part 2: Basic Monitoring Dashboard**

Create a `/dashboard` route in your command center application. Display:
1. The last 10 entries from agent_traces (activity feed)
2. A count of errors in the last 24 hours
3. A count of current active tasks (from your tasks table or ACTIVE_TASKS.md)

You don't need charts yet — even a simple table of recent agent activity is more valuable than nothing.

**Deliverable:** A working n8n heartbeat workflow with Telegram alerts + a basic dashboard page showing recent agent activity.

---

## 🧠 KEY TAKEAWAY

You cannot improve what you cannot see. The heartbeat pattern catches infrastructure problems before they become incidents. SESSION_LOG.md is the audit trail — it must be written every session or the entire coordination system breaks down. Supabase provides the queryable monitoring backend. Self-healing is what keeps the system from accumulating drift over weeks and months. The weekly retro is the forcing function that converts monitoring data into system improvements. Build monitoring first; everything else depends on knowing whether it's working.

---

**Next:** [Lesson 4 — Autonomous Decision Pipelines](../lesson-04-autonomous-pipelines/LESSON.md)
