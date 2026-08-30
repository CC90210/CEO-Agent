---
description: "Routes tasks inline or to sub-agents by 6-dimension risk matrix; governs tool choice, delegation scope, and agent-layer selection"
tags: [orchestration, governance, routing, critical, delegation]
last_updated: 2026-08-22
freshness_threshold_days: 30
verified: 2026-08-22
---
# ORCHESTRATION — Capability Governance & Routing Integrity

> This document exists because of two critical failures: (1) the agent tried to use an MCP connector for Gmail instead of the CLI tool built for that purpose, and (2) the agent treated "delegate to a sub-agent" as if file count alone was the deciding variable, missing risk and blast radius. Both must never happen again.
> **Read this when:** adding new tools, spawning sub-agents, debugging routing failures, onboarding new capabilities, or deciding delegate-vs-inline on any non-trivial task.

---

# PART 1 — DELEGATION & ORCHESTRATION PROTOCOL (V5.7, 2026-04-21)

> **Research synthesis:** 2026 Anthropic Claude Code sub-agent docs · wshobson/agents architecture · Dicklesworthstone/claude_code_agent_farm file-lock pattern · Dicklesworthstone/mcp_agent_mail async inbox · steipete/claude-code-mcp Boomerang pattern · academic papers on MCP+A2A protocols (arXiv:2601.13671), HALO DAG dependencies (arXiv:2505.13516), multi-agent incident response (arXiv:2511.15755) · adversarial review from Codex (task-mo95n14y-fi5aws).

## The Core Question

For any non-trivial task, answer in order:

```
1. Can I do this INLINE in <3 tool calls with high confidence?          → DO INLINE
2. Is the task domain-specialized enough that a persona fits?           → SPAWN SUB-AGENT
3. Are there 2+ INDEPENDENT queries with no shared state?               → SPAWN PARALLEL
4. Is this backend-heavy, adversarial review, or a second opinion?      → DELEGATE TO CODEX
5. Would this flood my main context with logs/files I won't reference?  → SPAWN SUB-AGENT (isolation)
6. Is this trivial, conversational, or time-critical (<30s response)?   → DO INLINE (spawn overhead > task)
```

## Risk-Weighted Routing (replaces file-count tiering)

**Old mental model** (deprecated): classify by file count → TRIVIAL/SIMPLE/MODERATE/COMPLEX/ARCHITECTURAL.
**Why deprecated:** a 1-file Stripe webhook edit is more dangerous than a 10-file CSS cleanup.

**New model:** weight the task across 6 dimensions, route to the highest-risk-tier output.

| Dimension | Low (1) | Medium (2) | High (3) |
|-----------|---------|------------|----------|
| **Risk** | Idempotent, reversible | Mutates state, recoverable | Irreversible (DB drop, force push, secret rotation) |
| **Ambiguity** | Clear spec | Needs 1 clarifying Q | Multi-hypothesis — needs LATS / hyperthink |
| **Blast radius** | Local file | Single service | Cross-service / client-facing / billing |
| **Domain specialization** | General coding | 1 domain (frontend, SQL) | Deep specialist (security, tax, compliance) |
| **Expected file count** | 1-2 files | 3-5 files | 6+ files |
| **Verification cost** | Run once | Smoke test suite | Full test suite + manual review |

**Routing rule:** if any dimension scores 3 → mandatory reviewer gate. If 2+ dimensions score 3 → Codex adversarial-review before ship. If risk=3 AND blast_radius=3 → CC approval required, no autonomous action.

## Layer Selection Matrix

Bravo has four distinct sub-agent layers. Using the right one is non-obvious:

| Layer | Location | Best Use | Don't Use For |
|-------|----------|----------|---------------|
| **`agents/`** (canonical) | 13 file-based Bravo personas | Recurring, mature operations (writer, reviewer, debugger, git-ops, revenue-hunter, chief-of-staff). Full Decision Autonomy + Quality Gates + Anti-Patterns spec. | One-shot specialist work — use `.claude/agents/` instead |
| **`.claude/agents/`** (native) | 6 Claude Code auto-discovered | One-shot spawns Claude Code triggers by frontmatter match (architect, code-reviewer, content-writer, debugger, researcher, security-reviewer) | Anything where you need Bravo's Decision Autonomy + Quality Gates — use `agents/` |
| **`agents/voltagent/`** (drop-in) | 5 community personas | Domain coverage where Bravo doesn't have its own yet (security-auditor, competitive-analyst, market-researcher, api-designer, code-reviewer-voltagent) | Work already covered by `agents/` canonical — avoid duplicate role invocation |
| **Codex** (external) | `codex-companion.mjs` | Backend-heavy implementation, adversarial review, second opinion, parallel work while Bravo stays on frontend/business | Frontend/UI, content/brand, memory writes, MCP-dependent tasks. Per CLAUDE.md Rule 8. |

