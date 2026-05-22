# ARCHITECTURE — Business-Empire-Agent V6.0

> This document explains the engineering design of Bravo — not just what it is, but why every decision was made this way.
> Written for engineers who need to understand the system deeply enough to extend, debug, or rebuild any part of it.

## V6.0 — Transactional State, Retrieval-Driven Context, Hook-Fenced Execution (2026-05-10)

V6.0 is the substrate underneath every other system in this document. V5.6 (outbound chokepoint) and earlier sections still describe what the agent *does*; V6.0 describes how it *holds state*, *recalls memory*, *coordinates with siblings*, and *protects itself* from its own LLM-generated mistakes.

Five pillars, all gated by `EMPIRE_V6_MODE` (`off` → V5.5 behavior unchanged · `shadow` → dual-write to flat files AND DB for the soak period · `on` → DB authoritative, markdown becomes auto-generated mirror).

### Pillar 1 — Transactional state (`scripts/state/state_manager.py` + `state/empire_state.db`)

SQLite in WAL mode is the new source of truth for `agent_state`, `session_log`, `active_task`, and a full `state_transaction` audit trail. **One writer proxy** (`state_manager.py`) wraps every mutation in `BEGIN IMMEDIATE … COMMIT` with a 5-second `busy_timeout`. Five concurrent processes can append to `session_log` simultaneously and the UNIQUE(`session_id`, `note`) constraint gives atomic dedup — replacing the V5.5 race-prone "regex-find-and-replace into markdown" path that lost writes under load.

Markdown stays readable. After every commit, `state_manager.export_markdown()` regenerates `brain/STATE.md` (heartbeat block) and `memory/SESSION_LOG.md` (entries section between AUTO-GENERATED-BEGIN/END markers) from the DB. The operator opens the same files and sees the same data — but the bytes flow DB → markdown, not the other way around. `python scripts/state/state_manager.py export --check` exits non-zero if the mirrors drift, gating commits.

The CLI surface (`heartbeat`, `log`, `task add/close/list`, `export`, `status`, `import-from-files`) is what every other script calls. `state_sync.py` is now a thin dispatcher that routes to either the V5.5 flat-file path or `state_manager` based on `EMPIRE_V6_MODE` — no caller has to know which era they're running in.

### Pillar 2 — Hybrid retrieval: FTS5 (lexical) + LanceDB/ONNX (semantic) (`scripts/core/memory_retriever.py`)

Two indexes, one query surface, one merge function.

**Lexical leg — `state/memory_index.db`** (SQLite FTS5). Virtual table over `memory/`, `skills/`, `brain/`, and the five entry-point markdown files (CLAUDE.md / AGENTS.md / GEMINI.md / ANTIGRAVITY.md / OPENCODE.md). Files split into ~400-token chunks on H2/H3 boundaries; each chunk gets `source`, `kind`, `heading`, `body`, `tags` columns + a `chunk_meta` row recording `line_start`/`line_end`/`chunk_idx` so every hit returns a clickable file:line ref. Queries default to FTS5 implicit-AND with OR fallback. BM25 ranking. ~9 ms median latency.

**Semantic leg — `state/memory_lance/` (V6 BUILD 2, 2026-05-11).** A LanceDB vector store holding the same 2,800+ chunks alongside L2-normalized 384-dim embeddings produced by `fastembed` running the ONNX-quantized `sentence-transformers/all-MiniLM-L6-v2` model. **No PyTorch** — `fastembed` ships ONNX Runtime directly (~80 MB total install). Cosine ANN search via LanceDB's IVF index. Lazy-loaded: a caller that asks for `--lexical-only` never pays the model-load cost.

**Hybrid merge — Reciprocal Rank Fusion (RRF).** For a query, run both legs independently → take top N from each → compute `score(d) = Σ over rankers r: 1 / (k + rank_r(d))` for each unique chunk, with `k = 60` (standard). Top-K by aggregate RRF score wins. Why rank fusion and not raw-score normalization: BM25 and cosine live on different scales — combining them numerically requires per-corpus tuning that drifts. RRF is parameter-light and provably robust against scale mismatches. The merger sorts (score DESC, chunk-key ASC) so input ordering can't change output.

**CLI surface:**
```bash
python scripts/core/memory_retriever.py query "price objections"                    # hybrid (default)
python scripts/core/memory_retriever.py query "..." --lexical-only                  # FTS5 only
python scripts/core/memory_retriever.py query "..." --semantic-only                 # LanceDB only
python scripts/core/memory_retriever.py query "..." --explain                       # show lex_rank, sem_rank, rrf_score per hit
python scripts/core/memory_retriever.py query "..." --kind {skill,memory,brain,entry}
python scripts/core/memory_retriever.py build [--force] [--lexical-only]            # full reindex (lexical-only skips embedding pass)
python scripts/core/memory_retriever.py update                                      # incremental (hash-skipped)
python scripts/core/memory_retriever.py status                                      # both legs + LanceDB row count
```

**Concrete payoff (measured 2026-05-11):** the query `price objections` returns:
- **Lexical-only:** top-1 = `skills/web-scraping/SKILL.md` (false positive on the word "pricing" in JSON-schema examples).
- **Semantic-only:** top-1 = `skills/sales-methodology/SKILL.md:209` (an actual objection-handling playbook, `cost resistance` framing — no lexical overlap with the query).
- **Hybrid (RRF):** top-1 = `skills/sales-closing/SKILL.md:93` ("Real meaning: unspoken objection") — found at rank 5 lexical, rank 3 semantic, fused to rank 1.

**Token impact:** a Tier 2 standard load that used to inject ~104K tokens now resolves to ≤1500 tokens of targeted snippets — preserved from BUILD 1. The hybrid upgrade adds conceptual recall without enlarging the output budget.

**Index freshness:** a `PostToolUse` hook (`scripts/retriever_postedit.py`) runs `memory_retriever.py update` in the background after every Edit/Write inside the indexed scopes. Update is incremental — files unchanged since their hash was last recorded are skipped (zero re-embed cost on no-op edits).

**Architectural rule (unchanged from BUILD 1):** queries hit the retriever first; whole-file reads are an escalation, not a default. `brain/AGENT_ROUTER.md` directs every operator request through this path. Self-improvement workflows (`/evolve`, `/retro`) consume snippets, not whole files.

**Behavior locked by `tests/test_retrieval_hybrid.py`** (22 tests): mode-plumbing structural shape, 10 parametrized paraphrase pairs proving semantic surfaces unique chunks lexical can't reach, RRF math symmetry + dual-appearance preference, kind-filter respected across all three modes, token-budget enforcement, empty-query guard, dual-engine status reporting.

### Pillar 3 — Hook-fenced execution (`scripts/{exec,secret,state}_guard.py`)

Three Claude Code `PreToolUse` hooks wired in `.claude/settings.local.json`:

