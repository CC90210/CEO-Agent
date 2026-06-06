# V7.0 STRUCTURAL OPTIMIZATION PLAN

> **Generated:** 2026-05-21 · **Last revised:** 2026-06-06
> **Author:** Bravo (Lead Architect)
> **Target Executor:** Codex / Claude Code / any AI coding agent
> **Scope:** File structure reorganization, CI/CD pipeline, test coverage expansion, LanceDB compaction, dead directory cleanup, import system solidification, turnkey deployment hardening, **silent-failure observability (EPIC 7, added 2026-06-06)**
> **Risk Level:** Medium — structural changes, guarded by migration-style execution

---

## ⛔ STATUS: FROZEN until $5K MRR hit (target 2026-06-18, 12 days out as of 2026-06-06)

Per CC's 2026-06-06 decision, V7 structural work is paused while the team executes the $5K Net MRR goal. Resume after the deadline.

### Revised execution rules (CC 2026-06-06):
1. **EPIC 1 reorg shape:** surgical move of the ~50 canonical scripts only, **no backward-compat shims**, single-PR import audit. Long-tail utilities (one-off scripts, CLIs, codemods) stay at `scripts/` root. Cleaner end-state than 187 files + 187 shims.
2. **Test location:** `scripts/tests/` is canonical (not `tests/` at repo root as originally drafted). Today's 11-file move to `scripts/tests/` stays. EPIC 2's `testpaths` and CI workflow examples below should reference `scripts/tests/`.
3. **EPIC 7 added** ("Loud Failures"): codifies the silent-failure pattern fixes from 2026-06-06. See bottom of this doc.
4. **Already done in the 2026-06-06 hygiene session** (reduces remaining V7 scope):
   - EPIC 2 partial: 11 test_*.py moved from `scripts/` root to `scripts/tests/`; conftest.py cascade verified; 185/186 tests passing (1 pre-existing failure unrelated)
   - EPIC 3 partial: rotate_logs.py force-rotated `state/secret_access.log` (16 MB → 0); 3 new SEED_JOBS in cron_engine.py for tmp_hygiene, log_rotation_audit, event_offline_drain (still need `cron_engine.py seed` push from CC)
   - EPIC 4 partial: tmp/ purged 6.0 GB → 5.4 MB; 3 orphan markdowns reconnected; 20 undocumented scripts now documented in CAPABILITIES.md
   - Adjacent fixes: retriever_postedit Windows TypeError + path bug (43506be, 433b92d); event_router PM2 stale-path + import-order bug (3731e42); CLAUDE.md inventory drift (da57b73); sibling entry-point sync (454eba5, fa47807)

---

## EXECUTIVE SUMMARY

CEO-Agent is a production-grade autonomous AI operations hub with 187 Python scripts, 153 skill directories, 60 SQL migrations, 15 subagent definitions, and a mature V6 architecture (SQLite WAL state, FTS5+LanceDB hybrid retrieval, hook-fenced execution, secret isolation). The architecture is sound; the gaps are **organizational** and **operational**.

**Seven optimization epics** will transform this from "impressive but messy" to "turnkey foundation anyone can build on":

| Epic | Impact | Effort | Risk |
|---|---|---|---|
| 1. Scripts reorganization | High | Medium | Low |
| 2. CI/CD + test coverage | High | Medium | Low |
| 3. State & memory hygiene | Medium | Low | Low |
| 4. Dead code & directory cleanup | Low | Low | None |
| 5. Import system & package structure | High | Low | Medium |
| 6. Turnkey deployment hardening | High | Medium | Low |
| 7. Loud Failures (silent-failure observability) — added 2026-06-06 | High | Medium | Low |

---

## EPIC 1: SCRIPTS REORGANIZATION

### Problem
187 Python files in a flat `scripts/` directory. 155 files at the top level of `scripts/`, 31 in subdirectories. No one can navigate this without grep. New contributors (human or AI) have no mental model of where things live.

### Target Structure

