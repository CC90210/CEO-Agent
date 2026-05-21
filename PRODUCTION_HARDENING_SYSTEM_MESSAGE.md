# SYSTEM MESSAGE — Business-Empire-Agent Production Hardening & Turnkey Finalization

> **Target Agent:** Claude Code (Bravo)
> **Mission:** Transform Business-Empire-Agent from "clean and coherent" into **production-grade, turnkey, zero-surprise infrastructure** — the kind of system that ships to enterprise clients without hesitation
> **Scope:** Full repository — hardening, observability, reliability, deployment readiness, security audit, test suite completion
> **Constraint:** DO NOT break working systems. DO NOT change business logic. DO NOT refactor for aesthetics. This is production hardening, not a rewrite. Every change must have a measurable impact on reliability, observability, or deployment readiness.

---

## CONTEXT & CURRENT STATE

You are operating on `C:\Users\User\Business-Empire-Agent` — CC's (Conaugh McKenna) autonomous AI operations hub. This system has just completed a 7-phase cleanup + verification pass (commit `fa5e123`, 451 files changed). The structural gaps are closed:

- 538 wikilinks fixed across 204 SKILL.md files
- 5 entry points synced (V6.5–V6.8)
- 0/201 script compile errors
- 105/112 tests passing (7 pre-existing failures in TestContextBuilder)
- Docker compose validates cleanly across all 3 files
- SMTP chokepoint unified via `lib/smtp_send.py`
- `.env.agents.template` created with all V6 guard vars
- CI/CD pipeline fixed

**What remains is not broken — it's incomplete for production.** This pass closes the gap between "works on CC's machine" and "ships to anyone."

---

## GOLDEN RULES (NON-NEGOTIABLE)

1. **Read before writing.** Always read the current state of a file before editing.
2. **One change at a time.** Verify each fix before moving to the next.
3. **Never break working code.** If a script works, don't refactor it unless the fix is trivial and measurable.
4. **Preserve git history.** Use edits, not delete+recreate.
5. **Update cross-references.** When you move/rename anything, update ALL references.
6. **Sync entry points.** When you change something that entry points reference, update ALL five.
7. **Log your work.** Update `memory/SESSION_LOG.md` after each phase.
8. **Ask before deleting.** If unsure whether something is dead, flag it for CC.
9. **No drive-by changes.** Fix what's in scope. Don't "while I'm here" refactor.
10. **Verify after every change.** Run the relevant test, check the import, confirm the path.
11. **Production-first mindset.** Every change must answer: "Does this make the system more reliable, observable, or deployable?" If not, skip it.
12. **No silent failures.** Every error path must be explicit, logged, and recoverable.

---

## PHASE 1: RELIABILITY HARDENING (The System Must Not Crash)

### 1.1 Create `scripts/lib/retry.py` — Exponential Backoff + Circuit Breaker

**Problem:** All integration tools (`supabase_tool.py`, `stripe_tool.py`, `google_tool.py`, `n8n_tool.py`) fail silently or crash on API errors. No retry logic, no circuit breaker, no timeout enforcement.

**Deliverable:** A production-grade retry module with:

```python
# scripts/lib/retry.py
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True  # prevent thundering herd
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, httpx.HTTPStatusError)

class CircuitBreaker:
    """Open/half-open/closed state machine.
    - Closed: normal operation, tracks failure count
    - Open: all calls fail immediately, after timeout → half-open
    - Half-open: allow one test call, success → closed, failure → open
    """
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    state: Literal["closed", "open", "half-open"]

@retry(config=RetryConfig())
def api_call(): ...

@circuit_breaker(name="supabase", config=CircuitBreakerConfig())
def db_query(): ...
```

**Requirements:**
- Zero external dependencies (pure Python)
- Thread-safe (use `threading.Lock`)
- JSON-serializable state (for circuit breaker persistence)
- Full docstrings with usage examples
- Unit tests in `scripts/test_retry.py` (minimum 15 tests covering: success on first try, retry on failure, max retries exceeded, jitter randomness, circuit breaker state transitions, recovery timeout, half-open test call)

**Apply to integration tools:**
- `scripts/integrations/supabase_tool.py` — wrap all HTTP calls with `@retry` + `@circuit_breaker(name="supabase")`
- `scripts/integrations/stripe_tool.py` — wrap all Stripe API calls
- `scripts/integrations/google_tool.py` — wrap GWS CLI calls
- `scripts/integrations/n8n_tool.py` — wrap n8n API calls
- `scripts/integrations/firecrawl_tool.py` — wrap Firecrawl API calls

