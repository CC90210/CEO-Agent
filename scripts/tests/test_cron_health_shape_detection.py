"""cron_health_check — failure is a SHAPE, not a prefix (2026-08-21).

The watchdog only ever flagged `last_result` strings starting with ERROR/FAILED,
on `is_active = True` rows. Three whole classes of dead automation were invisible
by construction:

  * a job that reports its own error count in a JSON summary,
  * a job that stopped running altogether (no new result at all),
  * a job somebody disarmed and forgot.

Eight SunBiz crons sat enabled-and-dead for fifteen days without one alert.

The test at the bottom, `test_a_decoded_dict_is_classified_like_a_json_string`,
pins the bug that code review did NOT catch and a live delivery probe did: the
Turso compat layer auto-decodes JSON TEXT columns, so `last_result` reaches the
classifier as a real dict. Stringifying that yields Python repr — `{'errors': 3}`
with single quotes — which json.loads rejects and the plain-text regex misses. So
the JSON detector passed every hand-written-string unit test while being dead
against every row in production. Hand-written fixtures agreed with the code and
both were wrong; only the live row disagreed.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

import cron_health_check as chc  # noqa: E402


# ── failure by shape ────────────────────────────────────────────────────────

def test_legacy_error_prefix_still_flags():
    """The rewrite must not lose the case it already handled."""
    assert chc.classify_last_result("ERROR: script_run exit 1: boom")[0] is True
    assert chc.classify_last_result("FAILED (exit 2): missing file")[0] is True


def test_json_summary_with_errors_is_a_failure():
    """The shape the prefix check was blind to. No 'ERROR' anywhere in it."""
    is_fail, reason = chc.classify_last_result('{"errors": 3, "sent": 0}')
    assert is_fail is True
    assert "errors=3" in reason


def test_healthy_json_summaries_stay_green():
    """Guard the guard. These are REAL last_result values from live rows — if
    the classifier flags any of them the watchdog pages CC hourly about a
    healthy fleet, which is how a watchdog gets muted."""
    for healthy in (
        '{"drained": 0}',
        '{"replayed": 0, "failed": 0, "remaining": 0}',
        '{"errors":0,"exhausted":1,"replied":1,"calls":1,"scanned":2,"in_scope":2,"live":true}',
        '{"status": "checked", "unread_count": 0, "message": "No unread emails"}',
        "[]",
        "synced: 157  ·  failed: 0",
        "ok: all crons healthy",
        "qualified: 0 / 0",
    ):
        assert chc.classify_last_result(healthy)[0] is False, healthy


def test_ok_false_and_error_status_are_failures():
    assert chc.classify_last_result('{"ok": false}')[0] is True
    assert chc.classify_last_result('{"status": "error"}')[0] is True
    assert chc.classify_last_result('{"status": "failed", "n": 0}')[0] is True


def test_nested_error_counts_are_found():
    """Handlers wrap their counts; a summary one level down still counts."""
    assert chc.classify_last_result('{"summary": {"errors": 2}, "ok": true}')[0] is True


def test_plain_text_counter_is_a_failure():
    assert chc.classify_last_result("processed 10, failed: 3")[0] is True
    assert chc.classify_last_result("processed 10, failed: 0")[0] is False


def test_an_opaque_result_is_not_a_failure():
    """Several jobs store the last stdout line of pretty-printed JSON, which is
    a lone '}'. Flagging that would page CC about three healthy jobs every hour.
    It is surfaced as `opaque` instead — visible, never alerting."""
    assert chc.classify_last_result("}")[0] is False
    assert chc._is_opaque("}") is True
    assert chc._is_opaque('{"errors": 1}') is False


def test_a_decoded_dict_is_classified_like_a_json_string():
    """THE BUG THE UNIT TESTS MISSED AND THE LIVE PROBE CAUGHT.

    The Turso compat layer decodes JSON TEXT columns, so this function receives
    a dict for exactly the rows it exists to catch. str(dict) is Python repr —
    single quotes — so json.loads fails and the text regex does not match. The
    detector was green in CI and dead in production.
    """
    is_fail, reason = chc.classify_last_result({"errors": 3, "processed": 0})
    assert is_fail is True, "a pre-decoded dict must classify like its string form"
    assert "errors=3" in reason
    assert chc.classify_last_result({"drained": 0})[0] is False
    assert chc.classify_last_result([])[0] is False


# ── failure by silence ──────────────────────────────────────────────────────

def _ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def test_a_job_that_stopped_running_is_stale():
    """The SunBiz case: last_result still says 'success' from two weeks ago."""
    stale, reason = chc.staleness("* * * * *", _ago(days=15))
    assert stale is True
    assert "missed" in reason


def test_a_job_running_on_time_is_not_stale():
    assert chc.staleness("* * * * *", _ago(minutes=2))[0] is False
    assert chc.staleness("0 6 * * *", _ago(hours=20))[0] is False


def test_staleness_scales_with_the_jobs_own_schedule():
    """A weekly job silent for two days is fine; a per-minute job is not.
    One flat threshold cannot express both, which is why the window is derived
    from the schedule."""
    assert chc.staleness("0 7 * * SUN", _ago(days=2))[0] is False
    assert chc.staleness("*/5 * * * *", _ago(days=2))[0] is True


def test_a_weekday_only_job_is_not_stale_over_the_weekend():
    """MON-FRI has a legitimate 3-day gap. Measuring against the MEAN interval
    would page CC every Sunday morning forever."""
    assert chc.staleness("0 10 * * MON-FRI", _ago(days=3, hours=1))[0] is False


def test_a_never_run_job_is_caught_via_created_at():
    """Enabled, scheduled, and never once executed is the worst state of all —
    it looks perfectly healthy in every dashboard."""
    stale, reason = chc.staleness("0 6 * * *", None, created_at=_ago(days=30))
    assert stale is True
    assert "never ran" in reason


def test_a_freshly_created_job_is_not_stale():
    """A row added an hour ago has not missed anything yet."""
    assert chc.staleness("0 8 * * *", None, created_at=_ago(hours=1))[0] is False


def test_an_unparseable_schedule_yields_no_verdict():
    """No opinion beats a wrong opinion — an unparseable cron must not be
    reported as dead."""
    assert chc.staleness("@reboot", _ago(days=99))[0] is False


# ── alert composition ───────────────────────────────────────────────────────

def test_dedup_key_is_unchanged_for_a_failing_only_alert():
    """An escalation ladder already in flight must NOT be reset by this rewrite:
    a stuck alert mid-backoff must not win a free re-fire because the code
    changed. Byte-identical to the pre-rewrite key when only failures exist."""
    buckets = chc._as_buckets([{"name": "B", "last_result": "ERROR"},
                               {"name": "A", "last_result": "ERROR"}])
    assert chc.alert_dedup_key(buckets) == "cron_failing:A|B"


def test_stale_and_disarmed_are_separate_conditions_in_the_key():
    """A job going quiet is news; it must page immediately rather than inherit
    the failing set's open backoff window."""
    a = chc.alert_dedup_key(chc._as_buckets({"failing": [{"name": "A"}]}))
    b = chc.alert_dedup_key(chc._as_buckets({"failing": [{"name": "A"}],
                                             "stale": [{"name": "S"}]}))
    assert a != b


