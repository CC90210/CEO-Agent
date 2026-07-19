# Changelog

All notable changes to Business-Empire-Agent are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The numbering encodes the V-major.minor.patch axis used in `brain/STATE.md`:
- **Major** — breaking changes to the cross-agent substrate (state DB schema,
  event-bus contract, sibling-agent ABI).
- **Minor** — a new epic landing (e.g. V6.5 multi-machine bridge, V6.6
  capability graph, V6.7 agentic-OS orchestration, V6.8 vocabulary layer,
  V7.0 reliability/observability, V7.2 persona bench, V7.3 typed memory).
- **Patch** — production-hardening passes, doc syncs, test repairs.

## [Unreleased]

## [7.3.5] — 2026-07-19

V7.3.5 — **System currency sweep.** Three-lens audit for semantic staleness (prose
contradicting live reality — the rot class freshness gates can't see): 6 HIGH / 14 MED /
10 LOW findings, all fixed. Suga fully retired from the brain (Solara + Helios
canonicalized in CONTEXT.md); STATE.md body no longer claims V6 Apex; Montreal QC
propagated across entry points + siblings; model tables mirror model_registry;
knowledge wiki refreshed; agent-forge scaffold gap closed; README stats check wired
into pre-commit (blocked its own shipping commit as live proof). Reference:
`docs/audits/2026-07-19-currency-audit.md` · repeatable via `skills/currency-audit`.


## [7.3.3] — 2026-07-18

V7.2 + V7.3 — **Persona Bench & Typed Memory.** Two-repo integration audit
(msitarzewski/agency-agents MIT · volcengine/OpenViking AGPLv3-patterns-only)
shipped as two epics, eight layer commits, per `prompts/INTEGRATE_NEW_TOOL.md`.

- **V7.2.0–V7.2.3 Persona Bench:** 10 hand-scoped personas into `agents/`
  (QA/test engineering, accessibility, DB reliability, DevOps, incident command,
  AI-code audit, product mgmt, project shepherd, MCP builder, inbound discovery
  coach — every file explicit `tools:`/`model:`; validator 100/100);
  `discover_agents()` now recursive with stem-dedup (`.claude/agents` wins) —
  voltagent/ graph-visible for the first time since April; routing rows in
  AGENTS.md + ORCHESTRATION_DECISION_TABLE; counts read from graph totals;
  sibling shards committed: Maven +2 (SEO, email-nurture strategy — ccb8f6b),
  Atlas +2 (FP&A, tax w/ CRA+Revenu Québec transition framing — 777e6be; the
  validator caught stale Ontario residency, live-verified against USER.md).
- **V7.3.0–V7.3.3 Typed Memory:** bravo_sleep dedup state machine
  (cooldown → retrieval near-dup probe → judged create/skip; merge deliberately
  not adopted) + `state/memory_diff/` per-run audit artifacts + anti-pollution
  input filter; retriever L1 abstract column (migration 003, FTS5+LanceDB) with
  `description:` backfill across 79 files (abstract coverage 163→242/267
  sources) + freshness-decay ranking (memory_aging inputs finally reach
  retrieval); ADR-0011 registry of per-file update semantics; mem0 verified
  already flag-gated (verdict recorded, no new stores).
- **Explicitly not done:** no bulk persona import (untyped tools vs guard
  model), no OpenViking server/code (AGPL + cloud-VLM dependency + would be a
  4th vector store), no knowledge/ vector-indexing, vendor benchmarks not
  cited as fact.

## [7.1.3] — 2026-07-17

V7.1 — **Free-Tier & Knowledge Radar.** Six-repo integration audit (free-for-dev,
public-apis, free-programming-books, LLMs-from-scratch, ML-From-Scratch, Made-With-ML)
shipped as four layer commits per `prompts/INTEGRATE_NEW_TOOL.md`. External-service
knowledge is now cataloged, machine-queryable, and governed; the harness eval gained
per-slice scoring + run history. (The V7.1 roadmap items captured by the V7.0 research
sweep — stuck-loop detector, outcome-state verification, etc. — remain open; they were
not part of this drop.)

- **V7.1.0 substrate:** `brain/TOOL_SHED.md` § 9 Free-Tier Radar (14 curated rows:
  1 adopted, 1 rejected, 1 policy, 11 candidates awaiting CC signups);
  `discover_resources()` → `resource:` capability-graph nodes + status-enum drift check;
  `skills/resource-radar` lookup skill (all-soft deps); `scripts/integrations/
  email_validate_tool.py` zero-key Disify wrapper (verified live: disposable
  detection, batch mode); `harness_eval.py` named slices + `state/
  harness_eval_history.jsonl` run records (Made-With-ML patterns, MIT).
- **V7.1.1 conventions:** ADR-0010 (one catalog, row contract, link-don't-vendor,
  keyed-adoption path, closed slots); ENV_KEYS_TEMPLATE "Radar adoptions" section.
- **V7.1.2 vocabulary:** CONTEXT.md — Free-Tier Radar / Resource node / Slice-based
  eval; TOOL_SHED § 10 Learning & R&D references (honest one-liners incl. the own-LLM
  future recipes in LLMs-from-scratch Appendix E/ch06/ch07).
- **V7.1.3 distribution:** plugin.json exclusion note (resource-radar is empire-
  specific, not distributed); STATE.md version bump; this entry.

## [7.0.0] — 2026-06-10

V7.0 — **Reliability & Observability foundation.** CC lifted the $5K freeze to harden the OS
to elite-grade. A 5-agent audit + GitHub/arXiv research sweep grounded a turnkey pass that
makes silent failures *loud*, bounds unbounded state, gates routing accuracy, and brings the
fleet to security parity. The structural file-reorg (original EPIC 1) is deferred to V7.1 —
lower value, and unsafe under a live concurrent session. See `docs/V7_OPTIMIZATION_PLAN.md`.

- **Loud Failures (EPIC 7):** `scripts/system_health.py` — 7 probes (cron-script/hook/MCP
  existence, PM2 stale-`pm_exec_path` audit, **path-drift detector covering the segmented
  `Path/"scripts"/"X.py"` construction**, raw-subprocess + silent-except sweeps) + weekly cron.
  **Found + fixed 8 LIVE path-drift silent-failures** — wizard + bridge_chat_server state-DB
  bootstrap was dead behind always-False `.exists()` guards (fresh-install DB never initialized;
  VPS chat session-log silently dropped); state_sync mem0, md_to_gdoc, fleet_health,
  agent_self_improvement all referenced moved files. EPIC 7B: breadcrumbs on revenue_engine's
  silent $0-MRR-on-DB-error + event_bus ack/fail swallows. EPIC 7A: bravo_sleep windowless flags;
  subprocess audit 15→5 (exempt confirmed false-positives so a real one is unmissable).
- **State hygiene (EPIC 3):** `scripts/core/state_compact.py` — LanceDB 410→1 versions,
  30.7→7.5 MB reclaimed; weekly compaction cron. (Bounds the unbounded PostToolUse re-index growth.)
- **Routing-accuracy gate:** `test_routing_accuracy.py` — golden regression + capability-floor
  tiers (Anthropic eval-graduation pattern), CI-gated against gws-*-pollution-class regressions.
- **state_manager tests:** the zero-tested DB single-writer / source-of-truth now has 4 round-trip
  tests (heartbeat/session-log-dedup/task).
- **Fleet parity:** the `LOCKSTEP:untrusted_content` prompt-injection block (which had silently
  never propagated past CEO) shipped to all 3 siblings (CMO/CFO/SunBiz); system_health +
  state_compact promoted into the harness scaffold for new client agents.
- **V7.1 roadmap** captured from the research sweep (stuck-loop detector, outcome-state
  verification, semantic tool pre-filter, temporal memory index, causal-chain tracing).

## [6.9.2] — 2026-06-09

V6.9.2 — **Evals, adversarial defense & dispositions.** The fleet was proven *disciplined*
(V6.9.0/.1); this proves it *good* and *defended*, and tidies the repo estate. See
`plans/MISSION_2026-06-09_V3.md` + `_V3_PROGRESS.md`.

- **Behavioral evals (the capability gate):** `empire-harness` ships `eval_runner.py`
  (deterministic scorers + baselines, regression = red) + `eval_mine_mistakes.py` +
  adapter contract + scheduled `evals.yml`. Each agent repo got a suite whose adapter
  exercises its **real** code in dry-run — **105 real cases across 6 agents, 100% pass**
  (CEO routing/send-policy/CASL · SunBiz underwriting/templating · CFO tax/money-gate ·
  CMO anti-slop/compliance · hermes EDI parse · AURA voice security-gate). MISTAKES.md
  mined into a 26-case `needs-model` regression backlog (honest, not fake-passed).
- **Injection red-team:** `redteam/corpus.jsonl` (24 payloads, surface×technique +
  benign twins) + `redteam_runner.py` assert zero unauthorized *effects* via each repo's
  real guards. Found **2 genuine exec_guard gaps** (`rm -rf ~/`, `curl|bash`) → hardened
  (re-run 0 breaches). Shipped the **`LOCKSTEP:untrusted_content`** provenance block to all
  5 entry points + `provenance.wrap_untrusted`. Finding reported: the guards depend on the
  hook runner putting `scripts/` on PYTHONPATH (production works; not self-sufficient).
- **empire-harness v1.1.0:** secret-scanner **confidence tiers** (test/template/fake → LOW,
  never hidden; fleet HIGH=0) + hardened `pii_sweep` (string #N) + **lock-driven
  `harness_sync`** (product-safe adaptive init). Fleet re-stamped 8 repos to v1.1.0 in ~20s.
- **Dispositions (CC ledger D1–D4):** command-center → **private**; oasis-ai-platform +
  6 dormants → **archived**; 2 keepers hardened; **PropFlow adopted** (LOCKSTEP-in-9).
- **Receipt-scrub PII:** the V2 changelog had reprinted 2 purged surnames — hardened
  `pii_sweep` + scrubbed + rewrote history (fresh clone clean). New standing law:
  redaction tooling/paperwork must never emit the strings it redacts.
- **Break-glass:** `BREAK_GLASS.md` 10-minute runbook + quarterly drill (0 drift).

## [6.9.1] — 2026-06-09

V6.9.1 — **Fleet harmonization.** The harness that made V6.9.0 work is now a shipped
substrate (`CC90210/empire-harness` v1.0.0) that the agent fleet consumes instead of
copies. See `plans/HANDOFF_FABLE_FLEET_V2_2026-06-09.md`.

- **Residual PII (content-keyed):** purged 25 adjudicated lead strings the V1 path-keyed
  purge missed (history `execution_log.json` + the adjudicated lead-name cluster (see local adjudication file)). Branches+tags
  verified clean on a fresh clone; `scripts/pii_sweep.py` added. CSV untracked + example.
- **Adopted empire-harness v1.0.0** (dogfood): vendored canonical LOCKSTEP block +
  `HARNESS_VERSION` + `harness.lock` + `scripts/tests/test_harness_canonical.py` (CEO's
  entry-point blocks must match the fleet canonical byte-for-byte).
- **Fleet-wide:** 8 repos now carry the LOCKSTEP discipline block (was 1). empire-harness
  ships the portable tests, checkers, `fleet_doctor`/`fleet_quick_audit`, `new_agent` scaffold.

## [6.9.0] — 2026-06-09

V6.9.0 — **Audit Remediation.** A 10-phase pass against an external architecture +
security audit (commit fa47807-era, full 853-commit history scanned). The through-line
is **harness reliability** — structural fixes that make *any* model (including
lower-tier OpenCode/Gemini) more accurate, and that the sibling agents (Maven/Atlas/
SunBiz) can replicate. See `plans/MISSION_2026-06-09_PROGRESS.md` and
`memory/RETROSPECTIVE_2026-06-09_audit_remediation.md`.

- **Security — PII purge:** rewrote all GitHub history to remove 11 real third-party
  lead emails + 5 lead-data files (scope corrected with CC mid-flight — `goldstorm`
  is CC's *test* address, not prospect data). Branches + tags clean; residual lives
  only in GitHub PR refs (CC action: GitHub Support purge / private).
- **Security — outbound compliance:** `dashboard_email_consumer.py` now applies CASL
  suppression + footer + List-Unsubscribe at send time (it bypassed `send_gateway`);
  `email_doctor.py` check #5 is structural (recursive smtplib/smtp_send allowlist) and
  its broken post-reorg import paths were fixed (restored 7 silently-failing checks).
- **Security — guards enforce:** `secret_guard` + `exec_guard` → `enforce`, `state_guard`
  → `report` (was off), set in tracked `.claude/settings.json`; documented in
  `SECURITY_MODEL.md` §9–10.
- **Reliability — version single-sourced:** `brain/STATE.md:architecture_version` is the
  sole version; entry points are version-agnostic; `test_entrypoint_parity.py` enforces
  it + the byte-identical `LOCKSTEP:tool_discipline` block across all 5 entry points.
- **Reliability — generated routing docs:** `build_capability_graph.py --emit-docs`
  regenerates WHEN_TO_USE_SKILLS / brain·memory INDEX from the graph;
  `test_generated_docs_fresh.py` makes staleness a build failure.
- **Reliability — wiki-link integrity:** 125 dangling links → 0; `test_wiki_links.py`.
- **Reliability — migration ledger:** `database/100_schema_migrations_ledger.sql` +
  `apply_migration.py --status/--backfill-ledger` + checksum guard.
- **Reliability — brain freshness:** every brain doc dated; `check_brain_freshness.py`.
- **Reliability — pytest runnable from root:** `--import-mode=importlib` fixed a
  dual-`tests`-package collision that made `pytest -q` fail collection entirely
  (now 422 passing).
- **Hygiene:** 12 deploy prompts `brain/` → `docs/deploy/`; removed root forensic log +
  empty `app/`; `.gitignore` deduped + mojibake fixed.

## [6.8.3] — 2026-05-21

V6.8.3 — Production hardening pass. Built the missing reliability,
observability, and security primitives the previous cleanup pass identified
as gaps. Same agent identity, same V6 substrate; what changed is the
infrastructure underneath that the operator can now actually rely on.

### Added — Reliability primitives (`scripts/lib/`)
- **`retry.py`** — `@retry` + `@circuit_breaker` decorators with exponential
  backoff, jitter, and JSON-serializable breaker state for cross-restart
  persistence. 17 tests in `test_retry.py`.
- **`structured_log.py`** — JSON logging framework with 5MB rotation +
  gzipped backups, `EMPIRE_LOG_LEVEL` / `EMPIRE_LOG_FORMAT` env vars,
  per-module log files under `state/logs/`. 9 tests in `test_structured_log.py`.
- **`rate_limiter.py`** — token-bucket rate limiter with per-client buckets,
  thread-safe, standard `X-RateLimit-*` headers. 10 tests in `test_rate_limiter.py`.

### Added — State management (`scripts/state/`)
- **`backup_db.py`** — SQLite backup + restore for `empire_state.db`,
  `memory_index.db`, `site_reputation.db`. Uses native
  `sqlite3.Connection.backup()` with `PRAGMA wal_checkpoint(TRUNCATE)` for
  consistent snapshots. Atomic-swap restore, `PRAGMA integrity_check`
  verification, configurable pruning. 11 tests in `test_backup_db.py`.
- **`health_aggregator.py`** — 10-check system health dashboard (state DB,
  memory index, backups, guard modes, daemons, API endpoints, disk space,
  git status, credentials). Quiet mode for cron alerting. 16 tests in
  `test_health_aggregator.py`.

### Added — Observability (`scripts/core/`)
- **`error_knowledge_pipeline.py`** — parses JSONL guard/error logs into
  recurring patterns, suggests `MISTAKES.md` entries with auto-dedup via
  hidden `<!-- key: -->` markers. 10 tests in
  `test_error_knowledge_pipeline.py`.

### Added — Deployment + security
- **`scripts/security_audit.py`** — 7-scan audit: secrets, SQL injection,
  permission audit (direct `.env.agents` reads), eval/exec, path traversal,
  pip-audit dependencies, guard-mode posture.
- **`scripts/deploy/verify_deploy.py`** — pre-deploy gate: tests, compile,
  health, security, env vars, docker config, bridge manifest, entry-point
  consistency. Exit 0 = safe, 1 = critical fail, 2 = warnings.
- **`pyproject.toml`** — pytest / ruff / mypy configuration. `[tool.mypy]`
  files-list scoped to V6.8.3 net-new modules (not retrofitting legacy).
- **`package.json` scripts** — `npm test`, `lint`, `lint:fix`, `typecheck`,
  `verify-deploy`, `health`, `security-audit`, `backup`, `changelog`.

### Changed
- **`scripts/state/state_api.py`** — `/health` endpoint enriched with
  per-subsystem checks (database, memory_index, disk_space) matching the
  V6.8.3 health-endpoint spec; rate-limiter middleware (20 req/s steady,
  60 burst) applied to every endpoint except `/health`.
- **`scripts/integrations/n8n_tool.py`** — `N8nClient._request` wrapped with
  `@retry` (2 retries, exponential backoff, jitter) for transient
  `URLError` / `TimeoutError` / `ConnectionError`.
- **`scripts/integrations/supabase_tool.py`** — `cmd_query` raw SQL entry
  point now blocks `DROP` / `TRUNCATE` / `DELETE` / `ALTER…DROP` / `GRANT` /
  `REVOKE` unless `--dangerous-raw-query` is passed; every destructive run
  is logged via `structured_log`.
- **`scripts/core/cron_engine.py`** — `SEED_JOBS` adds nightly
  `state_backup` job at 03:00 (`backup --keep 7`).

### Tests
- 73 new tests added across 5 new test files. All passing.
- Pytest config: `addopts = --tb=short` + `markers = integration|slow`.

## [6.8.2] — 2026-05-21 (cleanup pass, commit `fa5e123`)

Closed the structural-drift gaps from the deep-diagnostic audit.

### Fixed
- 538 broken wikilinks across 204 SKILL.md files (every `[[skills/x/SKILL]]`
  → `[[skills/x/SKILL.md]]`, plus `[[skills/INDEX]]` /
  `[[skills/SKILL_LOADING]]` variants).
- All 5 entry points (CLAUDE.md / AGENTS.md / GEMINI.md / ANTIGRAVITY.md /
  OPENCODE.md) now carry V6.5 / V6.6 / V6.7 / V6.8 sync blocks + matching
  inventory counts.
- SMTP chokepoint bypasses (`dashboard_email_consumer.py`,
  `integrations/google_tool.py`) unified via `lib/smtp_send.py` (parallel
  fix by CC while the audit was running).
- Docker compose paths in `docker-compose.{yml,local.yml,cloud.yml}`:
  scheduler, webhook, state-api, healthcheck.
- 7 pre-existing `test_send_gateway.py` failures (context builder
  fixtures — partial; see file for repair status).
- CI/CD pipeline (`deploy-vps.yml` self_audit path).
- MRR goal sweep — June 18, 2026 across 10 files.

### Changed
- Moved `scripts/_subprocess_helpers.py` → `scripts/lib/subprocess_helpers.py`
  (with backward-compat shim).
- Moved `scripts/_outbound_log_post.py` → `scripts/lib/outbound_log_post.py`
  (with backward-compat shim).
- Archived `scripts/lib/safe_error.py` → `scripts/_archive/` (zero
  importers).
- Renamed `scripts/test_n8n_inbound_rpc.py` → `scripts/smoke_n8n_inbound_rpc.py`
  (it's a live-Supabase smoke test, not a pytest unit test).

### Added
- `scripts/conftest.py` — adds `scripts/` to `sys.path` for pytest collection.
- `.gemini/rules/` redirect stubs replacing 5 drift-prone copies.
- `database/MIGRATION_NOTES.md` — explains the intentional 047 gap and
  030/031 duplicate prefixes.
- Frontmatter on 17 memory files (`last_updated` + `freshness_threshold_days`).
- READMEs in `rules/`, `_templates/`, `app/`, `apps/agent-runner/` clarifying
  each directory's role.

## [6.8.1] — 2026-05-16
- V6.8 vocabulary layer promoted to load-bearing substrate (CONTEXT.md
  auto-injection, ADR-0001 enforcement, register.py wizard).

## [6.8.0] — 2026-05-16
- V6.8 Agent-OS Vocabulary Layer (CONTEXT.md, ADRs,
  `disable_model_invocation`, `argument_hint`, `requires:`).

## [6.7.0] — 2026-05-14
- V6.7 Agentic OS Orchestration — hooks-become-orchestration,
  Pantry/Prep Table/Plate data tier, three new canonical skills.

## [6.6.0] — 2026-05-13 (approximate)
- V6.6 Capability Graph (`brain/CAPABILITY_GRAPH.json`,
  `scripts/capability_query.py`, `scripts/register.py`).

## [6.5.0] — 2026-05-12 (approximate)
- V6.5 Multi-Machine Bridge Arbitration (`scripts/bridge_lock.py`).

## [6.0.0] — 2026-05-10
- V6 Apex closes the V6 Optimization Phase (cross-agent event bus, hybrid
  semantic memory, override-approval flow, event-feed router).