**Verification:** Run each tool with a forced failure (bad API key, wrong URL) and confirm:
- Retry happens 3 times with increasing delay
- Circuit breaker opens after 5 failures
- Half-open state allows one test call after recovery timeout
- All errors are logged with context (tool name, endpoint, error type, retry count)

### 1.2 Create `scripts/state/backup_db.py` — SQLite Backup & Restore

**Problem:** No backup strategy for `state/empire_state.db`, `state/memory_index.db`, `state/site_reputation.db`. One disk failure = state loss. No WAL checkpoint strategy. No point-in-time recovery.

**Deliverable:**

```python
# scripts/state/backup_db.py
"""SQLite backup and restore for V6 state databases.

Usage:
    python scripts/state/backup_db.py backup          # Backup all state DBs
    python scripts/state/backup_db.py restore --file backup_20260521.db  # Restore
    python scripts/state/backup_db.py list            # List available backups
    python scripts/state/backup_db.py verify --file backup_20260521.db  # Verify integrity
    python scripts/state/backup_db.py prune --keep 7  # Keep last 7 backups
"""
```

**Requirements:**
- Uses `sqlite3.Connection.backup()` (native SQLite backup API — consistent snapshot even with WAL mode)
- WAL checkpoint before backup (`PRAGMA wal_checkpoint(TRUNCATE)`)
- Backup files named: `backup_{db_name}_{YYYYMMDD_HHMMSS}.db`
- Backup directory: `state/backups/` (add to `.gitignore` if not already)
- Verification: `PRAGMA integrity_check` on backup file
- Restore: atomic swap (write to temp file, then rename)
- Pruning: keep last N backups, delete older ones
- JSON output for all commands (`--json` flag)
- Cron-compatible (exit 0 on success, exit 1 on failure, all errors to stderr)
- Unit tests in `scripts/test_backup_db.py` (minimum 10 tests)

**Register in cron engine:** Add to `cron_engine.py SEED_JOBS` as a daily job at 03:00:
```python
{"name": "state_backup", "schedule": "0 3 * * *", "action": "python scripts/state/backup_db.py backup --keep 7"}
```

**Verification:**
- Run `backup` → confirm files appear in `state/backups/`
- Run `verify` → confirm integrity check passes
- Run `list` → confirm JSON output with backup metadata
- Run `prune --keep 2` → confirm only 2 most recent remain

### 1.3 Create `scripts/lib/structured_log.py` — JSON Logging Framework

**Problem:** Logging is ad-hoc `print()` calls across the codebase. No structured JSON logging, no log levels, no centralized aggregation. JSONL audit logs exist but aren't queryable.

**Deliverable:**

```python
# scripts/lib/structured_log.py
"""Structured JSON logging for all Empire components.

Usage:
    from lib.structured_log import get_logger
    log = get_logger("send_gateway")
    log.info("Email sent", to="user@example.com", interaction_id="uuid")
    log.error("SMTP auth failed", error="invalid credentials", retry_count=3)
    log.warn("Rate limit approaching", current=95, cap=100)
"""
```

**Requirements:**
- Python `logging` module with JSON formatter (use `python-json-logger` if available, or custom formatter)
- Log levels: DEBUG, INFO, WARN, ERROR, CRITICAL
- Every log entry includes: `timestamp` (ISO 8601), `level`, `module`, `message`, `context` (key-value pairs)
- Log file rotation: `state/logs/{module}.log` → rotate at 5MB, keep 5 rotated files (gzipped)
- Console output: human-readable for interactive use, JSON for daemon mode
- Environment variable: `EMPIRE_LOG_LEVEL` (default `INFO`), `EMPIRE_LOG_FORMAT` (`json` or `text`)
- Backwards compatible: existing `print()` calls in daemons can be replaced incrementally
- Unit tests in `scripts/test_structured_log.py` (minimum 8 tests)

**Apply to critical daemons first (priority order):**
1. `scripts/integrations/send_gateway.py` — replace `print()` with structured log
2. `scripts/dashboard_email_consumer.py` — replace `print()` with structured log
3. `scripts/core/event_router.py` — replace `print()` with structured log
4. `scripts/state/exec_guard.py` — replace `print()` with structured log
5. `scripts/state/secret_guard.py` — replace `print()` with structured log

**Verification:**
- Run each daemon → confirm JSON log files appear in `state/logs/`
- Run `tail -f state/logs/send_gateway.log` → confirm structured output
- Run with `EMPIRE_LOG_LEVEL=DEBUG` → confirm debug messages appear
- Run with `EMPIRE_LOG_FORMAT=text` → confirm human-readable output

---

## PHASE 2: OBSERVABILITY & HEALTH (The System Must Report Its State)

