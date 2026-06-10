---
tags: [architecture, v6, reference]
last_updated: 2026-06-10
freshness_threshold_days: 90
---
# V6 Architecture — Canonical History (V6.0 → V6.8)

> Single source for the V6 substrate exposition that the 5 entry points used to duplicate verbatim. Entry points now carry a one-line pointer here. Operational commands stay in the entry points; this file is the *why/what* for architecture/redesign turns.
> Related: [[brain/CAPABILITIES]] · [[brain/AGENTIC_OS_REFERENCE]] · [[CONTEXT]]

## V6.0 Architecture (transactional, retrieval-driven, fenced)

Four pillars added 2026-05-10. All gated by `EMPIRE_V6_MODE` env var (off/shadow/on).

- **State** — `state/empire_state.db` (SQLite/WAL) is the new source of truth for heartbeats, session_log, active_task. Single writer proxy: `scripts/state/state_manager.py`. `state_sync.py` dispatches transparently. Markdown mirrors auto-regenerate via `state_manager.py export`.
- **Retrieval** — `scripts/core/memory_retriever.py` (FTS5) indexes 219 memory/skills/brain files into 2,700+ chunks. Query in <10ms; returns ≤1500-token snippet sets with file:line refs. Replaces whole-file context loads. Index DB: `state/memory_index.db` (separate from state DB so reads never block writes).
- **Sandbox** — `scripts/state/exec_guard.py` is the AST/regex policy gate on every Bash invocation; `scripts/state/state_guard.py` blocks edits on auto-generated mirror files.
- **Secrets** — `scripts/state/secret_guard.py` denies Read/Bash access to `.env.agents` and friends. `scripts/lib/secret_loader.py` is the canonical in-process loader for CLI wrappers (refuses to load from `tmp/`, refuses interactive shells, audit-logs every access to `state/secret_access.log`).

Soak/rollback: `EMPIRE_V6_MODE=off` (default) is V5.5; `shadow` dual-writes to flat files AND DB; `on` makes DB authoritative. Drift check: `python scripts/state/state_manager.py export --check` (exits 1 on drift).

**Phase 2 (productized deployment, 2026-05-10):** turnkey local + cloud via `infra/docker-compose.{local,cloud}.yml`. Setup wizard adds `step_environment` + `step_v6_init` (boots state DB, builds FTS5 index, fans out scoped env files `.env.agents.{core,webhook,dashboard}`). Command Center adds `/system-health` (reads `state-api` FastAPI, shows guard modes + DB stats) and `/playbook/onboarding` (renders `docs/playbooks/*.md` for non-technical clients). Cloud target enables `enforce` for all three guards by default; local target runs `shadow` with `secret_guard=enforce, exec_guard=report, state_guard=off`. Full registry: brain/CAPABILITIES.md "V6.0 Phase 2 — Productized Deployment".
## V6 Apex (2026-05-10 — V6 Optimization Phase closed)

The four pillars above ship the local-side state + retrieval + guards. **V6 Ascension** (BUILDs 1–5) wired the cross-agent substrate; **V6 Apex** (Phases 1–3) made it operator-facing.