- **`secret_guard.py`** — denies Read on `.env*`, `*.pem`, `*.key`, `credentials.json`, `secrets/`. Denies Bash commands that exfiltrate them via `cat`/`grep`/`sed`/`awk`/`cp`/`mv`/`python -c`/redirects/heredocs. Path regex covers all `.env.agents.*` fan-out files (`core`, `webhook`, `dashboard`, future variants) — `*` quantifier on the suffix group, not `?`.
- **`exec_guard.py`** — layered policy gate. Layer 1: hard-blocklist regex (DROP, TRUNCATE, ALTER DROP COLUMN, DELETE-no-WHERE, `rm -rf /` outside tmp, force-push to main, `git reset --hard <ref>`, `git clean -fdx`, fork bombs, `dd-to-disk`, `xargs rm`, bare `rm -rf` followed by pipe/EOL). Layer 2: SQL AST validation via `sqlglot` for any command containing `psql`/`sqlite3`/`supabase_tool execute-sql`. Layer 3: irreversible-op allowlist (`git push`, `vercel --prod`, `stripe charge/refund`, `supabase apply_migration`, `n8n publish_workflow`) — logged but not blocked in Phase 1. Layer 4: read-only CLI fast-path that **disables itself if the command contains `&&`, `||`, `;`, `|`, backticks, `$()`, `<()`, or `>()`** — Codex caught the chained-command leak.
- **`state_guard.py`** — denies Edit on auto-generated mirrors AND denies Bash commands that mutate them (redirects `>`/`>>`, `tee`, `cp`/`mv`/`rsync`, `sed -i`, `dd of=`, `python -c open(…, 'w')`). Anchored on the FULL relative path (`memory/SESSION_LOG.md`), not just basename, so a homonym like `backups/SESSION_LOG.md` correctly passes.

Each guard has three modes via env var (`enforce` / `report` / `off`). Default safe-mode for fresh installs: `secret_guard=enforce`, `exec_guard=report` (soak), `state_guard=off` (until `EMPIRE_V6_MODE=on` cutover). Cloud installs flip all three to `enforce` by default. Every block writes a JSONL audit row to `state/{guard}.log`. The full bypass surface is locked behind a 109-test regression suite at `tests/test_hook_regression.py` — including all three Codex Critical bypasses and five self-review follow-ups.

### Pillar 5 — Cross-agent event bus (`scripts/core/event_bus.py` + Supabase `agent_events`)

V5.x cross-agent coordination ran through three flat JSON files (`ceo_pulse.json`, `cfo_pulse.json`, `cmo_pulse.json`) that every agent polled. Race-prone, latency-bound, no push semantics. V6.0 layers a Postgres-backed durable pub/sub on top.

**Substrate:** `agent_events` table + migration 015 extensions (`source_agent`, `idempotency_key`, `status`, `retry_count`, `processed_at`, `processed_by`, `last_error`, `visibility_until`) + `notify_agent_event` trigger that emits `pg_notify(target_agent OR 'broadcast', payload)` on every INSERT + four RPC functions: `claim_events()` (atomic dequeue with `FOR UPDATE SKIP LOCKED`), `ack_event()`, `fail_event()` (3-retry budget then `dead`), `reap_stuck_events()` (visibility-timeout recovery).

**Publisher API:** `event_bus.publish(event_type, payload, source, target, idempotency_key, correlation_id)`. Idempotent — passing the same key twice is a silent no-op (unique partial index on `idempotency_key WHERE NOT NULL`). Offline-durable — if Supabase is unreachable, appends to `tmp/events_offline.jsonl` for `drain_offline_queue()` to replay.

**Subscriber API:** `await event_bus.subscribe(agent, handlers={event_type: async_callback})`. Primary path is raw `psycopg2` LISTEN/NOTIFY against `db.<ref>.supabase.co:5432` — wakes on `pg_notify`, then `claim_events()` atomically dequeues. Fallback path is 5-second polling of `claim_events()` when the direct-DB DSN isn't available (e.g., `PGBOUNCER_DB_PASSWORD` not in env). Same public contract regardless of which transport delivers the wake-up; race-free either way because `claim_events()` does the `FOR UPDATE SKIP LOCKED` work.

**Producers wired in BUILD 3 (3 of 4):**

- `state_manager.append_session_log` → `BRAVO_SESSION_LOG_APPENDED` on every successful insert
- `pulse_publish.cmd_refresh` → `BRAVO_PULSE_REFRESHED` after `_atomic_write`
- `bridge_chat_server._v6_log_chat_interaction` → `BRAVO_CHAT_INTERACTION` per dashboard chat turn
- `send_gateway` (deferred) → `BRAVO_OUTBOUND_SENT` (slated for a sober daylight session — surgical edits to the V5.6 outbound chokepoint warrant the full regression suite + a `--dry-run` smoke)

**Why pg_notify and not Supabase Realtime WebSocket:** lower latency, no WebSocket overhead, doesn't count against the Supabase Realtime quota, works from any backend Python daemon (no SDK dependency). The trade-off — needing the Postgres password rather than just the project anon key — is paid once at install time.

**Canonical event-type registry:** [brain/EVENT_BUS_CONTRACT.md](brain/EVENT_BUS_CONTRACT.md). Adding a new event type requires updating that file before merging.

### Pillar 4 — Secret isolation (`scripts/lib/secret_loader.py` + scoped env fan-out)

`.env.agents` is no longer LLM-readable. The hook layer (above) blocks every direct read; the in-process loader (`scripts/lib/secret_loader.py`) is the only path scripts use to access credentials. The loader:

- Parses `.env.agents` once per process and caches in module scope.
- Refuses to load if invoked from `tmp/` (LLM-written one-off scripts) or from an interactive Python shell (`PYTHONINSPECT` / `python -i`).
- Logs every access to `state/secret_access.log` with `{ts, caller_path, keys_accessed}` so we can audit which scripts touched which keys.
- Exposes `load_env(required=[…])` which raises on missing required keys and `get(key, default)` for ad-hoc access.

The setup wizard (`bravo_cli/wizard.py:step_v6_init`) fans out the master `.env.agents` into three per-service scoped files at install time:

| File | Keys included | Used by |
|------|---------------|---------|
| `.env.agents.core` | All keys | `bravo-core` daemon (autonomous loop) |
| `.env.agents.webhook` | Stripe webhook + Supabase + Telegram + EMPIRE_* (no Anthropic, no service-role) | `bravo-webhook` (FastAPI) |
| `.env.agents.dashboard` | Public Supabase anon key + STATE_API_URL only (zero secrets) | `command-center` Next.js |

Defense in depth: a single-service RCE in `bravo-webhook` cannot exfiltrate the full credential set because `bravo-webhook`'s container only has `.env.agents.webhook` mounted — the master file is never copied into any container layer (`.dockerignore` excludes it; `env_file:` in compose injects ONLY the scoped variables).

### Surrounding infrastructure

