---
name: context-optimization
description: Tiered context loading, transcript compaction, cost tracking, and memory aging — inspired by Claude Code's internal harness architecture.
tags: [skill, performance, context]
---

# Context Optimization — Harness-Level Efficiency

> **Source:** Patterns extracted from Claude Code's internal runtime (1,902 TS files, 35 subsystems).
> Claude Code uses 7-stage parallel bootstrap, transcript compaction at 12 turns, and a "simple mode"
> that reduces 184 tools to 3 for lightweight queries. This skill brings those patterns to our system.

## When to Use

- **Every session start** — determine the right context tier before loading files
- **Long sessions (10+ exchanges)** — run compaction check to prevent context bloat
- **Weekly maintenance** — run memory aging scan to detect stale facts
- **After heavy sessions** — log operation costs for optimization visibility

## Pattern 1: Tiered Context Loading

Not every query needs the full 4,944-line context. Match the load to the task.

### Tier Classification

| Tier | When | Files Loaded | ~Lines |
|------|------|-------------|--------|
| **T1 — Minimal** | Status checks, quick lookups, "what's the MRR?" | STATE.md, ACTIVE_TASKS.md | ~185 |
| **T2 — Standard** | Feature work, bug fixes, typical development | T1 + AGENTS.md, CAPABILITIES.md, SESSION_LOG.md | ~780 |
| **T3 — Full** | Architecture, SPARC tasks, complex multi-file refactors | T2 + INTERACTION_PROTOCOL.md, BRAIN_LOOP.md, HEARTBEAT.md, PATTERNS.md, MISTAKES.md | ~4,944 |

### Classification Keywords

**T1 triggers:** status, check, what, how much, MRR, balance, count, list, show
**T2 triggers:** build, fix, implement, create, update, add, modify, debug, test, deploy
**T3 triggers:** redesign, architecture, refactor, migrate, schema, system, overhaul, SPARC, complex

**Rule:** When ambiguous, default to T2. Only escalate to T3 when the task explicitly requires cross-system understanding.

### CLI Usage

```bash
# Check what tier a query needs
python scripts/context_manager.py tier "what's our current MRR?"
# → TIER 1: Load STATE.md + ACTIVE_TASKS.md (~185 lines)

python scripts/context_manager.py tier "build a new Stripe integration"
# → TIER 2: Load standard context (~780 lines)

python scripts/context_manager.py tier "redesign the agent orchestration system"
# → TIER 3: Load full context (~4,944 lines)
```

## Pattern 2: Transcript Compaction

Claude Code compacts transcripts after 12 turns and caps at 8 turns by default. Our equivalent: keep SESSION_LOG.md lean.

### Rules

- **Max active entries:** 10 (configurable in `.agents/config.toml` [context.compaction])
- **Archive after:** 14 days
- **Max lines:** 200 (warning threshold)
- **Archive destination:** `memory/ARCHIVES/sessions-YYYY-MM.md`

### CLI Usage

```bash
# Check if compaction is needed
python scripts/context_manager.py status
# → SESSION_LOG.md: 246 lines (18 entries) — COMPACT NOW

# Preview what would be archived
python scripts/context_manager.py compact --dry-run
# → Would archive 8 entries to memory/ARCHIVES/sessions-2026-03.md

# Execute compaction
python scripts/context_manager.py compact
# → Archived 8 entries. SESSION_LOG.md: 10 entries (120 lines)
```

### When to Trigger

- **Session start:** If `status` shows > 200 lines, compact before loading
- **Memory worker:** Auto-triggers every 30 minutes (`.agents/config.toml` [workers.memory])
- **Manual:** Anytime SESSION_LOG feels bloated

## Pattern 3: Cost Tracking

Claude Code uses a `CostTracker` with label:units per operation. We track CLI tool and MCP costs.

### How It Works

Every CLI tool call and MCP interaction gets a cost entry. This surfaces which operations are expensive so we can optimize or batch them.

