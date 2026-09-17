"""The inbox sweep's Turso connect must be bounded, not merely retried.

state/email_sweep.log is the evidence these tests exist for. On 2026-09-12 pid
32776 logged `start` at 21:11:33 and never logged `db_connected`; the failure
dump is stamped 21:16:25, ~292s later, at the scheduler's 300s wall. Every
stage after the connect is unreached code, so the sweep died inside
get_supabase() with both streams empty.

Nothing in that path was bounded. lib/db_turso.TursoDB.__init__ calls
libsql.connect() with no timeout parameter and then _discover_tenant_tables(),
whose slow path issues 206 sequential remote PRAGMA round trips. db_turso.py is
shared substrate the whole fleet reads (Rule 10), so the bound lives at the
email_engine call site instead of changing connect semantics fleet-wide.

These tests pin the two properties that make that bound worth having: it must
actually fire on a hang, and it must not disguise a real error as one.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from integrations import email_engine as ee  # noqa: E402


# --- the bound itself ---------------------------------------------------------

def test_a_connect_that_returns_in_time_passes_its_value_through():
    """The happy path is 1-4s in production; the wrapper must be invisible."""
    assert ee._bounded("fast", lambda: "db-handle", 5) == "db-handle"


def test_a_hung_connect_raises_instead_of_eating_the_whole_wall():
    """The 2026-09-12 incident in miniature. Without this the call blocks until
    the scheduler kills the process, which produces a dump with two empty
    streams and no way to tell a hang from a crash."""
    release = threading.Event()
    try:
        started = time.monotonic()
        with pytest.raises(TimeoutError) as caught:
            ee._bounded("hung", lambda: release.wait(30), 0.2)
        elapsed = time.monotonic() - started
        assert elapsed < 5, f"bound did not fire promptly ({elapsed:.1f}s)"
        assert "hung" in str(caught.value), "the label must name what hung"
    finally:
        # Let the abandoned worker finish rather than leaving it parked for the
        # rest of the session.
        release.set()


def test_the_abandoned_worker_cannot_hold_the_interpreter_open():
    """_bounded cannot kill the thread — Python cannot interrupt a blocking
    socket read on another thread — so the only thing keeping that leak
    harmless is daemon=True. If it were a non-daemon thread, a timed-out sweep
    would hang at exit instead of exiting non-zero, and the job would go from a
    loud failure to a silent one."""
    release = threading.Event()
    try:
        with pytest.raises(TimeoutError):
            ee._bounded("daemon-check", lambda: release.wait(30), 0.2)
        leftover = [t for t in threading.enumerate()
                    if t.name == "bounded-daemon-check"]
        assert leftover, "expected the abandoned worker to still be running"
        assert all(t.daemon for t in leftover), "abandoned worker must be a daemon"
    finally:
        release.set()


def test_a_real_failure_is_re_raised_not_relabelled_as_a_timeout():
    """A bad credential, a DNS failure, a schema error — each must reach the
    caller as itself. Converting every fault into TimeoutError would send real
    bugs down the transient-retry path and then report them as slowness."""
    def boom():
        raise ValueError("Hrana: tcp connect error (os error 10060)")

    with pytest.raises(ValueError, match="10060"):
        ee._bounded("boom", boom, 5)


# --- how the bound composes with the retry wrapper ----------------------------

def test_a_timeout_is_classified_transient_so_the_connect_is_retried():
    """_retry_transient decides by transport MARKER, not exception type. If
    TimeoutError were not transient it would be re-raised on the first attempt
    and a single slow connect would fail the whole sweep."""
    assert ee._is_transient(TimeoutError("turso connect exceeded 60s")) is True


def test_the_retry_budget_fits_inside_the_jobs_wall():
    """The arithmetic in the DB_CONNECT_TIMEOUT comment, pinned.

    The wall is not in cron_engine.SEED_JOBS: the "Inbound Email Sweep" row has
    action_type "email_inbox_check" and an empty action_config, so the number
    lives in scheduler.run_email_inbox_check. This reads it out of the source
    rather than hardcoding 300 twice — if that call is reshaped, this fails and
    a human re-checks the budget, which is the intended outcome.
    """
    src = (REPO / "scripts" / "scheduler.py").read_text(encoding="utf-8")
    m = re.search(
        r'run_script\(\s*"integrations/email_engine\.py".*?timeout=(\d+)',
        src, re.S)
    assert m, "could not find the inbox sweep's run_script call in scheduler.py"
    wall = int(m.group(1))

    worst_case = (ee.DB_CONNECT_TIMEOUT * ee.CONNECT_ATTEMPTS
                  + ee.CONNECT_RETRY_SLEEP * (ee.CONNECT_ATTEMPTS - 1))
    assert worst_case < wall, (
        f"connect budget {worst_case}s >= job wall {wall}s — a slow connect "
        f"would consume the entire run and leave no time for the sweep")