def test_compose_separates_the_three_verdicts():
    """A crash, a silence and an operator toggle need different reactions from
    CC. Flattening them into one list is what let the disarmed ones hide."""
    text = chc.compose_alert(chc._as_buckets({
        "failing": [{"name": "F", "detail": "reported errors=2"}],
        "stale": [{"name": "S", "detail": "no run for 15.0d"}],
        "disarmed": [{"name": "D"}],
    }))
    assert "failing" in text and "stopped running" in text and "disarmed" in text
    assert "F" in text and "S" in text and "D" in text


def test_an_alert_that_would_be_dropped_falls_back_to_names_only():
    """notify() DROPS (does not reroute) bodies matching its APEX-domain filter.
    A tenant job's error snippet can quote one of those words, which would
    silently bin the whole page and then mark this watchdog red for a delivery
    that was refused rather than failed. The names-only fallback keeps the page
    landing."""
    buckets = chc._as_buckets({"failing": [
        {"name": "TPS worker", "detail": "tps lookup backlog exceeded"}]})
    body = chc.compose_alert(buckets)
    out = chc._deliverable(body, buckets)
    import notify as nf
    assert nf._NOT_BRAVO_DOMAIN_RE.search(body), "fixture no longer trips the filter"
    assert not nf._NOT_BRAVO_DOMAIN_RE.search(out), "fallback must be deliverable"
    assert "TPS worker" in out, "CC still needs to know WHICH job"