- **`infra/docker-compose.local.yml`** — laptop sandbox: `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`, 127.0.0.1-only port binding, `memory/`/`brain/`/`skills/` mounted read-only, only `state/`, `tmp/`, `logs/` writable.
- **`infra/docker-compose.cloud.yml`** — `include:`s the prod stack (5 daemons + pgbouncer + Caddy) and adds `command-center` (Next.js standalone) + `state-api` (read-only FastAPI).
- **`infra/Dockerfile.commandcenter`** — Next.js 15 multi-stage build, non-root UID 10001, `output: 'standalone'`, `/api/health` healthcheck.
- **`infra/Caddyfile`** — TLS-terminated dashboard endpoint with basic auth + `/api/health` carve-out for probes.
- **Setup wizard (`bravo_cli/wizard.py`)** — `step_environment` detects local vs cloud; `step_v6_init` writes hook-mode defaults, bootstraps both DBs, builds the FTS5 index, fans out scoped env files, and optionally runs `docker compose build`.
- **Command Center modules** — `oasis-command-center:app/system-health/page.tsx` (DB stats + agent ticks + 3 guard cards live), `app/playbook/onboarding/page.tsx` (markdown SOPs from `docs/playbooks/`).
- **Two-tier `/api/state-health` read path (2026-05-10)** — `oasis-command-center:app/api/state-health/route.ts` tries `state-api:8500/status` first; on Vercel where that hostname is not routable, it falls back to a Supabase mirror that synthesizes the same `StateHealthResponse` shape from `agent_state_snapshot` + `agent_events` + `session_logs` via `getServiceSupabase()`. The response carries `source: "state-api" | "supabase-mirror"` so operators can see which path served the payload (rendered as a tag in the page header). Local-only fields (FTS5 stats, jsonl guard tails) are omitted in the fallback — the page already renders those sections conditionally.
- **~~Dashboard-driven override approvals (Apex Phase 2)~~** — DELETED 2026-05-22. See §9 "Operator-Approval Override Flow" for the deprecation rationale.
- **Event router + live feed (Apex Phase 3, 2026-05-10)** — `scripts/core/event_router.py loop` is the on-host event-bus tail. It polls `agent_events` with a cursor file (`state/event_router.cursor`) and appends a projected, scannable summary to `state/event_router.log` jsonl. The cursor makes the consumer lossless + crash-safe. The dashboard's `/feed` page is the cloud-side view of the same stream: server-renders the last hour, a 5-second `router.refresh()` client island keeps it live without websockets. `/api/event-feed` exposes the same read for any future poller. The router is single-machine — multiple hosts running it would each emit duplicate side-effects; the bridge_lock contract owns that arbitration.

### Cross-agent contract under V6.0

Sibling agents (Atlas, Maven, Aura, Hermes) read Bravo's state through the same paths as V5.5 — `memory/SESSION_LOG.md`, `brain/STATE.md`, `data/pulse/ceo_pulse.json` — because in V6.0 those files are auto-generated mirrors. The contract surface is unchanged. What's NEW: `ceo_pulse.json` carries an additive `v6` block (mode, hook_modes, state_db stats, fts5 stats) that V6.0-aware siblings can use for sub-second liveness checks; V5.5-era siblings ignore it (JSON additive). Hard-rule still holds: Bravo NEVER writes to a sibling repo, siblings NEVER write to this one.

### Why this layer exists

V5.5 worked. V6.0 was built because three failure modes had already manifested or were imminent:

1. **Race-prone flat files** — concurrent `state_sync.py` invocations from cron + a manual run overwrote each other's heartbeat blocks. Postgres `pg_try_advisory_xact_lock` protected sends ([send_gateway.py:840](scripts/integrations/send_gateway.py#L840)) but local state had no protection.
2. **Whole-file context bloat** — Tier 2 loads pulled ~104K tokens just to answer "what did we do last week?". The agent regularly burned 4-5× the context it needed before producing the first useful sentence.
3. **Live secret leak** — the 2026-05-06 plaintext-Stripe-key incident in `%APPDATA%\Antigravity\User\mcp.json` proved the LLM-readable secret surface was a live exploit path, not a theoretical one.

V6.0 closes all three with single-machine SQLite WAL, FTS5 chunk retrieval, and the hook-fenced execution layer. Multi-machine sync (Litestream / rqlite) is deliberately out of scope until 4+ agents run on different hosts; current load is single-machine.

---

## V5.6 — Outbound Communication Chokepoint (2026-04-20)

Every autonomous outbound action now routes through a single entry point: `scripts/integrations/send_gateway.py`. This is the V5.6 headline change.

**Why:** Before V5.6 four Python engines plus the N8N inbound qualifier could contact the same lead on the same day without seeing each other. The audit of 2026-04-19 traced the "AI sends 10 emails in a row" bug to this fragmentation. Idempotency was a library callers had to remember — so they forgot, or each wrote their own.

**How it works:**

1. Every engine imports `from send_gateway import send`.
2. `send()` enforces four gates in order: CASL suppression (commercial intent only) → active cooldown on (lead, channel) → daily cap per channel → channel-specific physical send.
3. Every successful send writes to `lead_interactions` (architectural truth with `cooldown_until` + `agent_source` + `metadata`), mirrors to `email_log` (legacy SMTP truth), and bumps `leads.last_contacted_at`.
4. Failures write to `email_log` with `status='failed'` for forensics.
5. The return shape is stable: `{"status": sent|blocked|suppressed|dry_run|error, "reason": str, "lead_id", "interaction_id", "cooldown_until", "daily_count"}`. `send()` never raises.

**Architectural contract:** A PR that calls `smtplib.SMTP_SSL()` from a business engine (outreach / funnel / booking / email) must be rejected. The chokepoint is the only path. This rule is what makes the cooldown ledger meaningful — one bypass invalidates the whole guarantee.

**Supporting files:**

- `database/003_unified_interaction_ledger.sql` — adds `cooldown_until`, `agent_source`, `metadata` columns + four indexes to `lead_interactions`. Purely additive, safe to apply mid-traffic.
- `scripts/apply_migration.py` — Management API runner for SQL migrations.
- `scripts/core/context_builder.py` — `get_entity_context(lead_id)` returns relationship stage, sentiment trajectory, and a compose-ready prompt block. Foundation for persona-aware LLM drafts.
- `scripts/test_send_gateway.py` — 17 tests covering golden, suppression, cooldown, daily cap, dry-run, input validation, SMTP failure, brand identity, auto-create lead, sentiment, stage inference. Must pass before any gateway change ships.
- `skills/send-gateway/SKILL.md` — full caller contract and extension guide.

**Engines rewired (four):** `outreach_engine`, `email_engine`, `funnel_nurture`, `booking_engine`. Each delegates physical send + CASL + logging to the gateway; each keeps only its business-specific logic (template rendering, .ics generation). The fifth engine, `outreach_batch` (semi-auto cold-outreach with Telegram approval), was retired 2026-05-16 — CC opted out of auto-drafted cold outreach; inbound notifications now flow through `funnel_fast_poll` instead.

**Still outside the chokepoint (tracked):** The N8N `OASIS Inbound Qualifier` workflow writes replies directly via Gmail node — closing this is a one-node N8N change (add a Supabase write to `lead_interactions` with `agent_source='n8n_inbound'`). Documented as follow-on work.

---

## 1. System Overview

Business-Empire-Agent is not a chatbot. It is an autonomous AI operations hub — a persistent intelligence layer that runs alongside CC's business empire, multiplying his capacity through automation, self-improving through every interaction, and maintaining perfect continuity across multiple AI interfaces and tools.

The core insight that shaped every design decision: **one person cannot be everywhere at once, but one intelligence system can**. CC operates across multiple brands (OASIS AI Solutions, PropFlow, Nostalgic Requests), multiple platforms (social media, CRMs, code repos, payment systems), and multiple AI tools simultaneously. Bravo is the shared brain that makes all of them act as one coordinated entity rather than isolated silos.

### What Bravo Actually Does

