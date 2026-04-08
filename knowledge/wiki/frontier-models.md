---
tags: [knowledge, models, frontier, mythos, preparation]
last_updated: 2026-04-08
confidence: 0.91
---

# Frontier Models — Mythos, Competitors, and AOS Preparation

> [[knowledge/index]] | [[knowledge/wiki/tech-stack]] | [[brain/CAPABILITIES]]

## Claude Mythos (Confirmed March 27, 2026)

**Status:** Preview only — restricted to ~52 organizations via Project Glasswing. NOT available via public API. Polymarket: 45% probability of public release by June 30, 2026. Anthropic says "a future Claude Opus model will introduce safeguards, eventually enabling safer broader deployment of Mythos-class capabilities."

**Internal codename:** Capybara

**Key benchmarks (Mythos Preview vs Opus 4.6):**

| Benchmark | Mythos | Opus 4.6 | Delta |
|-----------|--------|----------|-------|
| SWE-bench Verified | 93.9% | 80.8% | +13.1 |
| SWE-bench Pro | 77.8% | 53.4% | +24.4 |
| SWE-bench Multimodal | 59.0% | 27.1% | +31.9 (2x+) |
| Terminal-Bench 2.0 | 82.0% | 65.4% | +16.6 |
| GPQA Diamond | 94.6% | 91.3% | +3.3 |
| HLE (with tools) | 64.7% | 53.1% | +11.6 |
| BrowseComp | 86.9% | 83.7% | +3.2 (4.9x fewer tokens) |
| USAMO 2026 | 97.6% | 42.3% | +55.3 |
| Cybersecurity vuln reproduction | 83.1% | 66.6% | +16.5 |

**Why it matters for the AOS:**
- SWE-bench Multimodal doubling = can understand screenshots, diagrams, UI mockups natively
- 4.9x token efficiency on BrowseComp = Skool/Instagram browser loops cost 80% less
- USAMO +55 points = mathematical reasoning for financial modeling, forecasting
- Terminal-Bench +16.6 = better at autonomous shell operations (our entire CLI tool stack)

**Sources:** Fortune (March 26, 2026), The Decoder, officechai.com, TechCrunch (April 7, 2026), Anthropic.com/glasswing

## Competitor Landscape (April 2026)

| Model | Strengths | Weakness |
|-------|-----------|----------|
| GPT-5.4 (OpenAI) | 100% AIME math, 55.6% SWE-bench Pro | Prose quality, no MCP |
| Gemini 3.1 Pro (Google) | 77.1% ARC-AGI-2, cheapest API | Agent tooling immature |
| Claude Opus 4.6 (Anthropic) | Best prose, MCP ecosystem, Agent SDK | Math reasoning behind GPT-5.4 |
| Grok 4 (xAI) | Real-time X/Twitter data | Limited availability |
| Claude Mythos | Beats all on shared benchmarks | Not publicly available |

**The AOS multi-model approach (Claude + Gemini + Codex) is already aligned with the industry shift toward heterogeneous multi-model deployment.**

## Claude Code 2.0 Features (Shipped Q1 2026)

- **Remote Tasks** — Cloud-hosted agents that run on Anthropic infra, even when laptop is off. Cron scheduling built-in.
- **AutoMemory** — Claude automatically writes .claude/skills/ rules from observed coding habits
- **1M token context** — GA for Max/Team/Enterprise (no beta header)
- **Agent Teams** — Native parallel subagents (enabled in AOS)
- **Voice Mode** — 20 languages, spacebar activate
- **Computer Use** — Research Preview for Mac desktop control
- **Background Agents** — Parallel sub-tasks via Git Worktree isolation

## Claude Agent SDK

Python: `claude-agent-sdk` v0.1.48. TypeScript: `@anthropic-ai/claude-agent-sdk` v0.2.71.
Same agent loop, tools, and context management as Claude Code, packaged as a library.
Supports Bedrock, Vertex AI, Azure AI Foundry deployment targets.
All existing CLAUDE.md, Skills, and Commands work inside SDK-spawned agents via `settingSources: ['project']`.

## MCP Protocol Evolution

- 97 million installs (March 25, 2026)
- Donated to Agentic AI Foundation (Linux Foundation) — now vendor-neutral
- 5,800+ community servers, 10,000+ in production
- Coming: namespace isolation (scope tools per agent), standardized agent handoff, streaming (Q3 2026)

## AOS Preparation Actions (Ranked by Impact)

1. **Model Config Abstraction** — Read model names from .env.agents, not hardcoded. One env var change = instant Mythos upgrade.
2. **Migrate Daemons to Agent SDK** — Skool engine, Instagram engine, scheduler → Agent SDK query() loops with session persistence.
3. **Namespace-Scoped Subagent Toolsets** — Explicit allowedTools in .claude/agents/ definitions. Pre-empts MCP namespace isolation.
4. **1M Context Cost Guardrail** — context_manager.py should estimate token cost before T3 loads, log against cost_tracker.py budget.
5. **Remote Tasks Migration** — Move 12 cron jobs from PM2/Windows Task Scheduler to Claude Code /schedule Remote Tasks.
6. **Ingest This Research** — This wiki page exists for exactly this purpose.

## Remote Tasks Migration Plan (When Ready)

The following daemons/cron jobs currently run on local infrastructure (PM2 / Windows Task Scheduler).
When CC is ready, these can migrate to Claude Code Remote Tasks for cloud execution.

**DO NOT migrate yet — document only. Current setup works. Migrate when reliability issues arise or when Mythos access requires cloud execution.**

| Current Process | Infra | Remote Task Equivalent |
|----------------|-------|----------------------|
| Skool Engine (`skool_engine.py daemon`) | PM2 | `/schedule` with 5-min cron: scan posts, generate replies |
| Instagram Engine (`instagram_engine.py daemon`) | PM2 | `/schedule` with 10-min cron: check DMs, auto-reply |
| Skool Watchdog (`skool_watchdog.py`) | Windows Task Scheduler | `/schedule` with 5-min cron: health check |
| Scheduler (`scheduler.py`) | PM2 | Replace entirely — Remote Tasks IS a scheduler |
| 12 Cron Jobs (`cron_engine.py`) | Supabase-backed | Each becomes a separate `/schedule` entry |

**Migration prerequisites:**
1. Claude Code Max subscription (Remote Tasks requires it)
2. GitHub repo access configured for Remote Tasks
3. Test one non-critical job first (e.g., Skool Watchdog)
4. Verify webhook/notification delivery works
5. Keep PM2 as fallback for 2 weeks during migration

**Agent SDK alternative:** For more control, wrap daemons as Agent SDK `query()` loops with session persistence. This gives full tool access + hook lifecycle but still runs on CC's hardware.

## Model Config (.agents/config.toml)

```toml
# Change these when Mythos API access opens — all scripts read from here
model = "claude-opus-4-6"                          # Lead architect (Bravo)
fast_model = "claude-sonnet-4-6"                   # Daemons, quick tasks
extraction_model = "claude-haiku-4-5-20251001"     # Mem0, low-cost high-volume
```

Scripts that read these: skool_engine.py, instagram_engine.py, mem0_tool.py.
All scripts fall back to hardcoded defaults if config is missing — zero breaking changes.
Credentials stay in `.env.agents`. Model config stays in `.agents/config.toml`.

## Obsidian Links
- [[knowledge/index]] | [[knowledge/wiki/tech-stack]] | [[knowledge/wiki/revenue-model]]
- [[brain/CAPABILITIES]] | [[brain/AGENTS]] | [[brain/STATE]]

Last updated: 2026-04-08