def test_client_tenant_rows_never_reach_ccs_digest():
    """CC's scope ruling (2026-08-22): Bravo's digest covers OASIS + personal
    automations only. A dead SunBiz job paged the founder about a client
    automation he neither owns nor operates; client tenants have their own
    watchdog (the dashboard health-check -> sunbiz-ops lane). The scan must
    keep OASIS-tenant rows (Atlas is CC's personal CFO) and drop the rest."""
    import cron_health_check as chc
    from types import SimpleNamespace
    from datetime import datetime, timezone

    class FakeQ:
        def __init__(self, rows): self._r = rows
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self): return SimpleNamespace(data=self._r)

    class FakeDb:
        def table(self, name):
            assert name == "tenant_cron_jobs"
            return FakeQ([
                {"id": "1", "tenant_id": "aa04fa1f-sun", "agent_key": "helios",
                 "name": "SunBiz Follow-up Generator", "enabled": 1,
                 "schedule": "0 6 * * *", "last_run_at": "2026-08-01T06:00:00Z",
                 "last_run_status": "error", "last_run_error": "boom",
                 "last_run_output": None, "created_at": "2026-05-01T00:00:00Z"},
                {"id": "2", "tenant_id": "ef8d389e-oasis", "agent_key": "atlas",
                 "name": "Atlas — Pulse Refresh", "enabled": 1,
                 "schedule": "0 */4 * * *", "last_run_at": "2026-08-01T06:00:00Z",
                 "last_run_status": "error", "last_run_error": "boom",
                 "last_run_output": None, "created_at": "2026-05-01T00:00:00Z"},
            ])

    findings = {"failing": [], "stale": [], "disarmed": [], "opaque": []}
    out = chc._scan_tenant_crons(FakeDb(), findings, datetime.now(timezone.utc))
    all_names = [x["name"] for k in out for x in out[k]]
    assert any("Atlas" in n for n in all_names), "CC's own (OASIS-tenant) rows must stay covered"
    assert not any("SunBiz" in n for n in all_names), (
        "a client-tenant row reached the founder's digest — the scope ruling regressed"
    )


def test_stale_skip_cannot_hide_unresolved_scheduler_failures():
    failed, reason = chc.classify_empire_run(
        "skipped-stale: next_run_at was 65 min behind threshold", 2,
    )
    assert failed is True
    assert "2 unresolved consecutive" in reason


def test_a_real_success_with_zero_fail_count_stays_healthy():
    assert chc.classify_empire_run("ok: posted 2", 0) == (False, "")


def _pulse_manifest_vs_disabled_row():
    """One manifest job declared active against one live row that is disabled."""
    jobs = [{
        "name": "Atlas - Pulse Refresh", "enabled": True,
        "schedule": "0 */4 * * *", "action_type": "script_run",
        "action_payload": {"script": "tools/pulse_publish.py", "args": ["refresh"]},
    }]
    rows = [{
        "id": "pulse", "tenant_id": "ef8d389e-oasis", "agent_key": "atlas",
        "name": "Atlas - Pulse Refresh", "enabled": 0,
        "schedule": "0 */4 * * *", "action_type": "script_run",
        "action_payload": '{"script":"tools/pulse_publish.py","args":["refresh"]}',
    }]
    return rows, jobs