**Duplicate-role alert:** `agents/reviewer.md`, `.claude/agents/code-reviewer.md`, and `agents/voltagent/code-reviewer.md` all exist. Default: use `agents/reviewer` for Bravo's standard pre-commit gate. Use Claude Code native `code-reviewer` only when spawned from a Task tool. Use voltagent version only for independent second-opinion code review.

## Parallel Orchestration (DAG pattern)

**When to parallel:** 2+ tasks that are fully independent (no shared files, no dependent output). Example from 2026-04-21: orphan audit + wiring audit fired simultaneously, each scanned different concerns, no merge conflict.

**When NOT to parallel:** anything where task B needs output from task A, or both touch the same files (merge conflict risk).

**The DAG pattern:**
1. Build a dependency graph: nodes = tasks, edges = output→input dependencies
2. All leaf nodes (no dependencies) can fire in parallel
3. Each downstream node waits for its upstream nodes to reach terminal success
4. Use file ownership locks (one agent writes a given file at a time) — `tmp/agent_locks/<file-hash>.lock`

**Hard limits (enforced by `.agents/config.toml`):**
- Max 4 concurrent agents (coordination overhead dominates above this)
- Max 3 parallel writers on the SAME codebase (beyond = git merge hell)
- Orchestrator (Bravo) owns the final merge phase — never a sub-agent

**When concurrent config values conflict (as they currently do in `.agents/config.toml:86` vs `:189`): DEFAULT TO THE LOWER NUMBER.** Resolved value: 3 parallel writers max, 4 total concurrent (includes read-only agents).

## Sub-Agent Handoff Contract (every spawn MUST include)

```
1. GOAL         — One sentence: what to accomplish
2. CONTEXT      — Relevant file paths + prior findings (no re-explaining the codebase)
3. SCOPE        — What's in, what's out, hard boundaries
4. OUTPUT SHAPE — What structure of response the orchestrator expects (see Result Schema)
5. BUDGET       — Word count, time limit, or tool-call cap
6. NO-GO ZONES  — What the receiving agent MUST NOT touch (e.g., "do not edit any .env* file")
7. SUCCESS CRITERIA — How the orchestrator will validate the result
```

Source: OpenAI Agents SDK handoff spec + multi-agent incident response paper (arXiv:2511.15755). Handoff contracts drive actionable-recommendation rate from 1.7% (single-agent) to 100% (multi-agent with explicit contracts).

## Sub-Agent Result Schema (every return MUST match)

```yaml
findings: []           # What was discovered (claims + evidence)
changed_files: []      # Absolute paths to every file modified
tests_run: []          # Commands + pass/fail status
risks: []              # Anything the orchestrator should know before acting
confidence: 0-100      # Agent's own confidence in the result
next_actions: []       # Concrete follow-ups the orchestrator should schedule
```

**Why standardized:** today's session (2026-04-21) exposed the problem — the first orphan audit agent was wrong on 3 claims (voltagent files flagged as orphans, send-gateway skill flagged as orphan, CROSS_AGENT_AWARENESS flagged as redundant). Without a structured `confidence` + `next_actions` return, Bravo almost acted on false positives. The schema forces every agent to self-report uncertainty.

## Validator Pattern (Planning → Execution → Validation)

For any complex multi-agent operation, the flow is 3 phases, not 2:

```
1. PLANNING   (Sonnet / Bravo) — decompose task, assign sub-agents, build DAG
2. EXECUTION  (Haiku where deterministic, Sonnet where reasoning) — sub-agents run
3. VALIDATION (Haiku validator subagent, NEW) — scores results against success criteria BEFORE surfacing to CC
```

**The Validator is a read-only Haiku agent** (`.claude/agents/validator.md`) that receives:
- The original task success criteria
- Each sub-agent's Result Schema output
- The list of changed files

It returns: `validation_score` (0-100) and `failure_reasons[]`. If `validation_score < 70`, Bravo re-runs the failing step before reporting to CC.

