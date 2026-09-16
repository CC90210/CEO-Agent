"""SEED_JOBS shape — the defects a syntax check cannot see.

WHY THIS EXISTS
2026-08-14: an insertion put an entire job dict INSIDE another job's argv:

    "action_config": {"script": ".../marketing_publish_drain.py", "args": [    {
        "name": "Training Corpus Ingest",
        ...
    },
], "timeout": 900},

The file still parsed. `ast.parse` was clean, `import cron_engine` was clean, and
the live cron_jobs rows were fine because they had been seeded before the damage
— so nothing anywhere went red. It would have detonated on the next
`cron_engine.py seed`, handing the drain a dict as its argv.

A structural defect that leaves the syntax valid needs a test that looks at the
STRUCTURE. Every assertion below was run against the corrupted file first and
observed to fail.
"""
from __future__ import annotations

import sqlite3
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cron_engine as ce  # noqa: E402

JOBS = ce.SEED_JOBS
REPO = Path(__file__).resolve().parents[2]


def test_every_job_has_the_required_keys():
    required = {
        "name",
        "description",
        "schedule",
        "action_type",
        "action_config",
        "is_active",
        "owner_agent_key",
    }
    for j in JOBS:
        missing = required - set(j)
        assert not missing, f"{j.get('name', '<unnamed>')} is missing {sorted(missing)}"


def test_job_names_are_unique():
    """A duplicate name means one definition silently shadows the other on seed."""
    names = [j["name"] for j in JOBS]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate SEED_JOBS names: {dupes}"


def test_argv_is_a_list_of_strings():
    """The actual 2026-08-14 bug: a job dict nested inside another job's argv.

    argv is spliced onto a command line. A dict there is not a bad argument, it
    is a job definition that has stopped existing where it was supposed to.
    """
    for j in JOBS:
        args = (j.get("action_config") or {}).get("args")
        if args is None:
            continue
        assert isinstance(args, list), f"{j['name']}: args must be a list, got {type(args).__name__}"
        for i, a in enumerate(args):
            assert isinstance(a, str), (
                f"{j['name']}: args[{i}] is {type(a).__name__}, not str"
                + (f" — it is a job definition named {a.get('name')!r}" if isinstance(a, dict) else "")
            )


def test_action_config_is_a_dict():
    for j in JOBS:
        assert isinstance(j["action_config"], dict), f"{j['name']}: action_config must be a dict"


def test_every_script_job_points_at_a_file_that_exists():
    """A seeded job whose script was renamed fails silently on its own schedule."""
    missing = []
    for j in JOBS:
        cfg = j.get("action_config") or {}
        script = cfg.get("script")
        if not script:
            continue
        if not (REPO / script).exists():
            missing.append(f"{j['name']} -> {script}")
    assert not missing, "SEED_JOBS reference scripts that are not on disk: " + ", ".join(missing)


@pytest.mark.parametrize("job", JOBS, ids=lambda j: j["name"])
def test_schedule_has_five_cron_fields(job):
    parts = str(job["schedule"]).split()
    assert len(parts) == 5, f"{job['name']}: {job['schedule']!r} is not a 5-field cron expression"


def test_timeouts_are_positive_numbers():
    for j in JOBS:
        t = (j.get("action_config") or {}).get("timeout")
        if t is None:
            continue
        assert isinstance(t, (int, float)) and t > 0, f"{j['name']}: timeout {t!r} is not a positive number"


def test_seed_ownership_matches_the_verified_empire_inventory():
    """Agent grouping is stored data, not a dashboard name heuristic."""
    expected_maven = {
        "Carousel Media Retention",
        "Library Post Linker",
        "Marketing Publish Drain",
        "Maven — Carousel Post",
        "Post Analytics Sync",
        "Training Corpus Ingest",
    }
    actual_maven = {j["name"] for j in JOBS if j["owner_agent_key"] == "maven"}
    assert actual_maven == expected_maven
    assert all(j["owner_agent_key"] in {"bravo", "maven", "atlas", "aura"} for j in JOBS)


def test_maven_carousel_seed_describes_gen10_not_gen9():
    job = next(j for j in JOBS if j["name"] == "Maven — Carousel Post")
    assert "GEN-10" in job["description"]
    assert "GEN-9" not in job["description"]


