---
tags: [research, intelligence, architecture]
---

# Deep Research Intelligence Report — 2026-04-06

> Actionable intelligence across 6 research targets. Each finding rated HIGH/MEDIUM/LOW for applicability to Business-Empire-Agent.
> [[brain/STATE]] | [[memory/ACTIVE_TASKS]] | [[memory/SESSION_LOG]]

---

## 1. ANDREJ KARPATHY — LLM Knowledge Bases & Agentic Engineering

### Finding 1A: LLM Wiki Architecture (The "Compiled Wiki" Pattern)

**WHAT:** On April 3, 2026, Karpathy published a GitHub gist (`llm-wiki`) describing a three-layer knowledge base architecture that *bypasses traditional RAG entirely*:

- **Layer 1 — `raw/`**: Immutable source documents (articles, papers, images, datasets). The LLM reads but never modifies these. Obsidian Web Clipper converts web articles to markdown.
- **Layer 2 — `wiki/`**: Markdown files *entirely managed by the LLM*. Contains summaries, entity pages, concept pages, comparisons, and cross-referenced overviews. The LLM "compiles" raw materials into structured knowledge.
- **Layer 3 — Schema (`CLAUDE.md` / `AGENTS.md`)**: Configuration that tells the LLM how the wiki is structured, what conventions to follow, and what workflows to use.

Two critical index files:
- `index.md` — content-oriented catalog with one-line summaries per page, organized by category. The LLM reads this FIRST when answering queries.
- `log.md` — append-only chronological record (e.g., `## [2026-04-02] ingest | Article Title`).

Three core operations:
- **Ingest**: Process one source at a time. LLM reads, writes summaries, updates index, revises entity pages. One source typically touches 10-15 wiki pages.
- **Query**: Search wiki pages, synthesize answers with citations. Good answers get filed back as new pages.
- **Lint**: Periodic health-check for contradictions, stale claims, orphan pages, missing cross-refs.

Karpathy's key quote: "The document's only job is to communicate the pattern. Your LLM can figure out the rest."

**WHY IT MATTERS:** Our Business-Empire-Agent already has a similar structure (brain/, memory/, skills/) but we lack the *compilation* step. Our raw knowledge (session logs, research notes, client data) stays raw. Karpathy's approach would let Bravo *compile* scattered knowledge into structured, query-optimized wiki pages.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Create `knowledge/raw/` directory for dumping articles, research, client notes, market intel
2. Create `knowledge/wiki/` directory where Bravo compiles structured pages
3. Add `knowledge/index.md` (auto-maintained catalog) and `knowledge/log.md` (append-only ingest log)
4. Add an `/ingest` skill that processes raw docs into wiki pages
5. Add a `/lint-knowledge` skill for periodic health checks
6. Modify CLAUDE.md to instruct Bravo to read `knowledge/index.md` before answering research questions
7. Install Obsidian Web Clipper for CC to dump web articles directly into `knowledge/raw/`

### Finding 1B: "Agentic Engineering" Replaces "Vibe Coding"

**WHAT:** Karpathy coined "vibe coding" in Feb 2025, then declared it "passe" in early 2026. The replacement: **Agentic Engineering** — developers write <1% of code directly, instead orchestrating multiple specialized AI agents that plan, implement, and test in parallel. The human role shifts from coder to technical supervisor.

His personal workflow: controls home devices through a single WhatsApp conversation with an agent that orchestrates multiple APIs, reasons about results, and takes compound actions across systems.

**WHY IT MATTERS:** We're already doing this with the Bravo + Codex dual-AI model. Karpathy validates the architecture but suggests going further: more specialized agents, more parallelism, more delegation.

**APPLICABILITY:** **MEDIUM** (already partially implemented)