### How Bravo Invokes the Validator (MANDATORY after these triggers)

Spawn via Claude Code Task tool with `subagent_type: validator` after:
1. Any **parallel sub-agent spawn** (2+ agents ran concurrently)
2. Any **Codex task** that reports changed files (check via `codex-companion.mjs result <id>`)
3. Any operation scoring **risk=3 or blast_radius=3** per §Risk-Weighted Routing
4. Before running `/ship`, `/commit`, or any destructive skill

**Example invocation:**
```
Task: validator
Prompt: |
  Validate the recent parallel orphan-audit + wiring-audit spawn.
  
  GOAL: Find orphans and broken wiring in the knowledge graph.
  SUCCESS CRITERIA: Every flagged orphan has zero inbound links; every
  flagged missing-script is actually absent from docs.
  SCOPE: brain/, memory/, skills/, scripts/, agents/
  
  Sub-agent result A (orphan audit):
    findings: ["agents/voltagent/* are orphans (5 files)", ...]
    changed_files: []
    confidence: 72
  
  Sub-agent result B (wiring audit):
    findings: ["skills/verticals missing SKILL.md", ...]
    changed_files: []
    confidence: 88
  
  Score both. Recommend: ship | rerun | escalate.
```

**Do NOT invoke validator for:** trivial inline work, single-file edits you verified yourself, pure read operations.

**Precedent:** wshobson/agents uses this pattern across 112 agents. Anthropic's own Claude Code Design Space Paper (arXiv:2604.14228) names its absence the "Observability-Evaluation Gap" — the #1 blind spot in typical multi-agent setups.

## Per-Domain Verification Contracts (what "done" means)

`npm run build` + "no secrets committed" is necessary but nowhere near sufficient. Each domain needs its own proof:

| Domain | Required verification before "done" |
|--------|-------------------------------------|
| **API route (Next.js)** | Smoke test: curl the endpoint, expect 200 + expected shape |
| **Supabase migration** | `supabase_tool.py` dry-run OK + apply to local + rollback clean |
| **RLS policy change** | Test query as anon user AND as authed user — both expected outcomes |
| **Webhook handler** | Signature verification test + idempotency replay test |
| **n8n workflow** | Workflow activates without error + test run with pinned data |
| **CLI script** | `--help` renders + primary subcommand run with `--json` |
| **Email/send path** | Dry-run through send_gateway with cooldown check enabled |
| **Stripe integration** | Test mode keys + `stripe_tool.py events` shows expected events |
| **Content publish** | Late/Zernio dry-run + character-count check per platform |

Reviewer sign-off (via `agents/reviewer`) is mandatory before any task touching these domains is marked done.

## Do-Not-Delegate Heuristics

Skip sub-agent spawn for:

- **Trivial edits** — single-line change, known answer, no research needed
- **Conversational continuity** — CC is mid-thought, needs a human-feeling response now
- **Time-critical** — the spawn overhead (parse + context build + execution) exceeds the task cost
- **Sensitive context** — anything involving credentials, client financials, legal drafts
- **Already-known answer** — if Bravo can answer directly, don't wrap it in a sub-agent ceremony

Rule of thumb: **if you could finish the task in 3 tool calls before the sub-agent would even finish its first Read, do it inline.**

## Pre-Orchestration Self-Check

Before firing any parallel / complex sub-agent operation, Bravo runs:

```bash
python scripts/core/self_audit.py
```

If health score < 85 → abort orchestration, clean up drift first. Broken state multiplied across 4 parallel agents = compounded failure.

## The Observability Gap (Anthropic's named blind spot)

Anthropic's Claude Code Design Space Paper (arXiv:2604.14228) explicitly calls out: *"Limited mechanisms detect when agents silently fail or produce degraded outputs without user awareness."*

Bravo's mitigations for this gap:
1. **Validator subagent** (above) — Haiku reads all sub-agent outputs against criteria
2. **Result Schema** (above) — every agent must self-report `confidence` + `risks`
3. **Agent inbox** (SHIPPED 2026-04-21) — `scripts/core/agent_inbox.py` + `skills/agent-inbox/SKILL.md` + `tmp/agent_inbox/`. Bravo reads the inbox on session start per CLAUDE.md Session Protocol. Codex, Atlas, Maven, Aura all post to the inbox for async coordination. **Integration hook pending:** `codex-companion.mjs` should auto-post a completion message after every background task — currently manual, next session's wiring task.
4. **MISTAKES.md tag** — when an agent claim turns out wrong (like the orphan-audit false positives in session 2026-04-21), log tagged `agent-hallucination` so patterns surface over time