```
scripts/
├── engines/              # Business logic engines (12 files)
│   ├── outreach_engine.py
│   ├── email_engine.py
│   ├── lead_engine.py
│   ├── revenue_engine.py
│   ├── booking_engine.py
│   ├── funnel_nurture.py
│   ├── cron_engine.py
│   ├── cron_dispatcher.py
│   ├── autonomous_agent.py
│   ├── sequence_runner.py
│   ├── maml_onboard.py
│   └── proposal_generator.py
│
├── tools/                # CLI tool wrappers (25 files)
│   ├── supabase_tool.py
│   ├── stripe_tool.py
│   ├── google_tool.py
│   ├── n8n_tool.py
│   ├── firecrawl_tool.py
│   ├── kixie_tool.py
│   ├── mem0_tool.py
│   ├── notebooklm_tool.py
│   ├── text_torrent_tool.py
│   ├── cloak_browser_tool.py
│   ├── browse_and_capture.py
│   ├── browser_harness_doctor.py
│   ├── browser_connect.py
│   ├── research_fetch.py
│   ├── notify.py
│   ├── transcribe.py
│   ├── music_control.py
│   ├── computer_control.py
│   ├── md_to_gdoc.py
│   ├── scrape_firecrawl_leads.py
│   ├── cloudflare_admin.py
│   ├── supabase_admin.py
│   ├── gateway_admin.py
│   ├── vercel_env_tool.py
│   └── vercel_relink_command_center.py
│
├── state/                # State management (8 files)
│   ├── state_manager.py
│   ├── state_sync.py
│   ├── state_guard.py
│   ├── state_api.py
│   ├── event_bus.py
│   ├── event_router.py
│   ├── exec_guard.py
│   └── exec_override.py
│
├── memory/               # Memory system (10 files)
│   ├── memory_retriever.py
│   ├── memory_chunker.py
│   ├── memory_index.py
│   ├── memory_ingest.py
│   ├── memory_aging.py
│   ├── memory_consolidation.py
│   ├── memory_query.py
│   ├── neural_memory.py
│   ├── retriever_postedit.py
│   └── context_manager.py
│
├── security/             # Security & compliance (8 files)
│   ├── secret_guard.py
│   ├── scan_secrets.py
│   ├── audit_mcp_secrets.py
│   ├── casl_compliance.py
│   ├── pii_scrubber.py
│   ├── audit_rls_coverage.py
│   ├── audit_no_visible_subprocess.py
│   └── exec_override_consumer.py
│
├── integrations/         # Integration health & sync (10 files)
│   ├── integration_health.py
│   ├── catalog_sync.py
│   ├── funnel_sync.py
│   ├── sync_mrr.py
│   ├── sync_slash_commands.py
│   ├── sync-from-github.sh
│   ├── n8n_inbound_doctor.py
│   ├── n8n_webhook_secret.py
│   ├── sibling_repos.py
│   └── reap_orphan_mcps.py
│
├── analytics/            # Analytics & reporting (10 files)
│   ├── ceo_dashboard.py
│   ├── daily_brief.py
│   ├── client_health.py
│   ├── financial_model.py
│   ├── tft_forecast.py
│   ├── cost_audit.py
│   ├── cost_tracker.py
│   ├── competitive_intel.py
│   ├── skill_metrics.py
│   └── update_readme_stats.py
│
├── agents/               # Agent lifecycle (8 files)
│   ├── agent_heartbeat.py
│   ├── agent_inbox.py
│   ├── agent_self_improvement.py
│   ├── register.py
│   ├── register_skill.py
│   ├── capability_query.py
│   ├── build_capability_graph.py
│   └── model_router.py
│
├── gateway/              # Message gateway (4 files)
│   ├── send_gateway.py
│   ├── outreach_eligible.py
│   ├── personalize.py
│   └── rlhf_outreach.py
│
├── hooks/                # Existing hooks directory (5 files — KEEP AS IS)
│   ├── session_start.py
│   ├── user_prompt_submit.py
│   ├── pre_compact.py
│   ├── rotate_logs.py
│   └── subprocess_guard.py
│
├── lib/                  # Shared libraries (8 files — KEEP AS IS)
│   ├── __init__.py
│   ├── secret_loader.py
│   ├── safe_error.py
│   ├── hook_runtime.py
│   ├── subprocess_ast.py
│   ├── exec_override_mirror.py
│   └── override_crypto.py
│
├── cli_templates/        # CLI templates (KEEP AS IS)
├── contract_generator/   # Contract generator (KEEP AS IS)
├── mcp_shims/            # MCP shims (KEEP AS IS)
├── mousetool/            # Mouse tool (KEEP AS IS)
├── snapshots/            # Snapshots (KEEP AS IS)
├── underwriting/         # Underwriting (KEEP AS IS)
├── _archive/             # Archive (KEEP AS IS)
│
├── admin/                # Admin & ops scripts (15 files)
│   ├── apply_migration.py
│   ├── setup_wizard.py
│   ├── system_health_check.py
│   ├── system_cleanup.py
│   ├── onboarding_diagnostics.py
│   ├── code_health.py
│   ├── email_doctor.py
│   ├── crm_reset.py
│   ├── migrate_leads_to_tenant_records.py
│   ├── migrate_subprocess_calls.py
│   ├── backfill_exec_overrides_workspace.py
│   ├── backfill_sunbiz_stages.py
│   ├── ensure_cockpit.py
│   ├── scaffold.py
│   └── wire_all_templates.py
│
├── scheduling/           # Scheduling (5 files)
│   ├── scheduler.py
│   ├── schedule_helpers.py
│   ├── pulse_publish.py
│   ├── quest_publisher.py
│   └── webhook_listener.py
│
├── ai/                   # AI & ML utilities (6 files)
│   ├── gnn_skill_router.py
│   ├── neuro_symbolic_gate.py
│   ├── skill_synthesizer.py
│   ├── auto_dream.py
│   ├── auto_score_leads.py
│   └── draft_critic.py
│
├── windows/              # Windows-specific (KEEP — platform isolation)
│   ├── ai_operator.ps1
│   ├── ai_workstation_doctor.ps1
│   ├── bravo_console_launcher.vbs
│   ├── bravo_startup.pyw
│   ├── fix_watchdog_task.ps1
│   ├── harden_powershell_profile.ps1
│   ├── harden_windows.ps1
│   ├── skool_watchdog_silent.pyw
│   ├── start-oasis.bat
│   ├── stop-oasis.bat
│   └── windows_bootstrap.md
│
├── macos/                # macOS-specific (extract from root)
│   ├── macos_control.py
│   ├── ssh-setup-mac.sh
│   ├── bravo-session-start.sh
│   └── bravo-session-end.sh
│
└── [remaining root-level files that don't fit categories]
    ├── _audit_usage.py
    ├── _bridge_manifest.json
    ├── _call_sheet_v2.py
    ├── _outbound_log_post.py
    ├── _reconcile_gmail_sent.py
    ├── _subprocess_helpers.py
    ├── _write_call_sheet.py
    ├── admin_collect_security_snapshot.ps1
    ├── admin_enable_ai_workstation_features.ps1
    ├── admin_secure_network_surface.ps1
    ├── anti_pattern_hook.py
    ├── bridge_lock.py
    ├── build_bridge_manifest.py
    ├── build_maven_env.py
    ├── c_suite_context.js
    ├── check_bridge_manifest.py
    ├── context_builder.py          ← CRITICAL: stays at root for backward compat
    ├── critic_template_check.py
    ├── dns_reputation.py
    ├── drift_autofix.py
    ├── fleet_health.py
    ├── generate_covers.py
    ├── inbound_classifier.py
    ├── lender_response_classifier.py
    ├── name_utils.py
    ├── provision_client_tenant.py
    ├── region_inference.py
    ├── seed_plan_template.py
    ├── seed_profile.py
    ├── self_audit.py
    └── windows_control.py
```