### 2.1 Add Health Check Endpoints to FastAPI Services

**Problem:** Docker compose has no healthcheck definitions for most services. No `/health` endpoints on FastAPI services.

**Deliverable:**

Add `/health` endpoint to all FastAPI services:
- `scripts/state/state_api.py` — add `/health` endpoint
- `scripts/hooks/webhook_listener.py` — add `/health` endpoint (if it exists, or create minimal one)

**Health endpoint response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-05-21T12:00:00Z",
  "version": "V6.8.2",
  "checks": {
    "database": {"status": "ok", "latency_ms": 2},
    "memory_index": {"status": "ok", "chunks": 3042},
    "disk_space": {"status": "ok", "free_gb": 45.2}
  }
}
```

**Add healthcheck directives to Docker compose:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8500/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**Verification:**
- `curl http://localhost:8500/health` → returns valid JSON with status "healthy"
- `docker compose -f infra/docker-compose.local.yml config` → validates with healthcheck directives
- Kill a dependency (e.g., rename state DB temporarily) → health endpoint returns "degraded" with specific check failure

### 2.2 Create `scripts/state/health_aggregator.py` — System Health Dashboard

**Problem:** No single command gives a complete health overview. `self_audit.py` exists but doesn't check everything.

**Deliverable:**

```python
# scripts/state/health_aggregator.py
"""Aggregate health check across all Empire subsystems.

Usage:
    python scripts/state/health_aggregator.py          # Full health report
    python scripts/state/health_aggregator.py --json   # Machine-readable output
    python scripts/state/health_aggregator.py --quiet  # Exit 0 if healthy, 1 if not
"""
```

**Checks to implement:**
1. **State DB:** `empire_state.db` accessible, WAL mode enabled, table count matches schema
2. **Memory Index:** FTS5 index accessible, chunk count > 0, last indexed < 24h ago
3. **Site Reputation:** `site_reputation.db` accessible
4. **Backups:** At least 1 backup in last 24h, latest backup passes integrity check
5. **Guard Modes:** `secret_guard=enforce` (or report), `exec_guard` not off, `state_guard` not off (if V6 mode on)
6. **Daemons:** Check PM2 process list for expected daemons (event-router, override-consumer, sequence-runner, etc.)
7. **API Endpoints:** `/health` on state-api responds within 5s
8. **Disk Space:** `state/` directory < 80% full, `tmp/` < 90% full
9. **Git Status:** Working tree clean (no uncommitted changes), last commit < 7 days ago
10. **Credentials:** `.env.agents` exists, required keys present (not empty)

**Output format:**
```
Empire Health Report — 2026-05-21T12:00:00Z
═══════════════════════════════════════════════
State DB:        ✓ OK (WAL mode, 4 tables, 716 transactions)
Memory Index:    ✓ OK (3042 chunks, indexed 2h ago)
Backups:         ✓ OK (3 backups, latest 6h ago, integrity pass)
Guard Modes:     ⚠ WARN (exec_guard=report, recommend enforce)
Daemons:         ✓ OK (4/4 running: event-router, override-consumer, sequence-runner, lender-classifier)
API Endpoints:   ✓ OK (state-api:8500 healthy, latency 2ms)
Disk Space:      ✓ OK (state: 45% full, tmp: 62% full)
Git Status:      ✓ OK (clean, last commit 1h ago)
Credentials:     ✓ OK (.env.agents present, 42/42 keys set)
═══════════════════════════════════════════════
Overall: HEALTHY (9/9 checks passed, 1 warning)
```

**Verification:**
- Run with all systems healthy → "Overall: HEALTHY"
- Break one system (e.g., rename state DB) → "Overall: DEGRADED" with specific check failure
- Run with `--json` → valid JSON output
- Run with `--quiet` → exit 0 if healthy, exit 1 if not

### 2.3 Create Automated Error → Knowledge Pipeline

**Problem:** Production errors log to JSONL files but never auto-analyze into MISTAKES.md entries. The feedback loop is manual.

**Deliverable:**

```python
# scripts/core/error_knowledge_pipeline.py
"""Parse guard logs and error logs, surface recurring patterns,
auto-suggest MISTAKES.md entries. Closes the production error → knowledge feedback loop.

Usage:
    python scripts/core/error_knowledge_pipeline.py scan      # Scan logs for patterns
    python scripts/core/error_knowledge_pipeline.py suggest   # Suggest MISTAKES.md entries
    python scripts/core/error_knowledge_pipeline.py apply     # Apply suggestions (with CC approval)
"""
```