## Bravo's Own Context Budget (from Anthropic 2026 docs)

Anthropic's explicit position (from Claude Code Best Practices, 2026): *"If your CLAUDE.md is too long, Claude ignores half of it. Every line must pass the test: 'Would removing this cause Claude to make mistakes?'"*

Current Bravo CLAUDE.md: **120 lines (verified 2026-04-21)** — safely under the 150-line instruction-loss threshold. When adding to CLAUDE.md, enforce the test. Move skill-specific or domain-specific knowledge to skills/ (loaded on demand per Agent Skills protocol).

**Five-layer context compaction pipeline** (loaded transparently by Claude Code when context pressure rises):
1. Budget reduction (truncate old tool results)
2. Snip (remove specific noisy sections)
3. Microcompact (collapse related messages)
4. Context collapse (summarize entire conversation branches)
5. Auto-compact (full reset with carry-forward memory)

**Bravo's duty:** design with this in mind — anything Bravo needs across the pipeline must live in files (brain/, memory/), not in conversation state.

## Skill vs Sub-Agent (mental model correction)

This was previously conflated across `brain/AGENTS.md` and `agents/INDEX.md`. They are NOT the same thing:

- **Skill** = knowledge injection. Loaded on-demand via frontmatter `description` match. Cheap. Lives in main context. Good for workflows, domain knowledge, recipes.
- **Sub-agent** = isolated execution context. Spawned via Task tool or file reference. Expensive. Returns a summary. Good for exploration, specialized reasoning, unbounded-scope research.

**Rule:** if the task needs information → Skill. If the task needs execution + returns a report → Sub-agent.

**Destructive skills carry `disable-model-invocation: true`** in their frontmatter so they only fire on explicit `/skill-name` invocation, not semantic match.

**Flagged as of 2026-04-21 (sweep complete):**
- `skills/send-gateway/SKILL.md` — outbound email/DM chokepoint
- `skills/ship/SKILL.md` — full deployment pipeline
- `skills/gws-gmail-send/SKILL.md` — Gmail send
- `skills/gws-gmail-reply/SKILL.md` — Gmail reply (sends)
- `skills/gws-gmail-reply-all/SKILL.md` — Gmail reply-all (sends)
- `skills/gws-chat-send/SKILL.md` — Google Chat send

**Rule for future skills:** any skill that mutates external state (sends, posts, publishes, pays, deploys, writes to a production DB) MUST have the flag. Read-only knowledge skills (e.g., `supabase-patterns` for SQL guidance) do NOT need the flag.

## 3-Tier Model Routing (wshobson/agents pattern)

Currently most `agents/` are assigned "Sonnet" uniformly. This is cost-suboptimal and correctness-suboptimal:

| Tier | Model | Agents that belong here |
|------|-------|-------------------------|
| **Fast/deterministic** | Haiku 4.5 | git-ops, explorer, documenter, social-publisher, the Validator subagent, project-shepherd, sales-discovery-coach |
| **Reasoning** | Sonnet 4.6 | writer, reviewer, debugger, researcher, chief-of-staff, revenue-hunter, workflow-builder, the V7.2 agency-import bench, most of the fleet |
| **Critical/irreversible** | Opus 4.8 (heavy code) / Fable 5 (top reasoning) | architect (for billing / vendor lock-in / schema migration decisions ONLY), meta-agent. Canonical tier map: `scripts/lib/model_registry.py` — fable-5 is the main-loop standard since 2026-06-12 |

Pattern: Planning (Sonnet) → Execution (Haiku) → Validation (Sonnet or Haiku depending on domain). Opus reserved for decisions where a wrong call is irreversible.

## Tool Frontmatter Tightening (per Anthropic safety pattern)

Every sub-agent's `tools:` frontmatter should be as restrictive as possible. Anthropic's 7-layer safety architecture removes denied tools before the model sees them, so narrower tool visibility = more reliable tool selection.

Current good examples:
- `agents/explorer.md` — `tools: Read, Grep, Glob, Bash` (READ-ONLY by design)
- `agents/git-ops.md` — `tools: Bash(git *)` (git operations only)