- Executes tasks across code, content, outreach, automation, finance, and media
- Maintains persistent memory and state across all AI sessions
- Self-improves by logging every mistake, pattern, and insight into a queryable knowledge base
- Manages 8 external application codebases through a routing registry
- Orchestrates 14 specialized subagents, each calibrated for their domain
- Bridges three separate AI interfaces (Claude Code, Gemini CLI, Antigravity IDE) into a single coherent system

### What Bravo Is Not

- Not a monolithic application. No server. No process to kill.
- Not a database of tools. It is a reasoning system that uses tools.
- Not tied to any single AI model. The model executes Bravo's instructions; Bravo defines the behavior.

---

## 2. Core Architecture

### The Three-Interface Model

```
CC
 ├── Claude Code (Opus 4.6)       → Lead Architect — complex reasoning, code, debugging
 ├── Gemini CLI                   → Fast diagnostics, heartbeat, audits, fallback execution
 └── Antigravity IDE              → Local native agent — multi-model, workflow execution
      └── Telegram Bridge         → Remote execution via mobile — routes to Gemini/Claude CLI
```

**Why three interfaces instead of one?**

Because each AI interface has different strengths and different costs. Opus is expensive but architecturally brilliant — use it for complex multi-file work. Gemini CLI is fast and cheap — use it for heartbeats, status checks, and routine diagnostics. Antigravity runs natively in the IDE with multi-model support and is the best tool for workflow execution and editor-integrated tasks.

The real insight is that these three interfaces must share state perfectly, or the three-interface model becomes a liability instead of an asset. CC cannot afford to re-explain context every time he switches tools. This is why Rule 0 in CLAUDE.md is non-negotiable: every action taken in any interface must update the shared state immediately.

### Shared State: The Binding Layer

All three interfaces read from and write to the same files in the `Business-Empire-Agent` repository:

```
brain/STATE.md           — current operational reality (ephemeral, updated constantly)
memory/ACTIVE_TASKS.md   — task queue and status (ephemeral)
memory/SESSION_LOG.md    — full audit trail of all actions by all agents (append-only)
```

This is intentionally file-based. The alternative — a central API server that all interfaces call — was rejected because it introduces a single point of failure. If the API server is down, all three AI interfaces go blind. Files, by contrast, work offline, are trivially version-controlled with git, and are directly human-readable without any query layer.

Supabase provides a queryable analytics layer on top of the file-based truth, but files always win on conflict (see Section 6 for the full persistence strategy).

---

## 3. Brain System

The `brain/` directory is the agent's identity and governing intelligence. It is always loaded at session start and provides the immutable constraints that govern every action.

### File Inventory and Why Each Exists

| File | Purpose | Mutability |
|------|---------|------------|
| `SOUL.md` | Identity, values, personality | IMMUTABLE — CC only |
| `INTERACTION_PROTOCOL.md` | Logging rules, sync protocol, governance | SEMI-MUTABLE — agent proposes, CC approves |
| `BRAIN_LOOP.md` | 10-step reasoning protocol | SEMI-MUTABLE |
| `HEARTBEAT.md` | Proactive monitoring patterns | GOVERNED — probationary system |
| `GROWTH.md` | Capability evolution tracking | GOVERNED |
| `CAPABILITIES.md` | Tool and integration registry | GOVERNED |
| `AGENTS.md` | 14-subagent registry and routing matrix | GOVERNED |
| `APP_REGISTRY.md` | External app routing table | GOVERNED |
| `STATE.md` | Current operational state | EPHEMERAL — updated every session |
| `CHANGELOG.md` | Self-modification audit trail | FREELY MUTABLE |
| `USER.md` | CC's profile and preferences | — |

### Why SOUL.md Is Immutable

SOUL.md defines who Bravo is: the values, the personality, the prime directive. This is the one file the agent cannot modify. The reasoning is not philosophical — it is architectural. An agent that can rewrite its own identity constraints can silently drift away from its intended purpose. If Bravo could edit SOUL.md, there would be no reliable way to know whether it was still acting in CC's interests or had optimized itself toward some other objective.

Immutability here is a trust mechanism, not a technical constraint. CC can modify SOUL.md directly. The agent cannot, period.

### Mutability Tiers: Why Five Levels?

