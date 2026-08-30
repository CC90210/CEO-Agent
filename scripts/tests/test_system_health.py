"""system_health — the loud-failures probe, and the two ways it lied.

2026-08-03. The probe reported "1 cron(s) failing" to CC every hour. Two defects,
one symptom:

  1. Its single RED was a FALSE POSITIVE. check_path_drift flagged
     agent_genome.py → scripts/agent_sleep.py, but agent_genome's DEFAULTS are
     CANDIDATE lists ("the gene is expressed if ANY candidate exists") and that
     filename belongs to a sibling repo. Creating the file to satisfy the checker
     would have invented a dependency.
  2. Exiting 1 on a finding made a working probe look like a broken cron, and
     cron_health_check re-paged hourly for as long as the finding stood.

These tests pin both the fix AND the detection strength it must not cost:
a suppression marker that silences real drift is worse than the false positive.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import system_health as sh  # noqa: E402


# ── path-drift: the marker must be narrow ────────────────────────────────────

def _probe_dir(tmp_path, monkeypatch, body: str):
    """Point the probe at a throwaway tree containing one file."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "thing.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(sh, "PROJECT_ROOT", tmp_path)
    return sh.check_path_drift()


def test_unresolved_reference_is_still_red(tmp_path, monkeypatch):
    """Guard the guard. The whole point of this probe is catching a path that
    stopped resolving — if the marker work broke that, everything else is moot."""
    r = _probe_dir(tmp_path, monkeypatch, 'TARGET = "scripts/nope.py"\n')
    assert r["status"] == sh.RED, r
    assert any("scripts/nope.py" in i for i in r["items"])


def test_marker_on_the_same_line_suppresses_that_ref(tmp_path, monkeypatch):
    r = _probe_dir(tmp_path, monkeypatch,
                   'TARGET = "scripts/nope.py"  # path-drift-ok\n')
    assert r["status"] == sh.GREEN, r


def test_marker_does_not_suppress_a_different_ref_in_the_same_file(tmp_path, monkeypatch):
    """The marker is per-REF, not per-file. A file that legitimately names one
    cross-repo candidate must still red on a genuine drift two lines later."""
    r = _probe_dir(tmp_path, monkeypatch,
                   'A = "scripts/candidate.py"  # path-drift-ok\n'
                   'B = "scripts/really_gone.py"\n')
    assert r["status"] == sh.RED, r
    assert any("really_gone" in i for i in r["items"])
    assert not any("candidate" in i for i in r["items"])


def test_segmented_multiline_reference_is_still_detected(tmp_path, monkeypatch):
    """A Path build wrapped across lines is the incident class this probe exists
    for. A line-by-line scanner would silently stop seeing it — the suppression
    lookup runs as a separate pass precisely so detection keeps reading the blob."""
    r = _probe_dir(tmp_path, monkeypatch,
                   'P = (ROOT\n     / "scripts"\n     / "state"\n     / "ghost.py")\n')
    assert r["status"] == sh.RED, r
    assert any("ghost.py" in i for i in r["items"])


def test_live_repo_has_no_path_drift():
    """The actual condition CC was paged about."""
    r = sh.check_path_drift()
    assert r["status"] == sh.GREEN, r["items"]


# ── the alert identity ───────────────────────────────────────────────────────

def _rep(*checks):
    return {"reds": sum(1 for c in checks if c["status"] == sh.RED),
            "yellows": 0, "checks": list(checks)}


def test_dedup_key_names_only_the_red_checks():
    rep = _rep({"check": "path-drift", "status": sh.RED, "detail": "x", "items": []},
               {"check": "pm2-paths", "status": sh.GREEN, "detail": "ok", "items": []},
               {"check": "silent-except", "status": sh.YELLOW, "detail": "y", "items": []})
    assert sh.red_dedup_key(rep) == "system_health_red:path-drift"


def test_dedup_key_ignores_detail_drift():
    """The identity must survive the counts moving. Detail strings carry file
    counts that change run to run; keying on them mints a new identity every
    week and the backoff ladder never engages."""
    a = _rep({"check": "path-drift", "status": sh.RED, "detail": "3 refs", "items": ["a"]})
    b = _rep({"check": "path-drift", "status": sh.RED, "detail": "4 refs", "items": ["b"]})
    assert sh.red_dedup_key(a) == sh.red_dedup_key(b)


def test_a_new_red_check_is_a_new_condition():
    one = _rep({"check": "path-drift", "status": sh.RED, "detail": "x", "items": []})
    two = _rep({"check": "path-drift", "status": sh.RED, "detail": "x", "items": []},
               {"check": "pm2-paths", "status": sh.RED, "detail": "x", "items": []})
    assert sh.red_dedup_key(one) != sh.red_dedup_key(two)


