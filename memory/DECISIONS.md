---
tags: [decisions, architecture]
---
# DECISIONS LOG
> Architectural and technical decisions with rationale. Use ISO 8601 dates.

> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[brain/DASHBOARD]]

---

### 2026-02-27 — Multi-Agent Architecture (3-Tier)
**Context:** CC uses multiple AI interfaces (Claude Code, Gemini CLI, Antigravity IDE). Needed a unified system where all agents share the same brain.
**Options:**
1. Separate instruction sets per agent — causes drift and inconsistency
2. Single shared brain with per-agent entry points — consistent, scalable
3. Centralized API orchestrator — over-engineered for current needs
**Decision:** Option 2. Three entry points (CLAUDE.md, ANTIGRAVITY.md, GEMINI.md) all referencing shared brain/ and memory/ as the single source of truth.
**Consequences:** All agents share memory, tasks, patterns. Any agent can pick up where another left off.

### 2026-02-27 — Playwright as Sole Web Research Tool
**Context:** Previously had Brave Search + Fetch + Playwright. Brave Search was deprecated, Fetch was redundant.
**Options:**
1. Keep all three — wastes MCP slots, confusing routing
2. Playwright only — handles all web research
3. Replace with WebSearch native tool — limited vs full browser automation
**Decision:** Option 2. Playwright handles all web research. Removed Brave Search and Fetch references.
**Consequences:** Simpler MCP routing. One tool for all web research.

### 2026-02-27 — .env.agents as Centralized Secret Store
**Context:** Multiple agents need API keys. Keys were scattered across MCP configs.
**Options:**
1. Per-MCP config files with inline keys — scattered, hard to rotate
2. Single .env.agents file — centralized, gitignored, one place
3. OS-level environment variables — hard to manage across interfaces
**Decision:** Option 2. `.env.agents` in project root, protected by `.gitignore`.
**Consequences:** All agents know where to find keys. Key rotation is one file edit.

### 2026-04-04 — Content Pipeline: Codex for Images, Karaoke Captions
**Context:** CC needs a fully automated content pipeline for video editing, image generation, and distribution. No new API keys — everything through existing subscriptions.
**Options:**
1. Use Gemini's image generation API — requires new API key and integration
2. Use Codex (OpenAI) for images — already authenticated via ChatGPT subscription
3. External image gen service (Runway, Pika) — adds complexity and cost
**Decision:** Option 2. Codex handles all image generation via `codex-companion.mjs`. Captions use karaoke-style (MrBeast format) with word-by-word highlighting synced to Whisper timestamps.
**Consequences:** Zero new API keys. Image generation delegated to Codex, stays within dual-AI architecture (Bravo for orchestration + video editing, Codex for images). Karaoke captions are the proven viral format for scroll-stopping engagement.

---