### CLI Usage

```bash
# Log an operation cost
python scripts/cost_tracker.py log --label "supabase_query" --units 1 --detail "select from leads"

# View today's costs
python scripts/cost_tracker.py summary --period today

# Check budget alerts
python scripts/cost_tracker.py budget --check

# View session costs
python scripts/cost_tracker.py session
```

### Default Unit Costs

| Operation | Units | Rationale |
|-----------|-------|-----------|
| Supabase query | 1 | Lightweight read |
| Supabase write | 2 | Data mutation |
| Stripe API | 2 | External API call |
| n8n execute | 3 | Workflow execution |
| Zernio post | 2 | Single platform |
| Zernio cross-post | 5 | Multi-platform |
| Playwright session | 5 | Browser resource |
| File edit | 0.5 | Local operation |

### Integration Points

- **Post-operation hooks** should log costs after CLI tool calls
- **Session end** summary includes total cost for the session
- **Weekly retro** can reference cost data for optimization decisions

## Pattern 4: Memory Aging

Claude Code's `memdir` subsystem has `memoryAge.ts` for automated decay. We implement the same exponential decay model.

### Decay Formula

`C(t) = C₀ × e^(-λ × t)`

Where `λ` varies by category:
- **Business facts** (λ=0.02): A fact at 0.9 confidence drops to 0.49 after 30 days
- **Technical facts** (λ=0.015): Same fact stays at 0.57 after 30 days
- **Architectural decisions** (λ=0.005): Same fact stays at 0.77 after 30 days
- **Identity/values** (λ=0): Never decays

### CLI Usage

```bash
# Full decay scan across all memory files
python scripts/memory_aging.py scan

# Find stale facts (not updated in 30+ days)
python scripts/memory_aging.py stale --days 30

# Memory health report with letter grade
python scripts/memory_aging.py health

# Archive old entries (preview first)
python scripts/memory_aging.py archive --dry-run
python scripts/memory_aging.py archive
```

### When to Trigger

- **Weekly:** Run `scan` during `/retro` to catch decaying facts
- **Monthly:** Run `health` for full memory system assessment
- **Session start:** Run `stale --days 30` if making decisions based on remembered facts

## Pattern 5: Deferred Init

Claude Code only loads plugins, skills, MCP prefetch, and session hooks AFTER trust verification. We apply the same principle: don't load heavy resources until the task demands them.

### Heavy Resources (Load On-Demand Only)

| Resource | Trigger | Why Defer |
|----------|---------|-----------|
| Playwright MCP | Browser task detected | Spawns headless Chrome |
| e2e-testing skill | `/e2e` or test command | Launches 3 sub-agents |
| SPARC methodology | COMPLEX+ task routing | Full 5-phase process |
| instagram_engine.py | Instagram task | 70KB script |
| booking_engine.py | Booking task | 53KB script |

### Implementation

The agent should NOT pre-load these resources at session start. Instead:
1. Classify the task tier (Pattern 1)
2. Load only the tier-appropriate files
3. If the task later needs a heavy resource, load it then (just-in-time)

This is already the natural behavior of Claude Code's tool system — tools are lazy-loaded via `ToolSearch`. Our skill files follow the same pattern via `@` imports.

## Config Reference

All settings in `.agents/config.toml`:
- `[context]` — Tier definitions and file lists
- `[context.compaction]` — Compaction thresholds and archive paths
- `[context.deferred]` — Deferred init resource lists
- `[cost_tracking]` — Unit costs and budget alerts
- `[memory_aging]` — Decay rates and thresholds

## Obsidian Links
- [[brain/INTERACTION_PROTOCOL]] | [[brain/BRAIN_LOOP]]
- [[skills/memory-management/SKILL]] | [[skills/background-workers/SKILL]]
- [[memory/SESSION_LOG]] | [[memory/PATTERNS]]