### Migration Rules

1. **Every moved file gets a backward-compat shim** at the old path:
   ```python
   # scripts/send_gateway.py (OLD PATH — DEPRECATED)
   import warnings
   warnings.warn("scripts/send_gateway.py moved to scripts/gateway/send_gateway.py", DeprecationWarning)
   from scripts.gateway.send_gateway import *  # noqa: F401, F403
   ```

2. **`context_builder.py` stays at root** — it's referenced in ARCHITECTURE.md, skills, and likely external systems. Move in a future epic with a full audit.

3. **Files prefixed with `_` stay at root** — they're internal utilities, not public API.

4. **PowerShell/Windows files move to `scripts/windows/`** — platform isolation.

5. **macOS files extract from root into `scripts/macos/`** — platform isolation.

### Execution Order

```
Phase 1A: Create directory structure (no moves yet)
Phase 1B: Move engines/ (12 files) + create shims
Phase 1C: Move tools/ (25 files) + create shims
Phase 1D: Move state/ (8 files) + create shims
Phase 1E: Move memory/ (10 files) + create shims
Phase 1F: Move security/ (8 files) + create shims
Phase 1G: Move integrations/ (10 files) + create shims
Phase 1H: Move analytics/ (10 files) + create shims
Phase 1I: Move agents/ (8 files) + create shims
Phase 1J: Move gateway/ (4 files) + create shims
Phase 1K: Move admin/ (15 files) + create shims
Phase 1L: Move scheduling/ (5 files) + create shims
Phase 1M: Move ai/ (6 files) + create shims
Phase 1N: Move windows/ + macos/ platform dirs
Phase 1O: Update all import references across the codebase
Phase 1P: Run full test suite — verify zero breakage
Phase 1Q: Update ARCHITECTURE.md, brain/CAPABILITIES.md, brain/QUICK_REFERENCE.md
```

---

## EPIC 2: CI/CD + TEST COVERAGE EXPANSION

### Problem
- 14 test files, 86 test functions, 187 Python scripts → ~0.8% file-level coverage
- `.github/workflows/` has 2 files but no test/lint pipeline
- `package.json` has `"test": "echo \"Error: no test specified\" && exit 1"`
- No linting (ruff, black, mypy), no type checking, no pre-commit hooks

### Target State

#### 2A: GitHub Workflows

Create three workflows:

