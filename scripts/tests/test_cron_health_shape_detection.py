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