def test_notify_reds_passes_the_condition_key_and_is_silent_when_green(monkeypatch):
    sent = {}
    import notify as nf
    monkeypatch.setattr(nf, "notify", lambda msg, **kw: sent.update(kw, msg=msg) or True)

    assert sh.notify_reds(_rep({"check": "x", "status": sh.GREEN, "detail": "", "items": []})) is False
    assert sent == {}

    sh.notify_reds(_rep({"check": "path-drift", "status": sh.RED,
                         "detail": "1 unresolved", "items": ["a.py → b.py"]}))
    assert sent["dedup_key"] == "system_health_red:path-drift"
    assert sent["force"] is True
    assert "path-drift" in sent["msg"]


# ── the exit contract ────────────────────────────────────────────────────────

def test_cron_no_longer_runs_the_probe_with_strict():
    """A finding must not present as a broken cron. EXECUTION_RULES § 19: a
    blocking condition exits 0 and reports — the probe owns its own alert now."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
    import importlib.util as u
    spec = u.spec_from_file_location(
        "ce", Path(__file__).resolve().parent.parent / "core" / "cron_engine.py")
    mod = u.module_from_spec(spec)
    spec.loader.exec_module(mod)

    job = next(j for j in mod.SEED_JOBS if j["name"] == "Loud Failures Weekly Probe")
    args = job["action_config"]["args"]
    assert "--strict" not in args, "cron must not exit 1 on a finding"
    assert "--notify" in args, "removing --strict without --notify would make it silent"


def test_a_suppressed_alert_does_not_make_the_probe_red(monkeypatch):
    """Same trap as cron_health_check, in code written the same day. notify()
    returns False for both "deduped" and "failed"; treating suppression as
    failure would make the probe exit 1 and present as a broken cron — exactly
    what dropping --strict was meant to stop."""
    import notify as nf
    monkeypatch.setattr(nf, "notify", lambda *a, **kw: False)
    monkeypatch.setattr(nf, "LAST_SUPPRESSED", True)
    rep = _rep({"check": "path-drift", "status": sh.RED, "detail": "x", "items": []})
    assert sh.notify_reds(rep) is True


def test_a_genuinely_failed_probe_alert_is_still_red(monkeypatch):
    import notify as nf
    monkeypatch.setattr(nf, "notify", lambda *a, **kw: False)
    monkeypatch.setattr(nf, "LAST_SUPPRESSED", False)
    rep = _rep({"check": "path-drift", "status": sh.RED, "detail": "x", "items": []})
    assert sh.notify_reds(rep) is False


def test_a_failed_alarm_is_itself_a_broken_cron(monkeypatch, capsys):
    """Codex [P2]. Dropping --strict moved the alarm from the exit code into
    notify(). If that send fails and the probe still exits 0, the cron records a
    clean run while a red condition goes completely silent — the noisy true alert
    traded for no alert at all. A broken reporting path IS a broken cron."""
    monkeypatch.setattr(sh, "run", lambda: _rep(
        {"check": "path-drift", "status": sh.RED, "detail": "x", "items": []}))
    monkeypatch.setattr(sys, "argv", ["system_health.py", "--json", "--notify"])

    monkeypatch.setattr(sh, "notify_reds", lambda _rep: False)   # send failed
    assert sh.main() == 1
    assert "did not send" in capsys.readouterr().err

    monkeypatch.setattr(sh, "notify_reds", lambda _rep: True)    # send landed
    assert sh.main() == 0, "a reported finding must NOT look like a broken cron"
    capsys.readouterr()


def test_a_green_run_with_notify_stays_green(monkeypatch, capsys):
    """No reds means nothing to send — an unused alarm must not be read as a
    failed one."""
    monkeypatch.setattr(sh, "run", lambda: _rep(
        {"check": "path-drift", "status": sh.GREEN, "detail": "ok", "items": []}))
    monkeypatch.setattr(sh, "notify_reds", lambda _rep: False)
    monkeypatch.setattr(sys, "argv", ["system_health.py", "--json", "--notify"])
    assert sh.main() == 0
    capsys.readouterr()


def test_strict_still_exits_nonzero_for_humans_and_ci(monkeypatch, capsys):
    """The escape hatch has to keep working, or CI loses its gate."""
    monkeypatch.setattr(sh, "run", lambda: _rep(
        {"check": "path-drift", "status": sh.RED, "detail": "x", "items": []}))
    monkeypatch.setattr(sys, "argv", ["system_health.py", "--strict", "--json"])
    assert sh.main() == 1
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["system_health.py", "--json"])
    assert sh.main() == 0