def test_tenant_manifest_disabled_drift_is_not_silently_skipped():
    rows, jobs = _pulse_manifest_vs_disabled_row()
    issues = chc.tenant_manifest_issues(
        rows, jobs, agent_key="atlas", tenant_prefix="ef8d389e",
        enabled_authoritative=True,
    )
    assert issues == [{
        "bucket": "disarmed", "name": "Atlas - Pulse Refresh",
        "detail": "atlas manifest expects active; live tenant row is disabled",
    }]


def test_enabled_mismatch_is_silent_until_the_owning_agent_opts_in():
    """The on/off comparison must default OFF, or it is a permanent alarm.

    Atlas's register CLI writes the live row without writing the manifest, so
    three real Atlas rows sit disabled against a manifest that still says
    enabled. Comparing them by default puts a "3 disarmed" line in EVERY hourly
    digest, flips the watchdog's own last_result off "ok: all crons healthy"
    forever, and trains CC to ignore the alert — which is precisely how the
    original outage went unseen. Existence and behaviour drift still fire
    without the flag; only the operator-decidable field waits for an owner who
    keeps the two in step.
    """
    rows, jobs = _pulse_manifest_vs_disabled_row()
    assert chc.tenant_manifest_issues(
        rows, jobs, agent_key="atlas", tenant_prefix="ef8d389e",
    ) == []


def test_tenant_manifest_catches_missing_and_behaviour_drift():
    jobs = [
        {
            "name": "Atlas - Missing", "enabled": True,
            "schedule": "0 7 * * *", "action_type": "script_run",
            "action_payload": {"script": "tools/missing.py"},
        },
        {
            "name": "Atlas - Present", "enabled": True,
            "schedule": "0 8 * * *", "action_type": "script_run",
            "action_payload": {"script": "tools/present.py"},
        },
    ]
    rows = [{
        "id": "present", "tenant_id": "ef8d389e-oasis", "agent_key": "atlas",
        "name": "Atlas - Present", "enabled": 1,
        "schedule": "0 9 * * *", "action_type": "script_run",
        "action_payload": {"script": "tools/present.py"},
    }]
    issues = chc.tenant_manifest_issues(
        rows, jobs, agent_key="atlas", tenant_prefix="ef8d389e",
    )
    assert [(issue["name"], issue["bucket"]) for issue in issues] == [
        ("Atlas - Missing", "failing"),
        ("Atlas - Present", "failing"),
    ]
    assert "schedule" in issues[1]["detail"]


def test_find_bad_crons_fails_when_a_declared_job_vanishes():
    """The wiring, not the helper. Deleting the call must turn this red.

    audit_live_inventory() was unit-tested, but the single line in
    find_bad_crons that CALLS it was not. Remove that line and all 112 tests
    still passed — the hourly canary would silently stop checking the inventory
    contract, and the next time the Automations tab dropped from 41 rows to 4
    the watchdog would report "ok: all crons healthy" exactly as it did during
    the outage this guard exists to prevent.
    """
    import cron_engine
    from types import SimpleNamespace

    declared = cron_engine.SEED_JOBS[0]
    vanished = cron_engine.SEED_JOBS[1]["name"]

    class FakeQ:
        def __init__(self, rows): self._r = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def execute(self): return SimpleNamespace(data=self._r)

    class FakeDb:
        def table(self, name):
            if name == "cron_jobs":
                # Exactly one declared row survives. Every other SEED_JOBS entry
                # -- including `vanished` -- is absent, which is the outage.
                return FakeQ([{
                    "id": "only", "name": declared["name"], "is_active": 1,
                    "schedule": declared["schedule"],
                    "action_type": declared["action_type"],
                    "action_config": declared["action_config"],
                    "owner_agent_key": declared.get("owner_agent_key") or "bravo",
                    "last_result": "ok", "fail_count": 0,
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": "2026-05-01T00:00:00Z",
                }])
            return FakeQ([])

    import unittest.mock as mock
    with mock.patch.object(chc, "get_client", return_value=FakeDb()), \
            mock.patch.object(chc, "load_env", return_value={}), \
            mock.patch.object(chc, "_scan_daemon_backed", side_effect=lambda f: f):
        findings = chc.find_bad_crons(include_tenant=False)

    inventory = [f for f in findings["failing"]
                 if f.get("source") == "cron_jobs_inventory"]
    assert inventory, (
        "find_bad_crons returned no inventory findings while all but one declared "
        "SEED_JOBS row was missing — the audit_live_inventory() call is not wired in"
    )
    assert any(f["name"] == vanished for f in inventory), (
        f"the vanished job {vanished!r} was not named in the findings"
    )