**Requirements:**
- Parse JSONL logs: `state/exec_guard.log`, `state/secret_guard.log`, `state/secret_access.log`, `state/logs/*.log`
- Group errors by: error type, module, frequency, first seen, last seen
- Identify recurring patterns: same error > 3 times in 24h, same error across multiple modules
- Generate MISTAKES.md entry template for each pattern:
  ```markdown
  ## [ERROR_TYPE] in [MODULE] — [DATE]
  - **Root cause:** [auto-extracted from error context]
  - **Frequency:** [N times in 24h]
  - **Impact:** [affected subsystems]
  - **Prevention:** [suggested fix based on error pattern]
  - **Status:** [PROBATIONARY]
  ```
- Dry-run mode (default): print suggestions without modifying files
- Apply mode: append to MISTAKES.md with CC approval prompt
- Deduplication: skip patterns already documented in MISTAKES.md
- Unit tests in `scripts/test_error_knowledge_pipeline.py` (minimum 8 tests)

**Verification:**
- Run `scan` → confirms log parsing works, shows error groups
- Run `suggest` → generates MISTAKES.md templates for recurring errors
- Run `apply` (with approval) → appends to MISTAKES.md
- Run again → confirms deduplication (no duplicate entries)

---

## PHASE 3: TEST SUITE COMPLETION (The System Must Prove It Works)

### 3.1 Fix `test_send_gateway.py` — 7 Pre-Existing Failures

**Problem:** 7 tests fail in `TestContextBuilder` (tests 02-05 plus 3 others). These are pre-existing failures in context builder fixture mocks.

**Fix:**
- Read `scripts/test_send_gateway.py` and identify the failing tests
- Check if the failures are due to:
  - Mock fixture drift (V6.0-era mocks no longer match current `context_builder.py` interface)
  - Missing test data (Supabase tables not seeded)
  - Import path issues (same as the ones fixed for `test_email_engine.py`)
- Fix the fixtures, not the production code
- Add `conftest.py` fixtures if needed for shared test data
- Verify: `python -m pytest scripts/test_send_gateway.py -v` → all tests pass

**Target:** 69/69 tests passing in `test_send_gateway.py`

### 3.2 Create `scripts/test_health_aggregator.py` — Health System Tests

**Deliverable:** Minimum 12 tests covering:
- All 10 health checks pass when system is healthy
- Each check fails correctly when its dependency is broken
- `--json` output is valid JSON
- `--quiet` exit codes are correct (0 healthy, 1 degraded)
- Health report format matches expected output
- Disk space check handles edge cases (full disk, missing path)
- Credential check handles missing `.env.agents`
- Daemon check handles PM2 not installed

### 3.3 Create `scripts/test_structured_log.py` — Logging Tests

**Deliverable:** Minimum 8 tests covering:
- JSON output format is valid
- Log levels filter correctly (DEBUG vs INFO vs ERROR)
- Context key-value pairs are included in output
- Log rotation works (file > 5MB triggers rotation)
- Console output switches between JSON and text based on env var
- Multiple modules write to separate log files
- Timestamps are ISO 8601
- Error logs include stack traces

### 3.4 Create `scripts/test_backup_db.py` — Backup Tests

**Deliverable:** Minimum 10 tests covering:
- Backup creates valid SQLite file
- Backup passes integrity check
- Restore replaces database atomically
- Restore fails gracefully on corrupted backup
- List returns sorted backup files
- Prune keeps exactly N most recent backups
- WAL checkpoint runs before backup
- Backup handles missing source database gracefully
- JSON output is valid
- Cron-compatible exit codes

### 3.5 Create `scripts/test_retry.py` — Retry/Circuit Breaker Tests

**Deliverable:** Minimum 15 tests covering:
- Success on first try (no retry)
- Retry on transient failure (ConnectionError, TimeoutError)
- Max retries exceeded → raises final error
- Exponential backoff delay calculation is correct
- Jitter adds randomness (test statistical distribution)
- Circuit breaker: closed → open after threshold failures
- Circuit breaker: open → half-open after recovery timeout
- Circuit breaker: half-open → closed on success
- Circuit breaker: half-open → open on failure
- Circuit breaker state persists across process restarts (if using file persistence)
- Thread safety: concurrent calls don't corrupt state
- Retry config validation (negative retries, zero delay)
- Circuit breaker config validation (zero threshold, negative timeout)
- Integration test: mock API with retry + circuit breaker
- Decorator syntax works on class methods

### 3.6 Add Test Runner to `package.json` and `pyproject.toml`

**Problem:** No test script in `package.json` (just echoes error). No `pyproject.toml` for modern Python project configuration.

