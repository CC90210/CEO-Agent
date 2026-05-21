# Changelog

All notable changes to Business-Empire-Agent are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The numbering encodes the V-major.minor.patch axis used in `brain/STATE.md`:
- **Major** — breaking changes to the cross-agent substrate (state DB schema,
  event-bus contract, sibling-agent ABI).
- **Minor** — new V6.x epic landing (V6.5 multi-machine bridge,
  V6.6 capability graph, V6.7 agentic-OS orchestration, V6.8 vocabulary layer).
- **Patch** — production-hardening passes, doc syncs, test repairs.

## [Unreleased]

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