# ── crashes that never reach a row ──────────────────────────────────────────

def _dump_dir_with(tmp_path, *names):
    for n in names:
        (tmp_path / n).write_text("boom", encoding="utf-8")
    return tmp_path


def test_an_unrecovered_crash_is_reported(tmp_path):
    """A dump newer than the row's last run means the job has not come back."""
    now = datetime.now(timezone.utc)
    crashed = (now - timedelta(minutes=10)).strftime("%Y%m%dT%H%M%SZ")
    _dump_dir_with(tmp_path, f"scripts-review-loop-py-{crashed}.log")

    rows = [{
        "name": "Bravo - Review Harvest",
        "action_config": {"script": "scripts/review_loop.py"},
        "last_run_at": (now - timedelta(hours=3)).isoformat(),
        "last_result": "drained=0",
    }]
    unrecovered, recovered = chc.scan_crash_dumps(rows, now, dump_dir=tmp_path)
    assert len(unrecovered) == 1, (unrecovered, recovered)
    assert not recovered
    assert "hard crash dump" in unrecovered[0]["detail"]
    assert unrecovered[0]["source"] == "cron_failures"


def test_a_crash_the_job_recovered_from_is_recorded_but_never_paged(tmp_path):
    """THE ALARM-FATIGUE GUARD.

    24h held 18 dumps from 9 jobs, every row green by the time anyone read them.
    Paging all of them would leave this bucket non-empty every hour, flipping the
    watchdog's own last_result off "ok: all crons healthy" permanently -- which
    is how a digest gets muted, which is the failure this file exists to prevent.
    """
    now = datetime.now(timezone.utc)
    crashed = (now - timedelta(hours=3)).strftime("%Y%m%dT%H%M%SZ")
    _dump_dir_with(tmp_path, f"scripts-review-loop-py-{crashed}.log")

    rows = [{
        "name": "Bravo - Review Harvest",
        "action_config": {"script": "scripts/review_loop.py"},
        "last_run_at": (now - timedelta(minutes=5)).isoformat(),  # ran AFTER the crash
        "last_result": "drained=0",
    }]
    unrecovered, recovered = chc.scan_crash_dumps(rows, now, dump_dir=tmp_path)
    assert not unrecovered, f"a recovered crash was paged: {unrecovered}"
    assert len(recovered) == 1
    assert "since run again" in recovered[0]["detail"]


def test_a_dump_older_than_24h_is_ignored(tmp_path):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=3)).strftime("%Y%m%dT%H%M%SZ")
    _dump_dir_with(tmp_path, f"scripts-review-loop-py-{old}.log")
    rows = [{"name": "X", "action_config": {"script": "scripts/review_loop.py"},
             "last_run_at": None, "last_result": ""}]
    assert chc.scan_crash_dumps(rows, now, dump_dir=tmp_path) == ([], [])