Audit candidates (tighten next session):
- `agents/writer.md` — currently has broad access, should scope to `Read, Edit, Write, Bash, Grep, Glob` and explicitly deny `WebFetch, WebSearch` unless needed
- Any agent with `tools: *` — replace with explicit list

---

# PART 2 — THE IRON LAW OF ROUTING

```
CC says something → Match intent to QUICK_REFERENCE.md → Execute the CLI tool → Verify result
```

**NEVER:**
- Try an MCP connector when a CLI tool exists for the same task
- Ask CC to authenticate anything — if auth fails, switch to CLI
- Guess which tool to use — look it up in QUICK_REFERENCE.md
- Create workaround scripts when a tool already exists

**ALWAYS:**
- Check `brain/QUICK_REFERENCE.md` before executing any external operation
- Use CLI tools (they read `.env.agents` and never break)
- Verify the tool works before telling CC it doesn't

## Tool Hierarchy (Binding Order)

```
1. CLI tools in scripts/     ← PRIMARY (47 tools, all read .env.agents)
2. MCP servers (stateless)   ← SECONDARY (Playwright, Context7, Memory, SeqThink, KG only)
3. Direct API calls          ← LAST RESORT (only if CLI tool doesn't cover the operation)
4. claude.ai MCP connectors  ← NEVER (Gmail, Calendar, Square, Cloudflare — all blocked)
```

## Capability Regression Prevention

### The Problem
When new skills, tools, or knowledge are added, existing capabilities break because:
1. Documentation gets stale (counts wrong, tools missing from tables)
2. Routing instructions conflict across entry points
3. Agent forgets older tools exist and defaults to MCP or hallucination

### The Protocol: Adding New Capabilities

**BEFORE adding anything new, verify existing capabilities still work:**

```
Step 1: INVENTORY — What exists now? (Read QUICK_REFERENCE.md)
Step 2: TEST — Does the new capability conflict with any existing tool?
         Same task → use existing tool, don't duplicate
         Different task → proceed to Step 3
Step 3: ADD — Create the tool/skill/agent
Step 4: REGISTER — Add to ALL routing documents:
         □ brain/QUICK_REFERENCE.md (intent-based routing table)
         □ brain/CAPABILITIES.md (deep reference with full commands)
         □ CLAUDE.md (only if it changes a RULE — keep under 150 lines)
         □ GEMINI.md (if it affects Gemini routing)
         □ ANTIGRAVITY.md (if it affects Anti-Gravity routing)
Step 5: VERIFY — Run the new tool AND 3 related existing tools to confirm no regression
Step 6: SYNC — Update counts in CAPABILITIES.md header
```

### Cross-File Sync Chain (When Adding a CLI Tool)

```
New script in scripts/
  → brain/QUICK_REFERENCE.md    (add to intent table + All CLI Tools list)
  → brain/CAPABILITIES.md       (add to appropriate section + update header counts)
  → Entry points IF routing rules change (CLAUDE.md, GEMINI.md, ANTIGRAVITY.md)
  → memory/SESSION_LOG.md       (log what was added)
```

### Cross-File Sync Chain (When Adding a Skill)

```
New skill in skills/[name]/SKILL.md
  → brain/CAPABILITIES.md       (add to skill category table + update count)
  → CLAUDE.md Skills section    (add to key skills list IF frequently used)
  → brain/QUICK_REFERENCE.md    (add to workflow table IF it has a /command trigger)
```

### Cross-File Sync Chain (When Adding an Agent)

```
New agent in agents/[name].md or .claude/agents/[name].md
  → brain/AGENTS.md             (add to registry + orchestration decision matrix)
  → brain/CAPABILITIES.md       (update agent count)
```

## Routing Ambiguity Resolution

When the same user request could map to multiple tools:

| Ambiguity | Resolution |
|-----------|------------|
| "Send email" | One-off → `google_tool.py` · Sequence → `email_engine.py` |
| "Scrape this page" | Interactive/forms → Playwright MCP · Data extraction → `firecrawl_tool.py` |
| "Post content" | Single post → Maven (`../CMO-Agent/scripts/late_tool.py`) · Full pipeline → Maven (`../CMO-Agent/scripts/content_pipeline.py`) |
| "Check revenue" | Quick MRR → `revenue_engine.py` · Full dashboard → `ceo_dashboard.py` |
| "Search memory" | Structured → markdown files · Fuzzy → `mem0_tool.py` · Graph → Memory MCP |
| "Transcribe audio" | Quick voice note → `scripts/transcribe.py` · Full video pipeline → Maven (`../CMO-Agent/scripts/content_pipeline.py`) |
| "Generate image" | AI generation → Maven (`../CMO-Agent/scripts/codex_image_gen.py`) · Cover art → `generate_covers.py` |
| "Book a meeting" | CC's calendar → `google_tool.py` · Client booking → `booking_engine.py` |