def test_owner_migration_never_relabels_a_same_named_row_in_another_tenant():
    """Name reconciliation must retain the cron table's tenant boundary."""
    migration = (
        REPO / "database/turso_migrations/bravo__108_cron_owner_agent_key.sql"
    ).read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE cron_jobs ("
        "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, "
        "description TEXT, is_active INTEGER NOT NULL DEFAULT 1)"
    )
    cc_tenant = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
    other_tenant = "00000000-0000-4000-8000-000000000002"
    conn.executemany(
        "INSERT INTO cron_jobs (id, tenant_id, name, description) VALUES (?, ?, ?, ?)",
        [
            ("cc", cc_tenant, "Maven — Carousel Post", "legacy cc"),
            ("other", other_tenant, "Maven — Carousel Post", "other tenant contract"),
        ],
    )
    conn.executescript(migration)
    rows = {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT id, owner_agent_key, description FROM cron_jobs ORDER BY id"
        )
    }
    assert rows["cc"][0] == "maven"
    assert "GEN-10" in rows["cc"][1]
    assert rows["other"] == ("bravo", "other tenant contract")


def test_forward_owner_reconciliation_classifies_recognizable_non_bravo_rows():
    """Immutable migration 108 is completed by a forward owner reconciliation."""
    owner_migration = (
        REPO / "database/turso_migrations/bravo__108_cron_owner_agent_key.sql"
    ).read_text(encoding="utf-8")
    reconciliation = (
        REPO / "database/turso_migrations/bravo__110_cron_owner_reconciliation.sql"
    ).read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE cron_jobs ("
        "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, "
        "description TEXT, action_type TEXT, is_active INTEGER NOT NULL DEFAULT 1)"
    )
    conn.executemany(
        "INSERT INTO cron_jobs (id, tenant_id, name, description, action_type) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("atlas", "tenant-2", "Atlas — marketing spend", "old", "script_run"),
            ("aura", "tenant-2", "Morning Pow Wow", "old", "morning_powwow"),
            ("maven", "tenant-2", "Content analytics", "old", "script_run"),
            ("bravo", "tenant-2", "Ordinary job", "old", "script_run"),
            ("explicit", "tenant-2", "Ordinary explicit", "old", "script_run"),
        ],
    )
    conn.executescript(owner_migration)
    conn.execute("UPDATE cron_jobs SET owner_agent_key = 'aura' WHERE id = 'explicit'")
    conn.executescript(reconciliation)
    assert dict(conn.execute(
        "SELECT id, owner_agent_key FROM cron_jobs ORDER BY id"
    )) == {
        "atlas": "atlas",
        "aura": "aura",
        "bravo": "bravo",
        "explicit": "aura",
        "maven": "maven",
    }


def test_postgres_rollback_migration_has_scoped_owners_and_atomic_toggle_rpc():
    """The explicit Supabase rollback must preserve the Turso control contract."""
    migration = (
        REPO / "database/bravo__109_cron_owner_atomic_toggle.sql"
    ).read_text(encoding="utf-8")
    owner_backfill = re.search(
        r"UPDATE public\.cron_jobs\s+SET owner_agent_key = 'maven'(?P<body>.+?);",
        migration,
        flags=re.DOTALL,
    )
    assert owner_backfill, "Maven owner backfill is missing"
    body = owner_backfill.group("body")
    expected_maven = {
        "Carousel Media Retention",
        "Library Post Linker",
        "Marketing Publish Drain",
        "Maven — Carousel Post",
        "Post Analytics Sync",
        "Training Corpus Ingest",
    }
    assert expected_maven == set(re.findall(r"^\s+'([^']+)'[,]?$", body, re.MULTILINE))
    assert "tenant_id = 'ef8d389e-3f15-43f2-ae00-3660f69a1452'::uuid" in body

    atlas_backfill = migration.index("SET owner_agent_key = 'atlas'")
    aura_backfill = migration.index("SET owner_agent_key = 'aura'")
    bravo_default = migration.rindex("SET owner_agent_key = 'bravo'")
    assert atlas_backfill < bravo_default
    assert aura_backfill < bravo_default
    assert "owner_agent_key IS NULL" in migration[atlas_backfill:bravo_default]

    assert "ADD COLUMN IF NOT EXISTS owner_agent_key text" in migration
    assert "ALTER COLUMN owner_agent_key SET NOT NULL" in migration
    assert "CREATE OR REPLACE FUNCTION public.toggle_cron_job_with_audit_v1" in migration
    assert re.search(
        r"REVOKE ALL ON TABLE public\.cron_jobs FROM anon, authenticated'",
        migration,
    )
    assert migration.count("FOR UPDATE;") == 2
    assert "p_expected_name" in migration
    assert "p_expected_enabled" in migration
    assert "INSERT INTO public.tenant_audit_log" in migration
    assert "SECURITY DEFINER\nSET search_path = public, pg_temp" in migration
    assert not re.search(r"\bRETURNING\b", migration, re.IGNORECASE)
    assert not re.search(r"^\s*(BEGIN|COMMIT)\s*;", migration, re.MULTILINE | re.IGNORECASE)
    assert re.search(
        r"REVOKE ALL ON FUNCTION[\s\S]+FROM PUBLIC, anon, authenticated'",
        migration,
    )
    assert re.search(r"GRANT EXECUTE ON FUNCTION[\s\S]+TO service_role'", migration)
    assert not re.search(r"\bEXECUTE\s+format\b", migration, re.IGNORECASE)