def test_a_missing_dump_directory_is_healthy_not_an_error(tmp_path):
    """No dumps dir is the normal state on a fresh machine."""
    now = datetime.now(timezone.utc)
    rows = [{"name": "X", "action_config": {"script": "scripts/x.py"},
             "last_run_at": None, "last_result": ""}]
    assert chc.scan_crash_dumps(rows, now, dump_dir=tmp_path / "nope") == ([], [])


def test_the_dump_slug_matches_the_schedulers_own_transform():
    """The filename is derived from the SCRIPT PATH, never the job name, so
    correlating a dump to a row has to go through the same transform."""
    assert chc.dump_slug_for("scripts/review_loop.py") == "scripts-review-loop-py"
    assert chc.dump_slug_for("scripts/marketing_publish_drain.py") == \
        "scripts-marketing-publish-drain-py"


# ── the crashed bucket must be WIRED, not merely computed ───────────────────
# Adding a bucket is four separate couplings, and the first draft of this one
# had exactly zero of them: scan_crash_dumps computed findings that never
# reached the dedup key, never reached the names-only fallback, never entered
# `alertable` (so nothing paged), and `_recovered_crashes` was populated and
# then discarded by _as_buckets before anything could read it. A capability
# wired to nothing is the defect this whole branch exists to remove, so each
# coupling gets a test that fails when it is cut.

def _crash(name):
    return {"name": name, "source": "cron_failures", "last_result": "",
            "last_run_at": None, "detail": "2 hard crash dump(s) in 24h"}


def test_a_crash_is_its_own_condition_in_the_dedup_key():
    """A fresh segfault must page now, not inherit an unrelated backoff ladder."""
    base = chc._as_buckets({"failing": [{"name": "A"}]})
    with_crash = chc._as_buckets({"failing": [{"name": "A"}],
                                  "crashed": [_crash("Review Harvest")]})
    assert chc.alert_dedup_key(base) != chc.alert_dedup_key(with_crash), (
        "a crash does not change the dedup key, so a new crash is swallowed by "
        "the backoff window an unrelated failing job already opened"
    )
    assert "crashed=" in chc.alert_dedup_key(with_crash)


def test_two_different_crashes_are_different_conditions():
    a = chc._as_buckets({"crashed": [_crash("X")]})
    b = chc._as_buckets({"crashed": [_crash("Y")]})
    assert chc.alert_dedup_key(a) != chc.alert_dedup_key(b)


def test_the_names_only_fallback_still_names_the_crashed_jobs():
    """When a result snippet trips notify()'s domain filter the body is replaced
    by names. Omitting crashed there drops them from the only page CC gets."""
    buckets = chc._as_buckets({"crashed": [_crash("Marketing Publish Drain")]})
    out = chc._deliverable("body mentioning TPS phone lookup", buckets)
    assert "Marketing Publish Drain" in out or out == "body mentioning TPS phone lookup", (
        "the crashed job vanished from the names-only fallback"
    )


def test_recovered_crashes_survive_as_buckets():
    """Populated by the scan and then dropped before anything could read it."""
    buckets = chc._as_buckets({"recovered_crashes": [_crash("Review Harvest")]})
    assert buckets["recovered_crashes"], (
        "_as_buckets discarded _recovered_crashes — the instability signal is "
        "computed and then thrown away"
    )


def test_recovered_crashes_never_reach_the_alert():
    """The alarm-fatigue guard, pinned. They are reported, never paged."""
    buckets = chc._as_buckets({"recovered_crashes": [_crash("Review Harvest")]})
    assert not buckets["crashed"], "a recovered crash leaked into the paging bucket"
    assert "crashed=" not in chc.alert_dedup_key(buckets)


def test_the_legacy_list_shape_still_coerces():
    """telegram_alert is called by tests and possibly out-of-tree with a bare
    list. Adding keys must not break that path."""
    buckets = chc._as_buckets([{"name": "A", "last_result": "ERROR"}])
    assert buckets["crashed"] == [] and buckets["recovered_crashes"] == []
    assert chc.alert_dedup_key(buckets) == "cron_failing:A"