**Fix:**
- Add to `package.json`:
  ```json
  "scripts": {
    "test": "python -m pytest scripts/ -v --tb=short",
    "test:coverage": "python -m pytest scripts/ --cov=scripts --cov-report=term-missing",
    "test:fast": "python -m pytest scripts/ -v --tb=short -x",
    "lint": "ruff check scripts/",
    "lint:fix": "ruff check --fix scripts/",
    "typecheck": "mypy scripts/ --ignore-missing-imports"
  }
  ```
- Create `pyproject.toml` with:
  ```toml
  [project]
  name = "business-empire-agent"
  version = "6.8.2"
  description = "CC's Autonomous AI Operations Hub"
  requires-python = ">=3.12"

  [tool.pytest.ini_options]
  testpaths = ["scripts"]
  python_files = ["test_*.py"]
  addopts = "-v --tb=short"

  [tool.ruff]
  target-version = "py312"
  line-length = 120
  select = ["E", "F", "W", "I", "N", "UP", "B", "SIM"]
  ignore = ["E501"]  # line length handled by formatter

  [tool.mypy]
  python_version = "3.12"
  warn_return_any = true
  warn_unused_configs = true
  ignore_missing_imports = true
  ```

**Verification:**
- `npm test` → runs pytest, all tests pass
- `npm run lint` → ruff runs, no errors (or fixable errors auto-fixed)
- `npm run typecheck` → mypy runs, no critical errors

---

## PHASE 4: DEPLOYMENT READINESS (The System Must Ship Anywhere)

### 4.1 Create `CHANGELOG.md` — Automated from Conventional Commits

**Problem:** No project-level changelog. No semantic versioning, no release tags.

**Deliverable:**
- Create `CHANGELOG.md` with current version header:
  ```markdown
  # Changelog

  All notable changes to Business-Empire-Agent will be documented in this file.

  The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
  and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

  ## [6.8.2] — 2026-05-21

  ### Added
  - Retry + circuit breaker pattern (`scripts/lib/retry.py`)
  - SQLite backup & restore (`scripts/state/backup_db.py`)
  - Structured JSON logging (`scripts/lib/structured_log.py`)
  - Health aggregator (`scripts/state/health_aggregator.py`)
  - Automated error → knowledge pipeline (`scripts/core/error_knowledge_pipeline.py`)
  - `.env.agents.template` with all V6 guard vars
  - `pyproject.toml` for modern Python project configuration

  ### Fixed
  - 538 broken wikilinks across 204 SKILL.md files
  - Entry point sync (all 5 files now carry V6.5–V6.8)
  - SMTP chokepoint bypasses (unified via `lib/smtp_send.py`)
  - Docker compose paths (all 3 files + Dockerfile)
  - CI/CD pipeline (`deploy-vps.yml` self_audit.py path)
  - 7 test_send_gateway.py failures (context builder fixtures)
  - 2 stale `import _subprocess_helpers` (google_tool.py, notebooklm_tool.py)

  ### Changed
  - Moved `_subprocess_helpers.py` to `scripts/lib/subprocess_helpers.py` (with shim)
  - Moved `_outbound_log_post.py` to `scripts/lib/outbound_log_post.py`
  - Updated README.md stats (160 skills, 196 scripts, 9 MCPs, 8 subagents, 34 workflows)
  ```
- Create `scripts/generate_changelog.py` — parses git log for conventional commits and generates changelog entries
- Add to `package.json` scripts: `"changelog": "python scripts/generate_changelog.py"`

**Verification:**
- `npm run changangelog` → generates valid changelog from git history
- `CHANGELOG.md` has current version header with all cleanup changes listed

### 4.2 Fix `.obsidian/` Plugin Untracking

**Problem:** Plugin binaries (8.2 MB) tracked despite gitignore pattern.

**Fix:**
```bash
git rm --cached .obsidian/plugins/*/main.js .obsidian/plugins/*/styles.css
```

**Verification:**
- `git status` → shows these files as "deleted" (unstaged) — they're still on disk, just untracked
- `.gitignore` already has the patterns — future commits won't include them
- `.obsidian/` directory size in git history will shrink on next push

### 4.3 Add Rate Limiting to API Endpoints

**Problem:** No rate limiting on webhook endpoints, state API, or event feed.

**Deliverable:**

Create `scripts/lib/rate_limiter.py`:
```python
"""Token-bucket rate limiter for API endpoints.

Usage:
    from lib.rate_limiter import RateLimiter
    limiter = RateLimiter(rate=10, burst=20)  # 10 req/s, burst up to 20
    if not limiter.allow(client_id):
        return {"error": "rate_limited", "retry_after": 5}
"""
```

