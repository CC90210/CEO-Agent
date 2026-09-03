"""The two checks that close the harness's silent-cron blind spots.

Both gates fail on the live fleet TODAY (4 fresh email_engine crash dumps; 2
opaque + 3 truncated cron results), so the interesting direction is the other
one: these tests prove each gate also goes GREEN when the defect is absent, and
that it does not fire on the legible-but-bracket-shaped results that live
alongside the real findings. A gate that can only fail teaches an operator to
ignore it just as fast as one that can only pass.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import harness_eval as he  # noqa: E402


def _dump(dirpath: Path, slug: str, when: datetime) -> Path:
    """Write a dump named the way scheduler.persist_failure names them."""
    path = dirpath / f"{slug}-{when.strftime('%Y%m%dT%H%M%SZ')}.log"
    path.write_text("job : x\nexit code : 1\n", encoding="utf-8")
    return path


@pytest.fixture
def dumps(tmp_path, monkeypatch):
    d = tmp_path / "cron_failures"
    d.mkdir()
    monkeypatch.setattr(he, "FAILURE_DUMP_DIR", d)
    return d


# ── failure dumps ───────────────────────────────────────────────────────────

def test_fresh_dump_fails_and_names_the_script(dumps):
    now = datetime.now(timezone.utc)
    _dump(dumps, "integrations-email-engine-py", now - timedelta(hours=2))
    _dump(dumps, "integrations-email-engine-py", now - timedelta(hours=5))
    _dump(dumps, "booking-engine-py", now - timedelta(hours=1))

    ok, detail = he.check_no_recent_cron_failure_dumps()

    assert ok is False
    assert "3 cron failure dump(s) <24h old" in detail
    assert "integrations-email-engine-py x2" in detail
    assert "booking-engine-py x1" in detail


def test_old_dumps_alone_are_history_not_a_failure(dumps):
    now = datetime.now(timezone.utc)
    for days in (2, 9, 30):
        _dump(dumps, "booking-engine-py", now - timedelta(days=days))

    ok, detail = he.check_no_recent_cron_failure_dumps()

    assert ok is True
    assert "3 older dumps retained" in detail


def test_dump_just_inside_the_window_still_counts(dumps):
    _dump(dumps, "funnel-sync-py", datetime.now(timezone.utc) - timedelta(hours=23, minutes=50))

    ok, detail = he.check_no_recent_cron_failure_dumps()

    assert ok is False
    assert "funnel-sync-py x1" in detail


def test_unrecognized_filename_falls_back_to_mtime(dumps):
    """A name the regex misses must not vanish from the count — skipping it is
    how a fresh crash reads as an empty directory."""
    (dumps / "legacy-dump.log").write_text("boom", encoding="utf-8")

    ok, detail = he.check_no_recent_cron_failure_dumps()

    assert ok is False
    assert "legacy-dump.log" in detail


def test_unreadable_dump_dir_fails_closed(dumps, monkeypatch):
    def _boom(_path):
        raise PermissionError("access denied")

    monkeypatch.setattr(he.os, "scandir", _boom)

    ok, detail = he.check_no_recent_cron_failure_dumps()

    assert ok is False
    assert "unreadable" in detail
    assert "PermissionError" in detail


def test_absent_dump_dir_is_green(tmp_path, monkeypatch):
    monkeypatch.setattr(he, "FAILURE_DUMP_DIR", tmp_path / "never-written")

    ok, detail = he.check_no_recent_cron_failure_dumps()

    assert ok is True
    assert "absent" in detail


# ── opaque / truncated cron results ─────────────────────────────────────────

def _rows(monkeypatch, *results):
    rows = [{"name": f"Job {i}", "is_active": True, "last_result": r}
            for i, r in enumerate(results)]
    monkeypatch.setattr(he, "_load_cron_rows", lambda: (rows, ""))
    return rows


# The exact shape found live 2026-08-29 on "Loud Failures Weekly Probe": a JSON
# summary cut at scheduler.py's out[-1][:200] boundary, mid-token.
_TRUNCATED_200 = ('{"reds":0,"yellows":2,"checks":[{"check":"cron-scripts","status":"green",'
                  '"detail":"all 24 SEED_JOBS scripts exist + parse","items":[]},'
                  '{"check":"hook-targets","status":"green","detail":"all hook comma')


def test_truncation_fixture_matches_the_live_slice_boundary():
    assert len(_TRUNCATED_200) == 200
    assert 200 in he._SCHEDULER_RESULT_SLICES


def test_bare_closing_brace_is_opaque_not_healthy(monkeypatch):
    _rows(monkeypatch, "]", "}")

    ok, detail = he.check_cron_results_legible()

    assert ok is False
    assert "2 OPAQUE" in detail


def test_truncated_json_is_reported_as_its_own_category(monkeypatch):
    _rows(monkeypatch, _TRUNCATED_200)

    ok, detail = he.check_cron_results_legible()

    assert ok is False
    assert "TRUNCATED" in detail
    assert "OPAQUE" not in detail


def test_legible_bracket_text_is_not_flagged(monkeypatch):
    """The false positive this check must never produce: "Daily State DB Backup"
    stores a 195-char "[OK] {'db': ...}" line. It opens with a bracket and does
    not parse as JSON, but every word of it survived."""
    legible = ("[OK] {'db': 'site_reputation', 'status': 'ok', 'dest': 'C:\\\\backup.db', "
               "'size_bytes': 94208, 'integrity': 'ok'}")
    assert len(legible) not in he._SCHEDULER_RESULT_SLICES
    _rows(monkeypatch, legible, "ok", "", None, {"replayed": 0}, [])

    ok, detail = he.check_cron_results_legible()

    assert ok is True
    assert "0 opaque, 0 truncated" in detail


def test_decoded_dict_result_never_counts_as_truncated(monkeypatch):
    """The Turso compat layer decodes JSON columns; a dict arrived intact."""
    _rows(monkeypatch, {"status": "ok", "before": {"versions": 258}})

    ok, _detail = he.check_cron_results_legible()

    assert ok is True


def test_inactive_rows_are_out_of_scope(monkeypatch):
    monkeypatch.setattr(he, "_load_cron_rows",
                        lambda: ([{"name": "Retired", "is_active": False, "last_result": "}"}], ""))

    ok, _detail = he.check_cron_results_legible()

    assert ok is True


def test_registry_error_fails_loudly_rather_than_reading_as_clean(monkeypatch):
    monkeypatch.setattr(he, "_load_cron_rows", lambda: (None, "cron_engine returned non-JSON"))

    ok, detail = he.check_cron_results_legible()

    assert ok is False
    assert detail == "cron_engine returned non-JSON"


# ── registration: an unregistered check IS the defect it detects ────────────

@pytest.mark.parametrize("fn", [
    he.check_no_recent_cron_failure_dumps,
    he.check_cron_results_legible,
])
def test_new_checks_are_registered_in_CHECKS(fn):
    registered = {f for _name, f, _model_only, _slice in he.CHECKS}
    assert fn in registered, f"{fn.__name__} exists but never runs"


def test_registered_checks_are_not_model_gated():
    """Both must run on a plain nightly invocation, not only --with-model."""
    for _name, fn, model_only, slice_name in he.CHECKS:
        if fn in (he.check_no_recent_cron_failure_dumps, he.check_cron_results_legible):
            assert model_only is False
            assert slice_name == "live-health"