def test_an_unrecovered_crash_makes_the_run_alertable(monkeypatch, capsys):
    """The coupling the other three tests could not see.

    `alertable` is what decides whether telegram_alert is called at all. A
    crashed bucket that never enters it is a JSON field nobody is paged by --
    the wired-to-nothing shape this branch exists to remove. Nothing else
    exercises it, so cutting `+ buckets["crashed"]` left every other test green.
    """
    import json as _json

    crashed = {"name": "Bravo - Review Harvest", "source": "cron_failures",
               "last_result": "", "last_run_at": None,
               "detail": "2 hard crash dump(s) in 24h"}
    monkeypatch.setattr(chc, "find_bad_crons", lambda **kw: {
        "failing": [], "stale": [], "disarmed": [], "opaque": [],
        "crashed": [crashed], "recovered_crashes": [],
    })
    monkeypatch.setattr(sys, "argv", ["cron_health_check.py", "--json", "--dry-run"])
    chc.main()
    payload = _json.loads(capsys.readouterr().out)

    assert payload["crashed_count"] == 1
    assert payload["bad_count"] >= 1, (
        "an unrecovered hard crash left bad_count at 0, so no alert would ever "
        "be sent — the crashed bucket is computed and then never paged"
    )


def test_a_recovered_crash_alone_does_not_make_the_run_alertable(monkeypatch, capsys):
    """The other half: reported in the payload, never paged."""
    import json as _json

    recovered = {"name": "Bravo - Review Harvest", "source": "cron_failures",
                 "last_result": "", "last_run_at": None,
                 "detail": "2 hard crash dump(s) in 24h (job has since run again)"}
    monkeypatch.setattr(chc, "find_bad_crons", lambda **kw: {
        "failing": [], "stale": [], "disarmed": [], "opaque": [],
        "crashed": [], "recovered_crashes": [recovered],
    })
    monkeypatch.setattr(sys, "argv", ["cron_health_check.py", "--json", "--dry-run"])
    chc.main()
    payload = _json.loads(capsys.readouterr().out)

    assert payload["recovered_crash_count"] == 1, "the signal was dropped"
    assert payload["bad_count"] == 0, (
        "a crash the job already recovered from would page CC — that is the "
        "alarm fatigue that mutes the digest"
    )


def test_the_nightly_evals_own_scoreboard_is_not_a_crash(tmp_path):
    """5 of the 50 dumps on disk are the harness scoring ITSELF red.

    harness_eval writes a dump every time it exits non-zero on its own score.
    That is a scoreboard, not a crash, and harness_eval already suppresses it on
    its own side. Counting them here would put this bucket permanently
    non-empty, flip the watchdog's last_result off "ok: all crons healthy" and
    mute the digest -- the failure this branch exists to remove.

    The banner is what proves the script ran and scored itself. A genuine crash
    of harness_eval (import error, OS kill) writes NO banner and still counts,
    which is the whole point of the distinction.
    """
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(minutes=10)).strftime("%Y%m%dT%H%M%SZ")

    scoreboard = tmp_path / f"scripts-harness-eval-py-{ts}.log"
    scoreboard.write_text(
        "exit code : 1\nHARNESS EVAL - 13/17 checks green\n", encoding="utf-8")

    rows = [{
        "name": "Bravo - Nightly Harness Eval",
        "action_config": {"script": "scripts/harness_eval.py"},
        "last_run_at": (now - timedelta(hours=6)).isoformat(),
        "last_result": "ERROR: ... HARNESS EVAL - 13/17",
    }]
    unrecovered, recovered = chc.scan_crash_dumps(rows, now, dump_dir=tmp_path)
    assert not unrecovered and not recovered, (
        f"the eval's own scoreboard was counted as a crash: {unrecovered or recovered}"
    )

    # And the control: a REAL crash of the same script still counts.
    scoreboard.unlink()
    (tmp_path / f"scripts-harness-eval-py-{ts}.log").write_text(
        "exit code : 3221225477\nTraceback: access violation\n", encoding="utf-8")
    unrecovered, _ = chc.scan_crash_dumps(rows, now, dump_dir=tmp_path)
    assert unrecovered, (
        "a genuine crash of harness_eval (no self-score banner) was suppressed "
        "along with its scoreboards"
    )


