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