A binary "agent can edit / agent cannot edit" model is too coarse. It either locks down everything (the agent can't improve) or unlocks everything (the agent can corrupt its own governance). Five tiers provide granular control:

- **IMMUTABLE**: Identity. Never changes without CC explicitly deciding it.
- **SEMI-MUTABLE**: Governance and reasoning protocols. Agent can propose changes, CC must approve. The proposal goes to `memory/PROPOSED_CHANGES.md`.
- **GOVERNED**: Registries and capability inventories. Agent can modify freely, but new entries are tagged `[PROBATIONARY]` until validated across 3 sessions.
- **FREELY MUTABLE**: Learning files. Mistakes, patterns, reflections. The agent must be able to write to these continuously.
- **EPHEMERAL**: State and task tracking. Completely agent-controlled. Updated constantly.

The probationary system for GOVERNED files deserves particular attention. When an agent creates a new SOP or routing rule, it may have only seen one or two use cases. Tagging it `[PROBATIONARY]` and requiring three validated sessions before promotion prevents premature optimization — the agent doesn't commit to a pattern it hasn't tested.

### STATE.md: The Agent's Working Memory

STATE.md is updated at the end of every session, sometimes mid-session. It contains the agent's current focus area, confidence level, active infrastructure status, recent session summaries, and known blockers. Any agent (Claude, Gemini, or Antigravity) that loads this file gets immediate situational awareness without reading 30 sessions of history.

It is intentionally ephemeral — not preserved as historical record. The SESSION_LOG handles history. STATE.md is "what is true right now."

---

## 4. Memory Architecture

Bravo's memory system is a five-tier architecture inspired by human cognitive memory: some things are always in working memory, some are retrieved on demand, some are occasionally referenced, some are write-only logs, and some are archived cold storage.

### The Five Tiers

```
Tier 1: Brain (Always Loaded)
  brain/SOUL.md, brain/USER.md, brain/STATE.md
  Budget: <500 lines combined
  Rule: Loaded at every session start

Tier 2: Active Memory (Loaded on Demand)
  memory/ACTIVE_TASKS.md, memory/LONG_TERM.md, memory/SOP_LIBRARY.md
  Budget: <300 lines each
  Rule: Read during Brain Loop RECALL step when relevant

Tier 3: Reference Memory (Loaded When Needed)
  memory/PATTERNS.md, memory/MISTAKES.md, memory/DECISIONS.md
  Budget: <200 lines each
  Rule: Read when debugging, planning, or reviewing

Tier 4: Log Memory (Write-Mostly)
  memory/SESSION_LOG.md, memory/SELF_REFLECTIONS.md
  Budget: Unlimited (compressed regularly)
  Rule: Written to frequently, read rarely

Tier 5: Archive (Cold Storage)
  memory/ARCHIVES/*.md
  Budget: Unlimited
  Rule: Historical data, accessed for deep investigations only
```

**Why budget constraints on the upper tiers?** Context window management. AI models have finite context budgets, and loading unbounded memory files at session start would either overflow the context or push out the actual task content. The tier budgets ensure the high-priority files stay lean enough to always load.

### Confidence Scoring

Every memory entry carries a numeric confidence score (0.0–1.0):

| Score | Meaning | Autonomy Level |
|-------|---------|----------------|
| 0.95–1.0 | Verified fact (CC confirmed or test-proven) | Full autonomy |
| 0.8–0.94 | High confidence (observed pattern, 3+ occurrences) | Full autonomy |
| 0.5–0.79 | Medium confidence (1-2 observations) | Execute, show CC result |
| 0.2–0.49 | Low confidence (single uncertain observation) | Plan → CC approves → execute |
| 0.0–0.19 | Speculation | Ask CC before anything |

### Confidence Decay

Facts that aren't re-verified decay automatically:
- After 30 days without verification: confidence -= 0.1
- After 90 days without verification: confidence -= 0.3
- When contradicted by evidence: immediately flag and re-evaluate

Decay prevents the memory from calcifying around outdated facts. A business fact verified six months ago might no longer be true. Decay forces periodic re-verification rather than blind trust.

### Why Dual-Write (Files + Supabase)?

Files are the source of truth. Supabase is the queryable analytics layer. They serve different purposes:

**Files** give you: instant access without network calls, full git history, offline availability, human-readable state, zero query syntax.

**Supabase** gives you: cross-session analytics, activation scoring across all memories, structured search across thousands of entries, historical trends, multi-agent sync without file merge conflicts.

The rule is explicit: on conflict, files win. Supabase is updated from files, never the other way around. This prevents a scenario where a DB write from an old session overwrites a more recent file-based state update.

### Activation Scoring

Not all memories are equally relevant to retrieve. The activation score formula:

```
activation_score = (recency × 0.3) + (frequency × 0.4) + (confidence × 0.3)
```

Frequency is weighted highest (0.4) because frequently-used patterns are the ones most likely to be relevant again. Recency (0.3) captures temporal relevance. Confidence (0.3) ensures unreliable memories aren't surfaced at high priority.

This scoring means a highly-validated pattern used regularly is surfaced faster than a recent but speculative observation. The Supabase `skill_activation` table tracks access counts per pattern and SOP, feeding these weights.

### V6.0 Retrieval Layer (replaces whole-file context loads)

The five-tier model above describes WHERE memories live. The V6.0 retrieval layer changes HOW they enter context.

Instead of `Read memory/MISTAKES.md` (157 lines, ~6KB) on every recall, the agent runs `python scripts/core/memory_retriever.py query "stripe refund"` and gets back ranked snippets with file:line refs in <10ms. The FTS5 index (`state/memory_index.db`) covers `memory/`, `skills/`, `brain/`, and the five entry-point markdown files — 224 sources / 2,800+ chunks at the time of writing.

**Token impact:** a Tier 2 standard load that used to inject ~104K tokens now resolves to ≤1500 tokens of targeted snippets. The agent reads the FULL file only when the snippet's heading suggests context outside the chunk window matters.

**Index freshness:** a `PostToolUse` hook runs `memory_retriever.py update` after every Edit/Write inside the indexed scopes. Update is incremental — files unchanged since their hash was last recorded are skipped.

**Architectural rule (mirrors the V5.5 dual-write rule):** queries hit the FTS5 index first; whole-file reads are an escalation, not a default. `brain/AGENT_ROUTER.md` directs every operator request through this path. See the V6.0 Pillar 2 section above for the full retrieval contract.

---

## 5. Agent Orchestration

### 14 Subagents, Not One Generalist

The agent system is decomposed into 14 specialists instead of using one generalist for everything. The reasoning is cost, quality, and cognitive focus.

A generalist responding to "write a Python script" and "draft an email to a client" has to context-switch between technical and communication modes. A specialist has its context pre-loaded with the right constraints, tools, and mental model for its domain.

### Model Tier Selection

| Tier | Cost | When to Use |
|------|------|-------------|
| **Opus** | Highest | Architect — system design, DB schema, multi-service planning. Problems where a cheaper model's mistake would cost hours to undo. |
| **Sonnet** | Mid | Most subagents — coding, debugging, research, content, video, workflow building. The sweet spot between capability and cost. |
| **Haiku** | Lowest | Documenter, Git Ops, Social Publisher, Explorer. Tasks with well-defined inputs and outputs where creativity is not needed. |

The Architect agent is explicitly flagged "use sparingly" in AGENTS.md because Opus calls are expensive. Architectural decisions happen infrequently. Using Sonnet for architecture saves money and loses very little quality for most decisions.

### Decision Matrix

The routing matrix in AGENTS.md maps task signals to subagent triggers. This is not just documentation — it is the active routing logic. When a task arrives, the matrix determines which subagent mindset and principles to activate.

```
System design question → Architect
Bug report → Debugger
"Post this to LinkedIn" → Social Publisher → Late MCP
New n8n workflow needed → Workflow Builder → n8n-mcp
Client email → Chief of Staff
```

The matrix prevents role confusion. Without it, every task would default to the same generalist behavior, losing the benefits of specialization.

---

## 6. MCP Integration

### 8 MCP Servers

| Server | Purpose | Access Method |
|--------|---------|---------------|
| Playwright | Browser automation, web research | `npx @playwright/mcp --headless` |
| Context7 | Live library documentation | `npx @upstash/context7-mcp` |
| Memory | Persistent knowledge graph | `npx @modelcontextprotocol/server-memory` |
| Sequential Thinking | Structured reasoning | `npx @modelcontextprotocol/server-sequential-thinking` |
| n8n (CLI) | Workflow automation management | `python scripts/integrations/n8n_tool.py` |
| Late (CLI) | Social media posting (8+ platforms) | `python ../CMO-Agent/scripts/late_tool.py` (Maven) |
| Supabase (CLI) | Database queries and migrations | `python scripts/integrations/supabase_tool.py` |
| Stripe (CLI) | Payment and subscription data | `python scripts/integrations/stripe_tool.py` |

### Why MCP Over Raw API Calls?

MCP servers expose tool interfaces to the AI model natively. The model can call `browser_navigate` the same way it calls any other tool — with type-checked parameters, structured responses, and consistent error handling. Raw `curl` calls require the model to construct HTTP requests, parse raw JSON, and handle auth headers manually, which introduces far more failure modes.

The anti-pattern "if MCP fails, fall back to curl" is explicitly banned in CLAUDE.md. A fallback to curl means the system silently operates in a degraded mode without ever surfacing that the MCP is broken. Instead: if an MCP fails, report the error and stop. This forces the broken MCP to get fixed rather than papering over it.

### CLI-First Architecture

Credential-dependent services (n8n, Late, Supabase, Stripe) use Python CLI tools instead of MCP servers. These tools read credentials from `.env.agents` at runtime, support a `--json` flag for structured output, and work identically across Claude, Gemini, and Antigravity. The 4 remaining MCPs (Playwright, Context7, Memory, Sequential Thinking) are all stateless — they require no credentials and run via direct `npx`.

Zero credentials appear in any config file. The config files are safe to commit to git. `.env.agents` is gitignored and is the only place credentials ever live.

### The CLI-Anything Fallback

When MCPs break (and they do — Stripe MCP v0.3.1 silently switched to OAuth proxy mode and broke all `--api-key` auth), the CLI-Anything pattern provides a durable fallback:

```
python scripts/integrations/stripe_tool.py balance
python scripts/integrations/supabase_tool.py select <table> --project bravo
```

These are Python subprocess wrappers that use the official SDKs directly. They support a `--json` flag for structured output, read credentials from `.env.agents`, and work identically across Claude, Gemini, and Antigravity. MCPs are the preferred path; CLI tools are the resilience layer.

---

## 7. Brain Loop

### Why a 10-Step Protocol?

AI models are stateless by default. Each invocation starts fresh. Without a structured reasoning protocol, the model defaults to pattern matching on the most recent context, which means it may act on stale information, repeat past mistakes, skip verification, and fail to learn from failures.

The Brain Loop enforces a consistent reasoning cycle regardless of which model executes it:

```
ORIENT → RECALL → ASSESS → PLAN → VERIFY → EXECUTE → REFLECT → STORE → EVOLVE → HEAL
```

Not every task uses all 10 steps. The complexity scaling is explicit:

| Complexity | Steps Used |
|-----------|-----------|
| Trivial (typo, lookup) | 1, 2, 6 |
| Simple (single file edit) | 1-3, 5-6 |
| Moderate (feature, bug fix) | 1-8 |
| Complex (multi-file, architecture) | All 10 |
| Architectural | All 10 + CC approval at step 4 |

### Multi-Hypothesis Planning (LATS-Inspired)

Step 4 requires generating 2-3 candidate approaches for MODERATE+ tasks, ranking them by feasibility/risk/effort, selecting the best — but tracking the alternatives. This is inspired by Language Agent Tree Search (LATS).

The reason: single-hypothesis planning is fragile. If the chosen approach hits a dead end, the model without alternatives will either give up or start guessing. With ranked alternatives already generated, failure on approach A triggers a clean switch to approach B rather than thrashing.

This matters especially when working across complex codebases. "I'll update this component" can fail because of an unexpected dependency, a type error, or a DB schema constraint. Having approach B ("rebuild from the service layer down") ready before starting means the response to failure is "switching to alternative B" not "trying the same thing again."

### Reflexion on Failure

Step 7 implements structured Reflexion (Shinn et al., 2023). On any task failure:

1. What was attempted?
2. What went wrong specifically?
3. Why did it fail (root cause)?
4. What should be done differently?
5. Confidence in this reflection (0.0-1.0)?

This reflection is stored in `memory/SELF_REFLECTIONS.md` and Supabase. The next time a similar task is attempted, Step 2 (RECALL) surfaces the reflection, and the agent starts with the knowledge of what already failed and why.

Without this mechanism, the agent can repeat the same mistake across sessions. With it, failure is converted to future capability.

### The 3-Attempt Hard Stop

If all approaches fail after 3 total attempts, the protocol mandates a hard stop and escalation to CC. This prevents the agent from:
- Thrashing on a problem it cannot solve autonomously
- Making the situation worse by attempting increasingly desperate fixes
- Wasting CC's compute budget on a losing battle

Three attempts is enough to try the primary and two alternatives. After that, the problem likely requires human judgment.

---

## 8. Skill System

### On-Demand Loading

Skills are not loaded at session start. They are reference documents stored in `skills/[skill-name]/SKILL.md` and loaded only when their domain is relevant. This is critical for context management — loading all 55 skills at session start would consume most of the context budget before the task even begins. Each skill has YAML frontmatter (name, description, triggers, tier, dependencies) enabling progressive 3-tier loading per `skills/SKILL_LOADING.md`.

Skills are activated by:
- Explicit triggers (`/debug` command → loads `systematic-debugging/SKILL.md`)
- Task domain matching (bug reported → BRAIN_LOOP step 2 surfaces debugging skill)
- Direct `@skills/` references in instructions

### Skill Categories

| Category | Purpose |
|---------|---------|
| Agent Intelligence | Self-healing, memory management, heartbeat, SOP breakdown |
| Development | TDD, systematic debugging, executing plans, git worktrees |
| Browser & Testing | Playwright MCP reference, E2E testing with parallel sub-agents |
| Content | Brand guidelines, writing, internal comms |
| Code | MCP builder, code review, parallel agents |
| Automation | n8n patterns, Supabase patterns, AI integration |
| Security | Security protocol, credential handling |
| CLI & Integration | CLI-Anything (universal CLI wrapper generation) |

### The PROBATIONARY → VALIDATED Lifecycle

New skills and patterns start with a `[PROBATIONARY]` tag. They are used experimentally for 3 sessions. If they succeed consistently, they are promoted to `[VALIDATED]`. If they cause errors, they are tagged `[UNDER_REVIEW]`.

This lifecycle prevents two failure modes:
1. **Too loose**: Accepting a pattern after one successful use means one lucky result becomes entrenched behavior.
2. **Too strict**: Requiring exhaustive proof before using a pattern means the system can't adapt quickly enough to new situations.

Three sessions is the calibrated middle ground — enough to see the pattern work across different contexts, not so many that the system is frozen waiting for proof.

### Skill Compositionality (Voyager-Inspired)

Complex skills are built from simpler ones, and this composition is tracked explicitly:

```
Content Pipeline = Content Pillars + Platform Char Limits + Late API Posting + CC Voice Rules
Bug Investigation = Brain Loop (1-8) + Error Log Reading + Hypothesis Generation + Minimal Fix
Lead Enrichment = Gmail Scanning + Playwright Research + Notion CRM Entry + Data Validation
```

When a new skill is needed, the first question is always whether it can be assembled from existing skills rather than built from scratch. This prevents skill proliferation and keeps the system DRY.

---

## 9. Security Model

### The Single Secrets File

All credentials live exclusively in `.env.agents`. This file is:
- Gitignored (never committed)
- Read at runtime by wrapper scripts
- Never echoed in logs, chat, or Supabase traces
- The single file to update when credentials rotate

**Why one file?** With credentials spread across multiple config files, rotation requires finding and updating every location. Missing one means a production service fails silently or a stale credential gets committed to git. `.env.agents` as the single source means rotation is one operation.

### What Never Gets Logged

The interaction protocol explicitly lists what is sanitized before any logging:
- API keys, tokens, passwords (never logged anywhere)
- Full request/response bodies containing user data
- Supabase connection strings
- Personal financial account numbers (amounts are fine)
- Full file contents in traces (log filename and line count only)

This is not just policy — it is protocol. Supabase traces contain `input_summary` and `output_summary` fields that are truncated summaries, not full content.

### Supabase Row-Level Security

Every table in the Bravo Supabase project has RLS policies. No table is publicly accessible. This matters because the Supabase anon key is used by the SDK tools — if a table lacks RLS and the anon key is somehow exposed, that table's data is publicly readable. RLS means a leaked anon key exposes nothing without proper authentication.

### Credential Rotation Protocol

If an exposed credential is detected anywhere:
1. STOP all current operations immediately
2. Report to CC in one sentence
3. Initiate rotation — update `.env.agents`, invalidate the old credential in the external service
4. Grep the entire repo for any other instances of the credential string
5. Verify zero instances remain before resuming

The response is fast and deterministic. No judgment calls, no "maybe it's fine."

### V6.0 Hook-Fenced Execution Layer

Single-secrets-file plus RLS plus rotation discipline is the legacy stack. V6.0 adds three Claude Code `PreToolUse` hooks that run BEFORE any tool call reaches its destination — the LLM cannot route around them.

| Tool matcher | Hooks (in order) | What gets blocked |
|--------------|------------------|-------------------|
| `Bash` | `secret_guard` → `exec_guard` | Secret exfiltration commands; destructive SQL/shell; chained-command bypasses; force-push to main |
| `Read` | `secret_guard` | Read of `.env*`, `*.pem`, `*.key`, `credentials.json`, `secrets/` |
| `Edit` / `Write` / `MultiEdit` / `NotebookEdit` | `secret_guard` → `state_guard` | Edit on secret files; edit on auto-generated state mirrors |

Each guard is gated by an env var (`EMPIRE_HOOK_{SECRET,EXEC,STATE}_GUARD` ∈ `enforce` / `report` / `off`). Default safe-mode for fresh installs: secret=`enforce` (lowest false-positive risk), exec=`report` (14-day soak), state=`off` (until V6.0 cutover). Cloud installs flip all three to `enforce`. Every block writes a JSONL audit row to `state/{guard}.log`.

Hook commands are anchored to `${CLAUDE_PROJECT_DIR}` so they resolve correctly no matter what directory Bash is operating in — a `cd` mid-session can never break the hooks.

**The threat model:** the LLM itself, not a remote attacker. Prompt injection forces the LLM to attempt destructive or exfiltration ops; the hooks catch them before the tool layer fires. The V5.5 protocol said "agents shouldn't read .env.agents." V6.0 says "agents CAN'T."

### Secret Loader (CLI-tool-only credential access)

Scripts that need credentials no longer parse `.env.agents` themselves. They import `from lib.secret_loader import load_env`. The loader:

- Reads `.env.agents` once per process and caches in module scope.
- **Refuses to load** if the calling script lives in `tmp/` (LLM-written one-off scripts can't harvest secrets).
- **Refuses to load** if `PYTHONINSPECT=1` is set or the process is interactive (`python -i`).
- Logs every access to `state/secret_access.log` with `{ts, caller_path, keys_accessed}` for audit.

The CLI tool wrappers (`stripe_tool.py`, `supabase_tool.py`, `google_tool.py`, `n8n_tool.py`, `late_tool.py`, etc.) are the only path the agent uses to touch credentials. They load via the secret_loader, make their API call, and return ONLY a sanitized JSON payload — never the raw key, never an `Authorization` header, never a refresh token. Errors run through `lib/safe_error.scrub_traceback()` before display.

### Scoped Env Fan-Out (Defense in Depth)

The setup wizard generates three per-service env files at install time, each containing only the keys that service needs:

- `.env.agents.core` — every key (Bravo's autonomous loop needs the full set)
- `.env.agents.webhook` — Stripe webhook secret + Supabase + Telegram + EMPIRE_* (no Anthropic, no service-role)
- `.env.agents.dashboard` — public Supabase anon key + STATE_API_URL only (zero secrets)

Docker Compose mounts the per-service file via `env_file:`. A single-service RCE in `bravo-webhook` cannot exfiltrate Anthropic or service-role keys because they're not in that container's environment. The master `.env.agents` is excluded from `.dockerignore` and never copied into any container layer.

### Regression Suite (`tests/test_hook_regression.py`)

Every known bypass is locked behind a pytest case — 109 tests in
`test_hook_regression.py` covering per-vector behavior of `secret_guard` /
`exec_guard` / `state_guard` including all three Codex Critical findings
(scoped-env fan-out leak, shell-redirect bypass, chained-command leak past
the read-only fast-path) and five self-review follow-ups.

New Codex findings become CODEX-tagged vectors in the per-vector file.

### ~~Operator-Approval Override Flow~~ — DELETED 2026-05-22

This section used to describe a human-in-the-loop approval queue for
exec_guard blocks (BUILD 4 / V6 Apex Phase 2). CC's call: "I don't want
to be an approval bot. The block IS the protection."

The block path in `exec_guard` is unchanged — destructive commands
(DROP TABLE, rm -rf /, git push --force) are still refused outright.
The deletion removed: the `exec_overrides` Supabase table, the
`override_request` SQLite schema, `scripts/state/exec_override*.py`,
`scripts/lib/override_crypto.py`, the override-consumer PM2 daemon,
the dashboard `/overrides` page + `/api/exec-override` route, the
`Overrides pending` mini-tile on /operations, and the
`skills/exec-override/SKILL.md`. If an agent gets blocked, it now
picks a different approach — no queue, no UI, no escalation surface.

---

## 10. Cross-AI Synchronization

### The Multi-Agent Problem

CC uses Claude Code, Gemini CLI, and Antigravity IDE interchangeably throughout the day — sometimes within minutes of each other. Without synchronization, each AI starts a session with stale context and potentially contradicts work done by a previous agent.

The naive solution is a central state server that all agents call. This was rejected for two reasons:
1. Adds a network dependency to every agent session
2. Requires protocol negotiation that adds latency and complexity

### The File-Based Solution

The chosen solution uses git-tracked files as the shared state layer:

```
brain/STATE.md          → agent reads this to know what's happening right now
memory/ACTIVE_TASKS.md  → agent reads this to know what work is in flight
memory/SESSION_LOG.md   → agent reads this to know what other agents have done
```

**After every meaningful action**, the active agent updates these three files. Not at session end. After every action. This is Rule 0 in CLAUDE.md and it is non-negotiable.

The logic: if CC finishes a Claude session and immediately opens Gemini CLI, Gemini must see what Claude just did. If Claude updated STATE.md only at session end but CC switched before the session ended, Gemini operates blind. Continuous updates eliminate this gap.

### The Four Config Files

All three AI interfaces plus the Telegram bridge require MCP configuration. These configurations must stay in sync:

| File | Used By |
|------|---------|
| `.claude/mcp.json` | Claude Code CLI |
| `.vscode/mcp.json` | Antigravity IDE |
| `~/.gemini/settings.json` | Gemini CLI |
| `.env.agents` | Credentials (all interfaces) |

Rule 4 in CLAUDE.md mandates updating all four files whenever any MCP is added, removed, or modified. The failure mode of not doing this: one interface works, two others silently lose a tool, and debugging why Gemini can't post to social media takes an hour when the answer is "its MCP config was never updated."

### App Registry Routing

External app codebases (OASIS, PropFlow, TIKTIK, etc.) are never modified from within Business-Empire-Agent. APP_REGISTRY.md routes app work to the correct local path:

```
CC: "fix the login page in TIKTIK"
→ load brain/APP_REGISTRY.md
→ find TIKTIK → C:\Users\User\APPS\tiktik
→ cd to that path
→ make all changes there
→ commit from there
→ log 1-2 sentence summary to memory/SESSION_LOG.md
→ return to Business-Empire-Agent
```

This separation is architectural, not cosmetic. Business-Empire-Agent contains agent intelligence only. Mixing app source code into the agent repo would make it impossible to maintain clean separation between "the brain" and "the things the brain controls."

---

## 11. Self-Healing

### Five Healing Dimensions

The self-healing system monitors and repairs five categories of degradation:

**1. Memory Self-Healing**: Scans for contradictions between memory files, decays stale facts, compresses SESSION_LOG when it exceeds 200 lines, removes duplicate entries. Triggered at session start, session end, and after memory writes.

**2. Context Self-Healing**: Flags APPS_CONTEXT files not updated in 30+ days, cross-references USER.md against recent CC statements, ensures STATE.md reflects actual system state. Triggered monthly and after CC corrects agent behavior.

**3. Skill Self-Healing**: Tracks skill success rates via Supabase `skill_activation`. Flags skills with below 70% success rate for review. Identifies skill gaps when tasks repeatedly fail because no skill covers that domain.

**4. Infrastructure Self-Healing**: Tests MCP connectivity, validates `.env.agents` has required keys by name (never value), checks git status for unexpected state, flags package dependency issues.

**5. Relationship Self-Healing**: Detects CC frustration signals (redirections, corrections, expressed frustration). Logs calibration failures to SELF_REFLECTIONS.md. Adjusts communication style based on feedback patterns.

### Four Severity Tiers

| Tier | Scope | Response |
|------|-------|---------|
| 1: Auto-Fix | Trivial (junk files, format issues, stale timestamps) | Fix immediately, no CC notification |
| 2: Diagnose & Suggest | MCP auth failures, content limit violations, stale tasks | Fix with one-sentence notification to CC |
| 3: Deep Investigation | Recurring MCP failures, memory contradictions, skill degradation | 5-15 minute investigation, present findings |
| 4: Escalate | Destructive operations needed, credential exposure, unresolvable issues | Immediately surface to CC, stop and wait |

The tier model prevents over-escalation. If every minor issue required CC's attention, the system would be more burden than benefit. Auto-fix handles the trivial; escalation is reserved for genuine decisions that require human judgment.

### Integrity Checks (The Hard-Learned Lessons)

Two non-negotiable checks run after file operations:

**Referential Integrity Scan**: After any file rename, move, or deletion, grep the entire project for the old filename and fix every stale reference. On 2026-03-03, skipping this after deleting two files created 15+ broken cross-references across agents/, commands/, skills/, brain/, and memory/. Any agent loading those files would have had corrupted context. The check is non-negotiable precisely because the consequences of skipping it are invisible until something breaks in a hard-to-debug way.

**Capability Count Verification**: After adding or removing any agent, skill, or workflow, count the actual files and compare against the numbers in CAPABILITIES.md. Stale counts cause confusion about what the system can actually do.

---

## 12. Intentionally Not Included

Understanding what was deliberately left out is as important as understanding what is there.

### No Central Orchestration Server

There is no server process that all agents call. This is a deliberate simplicity choice. A central server would need authentication, availability guarantees, version management, and a deployment pipeline. For a single-operator system that runs on a local machine, this complexity has no return on investment. File-based sync plus git provides all the coordination needed.

### No Real-Time Event Bus

Agents do not emit events that other agents subscribe to. There is no Kafka, no Redis pub/sub, no WebSocket layer. Real-time inter-agent communication was evaluated and rejected. CC's workflow is sequential — he finishes one conversation before starting another. File-based state updates between sessions are sufficient. Real-time pub/sub would add infrastructure complexity that provides no actual workflow benefit.

### No Automated Git Pushes

The agent commits locally but never pushes to remote without explicit CC confirmation. This is a safety boundary. Automated pushes to a remote repository mean any agent mistake is immediately propagated and potentially deployed. The local commit is the checkpoint; the push is the human approval gate.

### No Multi-Tenant Design

This system is built for one operator. There are no user accounts, no tenant isolation, no permission hierarchies beyond the agent's own mutability tiers. Adding multi-tenancy would require restructuring the entire memory and credential model. For an empire-building tool for one person, this complexity would provide no value.

### No Autonomous Deployment

Bravo can write code, commit code, and push code — but it does not automatically deploy to Vercel or trigger production releases without CC's involvement. Deployment is a human gate. The consequences of a bad automated deploy (production downtime, data corruption, customer-facing errors) are severe enough that the gate is worth the friction.

### No Vector Database for Semantic Search

The Supabase `memories` table uses full-text search, not vector embeddings. Vector search would enable more powerful semantic retrieval — finding conceptually similar memories even without keyword overlap. It was not included because the current activation scoring system (recency + frequency + confidence) performs well enough for the actual use patterns, and vector embeddings would require a separate embedding pipeline, additional API costs, and infrastructure complexity. If memory retrieval quality becomes a bottleneck, this is the first upgrade to consider.

---

## Appendix: Key Files Reference

| File | Role | Updated By |
|------|------|-----------|
| `CLAUDE.md` | Claude Code entry point | CC (SEMI-MUTABLE) |
| `GEMINI.md` | Gemini CLI entry point | CC (SEMI-MUTABLE) |
| `ANTIGRAVITY.md` | Antigravity IDE entry point | CC (SEMI-MUTABLE) |
| `brain/SOUL.md` | Identity and values | CC only (IMMUTABLE) |
| `brain/STATE.md` | Current operational state | Agent (EPHEMERAL) |
| `brain/AGENTS.md` | 14-subagent registry | Agent (GOVERNED) |
| `brain/CAPABILITIES.md` | Tool and integration inventory | Agent (GOVERNED) |
| `brain/APP_REGISTRY.md` | External app routing table | CC + Agent (GOVERNED) |
| `brain/BRAIN_LOOP.md` | Reasoning protocol | CC approves changes (SEMI-MUTABLE) |
| `brain/INTERACTION_PROTOCOL.md` | Logging and governance | CC approves changes (SEMI-MUTABLE) |
| `memory/SESSION_LOG.md` | Audit trail of all agent actions | Agent (EPHEMERAL, append-only) |
| `memory/ACTIVE_TASKS.md` | Task queue and status | Agent (EPHEMERAL) |
| `memory/MISTAKES.md` | Error patterns and prevention | Agent (FREELY MUTABLE) |
| `memory/PATTERNS.md` | Validated behavior patterns | Agent (FREELY MUTABLE) |
| `memory/LONG_TERM.md` | High-confidence persistent facts | Agent (FREELY MUTABLE) |
| `memory/SOP_LIBRARY.md` | Standard operating procedures | Agent (GOVERNED) |
| `.env.agents` | All credentials (gitignored) | CC only |
| `scripts/integrations/supabase_tool.py` | Supabase SDK CLI | Agent/CC |
| `scripts/integrations/stripe_tool.py` | Stripe SDK CLI | Agent/CC |
| `scripts/integrations/n8n_tool.py` | n8n REST API CLI | Agent/CC |
| `../CMO-Agent/scripts/late_tool.py` (owned by Maven) | Late social media CLI | Agent/CC |

---

*Architecture documented: 2026-03-18*
*System version: Bravo V5.5 — Self-Evolving Intelligence Engine*
*Owner: Conaugh McKenna (CC), OASIS AI Solutions*

## Obsidian Links
- [[brain/SOUL]] | [[brain/AGENTS]] | [[brain/CAPABILITIES]] | [[brain/BRAIN_LOOP]]
- [[brain/INTERACTION_PROTOCOL]] | [[brain/CEO_OPERATING_SYSTEM]]
- [[skills/INDEX]] | [[.agents/workflows/INDEX]] | [[_templates/INDEX]]