# ── SEED_JOBS vs the LIVE registry ───────────────────────────────────────────
#
# `seed` skips any job whose name already exists and has no update path, so
# these definitions were the source of record on a fresh machine and pure
# documentation on a running one. Measured 2026-08-28, the first time anything
# compared them: 5 of 32 active crons disagreed, including two that mattered.
#   * "Bravo — Review Harvest" was missing `--seed-open` — the argument that
#     gives the whole review loop a trigger. Committed, believed shipped, never
#     executed.
#   * "Loud Failures Weekly Probe" still carried `--strict`, removed from the
#     source on 2026-08-03 precisely because it re-paged hourly. 25 more days.

class _FakeTable:
    def __init__(self, rows, updates):
        self._rows, self._updates, self._patch, self._id = rows, updates, None, None
        self._filters = {}

    def select(self, *_a):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()

    def update(self, patch):
        self._patch = patch
        return self

    def eq(self, col, value):
        self._filters[col] = value
        if col == "id":
            self._id = value
        return self


class _FakeClient:
    """Minimal stand-in for the Turso compat client: select/update only."""

    def __init__(self, rows):
        self.rows, self.updates = rows, []

    def table(self, _name):
        client = self

        class T(_FakeTable):
            def execute(inner):                      # noqa: N805
                if inner._patch is not None:
                    client.updates.append((inner._id, inner._patch))
                    return type("R", (), {"data": []})()
                rows = [
                    row for row in client.rows
                    if all(row.get(col) == value for col, value in inner._filters.items())
                ]
                return type("R", (), {"data": rows})()

        return T(self.rows, self.updates)


def _row_from(definition, **overrides):
    row = {"id": "row-1", "name": definition["name"], "is_active": 1,
           "tenant_id": ce.CC_EMPIRE_TENANT_ID,
           "schedule": definition["schedule"],
           "action_type": definition["action_type"],
           "action_config": definition["action_config"],
           "owner_agent_key": definition["owner_agent_key"]}
    row.update(overrides)
    return row


def test_inventory_contract_accepts_one_matching_row_per_definition():
    rows = [_row_from(j, id=f"row-{i}") for i, j in enumerate(JOBS)]
    assert ce.audit_live_inventory(rows) == []


def test_inventory_contract_catches_a_declared_job_that_disappears():
    """The exact Automations-tab outage class: a partial list must not look green."""
    rows = [_row_from(j, id=f"row-{i}") for i, j in enumerate(JOBS[1:])]
    issues = ce.audit_live_inventory(rows)
    assert len(issues) == 1
    assert issues[0]["kind"] == "missing"
    assert issues[0]["name"] == JOBS[0]["name"]


def test_inventory_contract_catches_duplicate_registered_rows():
    definition = JOBS[0]
    issues = ce.audit_live_inventory([
        _row_from(definition, id="first"),
        _row_from(definition, id="second"),
    ], [definition])
    assert issues == [{
        "kind": "duplicate",
        "name": definition["name"],
        "detail": "declared job has 2 live rows: first, second",
        "row_ids": ["first", "second"],
    }]


def test_inventory_contract_catches_owner_and_schedule_drift():
    definition = JOBS[0]
    issues = ce.audit_live_inventory([
        _row_from(definition, owner_agent_key="maven", schedule="0 0 * * *"),
    ], [definition])
    assert len(issues) == 1
    assert issues[0]["kind"] == "drift"
    assert set(issues[0]["diffs"]) == {"owner_agent_key", "schedule"}


def test_inventory_contract_keeps_ad_hoc_live_jobs_legitimate():
    definition = JOBS[0]
    rows = [
        _row_from(definition),
        {"id": "adhoc", "name": "Operator one-off", "schedule": "0 0 * * *"},
    ]
    assert ce.audit_live_inventory(rows, [definition]) == []