def _rows_from_seeds(ce_mod, **overrides_by_name):
    rows = []
    for seed in ce_mod.SEED_JOBS:
        row = {
            "id": seed["name"], "name": seed["name"], "is_active": 1,
            "schedule": seed["schedule"], "action_type": seed["action_type"],
            "action_config": seed["action_config"],
            "owner_agent_key": seed.get("owner_agent_key") or "bravo",
            "description": seed.get("description"),
            "last_result": "ok", "fail_count": 0,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "created_at": "2026-05-01T00:00:00Z",
        }
        row.update(overrides_by_name.get(seed["name"], {}))
        rows.append(row)
    return rows


def test_a_drifted_field_is_reported_but_never_paged():
    """Realigning drift means pushing to the shared cron registry, which
    CLAUDE.md makes a reviewed production mutation. The gap between editing a
    seed and CC approving the push is operator-sanctioned and can last days --
    an hourly page through that window is an alarm CC cannot clear, which is how
    the digest gets muted. It is also what the other two surfaces already
    decided: generate_automations marks drift per-row, cmd_drift exits non-zero
    only on missing/duplicate.
    """
    import cron_engine as ce_mod

    victim = ce_mod.SEED_JOBS[0]["name"]
    rows = _rows_from_seeds(ce_mod, **{victim: {"schedule": "59 23 31 2 *"}})

    findings = {"failing": [], "stale": [], "disarmed": [], "opaque": [],
                "crashed": [], "recovered_crashes": [], "inventory_drift": []}
    out = chc._scan_empire_inventory_contract(rows, findings)

    assert out["inventory_drift"], "a drifted field produced no finding at all"
    assert any(victim in f["name"] for f in out["inventory_drift"])
    assert not out["failing"], (
        f"drift landed in the paging bucket: {[f['name'] for f in out['failing']]}. "
        f"CC would be paged hourly for a config gap only a reviewed seed push "
        f"can close."
    )


def test_a_missing_job_still_pages():
    """The control. missing/duplicate mean the inventory itself is wrong --
    a declared job has no trigger. That is the 4-of-41 outage and it must page."""
    import cron_engine as ce_mod

    rows = _rows_from_seeds(ce_mod)[:1]          # every other declared job absent
    findings = {"failing": [], "stale": [], "disarmed": [], "opaque": [],
                "crashed": [], "recovered_crashes": [], "inventory_drift": []}
    out = chc._scan_empire_inventory_contract(rows, findings)

    assert out["failing"], "a missing declared job did not page"
    assert all("missing" in f["detail"] or "duplicate" in f["detail"]
               for f in out["failing"]), [f["detail"] for f in out["failing"]]


def test_inventory_drift_is_surfaced_and_excluded_from_alertable(monkeypatch, capsys):
    import json as _json

    drift = {"name": "Break-Glass Drill (quarterly)", "source": "cron_jobs_inventory",
             "last_result": "", "last_run_at": None,
             "detail": "inventory drift: live row disagrees with SEED_JOBS: action_type"}
    monkeypatch.setattr(chc, "find_bad_crons", lambda **kw: {
        "failing": [], "stale": [], "disarmed": [], "opaque": [], "crashed": [],
        "recovered_crashes": [], "inventory_drift": [drift],
    })
    monkeypatch.setattr(sys, "argv", ["cron_health_check.py", "--json", "--dry-run"])
    chc.main()
    payload = _json.loads(capsys.readouterr().out)

    assert payload["inventory_drift_count"] == 1, "the drift signal was dropped"
    assert payload["bad_count"] == 0, (
        "a drifted field would page CC hourly until a reviewed seed push clears it"
    )