**HOW TO IMPLEMENT:**
1. Lean into the agent teams feature for parallel execution
2. Consider adding a third AI engine (Gemini) for specific tasks (it's already available via telegram bridge)
3. Create more granular subagent definitions in `.claude/agents/` with specific scopes (one for client research, one for content, one for code)

---

## 2. CLAUDE CODE CREATOR / ANTHROPIC ENGINEERS — Configuration Best Practices

### Finding 2A: Anthropic's Internal Workflow (The "Parallel Sessions" Pattern)

**WHAT:** Anthropic engineers run 5-10 Claude Code instances simultaneously. They use:
- Named worktrees with single-keystroke aliases (`za`, `zb`, `zc`)
- A dedicated "analysis" worktree exclusively for reading logs and running queries
- Writer/Reviewer pattern: Session A implements, Session B reviews with fresh context
- Plan Mode separation: explore first (read files, no changes), then plan, then implement, then commit

Key insight: "A fresh context improves code review since Claude won't be biased toward code it just wrote."

**WHY IT MATTERS:** We run single sessions. Anthropic's own team says multiple parallel sessions is the highest-leverage workflow change.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Create bash aliases for worktree navigation in CC's PowerShell profile
2. Set up a permanent "analysis" worktree for read-only operations
3. Add a `/parallel` skill that spawns writer + reviewer sessions
4. Use `claude --worktree feature-X` for isolated feature work

### Finding 2B: CLAUDE.md Must Be Under 200 Lines

**WHAT:** Official Anthropic guidance: "There's roughly a 150-200 instruction budget before compliance drops off, and the system prompt already uses about 50 of those." For each line, ask: "Would removing this cause Claude to make mistakes?" If not, cut it.

Key rules:
- Prefer *pointers* to *copies* — don't paste code snippets, link to files instead
- Check CLAUDE.md into git so the team contributes
- Use `@path/to/import` syntax for progressive disclosure
- Convert frequently-ignored rules into deterministic hooks
- Use skills (`.claude/skills/`) for domain knowledge that loads on-demand, not every session

**WHY IT MATTERS:** Our CLAUDE.md is currently **extremely long** (hundreds of lines). This is confirmed to degrade performance. Rules get lost in the noise.

**APPLICABILITY:** **HIGH** (critical optimization)

**HOW TO IMPLEMENT:**
1. Audit every line in CLAUDE.md — remove anything Claude already does correctly without the instruction
2. Move domain knowledge to skills (already have 50+, but some rules in CLAUDE.md belong in skills)
3. Convert "must always" rules to hooks (deterministic > advisory)
4. Use `@imports` more aggressively — keep CLAUDE.md as a routing table, not an encyclopedia
5. Target: under 150 lines in the root CLAUDE.md

### Finding 2C: Agent Teams (Official Feature)

**WHAT:** Shipped Feb 2026 with Opus 4.6. Enable with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. Teammates talk to each other, claim tasks from a shared list, share discoveries, challenge each other's findings, and coordinate without the lead acting as intermediary. Uses git worktrees for isolation.

Best use cases: research (multiple agents investigate different aspects), new modules (each agent owns a piece), debugging with competing hypotheses, cross-layer coordination (frontend + backend + tests in parallel).

**WHY IT MATTERS:** This is native multi-agent orchestration built into Claude Code. Could replace our manual Codex delegation for some tasks.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Add `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` to CC's environment
2. Create a `/team` skill that configures agent teams for common patterns (research, feature build, debug)
3. Test on next MODERATE+ feature before full adoption

### Finding 2D: Subagents for Context Isolation

**WHAT:** Anthropic's #1 recommendation for managing context: use subagents for investigation. They explore in a separate context window and report back summaries, keeping the main conversation clean. Define in `.claude/agents/` with markdown frontmatter (name, description, tools, model).

**WHY IT MATTERS:** Our brain/ files are large. Having Bravo read them all fills context fast. Dedicated subagents for specific domains would be more efficient.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Create `.claude/agents/research-agent.md` — read-only codebase exploration
2. Create `.claude/agents/client-health-agent.md` — queries Supabase + Stripe for client metrics
3. Create `.claude/agents/content-agent.md` — handles content pipeline with CC's voice guidelines
4. Delegate via "use the research-agent to investigate X" prompts

---

## 3. NOTEBOOKLM MEMORY ARCHITECTURE

### Finding 3A: Source Grounding (Not Traditional RAG)

**WHAT:** Google engineers deliberately avoid calling NotebookLM "RAG." Their approach is "source grounding" — powered by Gemini models with up to 2M token context windows. Each notebook supports up to 4M words across sources (potentially 25M with internal optimizations). The system creates summaries of each uploaded file and uses those summaries for retrieval, not raw chunking.

Key distinction: NotebookLM creates *summaries per source* as an intermediate layer, then uses those for retrieval. This is closer to Karpathy's "compiled wiki" than to traditional vector-database RAG.

**WHY IT MATTERS:** The summary-as-intermediate-layer pattern is something we could replicate. Instead of raw session logs, compile them into structured summaries.

**APPLICABILITY:** **MEDIUM**

**HOW TO IMPLEMENT:**
1. Already partially doing this with SESSION_LOG.md (structured summaries of work)
2. Add an `/auto-summarize` skill that compresses daily session logs into topic-based summaries
3. Store summaries in `knowledge/wiki/` following the Karpathy pattern

### Finding 3B: Open-Source Alternatives

**WHAT:** Several production-ready open-source NotebookLM alternatives exist:
- **InsightsLM** — Built with Supabase + N8N + React (our exact stack!)
- **Open Notebook** — Supports multiple model providers, wide format support
- **SurfSense** — Two-tiered RAG with hybrid search + rerankers
- **AnythingLLM** — Desktop/Docker, fully offline capable

**WHY IT MATTERS:** InsightsLM uses our exact stack (Supabase + N8N). Could be deployed as an internal knowledge assistant.

**APPLICABILITY:** **MEDIUM** (InsightsLM is HIGH due to stack overlap)

**HOW TO IMPLEMENT:**
1. Clone InsightsLM and evaluate for internal use — it uses Supabase and N8N which we already run
2. Consider deploying as an OASIS AI product offering for clients (knowledge assistant as a service)
3. If client-facing: white-label InsightsLM under OASIS AI branding

---

## 4. OBSIDIAN AS RAG — Vault as Knowledge Base

### Finding 4A: obra/knowledge-graph Plugin (Claude Code Native)

**WHAT:** A Claude Code plugin that turns any Obsidian vault into a queryable knowledge graph. Features:
- Parses vault into untyped graph (files = nodes, wiki links = edges)
- Indexes into SQLite with vector embeddings + full-text search
- 10 operations: semantic search, path finding, community detection (Louvain), bridge nodes (betweenness centrality), central nodes (PageRank)
- **No LLM inside the tool** — pure data infrastructure. The reasoning layer is whatever agent holds the tools.
- Installs as Claude Code plugin — MCP server starts automatically

**WHY IT MATTERS:** Our Business-Empire-Agent IS an Obsidian vault (Rule 6 in CLAUDE.md). This plugin would instantly give Bravo graph-traversal, semantic search, and community detection over our entire knowledge base. It's the missing piece between our vault and intelligent retrieval.

**APPLICABILITY:** **HIGH** (highest-impact single integration)

**HOW TO IMPLEMENT:**
1. Install: `claude plugin add obra/knowledge-graph`
2. It auto-indexes the vault and exposes 10 MCP tools
3. Bravo can then: search semantically, find paths between concepts, detect knowledge communities, identify bridge nodes
4. Use for: "What do we know about client X?", "How does PropFlow connect to our revenue strategy?", "What knowledge gaps exist?"

### Finding 4B: Obsidian Copilot Plugin (In-Vault AI)

**WHAT:** Obsidian plugin with free tier (BYOK) and paid Plus tier. Features:
- Vault QA without pre-building index (optional semantic search mode)
- Multi-model support (OpenAI, Anthropic, Google, Ollama)
- Agent Mode (Plus): autonomous tool calling, long-term memory, time-based queries
- YouTube/web clipper for ingesting content
- Local semantic search engine (Miyo) for desktop

**WHY IT MATTERS:** When CC is working in Obsidian directly (not in terminal), this gives him AI-powered vault search without switching to Claude Code.

**APPLICABILITY:** **MEDIUM**

**HOW TO IMPLEMENT:**
1. Install Obsidian Copilot plugin from community marketplace
2. Configure with Anthropic API key for Claude integration
3. Enable Vault QA mode
4. CC can query the vault from within Obsidian during content creation or planning

### Finding 4C: Obsidian MCP Server for Claude Code

**WHAT:** `obsidian-claude-code-mcp` — MCP server that exposes vault operations to Claude Code via WebSocket. Auto-discovery, file read/write, configurable ports. Alternative: Claudian plugin embeds Claude Code CLI directly in Obsidian sidebar.

**WHY IT MATTERS:** We already have the vault. An MCP server would give Bravo structured access to vault operations (search, create, modify notes) beyond just reading files.

**APPLICABILITY:** **MEDIUM** (obra/knowledge-graph is better for our use case)

---

## 5. TOP CLAUDE CODE POWER USERS — Advanced Configurations

### Finding 5A: awesome-claude-code-toolkit (5,600+ Stars)

**WHAT:** The most comprehensive Claude Code toolkit. Key highlights:
- 135 agents, 35 curated skills, 42 commands, 150+ plugins, 19 hooks
- 12 CLAUDE.md templates optimized for cost reduction (30-60% savings)
- Token optimization via hybrid search (~40% token reduction)
- Session compression via SQLite + full-text search
- "Jarvis" system: runs 24/7 AI ops at $0 extra cost by utilizing idle Claude Max subscriptions
- Multi-wave parallel execution: 14-agent autonomous pipeline across PM, architecture, backend, frontend, QA, security roles

**WHY IT MATTERS:** We have 50 skills and 17 agents. This toolkit could be mined for patterns we haven't thought of. The cost optimization templates alone could save CC money on Claude usage.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Review their 12 CLAUDE.md templates for cost optimization patterns
2. Evaluate their hook implementations (15 production-tested hooks from 160+ hours)
3. Consider adopting their token optimization approach (hybrid BM25 + dense vector search)
4. Look at their `claude-cost-optimizer` plugin for immediate savings

### Finding 5B: everything-claude-code (Hackathon Winner)

**WHAT:** Built at Claude Code Hackathon (Feb 2026). Features:
- 47 agents organized by language and task
- AgentShield security scanning (1282 tests, 102 rules, 5 categories)
- Instinct-based learning with confidence scoring, import/export, evolution
- `/learn-eval` command: extract patterns from sessions into reusable skills
- `/evolve` command: cluster learned patterns into skills
- 5-layer security guard with observer loop prevention

**WHY IT MATTERS:** The `/learn-eval` and `/evolve` pattern is exactly what our Rule 9 (Continuous Self-Improvement) aims to do, but automated. Their instinct-based learning with confidence scoring maps to our [PROBATIONARY] -> [VALIDATED] pattern.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Study their `/learn-eval` implementation and port the pattern extraction logic
2. Automate our Rule 9 — instead of manual PATTERNS.md updates, auto-extract and score
3. Adopt their confidence scoring model for pattern validation
4. Consider integrating AgentShield for security scanning of our configs

### Finding 5C: Fractal Decomposition Pattern

**WHAT:** From the awesome toolkit — breaks goals into predicates, works the riskiest piece first, re-evaluates as it learns. Uses an idempotent state machine with dry run mode.

**WHY IT MATTERS:** More sophisticated than our current task routing (TRIVIAL -> ARCHITECTURAL). Risk-first execution would catch blockers earlier.

**APPLICABILITY:** **MEDIUM**

### Finding 5D: claude-session-restore

**WHAT:** Restores context from previous sessions by analyzing session files and git history. Multi-factor data collection. Handles files up to 2GB. Cross-agent handoff capabilities.

**WHY IT MATTERS:** We rely on memory files (STATE.md, SESSION_LOG.md) for cross-session context. This tool provides automated session restoration.

**APPLICABILITY:** **MEDIUM**

---

## 6. CUTTING-EDGE AI AGENT ARCHITECTURES

### Finding 6A: Mem0 — Universal Memory Layer

**WHAT:** Open-source memory layer (24M+ raised) that sits between app and LLM. Auto-extracts relevant info from conversations, stores it, retrieves when needed. 26% accuracy improvement over OpenAI Memory on LOCOMO benchmark. 91% faster, 90% lower tokens than full-context. Three memory types: vector memory, graph memory, procedural memory.

Key 2026 features:
- Async-first memory writes (eliminates user-facing latency)
- Metadata filtering (scoped queries by structured attributes)
- Reranking layer (second-pass scoring for retrieval precision)
- Actor-aware memories (tracks source provenance in multi-agent systems)

Integrates with 13 agent frameworks, 3 voice integrations, 19 vector store backends. Python and Node.js SDKs. SOC 2 & HIPAA compliant.

**WHY IT MATTERS:** Our memory system is file-based (markdown in memory/). Mem0 would add semantic retrieval, automatic extraction, and multi-agent provenance tracking. The graph memory type would capture relationships between clients, projects, and business entities.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. `pip install mem0ai` and add to `.venv`
2. Create `scripts/integrations/mem0_tool.py` as CLI wrapper (following our CLI-first pattern)
3. Configure with Anthropic as LLM provider, Supabase as vector store backend
4. Hook into session lifecycle: SessionEnd extracts memories, SessionStart loads relevant ones
5. Replace or augment our knowledge graph MCP with Mem0's graph memory
6. Actor-aware memories would distinguish Bravo/Gemini/Codex contributions

### Finding 6B: Letta (MemGPT) — LLM-as-Operating-System

**WHAT:** Three-tier memory architecture inspired by OS design:
- **Core Memory** (always in-context, like RAM): persona, user info, key facts
- **Recall Memory** (searchable conversation history, like disk cache): past interactions searchable via tool calls
- **Archival Memory** (long-term storage, like cold storage): queried via tool calls for deep knowledge

The LLM manages its own memory transitions — it decides what to promote from archival to core, what to archive from core to archival.

**WHY IT MATTERS:** Our current system loads brain/ files at boot (like core memory) but has no formal tiering. Letta's model would let Bravo dynamically manage what's in-context vs. what's archived, reducing context bloat.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Formalize our existing memory into three tiers:
   - **Core** (always loaded): SOUL.md, STATE.md, ACTIVE_TASKS.md (~500 tokens)
   - **Recall** (searchable, loaded on demand): SESSION_LOG.md, DECISIONS.md, PATTERNS.md
   - **Archival** (queried via tool): knowledge/wiki/, memory/ARCHIVES/, old session data
2. Create a `memory_manager.py` script that handles tier transitions
3. Add search tools for recall and archival tiers
4. Modify CLAUDE.md Rule -1 (Context-Aware Loading) to use these formal tiers

### Finding 6C: Anthropic's Multi-Agent Research System

**WHAT:** Anthropic's production architecture:
- Lead agent (Opus 4) analyzes queries, develops strategies, spawns 3-5 subagents (Sonnet 4) in parallel
- Subagents operate synchronously — lead waits for all to complete
- Subagents write structured outputs to filesystem (not passed through conversation)
- Lead saves research plans to external memory before 200K token threshold
- Scaling rules embedded in prompts: simple = 1 agent, comparisons = 2-4 agents, complex = 10+ agents
- 90.2% improvement over single-agent Opus 4 on research evals (15x token cost)

Critical lesson: "Early versions failed because instructions were vague enough that subagents misinterpreted the task."

Tool design insight: Anthropic created a tool-testing agent that "attempts to use the tool and then rewrites the tool description to avoid failures."

**WHY IT MATTERS:** This is the gold standard for multi-agent orchestration from the people who build Claude. Our Bravo + Codex model is simpler but could adopt the filesystem-based output pattern and scaling rules.

**APPLICABILITY:** **HIGH**

**HOW TO IMPLEMENT:**
1. Add scaling rules to our task routing skill: simple (<3 files) = Bravo solo, moderate = Bravo + review, complex = Bravo + Codex parallel, architectural = multi-subagent
2. Have subagents write to `tmp/agent-outputs/` instead of passing results through conversation
3. Add a tool-testing subagent that validates MCP tool descriptions
4. Set a 200K token threshold for saving research plans to external memory

### Finding 6D: Self-Evolving Agent Patterns

**WHAT:** Three cutting-edge approaches:

1. **Voyager Pattern** (from Minecraft research): automatic curriculum that maximizes exploration + skill library for storing/retrieving complex behaviors + iterative prompting for executable code. Skills compound over time.

2. **EvolveR Framework**: offline self-distillation (freeze policy, distill raw trajectories into strategic principles) + online interaction (apply distilled wisdom) + policy evolution (RL-based parameter updates). Closed loop.

3. **OpenAI Self-Evolving Agents Cookbook**: improved version replaces original baseline, becoming foundation for next iteration. Continuous cycle of learning, feedback, optimization.

**WHY IT MATTERS:** Our GROWTH.md already references Voyager-style skill compositionality. These newer frameworks (EvolveR) show how to close the loop: not just extracting patterns, but distilling them into strategic principles and updating the agent's behavior.

**APPLICABILITY:** **MEDIUM-HIGH**

**HOW TO IMPLEMENT:**
1. Our `/evolve` workflow already exists but is manual. Automate: after every 10 sessions, run autoDream to consolidate
2. Add "strategic principles" layer between raw patterns and skills — distilled wisdom that guides behavior
3. Implement confidence decay: patterns that haven't been validated in 30 days get demoted
4. Consider a `/self-distill` skill that reads recent session logs and extracts strategic principles

### Finding 6E: GraphRAG (Microsoft)

**WHAT:** Uses LLMs to extract entities and relationships from text, builds a knowledge graph, performs hierarchical clustering (Leiden technique), generates community summaries bottom-up. Substantial improvement over vector-only RAG for complex reasoning. Now available as open-source Python library.

**WHY IT MATTERS:** Could be applied to our client data, business context, and research notes. Would enable questions like "What connects the primary retainer's community growth to our revenue targets?" that require multi-hop reasoning.

**APPLICABILITY:** **MEDIUM** (valuable but complex to implement)

**HOW TO IMPLEMENT:**
1. The obra/knowledge-graph plugin (Finding 4A) gives us 80% of this benefit with 20% of the effort
2. If we need deeper graph reasoning, evaluate Microsoft GraphRAG library
3. Build a knowledge graph from our brain/ + memory/ files as a proof of concept

---

## PRIORITY IMPLEMENTATION RANKING

| # | Finding | Impact | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | **CLAUDE.md compression to <150 lines** (2B) | Critical | 2-3 hours | DO FIRST |
| 2 | **obra/knowledge-graph plugin** (4A) | High | 30 min install | DO FIRST |
| 3 | **Karpathy knowledge compilation pattern** (1A) | High | 4-6 hours setup | THIS WEEK |
| 4 | **Agent Teams enable** (2C) | High | 15 min | THIS WEEK |
| 5 | **Formal 3-tier memory** (6B) | High | 3-4 hours | THIS WEEK |
| 6 | **Subagent definitions** (2D) | High | 1-2 hours | THIS WEEK |
| 7 | **Mem0 integration** (6A) | High | 4-6 hours | NEXT SPRINT |
| 8 | **Auto pattern extraction** (5B) | High | 3-4 hours | NEXT SPRINT |
| 9 | **Multi-agent scaling rules** (6C) | High | 2 hours | NEXT SPRINT |
| 10 | **Obsidian Copilot plugin** (4B) | Medium | 30 min | WHEN CONVENIENT |
| 11 | **InsightsLM evaluation** (3B) | Medium | 2-3 hours | BACKLOG |
| 12 | **GraphRAG deep integration** (6E) | Medium | 8+ hours | BACKLOG |

---

## SOURCES

- [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Karpathy LLM KB — VentureBeat](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an)
- [Karpathy Three Folders — Digital Today](https://www.digitaltoday.co.kr/en/view/45521/karpathy-reveals-personal-ai-knowledge-base-built-with-three-folders)
- [Karpathy X Post on LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595)
- [Vibe Coding is Passe — The New Stack](https://thenewstack.io/vibe-coding-is-passe/)
- [Claude Code Best Practices — Official Docs](https://code.claude.com/docs/en/best-practices)
- [How Anthropic Teams Use Claude Code (PDF)](https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf)
- [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit)
- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [everything-claude-code](https://github.com/affaan-m/everything-claude-code)
- [claude-code-ultimate-guide](https://github.com/FlorianBruniaux/claude-code-ultimate-guide)
- [obra/knowledge-graph](https://github.com/obra/knowledge-graph)
- [Obsidian Claude Code MCP](https://github.com/iansinnott/obsidian-claude-code-mcp)
- [Obsidian Copilot](https://github.com/logancyang/obsidian-copilot)
- [Claudian — Claude in Obsidian](https://github.com/YishenTu/claudian)
- [Mem0 — Memory Layer](https://github.com/mem0ai/mem0)
- [State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [Letta (MemGPT)](https://github.com/letta-ai/letta)
- [Mem0 vs Letta Comparison](https://vectorize.io/articles/mem0-vs-letta)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [Voyager — Lifelong Learning Agent](https://voyager.minedojo.org/)
- [Self-Evolving Agents Survey](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents)
- [OpenAI Self-Evolving Agents Cookbook](https://cookbook.openai.com/examples/partners/self_evolving_agents/autonomous_agent_retraining)
- [InsightsLM (Supabase + N8N)](https://github.com/theaiautomators/insights-lm-public)
- [Claude Squad](https://github.com/smtg-ai/claude-squad)
- [Claude Code Agent Teams Docs](https://code.claude.com/docs/en/agent-teams)
- [NotebookLM Architecture Paper](https://arxiv.org/html/2504.09720v2)
- [CLAUDE.md Best Practices — UX Planet](https://uxplanet.org/claude-md-best-practices-1ef4f861ce7c)
- [HumanLayer — Writing a Good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