**Requirements:**
- Token-bucket algorithm (not sliding window — simpler, more predictable)
- Per-client rate limiting (by IP, API key, or client ID)
- Configurable rate and burst size
- Thread-safe
- In-memory storage (no persistence needed — rate limits reset on restart)
- JSON output for rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)
- Unit tests in `scripts/test_rate_limiter.py` (minimum 8 tests)

**Apply to:**
- `scripts/state/state_api.py` — add rate limiter to all endpoints
- `scripts/hooks/webhook_listener.py` — add rate limiter to webhook endpoint
- `scripts/core/event_router.py` — add rate limiter to event feed endpoint (if it has one)

**Verification:**
- Send 20 rapid requests → first 20 succeed, 21st returns 429
- Wait for token refill → requests succeed again
- Different client IDs get separate rate limits

### 4.4 Create `scripts/deploy/verify_deploy.py` — Pre-Deploy Gate

**Problem:** No pre-deploy verification script. CI/CD runs tests but doesn't verify deployment readiness.

**Deliverable:**

```python
# scripts/deploy/verify_deploy.py
"""Pre-deploy verification gate. Runs before every production deploy.

Usage:
    python scripts/deploy/verify_deploy.py          # Full verification
    python scripts/deploy/verify_deploy.py --json   # Machine-readable output
    python scripts/deploy/verify_deploy.py --quick  # Critical checks only
"""
```

**Checks:**
1. All tests pass (`pytest scripts/ -q`)
2. Lint passes (`ruff check scripts/`)
3. No compile errors (`py_compile` on all .py files)
4. State DB accessible and healthy
5. Memory index accessible
6. All required env vars present
7. No hardcoded secrets in codebase
8. Docker compose validates
9. Bridge manifest in sync
10. Entry points consistent (all 5 files have matching V6 sections)

**Exit codes:**
- 0: All checks pass — safe to deploy
- 1: Critical check failed — do NOT deploy
- 2: Warning check failed — deploy with caution

**Integrate into CI/CD:** Add as a step in `.github/workflows/deploy-vps.yml` before the deploy step.

**Verification:**
- Run with healthy system → exit 0
- Break one thing (e.g., remove a required env var) → exit 1 with specific failure message
- Run with `--json` → valid JSON output with check results

### 4.5 Update `infra/README.md` — Deployment Documentation

**Problem:** `infra/README.md` may have stale references after compose path fixes.

**Fix:**
- Read current `infra/README.md`
- Update all file path references to match current structure
- Add deployment checklist:
  1. Run `verify_deploy.py` → must pass
  2. Run `health_aggregator.py` → must be healthy
  3. Run `backup_db.py backup` → must succeed
  4. Run `docker compose -f infra/docker-compose.yml config` → must validate
  5. Run `docker compose up -d` → must start all services
  6. Run `curl http://localhost:8500/health` → must return healthy
  7. Run `python scripts/state/health_aggregator.py` → must show all checks green

**Verification:**
- Follow the checklist on local machine → all steps succeed
- README matches actual file paths and commands

---

## PHASE 5: SECURITY AUDIT (The System Must Be Lockdown-Tight)

### 5.1 Run Full Security Scan

**Deliverable:**

Create `scripts/security_audit.py`:
```python
"""Full security audit of the Empire codebase.

Usage:
    python scripts/security_audit.py scan      # Full scan
    python scripts/security_audit.py secrets   # Secret scan only
    python scripts/security_audit injection   # SQL injection scan only
    python scripts/security_audit.py perms     # Permission audit only
"""
```

**Scans to implement:**
1. **Secret scan:** Regex search for API keys, tokens, passwords in codebase (exclude `.env.agents`, `state/`, `tmp/`)
2. **SQL injection scan:** Find all raw SQL execution paths, verify parameterization
3. **Permission audit:** Verify all scripts use `secret_loader.py` (not direct `.env.agents` reads)
4. **Eval/exec scan:** Find all `eval()`, `exec()`, `os.system()` calls — flag if user input reaches them
5. **File traversal scan:** Find all file read/write paths — verify path sanitization
6. **Dependency audit:** `pip audit` + `npm audit` — flag known vulnerabilities
7. **Guard mode audit:** Verify `secret_guard=enforce` is default, `exec_guard` not off in production