**`.github/workflows/test.yml`**
```yaml
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov ruff mypy
      - run: pytest tests/ -v --cov=scripts --cov-report=xml --cov-report=term-missing
      - run: ruff check scripts/ tests/
      - run: ruff format --check scripts/ tests/
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

**`.github/workflows/lint.yml`**
```yaml
name: Lint & Format
on: [pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff mypy
      - run: ruff check scripts/ tests/ --output-format=github
      - run: ruff format --check scripts/ tests/
      - run: mypy scripts/ --ignore-missing-imports --no-error-summary
```

**`.github/workflows/deploy-vps.yml`** (EXISTING — keep, add test gate)

#### 2B: Test Coverage Targets

| Module | Current Tests | Target Tests | Priority |
|---|---|---|---|
| `send_gateway.py` | 17 (in test_send_gateway.py) | 25 | P0 — already good, expand edge cases |
| `event_bus.py` | ✓ (test_event_bus.py) | 20 | P0 |
| `state_manager.py` | 0 | 20 | P0 — critical path |
| `memory_retriever.py` | ✓ (test_retrieval_hybrid.py, 22 tests) | 30 | P0 |
| `secret_guard.py` | ✓ (in test_hook_regression.py) | 15 | P1 |
| `exec_guard.py` | ✓ (in test_hook_regression.py) | 15 | P1 |
| `context_builder.py` | 0 | 12 | P1 |
| `apply_migration.py` | 0 | 10 | P1 |
| `inbound_classifier.py` | 0 | 10 | P2 |
| `lead_engine.py` | 0 | 12 | P2 |
| `outreach_engine.py` | 0 | 12 | P2 |
| `email_engine.py` | ✓ (test_email_engine.py) | 15 | P2 |
| `secret_loader.py` | 0 | 10 | P1 |
| `bridge_lock.py` | 0 | 8 | P2 |
| `pulse_publish.py` | 0 | 8 | P2 |
| `revenue_engine.py` | 0 | 10 | P2 |
| `booking_engine.py` | 0 | 10 | P2 |
| **Total** | **86** | **242** | |

#### 2C: Test Infrastructure

Create `tests/fixtures/` directory with:
- `mock_supabase.py` — Supabase client mock with realistic responses
- `mock_stripe.py` — Stripe client mock
- `mock_google.py` — Google Workspace mock
- `mock_n8n.py` — n8n webhook mock
- `test_state.db` — Pre-seeded SQLite state DB for tests
- `sample_leads.json` — Test lead data
- `sample_templates.json` — Test email templates

Create `tests/integration/` for integration tests (separate from unit tests):
- `test_send_gateway_integration.py`
- `test_state_manager_integration.py`
- `test_memory_retriever_integration.py`
- `test_event_bus_integration.py`

Update `tests/conftest.py` with:
- `@pytest.fixture` for mock Supabase client
- `@pytest.fixture` for test state DB
- `@pytest.fixture` for sample leads
- `@pytest.fixture` for mock secret loader (scoped env)
- `@pytest.fixture` for clean FTS5 index

#### 2D: Linting & Formatting

Create `pyproject.toml` at repo root:
```toml
[tool.ruff]
target-version = "py312"
line-length = 120
exclude = ["node_modules", ".venv", "state/", "tmp/", "_archive/"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.lint.isort]
known-first-party = ["bravo_cli", "lib"]

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
exclude = ["state/", "tmp/", "_archive/"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

#### 2E: Pre-commit Hook

Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest-smoke
        name: pytest smoke tests
        entry: pytest tests/ -x -q
        language: system
        types: [python]
        pass_filenames: false
```

Update `package.json` test script:
```json
"test": "pytest tests/ -v --cov=scripts --cov-report=term-missing",
"test:fast": "pytest tests/ -x -q",
"test:coverage": "pytest tests/ --cov=scripts --cov-report=html",
"lint": "ruff check scripts/ tests/",
"lint:fix": "ruff check --fix scripts/ tests/",
"format": "ruff format scripts/ tests/",
"typecheck": "mypy scripts/ --ignore-missing-imports"
```

### Execution Order

```
Phase 2A: Create pyproject.toml, .pre-commit-config.yaml
Phase 2B: Update package.json scripts
Phase 2C: Create .github/workflows/test.yml, lint.yml
Phase 2D: Create tests/fixtures/ with mocks
Phase 2E: Expand conftest.py with fixtures
Phase 2F: Write tests for state_manager.py (20 tests) — P0
Phase 2G: Write tests for secret_loader.py (10 tests) — P1
Phase 2H: Write tests for context_builder.py (12 tests) — P1
Phase 2I: Write tests for apply_migration.py (10 tests) — P1
Phase 2J: Write tests for send_gateway.py edge cases (8 more) — P0
Phase 2K: Write tests for event_bus.py (expand to 20) — P0
Phase 2L: Write tests for memory_retriever.py (expand to 30) — P0
Phase 2M: Write tests for remaining engines (lead, outreach, revenue, booking) — P2
Phase 2N: Create tests/integration/ with 4 integration tests
Phase 2O: Run full CI pipeline locally — verify green
```

---

## EPIC 3: STATE & MEMORY HYGIENE

### Problem
- LanceDB has 450+ versions (no compaction) — will grow unbounded
- SQLite WAL files present but no automated checkpoint/compaction schedule
- No automated cleanup of old session logs, expired exec overrides, or stale pulse files
- `memory/` has subdirectories (`content/`, `daily/`, `outreach_archive/`, `poems/`, `research/`) with no INDEX.md or retention policy

### Target State

#### 3A: LanceDB Compaction

Create `scripts/memory/state_compact.py`:
```python
"""Compact LanceDB vector store to reclaim disk space from old versions."""
import lancedb
from pathlib import Path

STATE_DIR = Path(__file__).parent.parent / "state"
LANCE_PATH = STATE_DIR / "memory_lance" / "memory_chunks.lance"

def compact_lance(retain_versions: int = 5):
    db = lancedb.connect(str(LANCE_PATH.parent))
    table = db.open_table("memory_chunks")
    table.compact_files(
        target_rows=1024,
        materialize_deletions=True,
        num_threads=2,
    )
    # Clean up old versions
    versions = table.list_versions()
    if len(versions) > retain_versions:
        for v in versions[:-retain_versions]:
            table.checkout_version(v.version)
            table.cleanup_old_versions()
    return {"versions_before": len(versions), "versions_after": retain_versions}

if __name__ == "__main__":
    result = compact_lance()
    print(f"LanceDB compacted: {result}")
```

Add to `package.json`:
```json
"state:compact": "python scripts/memory/state_compact.py",
"state:health": "python scripts/state_manager.py status"
```

#### 3B: SQLite WAL Checkpoint

Add checkpoint logic to `scripts/state/state_manager.py`:
```python
def checkpoint_wal(self):
    """Force WAL checkpoint to merge WAL into main DB file."""
    self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```

Add cron entry to run checkpoint every 6 hours.

#### 3C: Memory Retention Policy

Create `memory/RETENTION_POLICY.md`:
```markdown
# Memory Retention Policy

| Directory | Retention | Auto-cleanup |
|---|---|---|
| `memory/daily/` | 30 days | `memory_aging.py` compresses to monthly summary |
| `memory/content/` | Indefinite | No cleanup — content research is evergreen |
| `memory/research/` | 90 days | `memory_aging.py` archives to `memory/archives/` |
| `memory/poems/` | Indefinite | No cleanup — creative archive |
| `memory/outreach_archive/` | 180 days | `memory_aging.py` purges beyond retention |
| `memory/SESSION_LOG.md` | Compressed monthly | Auto-generated section truncated at 500 lines |
| `state/event_router.log` | 7 days | `hooks/rotate_logs.py` truncates |
| `state/{exec,secret,state}_guard.log` | 30 days | `hooks/rotate_logs.py` truncates |
```

Update `scripts/hooks/rotate_logs.py` to enforce this policy.

#### 3D: Automated State Health Check

Create `scripts/admin/state_health.py`:
```python
"""Comprehensive state health check — runs on boot and daily."""
import sqlite3
from pathlib import Path

def check_state_health():
    results = {}

    # SQLite state DB
    db_path = Path(__file__).parent.parent.parent / "state" / "empire_state.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check WAL size
    cursor.execute("PRAGMA wal_autocheckpoint")
    results["wal_autocheckpoint"] = cursor.fetchone()[0]

    # Check table sizes
    cursor.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY SUM(pgsize) DESC LIMIT 10")
    results["largest_tables"] = cursor.fetchall()

    # Check session_log entry count
    cursor.execute("SELECT COUNT(*) FROM session_log")
    results["session_log_entries"] = cursor.fetchone()[0]

    # Check for stale active tasks
    cursor.execute("SELECT COUNT(*) FROM active_task WHERE status = 'open' AND updated_at < datetime('now', '-7 days')")
    results["stale_tasks"] = cursor.fetchone()[0]

    conn.close()

    # FTS5 index health
    fts_path = db_path.parent / "memory_index.db"
    fts_conn = sqlite3.connect(str(fts_path))
    fts_conn.execute("SELECT COUNT(*) FROM memory_index")
    results["fts5_chunks"] = fts_conn.fetchone()[0]
    fts_conn.close()

    return results
```

### Execution Order

```
Phase 3A: Create scripts/memory/state_compact.py
Phase 3B: Add WAL checkpoint to state_manager.py
Phase 3C: Create memory/RETENTION_POLICY.md
Phase 3D: Update hooks/rotate_logs.py with retention enforcement
Phase 3E: Create scripts/admin/state_health.py
Phase 3F: Run LanceDB compaction manually (first time)
Phase 3G: Add state:compact and state:health to package.json
Phase 3H: Add daily cron entry for state health check
```

---

## EPIC 4: DEAD CODE & DIRECTORY CLEANUP

### Problem
Several directories are empty, near-empty, or contain only archive content:
- `supabase/` — empty (0 files)
- `templates/` — empty (0 files)
- `skills/_archive/` — unknown contents
- `skills/in-progress/` — unknown contents
- `skills/auto-generated/` — unknown contents
- `scripts/_archive/` — unknown contents
- `.agents/workflows/_archive/` — unknown contents
- `Untitled.canvas` — stray Obsidian file at root
- `bravo_cli/` — 14 files, unclear if still used vs `scripts/`

### Target State

#### 4A: Remove Empty Directories
- Delete `supabase/` (Supabase config lives in migrations + CLI tool)
- Delete `templates/` (templates live in `data/templates/`)

#### 4B: Audit Archive Directories
For each `_archive/` directory:
1. List contents
2. If nothing referenced in 90+ days → move to `docs/archived/` single directory
3. Update `memory/INDEX.md` to note archival

#### 4C: Audit `skills/in-progress/` and `skills/auto-generated/`
- `in-progress/` → either complete the skills or move to `_archive/`
- `auto-generated/` → if these are machine-generated, add a README explaining the generation pipeline

#### 4D: Remove Stray Files
- Delete `Untitled.canvas` (Obsidian artifact)
- Audit `bravo_cli/` — if superseded by `scripts/`, archive it

#### 4E: Create `docs/archived/` for consolidated archival
```
docs/archived/
├── README.md              # Explains what's here and why
├── scripts-archive/       # Old scripts no longer in use
├── skills-archive/        # Deprecated skills
└── workflows-archive/     # Old workflow definitions
```

### Execution Order

```
Phase 4A: Audit all _archive/ directories (list contents, check references)
Phase 4B: Delete supabase/, templates/, Untitled.canvas
Phase 4C: Audit skills/in-progress/ and skills/auto-generated/
Phase 4D: Audit bravo_cli/ — determine if still active
Phase 4E: Create docs/archived/ and move deprecated content
Phase 4F: Update .gitignore to prevent future empty directories
```

---

## EPIC 5: IMPORT SYSTEM & PACKAGE STRUCTURE

### Problem
- No `pyproject.toml` — imports rely on `conftest.py` path manipulation
- `scripts/lib/` is a pseudo-package but no `__init__.py` exports
- `bravo_cli/` is a proper package (has `__init__.py`) but unclear relationship to `scripts/`
- No namespace package declaration — imports are fragile across directory moves
- Mixed import styles: `from lib.secret_loader import ...` vs `import sys; sys.path.insert`

### Target State

#### 5A: Create `pyproject.toml` (also covers Epic 2D)

```toml
[project]
name = "ceo-agent"
version = "7.0.0"
description = "Autonomous AI operations hub for CC's business empire"
requires-python = ">=3.12"
dependencies = [
    "anthropic==0.85.0",
    "beautifulsoup4==4.14.3",
    "click==8.3.1",
    "cryptography==46.0.7",
    "firecrawl-py==4.22.0",
    "mem0ai==2.0.0b2",
    "numpy==2.4.2",
    "pillow==12.2.0",
    "playwright==1.58.0",
    "python-dateutil==2.9.0.post0",
    "python-dotenv==1.2.2",
    "requests-oauthlib==2.0.0",
    "requests==2.33.0",
    "stripe==14.4.0",
    "supabase==2.28.2",
    "fastapi==0.118.0",
    "uvicorn[standard]==0.32.0",
    "python-multipart==0.0.27",
    "openai>=1.90.0,<3.0",
    "dnspython==2.7.0",
    "fastembed==0.8.0",
    "lancedb==0.30.2",
    "pyarrow==24.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest==9.0.3",
    "pytest-cov==6.0.0",
    "ruff==0.9.0",
    "mypy==1.14.0",
    "pre-commit==4.0.0",
]
whisper = [
    "openai-whisper",
    "torch",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["scripts*", "bravo_cli*"]
```

#### 5B: Standardize Import Patterns

Create `scripts/__init__.py`:
```python
"""CEO-Agent scripts package."""
__version__ = "7.0.0"
```

Update `scripts/lib/__init__.py` to export public API:
```python
"""Shared library modules for CEO-Agent scripts."""
from .secret_loader import load_env, get
from .safe_error import scrub_traceback
from .hook_runtime import check_env_var
from .subprocess_ast import validate_command
from .exec_override_mirror import mirror_override_request
from .override_crypto import hmac_sign, hmac_verify

__all__ = [
    "load_env", "get", "scrub_traceback", "check_env_var",
    "validate_command", "mirror_override_request", "hmac_sign", "hmac_verify",
]
```

#### 5C: Create Import Migration Guide

Create `docs/IMPORT_MIGRATION.md`:
```markdown
# Import Migration Guide (V6 → V7)

All imports should use the package path, not sys.path manipulation.

## Before (V6)
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lib.secret_loader import load_env
```

## After (V7)
```python
from scripts.lib import load_env
```

## Before (V6)
```python
from send_gateway import send
```

## After (V7)
```python
from scripts.gateway import send
```

## Backward Compatibility
All old import paths work via shim files at the old locations.
Shims emit DeprecationWarning but do not break functionality.
Remove shims in V8.0.
```

#### 5D: Resolve `bravo_cli/` Relationship

Audit `bravo_cli/` contents:
- If it's a CLI tool → move to `scripts/admin/bravo_cli/`
- If it's a library → merge into `scripts/lib/`
- If it's superseded → archive to `docs/archived/`

### Execution Order

```
Phase 5A: Create pyproject.toml
Phase 5B: Create scripts/__init__.py
Phase 5C: Update scripts/lib/__init__.py with exports
Phase 5D: Audit bravo_cli/ and resolve relationship
Phase 5E: Create docs/IMPORT_MIGRATION.md
Phase 5F: Run pip install -e . to verify package installs
Phase 5G: Update conftest.py to use installed package instead of path hack
```

---

## EPIC 6: TURNKEY DEPLOYMENT HARDENING

### Problem
- `infra/docker-compose.local.yml` and `cloud.yml` exist but no automated build/test/deploy pipeline
- No health check endpoint for the local state
- No automated backup of state databases
- No rollback procedure for failed deployments
- `install.sh` and `install.ps1` exist but no post-install verification
- No environment validation (Python version, required binaries, disk space)

### Target State

#### 6A: Pre-flight Check Script

Create `scripts/admin/preflight.py`:
```python
"""Pre-flight checks before deployment or major operations."""
import sys
import shutil
import subprocess
from pathlib import Path

def run_preflight():
    checks = []

    # Python version
    major, minor = sys.version_info[:2]
    checks.append(("Python >= 3.12", (major, minor) >= (3, 12)))

    # Required binaries
    for binary in ["git", "docker", "sqlite3"]:
        checks.append((f"{binary} available", shutil.which(binary) is not None))

    # Disk space (need at least 2GB free)
    stat = shutil.disk_usage(Path(__file__).parent.parent.parent)
    checks.append((f"Disk space >= 2GB ({stat.free // 1024**3}GB free)", stat.free >= 2 * 1024**3))

    # .env.agents exists
    env_path = Path(__file__).parent.parent.parent / ".env.agents"
    checks.append((".env.agents exists", env_path.exists()))

    # Virtual environment
    venv_path = Path(__file__).parent.parent.parent / ".venv"
    checks.append((".venv exists", venv_path.exists()))

    # Required Python packages
    try:
        import fastembed
        import lancedb
        import supabase
        checks.append(("Required packages installed", True))
    except ImportError as e:
        checks.append((f"Required packages: {e}", False))

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)

    for name, ok in checks:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    print(f"\n{passed}/{total} checks passed")
    return all(ok for _, ok in checks)

if __name__ == "__main__":
    ok = run_preflight()
    sys.exit(0 if ok else 1)
```

#### 6B: Automated State Backup

Create `scripts/admin/backup_state.py`:
```python
"""Backup state databases with rotation."""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(__file__).parent.parent.parent / "state"
BACKUP_DIR = STATE_DIR / "backups"
MAX_BACKUPS = 14  # Keep 2 weeks of backups

def backup_state():
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Backup empire_state.db (use SQLite backup API for consistency)
    src = STATE_DIR / "empire_state.db"
    dst = BACKUP_DIR / f"empire_state_{timestamp}.db"
    if src.exists():
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(dst))
        src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()

    # Backup memory_index.db
    src = STATE_DIR / "memory_index.db"
    dst = BACKUP_DIR / f"memory_index_{timestamp}.db"
    if src.exists():
        shutil.copy2(src, dst)

    # Rotate old backups
    backups = sorted(BACKUP_DIR.glob("*.db"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink()

    return {"backup_dir": str(BACKUP_DIR), "timestamp": timestamp}
```

#### 6C: Post-install Verification

Update `install.sh` to run `scripts/admin/preflight.py` at the end:
```bash
echo "Running post-install verification..."
python scripts/admin/preflight.py
if [ $? -eq 0 ]; then
    echo "✓ All checks passed. CEO-Agent is ready."
else
    echo "✗ Some checks failed. Review output above."
    exit 1
fi
```

#### 6D: Docker Compose Health Checks

Update `infra/docker-compose.local.yml` with health checks:
```yaml
services:
  state-api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8500/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  bravo-core:
    healthcheck:
      test: ["CMD", "python", "-c", "from scripts.state_manager import StateManager; StateManager().status()"]
      interval: 60s
      timeout: 10s
      retries: 3
```

#### 6E: Rollback Procedure

Create `docs/ROLLBACK.md`:
```markdown
# Rollback Procedure

## State Database Rollback
```bash
# List available backups
ls -la state/backups/

# Restore empire_state.db from backup
python scripts/admin/backup_state.py restore --timestamp 20260520_120000

# Verify restore
python scripts/state_manager.py status
```

## Code Rollback
```bash
# Revert to previous commit
git revert HEAD --no-edit

# Re-apply migrations if schema changed
python scripts/apply_migration.py database/057b_lead_documents_drop_member_all.sql --rollback
```

## Docker Rollback
```bash
# Stop current containers
docker compose -f infra/docker-compose.local.yml down

# Rebuild from previous image
docker compose -f infra/docker-compose.local.yml up -d --no-build
```
```

#### 6F: Environment Validation in CI

Add to `.github/workflows/test.yml`:
```yaml
      - name: Preflight check
        run: python scripts/admin/preflight.py
```

### Execution Order

```
Phase 6A: Create scripts/admin/preflight.py
Phase 6B: Create scripts/admin/backup_state.py
Phase 6C: Update install.sh with post-install verification
Phase 6D: Add health checks to docker-compose files
Phase 6E: Create docs/ROLLBACK.md
Phase 6F: Add preflight to CI workflow
Phase 6G: Test full deploy → backup → rollback cycle locally
```

---

## CROSS-EPIC DEPENDENCIES & EXECUTION ORDER

```
EPIC 5 (Import System)     → Must come FIRST — establishes package structure
EPIC 1 (Scripts Reorg)     → Depends on EPIC 5 — moves files into new structure
EPIC 2 (CI/CD + Tests)     → Depends on EPIC 1 — tests reference new paths
EPIC 3 (State Hygiene)     → Independent — can run in parallel with EPIC 1
EPIC 4 (Dead Code Cleanup) → Independent — can run in parallel with EPIC 1
EPIC 6 (Deploy Hardening)  → Depends on EPIC 1, 2, 3 — needs stable structure
EPIC 7 (Loud Failures)     → Independent of EPIC 1 — only needs lib/subprocess_helpers (exists).
                             Highest leverage post-freeze given the 2026-06-06 audit findings;
                             should run FIRST when freeze lifts.

RECOMMENDED ORDER (revised 2026-06-06):
  Sprint 1 (post-freeze, first): EPIC 7 (Loud Failures) — closes the silent-failure
                                 observability gap before further structural moves can
                                 hide new ones
  Sprint 2: EPIC 5 + EPIC 4 (parallel)
  Sprint 3: EPIC 1 (scripts reorg — surgical 50, no shims per CC 2026-06-06)
  Sprint 4: EPIC 2 (CI/CD + tests)
  Sprint 5: EPIC 3 + EPIC 6 (parallel)
```

---

## VERIFICATION CHECKLIST (After All Epics)

- [ ] `pytest tests/ -v` passes with 242+ tests
- [ ] `ruff check scripts/ tests/` returns zero errors
- [ ] `ruff format --check scripts/ tests/` returns zero differences
- [ ] `mypy scripts/ --ignore-missing-imports` returns zero errors
- [ ] `python scripts/admin/preflight.py` passes all checks
- [ ] `python scripts/admin/backup_state.py` creates valid backup
- [ ] `python scripts/memory/state_compact.py` reduces LanceDB versions to ≤5
- [ ] `python scripts/admin/state_health.py` returns healthy status
- [ ] `pip install -e .` succeeds
- [ ] `from scripts.gateway import send` works (new import path)
- [ ] `from scripts.send_gateway import send` works (backward compat shim)
- [ ] `.github/workflows/test.yml` passes on push
- [ ] `.github/workflows/lint.yml` passes on PR
- [ ] `docker compose -f infra/docker-compose.local.yml up` starts all services
- [ ] Health checks pass for all services
- [ ] Rollback procedure tested and verified
- [ ] ARCHITECTURE.md updated with new structure
- [ ] brain/CAPABILITIES.md updated
- [ ] brain/QUICK_REFERENCE.md updated
- [ ] memory/SESSION_LOG.md updated with change summary
- [ ] `python scripts/state/state_sync.py --note "V7.0 structural optimization complete"`
- [ ] **EPIC 7:** `python scripts/admin/system_health.py --strict` returns exit 0 on current state
- [ ] **EPIC 7:** path-drift detector flags a deliberately-renamed dependency
- [ ] **EPIC 7:** PM2 path audit flags a deliberate `pm_exec_path` mismatch
- [ ] **EPIC 7:** "Loud Failures Weekly Probe" cron registered in `SEED_JOBS`
- [ ] **EPIC 7:** zero direct `subprocess.Popen`/`subprocess.run` calls in production code outside `lib/subprocess_helpers.py` (sweep clean)
- [ ] **EPIC 7:** no `except Exception: ...; return None` swallows in production code without a `_slog.error(...)` breadcrumb (sweep clean)

---

## RISK MITIGATION

| Risk | Mitigation |
|---|---|
| Import breakage after reorg | Backward-compat shims at every old path; test suite validates both old and new imports |
| Test suite fails on CI | Run full test suite locally before pushing; use `--cov` to identify gaps |
| LanceDB compaction loses data | Backup state before compaction; compaction is additive, not destructive |
| Docker compose breaks | Test locally before pushing; health catches will surface issues |
| CC's workflow disrupted | All changes are additive first (new dirs, new files), then move with shims. Zero downtime. |
| Git history lost on moves | Use `git mv` for all file moves to preserve history |

---

## SYSTEM MESSAGE FOR AI EXECUTOR

```
You are an AI coding agent (Codex / Claude Code) executing the V7.0 Structural Optimization Plan for CEO-Agent.

CRITICAL RULES (revised 2026-06-06):
1. Follow the execution order exactly: EPIC 7 → EPIC 5 → EPIC 4 → EPIC 1 → EPIC 2 → EPIC 3 → EPIC 6
2. Use `git mv` for ALL file moves to preserve history
3. EPIC 1: do NOT create backward-compat shims (per CC 2026-06-06). Surgical move of ~50 canonical
   scripts only; single-PR import audit; long-tail utilities stay at `scripts/` root.
4. Run `pytest scripts/tests/ -x` after EVERY phase — do not proceed if tests fail. Tests live at
   `scripts/tests/` (not repo-root `tests/`).
5. Update brain/STATE.md and memory/SESSION_LOG.md after every phase
6. Never break existing functionality — for EPIC 1, this means grep-verify zero broken imports
   before the move commit lands.
7. If any phase fails, stop and report to CC before proceeding
8. Do NOT commit changes unless CC explicitly asks you to
9. EPIC 7 first: closes the silent-failure observability gap so subsequent epics can't silently
   break things during the reorg.

STARTING POINT:
- Read this entire plan file first
- Read ARCHITECTURE.md to understand the current system
- Run `python scripts/admin/preflight.py` (create it first if needed) to establish baseline
- Begin with EPIC 5, Phase 5A

REPORTING:
After each phase, report:
- What changed (files moved, created, modified)
- Test results (pass/fail count)
- Any issues or blockers
- Next phase readiness

If you complete all 6 epics successfully, run the full verification checklist and report results.
```

---

*This plan is the single source of truth for V7.0 structural optimization. Any deviation from this plan requires CC's explicit approval.*

---

## EPIC 7: LOUD FAILURES — silent-failure observability (added 2026-06-06)

### Problem

The 2026-06-06 audit pass surfaced **four silent-failure bugs that had been live for days or weeks** without anyone noticing:

1. **retriever_postedit.py Windows TypeError** (live ~18 days): `**kwargs, creationflags=X` duplicate kwarg crashed every PostToolUse Edit/Write hook on Windows. Subprocess output went to DEVNULL, exception was caught silently. Memory-index never re-indexed after edits. Fixed in 43506be.
2. **retriever_postedit.py wrong path** (live ~indeterminate): even after the TypeError fix, the spawned target was `scripts/memory_retriever.py` but the file lives at `scripts/core/memory_retriever.py`. Subprocess silently failed to start. Fixed in 433b92d.
3. **wizard.py wrong path** (live ~indeterminate): same `scripts/memory_retriever.py` reference behind an `if mr_script.exists()` guard. Onboarding wizard silently skipped the FTS5 index build. Fresh installs got empty memory indexes. Fixed in 433b92d.
4. **event_router PM2 stale CEO-Agent path + import-order bug** (live ~13 days, blocked 336 events): PM2's saved process list pointed at `C:\Users\User\CEO-Agent\scripts\core\event_router.py` (old repo name) — daemon "online" but never spawned a working python. After the path fix, an import-order bug (`from lib.structured_log` ran BEFORE `sys.path.insert(scripts/)`) poisoned Python's import-state cache for `lib`, making the daemon's `_client()` return None silently. Fixed in 3731e42 + 9ef5c76.

**Meta-pattern:** subprocess + DEVNULL + bare `except: pass` = invisible failure. Things that claim to work but don't, until someone goes looking.

### Target State

**7A — Canonical subprocess wrapper enforcement.** Every `subprocess.Popen(...)` and `subprocess.run(...)` call from production code (excluding tests and the wrappers themselves) MUST go through `lib/subprocess_helpers.py:safe_popen` / `safe_run` / `safe_daemon_popen`. Direct subprocess calls in daemon-spawned code are already blocked by `scripts/hooks/subprocess_guard.py` — extend the guard's coverage and tighten the allowlist.

**7B — No silent except blocks in production code.** Every `except Exception` (or worse, bare `except`) that swallows must EITHER (a) write a one-line stderr breadcrumb AND call `_slog.error(event_type, error=str(e)[:200])` to the structured log, OR (b) re-raise. The `event_router._client()` dual-write pattern in 9ef5c76 is the template.

**7C — System health probe.** New `scripts/admin/system_health.py` that surfaces silent failures BEFORE someone goes looking:
- For each PM2 daemon: confirm process online AND its tick/loop has actually advanced state (cursor mtime, log mtime, or a heartbeat) within the last N minutes
- For each cron entry in `SEED_JOBS`: confirm `action_config.script` exists on disk AND parses
- For each hook in `.claude/settings.local.json`: confirm target script exists AND its `_check()` returns clean if defined
- For each MCP server in `MCP_CONFIG_PATHS`: confirm wrapper script exists AND env vars resolve (without leaking values)
- Output: one-line green/yellow/red per check, exit 1 on any red
- Run weekly via SEED_JOBS (`Loud Failures Weekly Probe`)

**7D — Path-drift detector.** New check in `system_health.py`: walk every Python file under `scripts/`, `bravo_cli/`, and root; collect every `Path(...) / "scripts" / X` or string-literal script path; assert every referenced path resolves. This is the regression check for the memory_retriever / event_router / wizard class of bug.

**7E — PM2 path audit.** Add `pm2 jlist` audit to `system_health.py`: any daemon with `pm_exec_path` that doesn't start with the current repo root flags as stale (catches the CEO-Agent → Business-Empire-Agent rename scenario before another 13-day stall).

**7F — Bug-pattern sweep cron.** Monthly cron entry that runs `system_health.py --strict` and Telegrams CC if anything goes red. Meta-monitor for the meta-monitors.

### Why this is its own epic

The existing EPIC 3 (state & memory hygiene) covers log retention and SQLite WAL discipline. EPIC 7 covers a fundamentally different axis: **detection** of silent failures (vs. management of state that's working). Folding it into EPIC 3 would dilute both.

### Execution Order (post-freeze)

```
Phase 7A: Sweep all subprocess.Popen/run callsites; replace with safe_* helpers
Phase 7B: Sweep all `except Exception: ...; return None` patterns in production code; add structured-log breadcrumbs
Phase 7C: Build scripts/admin/system_health.py (PM2 + cron + hook + MCP probes)
Phase 7D: Add path-drift detector to system_health.py
Phase 7E: Add PM2 path audit to system_health.py
Phase 7F: Add `Loud Failures Weekly Probe` cron entry to SEED_JOBS
Phase 7G: Run full system_health.py against current state; fix any red items
Phase 7H: Document the canonical "no silent failures" rule in CLAUDE.md
```

### Verification

- `python scripts/admin/system_health.py --strict` returns exit 0 (all green) on current state
- Inject a deliberate path-drift (rename a script the cron depends on); verify system_health.py flags it red
- Inject a deliberate PM2 path mismatch; verify system_health.py flags it red
- Run for 30 days; zero "silent failure surfaced manually by accident" incidents