def test_inventory_contract_compares_action_config_by_meaning():
    import json
    definition = JOBS[0]
    row = _row_from(definition, action_config=json.dumps(definition["action_config"]))
    assert ce.audit_live_inventory([row], [definition]) == []


def test_no_drift_when_the_live_row_matches():
    definition = JOBS[0]
    assert ce._drift_rows(_FakeClient([_row_from(definition)])) == []


def test_drift_detected_when_live_args_differ():
    """The exact live defect: the seed grew an argument, the row did not."""
    definition = next(j for j in JOBS if isinstance(j["action_config"], dict)
                      and j["action_config"].get("args"))
    stale = dict(definition["action_config"])
    stale["args"] = stale["args"][1:]                # one argument dropped
    drift = ce._drift_rows(_FakeClient([_row_from(definition, action_config=stale)]))
    assert len(drift) == 1
    assert "action_config" in drift[0]["diffs"]


def test_drift_ignores_a_same_named_row_in_another_tenant():
    """The Empire fixer must never compare or relabel a peer tenant's row."""
    definition = next(j for j in JOBS if j["owner_agent_key"] == "maven")
    other_tenant_row = _row_from(
        definition,
        tenant_id="00000000-0000-4000-8000-000000000002",
        owner_agent_key="bravo",
    )
    assert ce._drift_rows(_FakeClient([other_tenant_row])) == []


def test_encoding_is_not_mistaken_for_drift():
    """action_config comes back as TEXT from some writers and dict from others.
    Comparing the raw values would report every single row as drifted, and a
    check that always fires is a check nobody reads."""
    import json
    definition = JOBS[0]
    as_text = _row_from(definition, action_config=json.dumps(definition["action_config"]))
    assert ce._drift_rows(_FakeClient([as_text])) == []


def test_a_row_with_no_seed_definition_is_not_drift():
    """Jobs added live with `cron_engine.py add` are legitimate and have no
    SEED_JOBS counterpart. Reporting them would make the signal noise."""
    assert ce._drift_rows(_FakeClient([{
        "id": "x", "name": "Ad-hoc job nobody seeded", "is_active": 1,
        "schedule": "0 0 * * *", "action_type": "script_run",
        "action_config": {"script": "whatever.py"}}])) == []


def test_drift_reports_by_default_and_only_writes_with_fix(capsys):
    """Rewriting a live production schedule is the change CLAUDE.md says CC
    reviews first. Report-only is the default; --fix is the deliberate act."""
    definition = next(j for j in JOBS if isinstance(j["action_config"], dict)
                      and j["action_config"].get("args"))
    stale = dict(definition["action_config"])
    stale["args"] = []

    client = _FakeClient([_row_from(definition, action_config=stale)])
    args = type("A", (), {"only": definition["name"], "fix": False})()
    with pytest.raises(SystemExit) as exc:
        ce.cmd_drift(client, args, False)
    assert exc.value.code == 1, "drift must exit non-zero so a caller can gate on it"
    assert client.updates == [], "report mode must not write"

    client = _FakeClient([_row_from(definition, action_config=stale)])
    ce.cmd_drift(client, type("A", (), {
        "only": definition["name"], "fix": True,
    })(), False)
    assert len(client.updates) == 1, "--fix must write exactly one row"
    _, patch = client.updates[0]
    assert isinstance(patch["action_config"], str), "action_config is stored as TEXT"


def test_drift_cli_flags_a_declared_job_missing_from_live_registry(capsys):
    definition = JOBS[0]
    client = _FakeClient([])
    args = type("A", (), {
        "only": definition["name"], "fix": False, "fix_docs": False,
    })()
    with pytest.raises(SystemExit) as exc:
        ce.cmd_drift(client, args, False)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "INVENTORY CONTRACT FAILED" in out
    assert definition["name"] in out


def test_the_harness_eval_actually_runs_the_drift_check():
    """A check that exists but is not in CHECKS is the same defect it detects."""
    import harness_eval
    names = [name for name, *_ in harness_eval.CHECKS]
    assert any("cron definitions match" in n for n in names), (
        "the drift check must be registered in CHECKS, not merely defined")


def test_harness_eval_fails_when_a_declared_cron_is_missing(monkeypatch):
    import json
    import harness_eval
    payload = {
        "drifted": [], "doc_drifted": [],
        "inventory_issues": [{"kind": "missing", "name": "Missing Job"}],
    }
    monkeypatch.setattr(
        harness_eval, "_run", lambda *_a, **_k: (1, json.dumps(payload), ""),
    )
    ok, detail = harness_eval.check_cron_definitions_match_live()
    assert ok is False
    assert "Missing Job" in detail
