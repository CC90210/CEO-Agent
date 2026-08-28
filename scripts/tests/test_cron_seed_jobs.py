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

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cron_engine as ce  # noqa: E402

JOBS = ce.SEED_JOBS
REPO = Path(__file__).resolve().parents[2]


def test_every_job_has_the_required_keys():
    required = {"name", "description", "schedule", "action_type", "action_config", "is_active"}
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

    def select(self, *_a):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()

    def update(self, patch):
        self._patch = patch
        return self

    def eq(self, _col, value):
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
                return type("R", (), {"data": client.rows})()

        return T(self.rows, self.updates)


def _row_from(definition, **overrides):
    row = {"id": "row-1", "name": definition["name"], "is_active": 1,
           "schedule": definition["schedule"],
           "action_type": definition["action_type"],
           "action_config": definition["action_config"]}
    row.update(overrides)
    return row


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
    args = type("A", (), {"only": None, "fix": False})()
    with pytest.raises(SystemExit) as exc:
        ce.cmd_drift(client, args, False)
    assert exc.value.code == 1, "drift must exit non-zero so a caller can gate on it"
    assert client.updates == [], "report mode must not write"

    client = _FakeClient([_row_from(definition, action_config=stale)])
    ce.cmd_drift(client, type("A", (), {"only": None, "fix": True})(), False)
    assert len(client.updates) == 1, "--fix must write exactly one row"
    _, patch = client.updates[0]
    assert isinstance(patch["action_config"], str), "action_config is stored as TEXT"


def test_the_harness_eval_actually_runs_the_drift_check():
    """A check that exists but is not in CHECKS is the same defect it detects."""
    import harness_eval
    names = [name for name, *_ in harness_eval.CHECKS]
    assert any("cron definitions match" in n for n in names), (
        "the drift check must be registered in CHECKS, not merely defined")