## Daemon-Backed Automations (added 2026-08-22)

A job with a HUMAN WAITING on the other end does not belong behind the shared
scheduler queue. scripts/scheduler.py runs every due job sequentially, so a
conversational reply inherits the latency of whatever batch job ran first —
measured 2026-08-21: the Instagram setter's real interval was ~291s regardless
of its cron expression, and a prospect waited 3m46s for "Yo Wsp".

The pattern (first instance: `bravo-ig-dm` → `ig_dm_daemon.py`):

| Rule | Why |
|---|---|
| Human-waiting work gets its OWN PM2 process | its latency must not depend on the email sweep |
| The cron row stays `is_active=0` FOREVER, seeded with `daemon_backed: "<pm2-name>"` | the daemon refuses to boot while the row is armed — two runners double-message |
| Toggling = `pm2 start/stop <name>`, never the row | the dashboard's daemon-cron-guard enforces this at the API |
| `cron_health_check` watches the PM2 process itself | a row-based scan can never see a daemon die; a non-online process reports as FAILING with the revive command |
| The daemon gates each tick on pyflakes over its imports | it runs the working tree — a half-saved refactor otherwise reaches live prospects in ~20s (happened 2026-08-21, errors=25) |

Batch jobs stay on the scheduler; the queue is fine when nobody is watching a
typing indicator.

## Entry Point Parity

All 3 entry points MUST agree on tool routing:

| Rule | CLAUDE.md | GEMINI.md | ANTIGRAVITY.md |
|------|-----------|-----------|----------------|
| MCPs (stateless only) | Playwright, Context7, Memory, SeqThink, KG | Same | Same |
| CLI-first for everything else | ✓ | ✓ | ✓ |
| Never use claude.ai connectors | ✓ | ✓ | ✓ |
| Route to QUICK_REFERENCE.md | ✓ | ✓ | ✓ |

When updating routing in ANY entry point → update ALL THREE.

## Stress Test Protocol

Run quarterly or after major capability additions:

```bash
# Tier 1: Core tools (must all pass)
python scripts/integrations/google_tool.py test
python scripts/integrations/supabase_tool.py list-tables --project bravo
python scripts/integrations/stripe_tool.py balance
python ../CMO-Agent/scripts/late_tool.py --json accounts
python scripts/integrations/n8n_tool.py list
python scripts/integrations/firecrawl_tool.py search "test"

# Tier 2: Business ops (must all pass)
python scripts/lead_engine.py --json list
python scripts/revenue_engine.py mrr --json
python scripts/ceo_dashboard.py briefing --json

# Tier 3: Count verification
ls scripts/*.py | wc -l  # Should match CAPABILITIES.md header
ls skills/*/SKILL.md | wc -l  # Should match CAPABILITIES.md header
ls .agents/workflows/*.md | wc -l  # Should match CAPABILITIES.md header
```

## Failure Response Protocol

When a tool fails at runtime:

```
1. STOP — Do not ask CC to authenticate anything
2. CHECK — Is there a CLI alternative? (Check QUICK_REFERENCE.md)
3. SWITCH — Use the CLI tool instead
4. LOG — Add to memory/MISTAKES.md with root cause
5. FIX — Update routing docs if the failure reveals a gap
```

## Document Hierarchy

```
CLAUDE.md (120 lines)          ← WHAT rules to follow (decision-relevant only)
  ↓ references
brain/QUICK_REFERENCE.md       ← WHERE to route (intent → tool mapping)
  ↓ deep reference
brain/CAPABILITIES.md          ← HOW to use tools (full commands, schemas, config)
brain/AGENTS.md                ← WHO to delegate to (agent registry + decision matrix)
brain/ORCHESTRATION.md (this)  ← WHY routing works this way (governance + regression prevention)
```

## Obsidian Links
- [[CLAUDE]] | [[brain/QUICK_REFERENCE]] | [[brain/CAPABILITIES]] | [[brain/AGENTS]]
- [[memory/MISTAKES]] | [[memory/PATTERNS]]
