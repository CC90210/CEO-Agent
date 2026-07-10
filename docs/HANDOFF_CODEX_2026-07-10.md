---
tags: [handoff, codex, audit, genome]
purpose: Full-system handoff for Codex — audit mandate, complete 2026-07-09/10 change ledger, iron rules, open items, and research directions. Codex reads this, audits the system, and proposes/executes upgrades.
owner: CC (Conaugh McKenna)
last_updated: 2026-07-10
---

# HANDOFF → CODEX — Full Audit & Upgrade Mandate (2026-07-10)

**From:** Bravo (Claude, Business-Empire-Agent) · **To:** Codex (dual-AI backend specialist)
**Mandate from CC:** audit everything below, find errors or things that need to get better, and upgrade them. You have standing to propose ANY improvement; execution rules in §3 are non-negotiable.

Related: [[PERSONAL.md]] (the genome seed) · [[brain/QUICK_REFERENCE]] · [[docs/HANDOVER-2026-07-10]] (OpenCode-Bravo's repo cross-reference audit, unverified)

---

## §1 What was shipped 2026-07-09 → 2026-07-10 (the efficiency ledger)

All verified live; commits are on `chore/montreal-turnkey-reset` (Bravo) unless noted.

### A. Telegram automations — dead → production (the original complaint)
- Daily brief rendered "MRR: — / AI narration unavailable" for weeks. TWO root causes: fallback read snapshot keys that never existed; narration called api.anthropic.com on the **out-of-credits metered key**. Fixed: schema-correct deterministic render + local-CLI narration + HTML-escaping + degraded→"unavailable" honesty guards. `40156d8d`, `588c246c`, `4c9a70da`.
- `scripts/lib/claude_cli.py` (NEW): THE blessed model-call primitive — local `claude` CLI, subscription OAuth, **toolless** (`--allowed-tools ""`), lean boot. `52da0b01`.
- Sleep Agent (nightly memory consolidation) + `auto_score_leads` ported off the dead key; extraction break-glass fallback retired behind env flag; cron watchdog fixed (read bare os.environ → always "telegram_not_configured"; now via notify(), exits RED on delivery failure).
- Weekly MRR Report + Morning Pow Wow crons disabled (DB + SEED lockstep); `run_revenue_report` handler REFUSES to send MRR (defense-in-depth); monthly snapshot strips dollar figures. **Atlas owns all revenue reporting.**
- `cron_engine.py cmd_add` bugfix: never stamped tenant_id → every `add` failed NOT NULL since the column landed.

### B. Inbound-only CRM pivot
- 156 outbound leads hard-deleted (109 cold_outreach + 47 gateway_autocreate; backup `state/backups/leads_purge_*.json`; another tenant's 13 rows preserved). `07eef9ec`.
- `lead_engine.py` pipeline/followups tenant-scoped to `OASIS_TENANT_ID`; **inserts tenant-stamped** (Codex's own catch — read-filter without write-stamp would have orphaned new leads).
- Brief now shows 8 real inbound + 1 won. Inbound-first documented in every entry point + router file.

### C. Deep structure audit (6-auditor fan-out) + fixes
- ~60 findings executed across skills/brain/docs/workflows/apps: 19 skills reworded to the Atlas boundary; 6 routing-blind skills fixed (YAML block-scalar `>` descriptions the graph parser swallowed) + drift detector hardened; brain router files (AGENT_ROUTER/EXECUTION_RULES/INTENTS/QUICK_REFERENCE/CAPABILITIES) purged of Bravo-owns-MRR + outbound-first + dead-API-key guidance; README/ARCHITECTURE/ENV_KEYS + 5 VPS prompts banner'd; T0 telegram prompt fixed; 4 orphan scripts archived; `.agents/config.toml` refreshed. `e2046cba`, `51a9d568`.

### D. THE AGENT GENOME (the architecture)
- **`PERSONAL.md`** = germline seed (identity core + behavioral blocks + 10-gene contract). **`scripts/genome_sync.py`** stamps seed blocks byte-identical into all 6 runtime entry points + `.gemini/rules/` mirrors (replace-between-markers only; duplicate/nested markers hard-rejected; `--check` CI gate). **`scripts/agent_genome.py`** = 10-gene expression verifier, repo-agnostic via per-repo `genome.json`. `f286b23e`, `f154e5d3`.
- **Propagated fleet-wide same day (CC directive):** Atlas **10/10** (CFO-Agent `42962fa`, was 4/10) · Maven **10/10** (CMO-Agent `12e3a2e`, was 3/10) · SunBiz **8/10** lean-by-design (`0e03e4a`, main→VPS) · Breeze **5/10** measured-as-product (`a2b49d6`). Tools byte-identical everywhere; config in genome.json.
- **Fitness loop closed:** cron "Bravo — Nightly Harness Eval" 03:30 daily → `harness_eval.py` (10 deterministic checks) → Telegram on any red. **First unattended run 2026-07-10 03:30: ALL GREEN.**

### E. Associative recall (retrieval upgrade, 2026-07-10)
- **`scripts/core/graph_activation.py`** (NEW): spreading activation over the Obsidian wiki-link graph (264 nodes / 833 edges) — query matches seed activation, flows 1 hop along `[[links]]` (fwd 0.5 / back 0.35), recency-decayed (180d half-life), surfaces ≤3 `kind:associative` extras. Wired into `memory_retriever.query()` hybrid path behind `EMPIRE_GRAPH_BOOST` (default on, HARD fallback). Boost runs **after** trim (pre-trim boost silently dropped extras — found by self-review). `271e6594`, `9595f641`.
- RULE 6's ≥2-wiki-links is now **load-bearing**: links are the agent's associations.

---

## §2 Verification protocol (run these; trust nothing else)
```
python scripts/harness_eval.py            # 10 live-health checks — must be 10/10
python scripts/agent_genome.py            # 10 structural genes — must be 10/10 (Bravo)
python scripts/genome_sync.py --check     # seed↔expression drift — must be CLEAN
python -m pytest scripts/tests/test_entrypoint_parity.py -q   # 5 passed
python scripts/core/graph_activation.py status                # graph fresh
python scripts/core/cron_engine.py --json list                # no ERROR last_results
```

## §3 Iron rules Codex MUST honor (violations = rejected work)
1. **CLI-only model access** — never ANTHROPIC_API_KEY / api.anthropic.com in automations. Use `scripts/lib/claude_cli.py`. The metered key is out of credits AND banned.
2. **Atlas owns MRR/revenue reporting.** Bravo never reports figures; mechanics only on explicit CC request.
3. **CRM is inbound-first.** Cold outbound = on-demand + operator-approved, never autonomous.
4. **LOCKSTEP blocks:** edit `PERSONAL.md` → `python scripts/genome_sync.py`. NEVER hand-edit blocks in entry points.
5. **Rule 4 cross-file sync** for any entry-point/config change; **Rule 6** frontmatter + ≥2 wiki-links on new .md (now feeds retrieval); **Rule 10** verify inherited claims live before acting.
6. **Never write to sibling repos** (CFO/CMO/SunBiz/breeze) without CC's explicit per-repo instruction. SunBiz+Breeze are client production.
7. Guards (secret/exec/state) are enforce-mode in Bravo — do not bypass with eval/base64/--no-verify.
8. All sends via `scripts/integrations/send_gateway.py`; gateway changes require `scripts/tests/test_send_gateway.py` green FIRST.

## §4 Known open items (ranked — start your audit here)
1. **task_outcomes loop is open** (highest leverage): `scripts/core/task_outcomes.py` exists but has ZERO writers — validator subagent + Codex-review verdicts are never recorded; first_pass_success_pct permanently null. Wire `subagent_stop_validator.py` + the codex-companion wrapper to `task_outcomes.py record`. This closes the quantitative self-improvement loop.
2. **auto_dream consolidate/prune detects but never executes** — [P]→[V] pattern promotion + duplicate-mistake collapse return action lists only (`scripts/auto_dream.py:169-271`). Make them write back (append-only, git-committed).
3. **Dead-key stragglers**: `model_router.py` (fix here fixes many consumers), `inbound_classifier.py`, `autonomous_agent.py`, `aura/brain.py`, telegram_agent.js API-key fallback + bridge_chat_server sticky-paid respawn — migrate to claude_cli / retire.
4. **Sibling guard ACTIVATION** (structural-only today): generate `.claude/settings.local.json` from the copied hooks template per machine + EMPIRE_HOOK_* env. Needs CC per-repo go.
5. **Sibling recall upgrade**: copy `graph_activation.py` + re-sync `memory_retriever.py` to Atlas/Maven (their vaults are wiki-linked; SunBiz lacks a retriever by design).
6. **Scaffold** (`templates/agent-scaffold/`) still emits a thin pre-genome shell — new agents should be born 10/10.
7. Smaller: CLAUDE.md is 250 lines vs ≤150 rule (compression pass); ADR numbering collision (two 0003s/0004s); Atlas has 2 routing-blind `>` skill descriptions; `learning_loop_extra` dead key in agent_genome DEFAULTS (remove at next version bump + re-sync all copies); manifest-ai-editor skill's ai-agent workflow step needs a live API-key-usage check; 34 docs lack frontmatter (skipped deliberately — paste-prompt corruption risk); OKRs.md is an expired Q2 register.

## §5 Research directions (fold results into your audit)
A researcher pass on 2026 frontier practice is being appended below when complete. Themes to evaluate against this system: harness-side sequential-reasoning protocols (plan-verify-execute, verification sampling), trajectory/telemetry stores (per-run tool-call traces → failure replay), temporal/provenance-weighted memory graphs, eval-in-CI (GitHub Actions gate on harness_eval/agent_genome), task-tier model routing (model_registry ladder exists; resolver doesn't), A2A-class agent protocols beyond the agent_activity table.

### Research appendix — distilled from this session's frontier sweep (WebSearch-verified where cited)

**Adopt now (ranked by leverage for THIS system):**
1. **Eval-in-CI** — a GitHub Actions workflow gating pushes on `harness_eval.py --json` + `agent_genome.py --json` exit codes. We built the checkers + nightly cron; CI is the missing enforcement ring. (RLVR discipline applied to the substrate; convergent across OpenAI SDK / ADK / LangGraph eval tooling.)
2. **Telemetry/verdict loop** — every frontier harness traces runs first-class (OpenAI SDK `trace()`/spans — https://openai.github.io/openai-agents-python/tracing/ ; ADK TrajectoryEvaluator). Our equivalent: wire validator + Codex verdicts into `task_outcomes.py record` (§4.1) and add a minimal per-task tool-call trajectory store (JSONL in state/) — the substrate for failure-replay and routing improvements.
3. **Golden-task behavioral evals** — harness_eval asserts STATE; frontier systems also run a small task dataset with expected_tool_use/expected_output and an LLM-judge after prompt/router/skill edits. Start with 5-10 golden tasks (route MRR→Atlas, send-email→gateway, fetch-URL→research_fetch).
4. **Task-tier model routing** — `model_registry.py` defines the FABLE/OPUS/SONNET/HAIKU ladder with intents, but `claude_cli.py` hardcodes sonnet. A resolver (intent→tier) is a clean cost/quality lever; taxonomy already exists.
5. **Context compaction triggers** — structured note-taking + summarize-and-reinitiate at window limits is convergent practice (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents). We have state_compact.py + memory files; the auto-trigger is the thin spot.

**Watch:** temporal/provenance-weighted memory graphs (Zep/graphiti-class — our graph_activation covers association; provenance-weighting is the next rung) · Letta/MemGPT-class self-editing memory (our sleep-agent is the safer append-only variant) · A2A-class agent-to-agent protocol for Bravo↔APEX beyond the agent_activity table (https://afnexis.com/articles/google-adk-vs-langgraph) · OpenHands/SWE-agent execution-loop patterns for the eventual autonomous-PR lane.

**Skip:** heavyweight orchestration frameworks (LangGraph/CrewAI as dependencies — we already have deterministic workflows + subagents; adopt patterns, not runtimes) · vector-DB migrations (hybrid FTS5+Lance+graph outperforms a rip-and-replace at this corpus size) · autonomous self-modifying prompts (our germline/epigenome split exists precisely to prevent identity drift).

## §6 How to work
Present findings verdict-first with file:line evidence. AUTO-fix mechanical items; propose judgment calls to CC with one-line tradeoffs. Every change: verify per §2, then commit conventional-format on the current branch. The four-line report (Changed/Why/Proof/Needs) closes every work session.