**Output:**
```
Security Audit Report — 2026-05-21T12:00:00Z
═══════════════════════════════════════════════
Secret Scan:       ✓ PASS (0 secrets found in codebase)
SQL Injection:     ⚠ WARN (2 raw query paths in supabase_tool.py — parameterized but not enforced)
Permissions:       ⚠ WARN (14 scripts still read .env.agents directly — should use secret_loader)
Eval/Exec Scan:    ✓ PASS (0 unsafe eval/exec calls)
File Traversal:    ✓ PASS (all paths sanitized)
Dependencies:      ✓ PASS (0 known vulnerabilities)
Guard Modes:       ⚠ WARN (exec_guard=report, recommend enforce for production)
═══════════════════════════════════════════════
Overall: PASS WITH WARNINGS (3 warnings, 0 critical)
```

**Verification:**
- Run `scan` → confirms all 7 checks run
- Introduce a fake secret (e.g., `API_KEY = "sk-test-123"`) → secret scan catches it
- Run with `--json` → valid JSON output

### 5.2 Fix Permission Audit Warnings

**Problem:** 14 scripts still read `.env.agents` directly instead of through `secret_loader.py`.

**Fix:**
- Identify the 14 scripts (from security audit output)
- Convert each to use `secret_loader.py`:
  ```python
  # Before:
  from dotenv import load_dotenv
  load_dotenv(PROJECT_ROOT / ".env.agents")
  api_key = os.environ["STRIPE_SECRET_KEY"]

  # After:
  from lib.secret_loader import load_env
  env = load_env()
  api_key = env["STRIPE_SECRET_KEY"]
  ```
- Verify each script still works after conversion

**Target:** 0 scripts reading `.env.agents` directly (all use `secret_loader.py`)

### 5.3 Fix SQL Injection Warnings

**Problem:** `supabase_tool.py` accepts raw query strings via CLI `query "SELECT..."` — parameterized for SDK calls but the raw query entry point is a vector.

**Fix:**
- Add input validation to raw query entry point:
  - Block `DROP`, `DELETE`, `TRUNCATE`, `ALTER` in user-supplied queries
  - Log all raw query executions
  - Add `--dangerous-raw-query` flag to acknowledge risk
- Document the risk in `supabase_tool.py` docstring

**Verification:**
- Run `supabase_tool.py query "DROP TABLE leads"` → blocked with error message
- Run `supabase_tool.py query "SELECT * FROM leads" --dangerous-raw-query` → allowed with warning log

---

## PHASE 6: FINAL VERIFICATION & SYNC (The System Must Prove It's Ready)

### 6.1 Run Full Test Suite

```bash
python -m pytest scripts/ -v --tb=short
```

**Target:** 100% test pass rate (all tests, no exclusions)

**If any tests fail:**
- Fix the test, not the production code (unless the production code is actually broken)
- Document why the test was failing and how it was fixed
- Do NOT skip tests to achieve 100%

### 6.2 Run Full Lint Suite

```bash
ruff check scripts/ --select E,F,W,I,N,UP,B,SIM
ruff format scripts/ --check
```

**Target:** 0 lint errors, 0 format violations

**If any lint errors:**
- Fix them (use `ruff check --fix` for auto-fixable)
- Do NOT add `# noqa` comments unless the warning is a false positive

### 6.3 Run Full Compile Check

```bash
python -c "
import py_compile, glob, sys
errors = []
for f in glob.glob('scripts/**/*.py', recursive=True):
    try:
        py_compile.compile(f, doraise=True, quiet=True)
    except py_compile.PyCompileError as e:
        errors.append(f'{f}: {e}')
if errors:
    print('FAILURES:')
    for e in errors:
        print(e)
    sys.exit(1)
print(f'All {len(glob.glob(\"scripts/**/*.py\", recursive=True))} scripts compile cleanly')
"
```

**Target:** 0 compile errors

### 6.4 Run Full Security Audit

```bash
python scripts/security_audit.py scan
```

**Target:** 0 critical findings, 0 warnings (or all warnings documented and accepted)

### 6.5 Run Full Health Check

```bash
python scripts/state/health_aggregator.py
python scripts/deploy/verify_deploy.py
```

**Target:** "Overall: HEALTHY" and "All checks pass — safe to deploy"

### 6.6 Run Docker Compose Validation

```bash
docker compose -f infra/docker-compose.yml config
docker compose -f infra/docker-compose.local.yml config
docker compose -f infra/docker-compose.cloud.yml config
```

**Target:** All 3 validate without errors

### 6.7 Verify Entry Point Consistency

Run a diff-style check across all 5 entry points:
- CLAUDE.md
- AGENTS.md
- GEMINI.md
- ANTIGRAVITY.md
- OPENCODE.md

**Verify:**
- All have V6.5, V6.6, V6.7, V6.8 sections
- All have matching skill count (160)
- All have matching script count (196)
- All have matching MCP count (9)
- All have matching subagent count (8)
- All have matching workflow count (34)
- All have matching MRR goal ($5,000 USD Net MRR by June 18, 2026)

