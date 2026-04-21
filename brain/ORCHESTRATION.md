---
tags: [orchestration, governance, routing, critical]
---

# ORCHESTRATION — Capability Governance & Routing Integrity

> This document exists because of a critical failure: the agent tried to use an MCP connector for Gmail
> instead of the CLI tool that was built for this exact purpose. This must never happen again.
> **Read this when:** adding new tools, debugging routing failures, onboarding new capabilities.

## The Iron Law of Routing

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
| "Post content" | Single post → `late_tool.py` · Full pipeline → Maven (`../CMO-Agent/scripts/content_pipeline.py`) |
| "Check revenue" | Quick MRR → `revenue_engine.py` · Full dashboard → `ceo_dashboard.py` |
| "Search memory" | Structured → markdown files · Fuzzy → `mem0_tool.py` · Graph → Memory MCP |
| "Transcribe audio" | Quick voice note → `scripts/transcribe.py` · Full video pipeline → Maven (`../CMO-Agent/scripts/content_pipeline.py`) |
| "Generate image" | AI generation → `codex_image_gen.py` · Cover art → `generate_covers.py` |
| "Book a meeting" | CC's calendar → `google_tool.py` · Client booking → `booking_engine.py` |

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
python scripts/google_tool.py test
python scripts/supabase_tool.py list-tables --project bravo
python scripts/stripe_tool.py balance
python scripts/late_tool.py --json accounts
python scripts/n8n_tool.py list
python scripts/firecrawl_tool.py search "test"

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