- **Cross-agent event bus (Ascension BUILD 3):** Postgres `agent_events` substrate with raw psycopg LISTEN/NOTIFY for sub-100ms wake-up + `claim_events()` (`FOR UPDATE SKIP LOCKED`) for atomic dequeue. Producers: `state_manager.append_session_log` → `BRAVO_SESSION_LOG_APPENDED`, `pulse_publish.cmd_refresh` → `BRAVO_PULSE_REFRESHED`, `bridge_chat_server._v6_log_chat_interaction` → `BRAVO_CHAT_INTERACTION`, `send_gateway._emit_outbound_sent` → `BRAVO_OUTBOUND_SENT`. Idempotency via unique `idempotency_key` index; offline fallback to `tmp/events_offline.jsonl`. Substrate spec: `brain/EVENT_BUS_CONTRACT.md`.
- **Hybrid semantic memory (Ascension BUILD 2):** FTS5 lexical (BM25) + LanceDB cosine (fastembed ONNX MiniLM-L6-v2, 384-dim, no PyTorch dep) fused via Reciprocal Rank Fusion (k=60). Same `memory_retriever.py query "..."` entry point — the hybrid is transparent. LanceDB store: `state/memory_lance/`.
- **~~Dashboard-driven override approvals (Apex Phase 2)~~** — DELETED 2026-05-22 per CC. The block in `exec_guard` is still in place (refuses DROP TABLE / rm -rf / git push --force), but no longer creates approval-request rows in `exec_overrides` or surfaces an Approve/Deny page. The block IS the protection; the agent picks a different approach when blocked.
- **Cross-agent event feed (Apex Phase 3):** `scripts/core/event_router.py loop` is a cursor-based, lossless on-host tail (`state/event_router.cursor` + `state/event_router.log`). The dashboard `/feed` page is the cloud-side view of the same stream; a 5-second `router.refresh()` client island keeps it live without websocket dependencies. Single-machine — multi-host arbitration is `bridge_lock.py`'s contract.
- **State-health fallback (Apex Phase 1):** `app/api/state-health/route.ts` in the [oasis-command-center](https://github.com/CC90210/oasis-command-center) repo is two-tier: state-api passthrough preferred (local + Cloud Compose), Supabase mirror fallback on Vercel where `state-api:8500` is not routable. Response carries `source: "state-api" | "supabase-mirror"`; the header tags the path so operators see which side served the payload.

Daemons that should run 24/7 on CC's machine (see PLAYBOOK.md for full ops):
```bash
pm2 start scripts/core/event_router.py            --name event-router      --interpreter python -- loop --interval 3
pm2 save
```

V6 Apex closes the V6 Optimization Phase. Architecture work is complete; next epic is business execution ($5K Net MRR by June 18).
## Multi-Machine Bridge Arbitration (V6.5)

`scripts/bridge_lock.py` is the shared multi-machine arbiter for Telegram (and future Discord/Slack) bridges. Lockfile at `~/.oasis/bridge_locks/<agent>.json` holds host+pid+heartbeat. Each bridge calls `acquire` at startup (exits 1 if another host has fresh heartbeat <60s old; PM2 backs off + retries), `heartbeat` every 15s, `release` on shutdown. CLI: `python scripts/bridge_lock.py {acquire|heartbeat|release|status} --agent bravo --json`. Replaces the old "go dormant on 409" path that left bridges silently broken for days.
## Capability Graph (V6.6)

`brain/CAPABILITY_GRAPH.json` is the canonical machine-readable registry of every skill, script, agent, MCP server, and workflow in this repo. Three scripts maintain it:

- `scripts/build_capability_graph.py` — auto-discovers capabilities from frontmatter + docstrings + MCP configs. Run after adding any new file in skills/, scripts/, agents/, or .agents/workflows/.
- `scripts/capability_query.py` — runtime resolver. `resolve "send outreach email"` returns top-N matching skills by trigger overlap. Use this at decision time instead of grepping markdown.
## Agentic OS Orchestration (V6.7, 2026-05-14)

Closes the highest-leverage gaps from `brain/AGENTIC_OS_REFERENCE.md` §10 — the canonical 5-layer agentic-OS logic spec all CC agents (Bravo, Maven, Atlas, Hermes, future client agents) must be mappable to. Where V6.0–V6.6 built the *substrate* (state DB, retrieval, guards, event bus, capability graph), V6.7 turns hooks into orchestration (not just guards) and adds the **Prep Table** data tier so agents stop burning context window on retrieval.

- **Hooks become orchestration (not just guards):** `.claude/settings.local.json` adds `SessionStart` → `scripts/hooks/session_start.py` (state + inbox + 7-day staleness on cold-start, ~380ms), `PreCompact` → `scripts/hooks/pre_compact.py` (SOUL + ACTIVE_TASKS + recent DECISIONS re-injected before compression, ~7KB context), `UserPromptSubmit` → `scripts/hooks/user_prompt_submit.py` (tiered T1/T2/T3 `memory_retriever` snippet injection, ~200ms), and wires the previously-orphaned `scripts/hooks/anti_pattern_hook.py` into `PreToolUse Bash` (regex-flags known mistakes from `memory/ANTI_PATTERNS.json`, report-mode by default). `scripts/hooks/rotate_logs.py` runs from `SessionStart` (12h idempotency stamp, gzips `state/*.log` >5MB).
- **Pantry / Prep Table / Plate data tier:** `brain/DATA_TAXONOMY.md` is the canonical manifest of every raw source (Pantry), every deterministic Python pre-aggregation (Prep Table), and every consumer view (Plate). Snapshots: `scripts/snapshots/briefing_snapshot.py` (daily 06:00), `scripts/snapshots/leads_snapshot.py` (Sat 22:00), `scripts/snapshots/client_alerts_snapshot.py` (daily 07:00). Outputs land in `state/snapshots/latest_*.json` + dated copies. Three jobs registered in `cron_engine.py SEED_JOBS` with `action_type=snapshot_run`; consumers (`skills/ceo-briefing`, `skills/ceo-dashboard`, `agents/chief-of-staff.md`) prefer the snapshot, fall back to live engines only when stale (>24h). N8n handler for `snapshot_run` action_type is the open path to full automation.
- **Three new canonical skills:** `skills/silver-platter/` (per-agent data-readiness audit producing HTML report), `skills/integrations-sync/` (idempotent refresh patterns for Stripe / Supabase / GWS / n8n / funnels with audit log), `skills/memory-journaling/` (structured DECISIONS / PATTERNS / MISTAKES logging with frontmatter + wiki-links).
- **Six new INTENTS playbooks** in `brain/INTENTS.md`: generate CEO briefing, draft proposal/SOW, score a lead, log a decision, sync an external data source, publish to social (Maven delegation hint).

Source provenance: `brain/AGENTIC_OS_REFERENCE.md` (captured 2026-05-14 from YouTube "Build your agentic OS better than 99% of people"; full transcript at `docs/references/agentic-os-99pct-transcript.txt`). All four sibling agents (Bravo here, Maven at `~/CMO-Agent`, Atlas at `~/APPS/CFO-Agent`, Hermes at `~/APPS/hermes`) carry the same V6.7 logic anchor — implementation differs per-agent, taxonomy and skill set is shared. Client harness (`skills/agent-forge`, `skills/agent-runtime-packaging`) must include the full V6.7 layout so forked client agents inherit the orchestration + Prep Table + canonical skills out of the box.
- `scripts/register.py` — one-command "add new capability" wizard. `register.py skill <name> --description "..." --triggers "..."` scaffolds the file with proper frontmatter, rebuilds the graph, runs self_audit, prints next-steps. Ends the 6-step add-a-skill ritual.
## Agent-OS Vocabulary Layer (V6.8, 2026-05-16)

Closes the discoverability + governance gap surfaced by auditing [mattpocock/skills](https://github.com/mattpocock/skills) against our setup. V6.0–V6.7 built the substrate; V6.8 makes it self-documenting and externally distributable. Full propagation contract: [brain/V68_AGENT_OS_PATTERNS.md](brain/V68_AGENT_OS_PATTERNS.md).

- **[CONTEXT.md](CONTEXT.md) at project root** — canonical empire vocabulary glossary (people, brands, multi-tenancy, sales/CRM, state/substrate, V6 arch, skill/agent semantics, browser ladder, North Star). All five sibling entry points (CLAUDE.md, GEMINI.md, ANTIGRAVITY.md, AGENTS.md, OPENCODE.md) reference it as boot item #5 — lazy-load when a domain term needs canonicalization. Indexed by `memory_retriever.py` (new `context` scope) so cold sessions get the right definition in <100ms.
- **[docs/adr/](docs/adr/) — Architectural Decision Records** — numbered, dated, frontmatter-tagged. Starter ADRs: `0001-skill-dependency-classification.md` (hard vs soft deps), `0002-context-md-canonical-vocabulary.md` (this section's enforcement). Scaffold new ones with `python scripts/register.py adr-new <slug>`. Distinct from `memory/DECISIONS.md` (tactical/business decisions) — ADRs are architectural and persistent.
- **Skill frontmatter conventions** — three new keys honored across the graph + resolver:
  - `disable_model_invocation: true` — skill never auto-loads via semantic match; fires ONLY on explicit `/command`. Applied to `hyperthink`, `sparc-methodology`, `retro`. Verify exclusion: `python scripts/capability_query.py resolve "<intent>"` (default mode).
  - `argument_hint: "<question>"` — surfaces invocation prompt at runtime. Applied to `writing-plans`, `outreach-send`. Surfaced in `CAPABILITY_GRAPH.json` entries.
  - `requires: [env:KEY, daemon:NAME, state:PATH]` (V6.8.1) — declares hard dependencies per ADR-0001. Enforced by `python scripts/capability_query.py check-deps <node_id>` which returns ok/missing/pointer report (exits 1 on miss). Wizard supports `--requires-env`, `--requires-daemon`, `--requires-state` flags.
- **Skill lifecycle directories** — `skills/_archive/` (retired, preserved for reference) and `skills/in-progress/` (staging lane for drafts). Both excluded from `build_capability_graph.py` (via `SKIP_SKILL_DIRS`) and `.claude-plugin/plugin.json`. Use the staging lane for skills not yet `[PROBATIONARY]`.
- **[.claude-plugin/plugin.json](.claude-plugin/plugin.json)** — distribution manifest. 47 universally-useful skills listed for `npx skills@latest add` consumption. Excludes Bravo-internal (`outreach-send`, `gws-*`), staging, archived. Will power the `skills/agent-forge` client harness mandate.
- **[skills/skill-creator/SKILL.md](skills/skill-creator/SKILL.md)** — opens with a 4-step "Before drafting any new skill" checklist enforcing CONTEXT.md consult + hard/soft dep classification per ADR-0001 + invocation-discipline decision (disable_model_invocation / argument_hint) + scaffold via `register.py skill`.

**Propagation contract:** Siblings (Maven at `~/CMO-Agent`, Atlas at `~/APPS/CFO-Agent`, future Hermes) inherit the *patterns* — CONTEXT.md tailored to their domain (brand/content for Maven, finance/tax for Atlas), `docs/adr/` with their own decisions, frontmatter conventions when they audit their skills. The patterns are universal; the content is per-agent. See [brain/V68_AGENT_OS_PATTERNS.md](brain/V68_AGENT_OS_PATTERNS.md).

Source provenance: cross-reference audit against [mattpocock/skills](https://github.com/mattpocock/skills). Plan: `~/.claude/plans/i-found-a-really-parallel-pascal.md`. Probationary pattern logged in `memory/PATTERNS.md` — promote to `[V]` after 3 more external-repo imports re-use this surgical cross-reference approach.

**V6.8.1 (2026-05-16):** Promoted V6.8 from static files to load-bearing substrate. `user_prompt_submit.py` now auto-injects CONTEXT.md definitions on every prompt that mentions a glossary term (verified live: "warm Lead in the pipeline … Pulse cadence" → Pipeline + Pulse + Lead defs surfaced before agent reads). `capability_query.py check-deps` enforces ADR-0001 `requires:` declarations. `register.py skill` wizard emits V6.8 frontmatter by default (5 new flags). All five Maven and all five Atlas sibling entry points sync'd to reference CONTEXT.md on operational turns. Commits: bec2fcc (Bravo), 00d8e14 (Maven), 18e89af (Atlas).