### 6.8 Update SESSION_LOG.md

Log all changes made, files touched, and any decisions that need CC's review.

### 6.9 Generate Final Summary

Create a summary document listing:
- What was added (new files, new capabilities)
- What was fixed (broken references, failing tests, security gaps)
- What was improved (observability, reliability, deployment readiness)
- What remains as known issues (if any)
- Verification results (test pass rate, lint status, security audit, health check)

---

## PHASE 7: GIT & GITHUB SYNC (The System Must Be Committed)

### 7.1 Stage All Changes

```bash
git add -A
git status
```

### 7.2 Commit with Descriptive Message

```bash
git commit -m "chore: V6.8.3 production hardening — turnkey finalization

Production hardening pass across entire repository.

RELIABILITY:
- Retry + circuit breaker pattern (scripts/lib/retry.py) — applied to all integration tools
- SQLite backup & restore (scripts/state/backup_db.py) — WAL checkpoint, integrity check, cron rotation
- Structured JSON logging (scripts/lib/structured_log.py) — applied to 5 critical daemons

OBSERVABILITY:
- Health check endpoints on all FastAPI services (/health)
- Health aggregator (scripts/state/health_aggregator.py) — 10 subsystem checks
- Automated error → knowledge pipeline (scripts/core/error_knowledge_pipeline.py)

TESTING:
- Fixed 7 test_send_gateway.py failures (context builder fixtures)
- Added test_retry.py (15 tests), test_backup_db.py (10 tests), test_structured_log.py (8 tests)
- Added test_health_aggregator.py (12 tests), test_rate_limiter.py (8 tests)
- Added test_error_knowledge_pipeline.py (8 tests)
- All tests passing (target: 100%)

DEPLOYMENT:
- CHANGELOG.md created with conventional commit generation
- pyproject.toml created (pytest, ruff, mypy config)
- Rate limiter (scripts/lib/rate_limiter.py) — applied to all API endpoints
- Pre-deploy gate (scripts/deploy/verify_deploy.py) — 10 checks
- infra/README.md updated with deployment checklist

SECURITY:
- Full security audit (scripts/security_audit.py) — 7 scan types
- Fixed 14 scripts reading .env.agents directly (now use secret_loader.py)
- SQL injection protection on supabase_tool.py raw query entry point
- .obsidian/ plugin binaries untracked

VERIFICATION:
- 0 compile errors
- 0 lint errors
- 0 security critical findings
- All health checks green
- All Docker compose files validate
- All 5 entry points consistent"
```

### 7.3 Push to GitHub

```bash
git push origin main
```

### 7.4 Verify Push

```bash
git log --oneline -5
git status
```

---

## WHAT NOT TO TOUCH

- `.env.agents` — credentials, CC manages
- `brain/SOUL.md` — immutable
- Supabase production database — read-only unless explicitly asked
- `revenue_events`, `monthly_metrics` tables — financial truth
- Any file CC has explicitly said not to touch
- Business logic in working scripts
- The Telegram bridge (telegram_agent.js) — only add rate limiting, don't refactor
- Existing tests that pass — don't "improve" them, only fix failing ones

---

## COMMUNICATION PROTOCOL

- Report progress after each phase
- Flag any contradictions or ambiguities before acting
- Present deletion candidates to CC before deleting
- Use plain English — CC is a founder, not an engineer
- When done, present a summary: what changed, what's production-ready, what needs attention

---

## SUCCESS CRITERIA

This pass is complete when ALL of the following are true:

1. ✅ All tests pass (100% pass rate, no exclusions)
2. ✅ All scripts compile cleanly (0 errors)
3. ✅ All lint checks pass (0 errors, 0 format violations)
4. ✅ Security audit shows 0 critical findings
5. ✅ Health aggregator shows "Overall: HEALTHY"
6. ✅ Pre-deploy gate shows "All checks pass — safe to deploy"
7. ✅ All 3 Docker compose files validate
8. ✅ All 5 entry points are consistent
9. ✅ CHANGELOG.md exists with current version
10. ✅ pyproject.toml exists with test/lint/typecheck config
11. ✅ Committed to GitHub with descriptive message
12. ✅ SESSION_LOG.md updated with summary

---

*This system message was generated on 2026-05-21 after a deep diagnostic (4 parallel audit agents), a 7-phase cleanup (270+ files touched, commit fa5e123), and a grand-scope third-party audit. It represents the final hardening pass to make Business-Empire-Agent production-grade, turnkey, and ship-ready.*
