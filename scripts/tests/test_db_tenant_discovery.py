"""Tenant-table discovery: one query instead of 206, without weakening the boundary.

`_discover_tenant_tables()` runs on EVERY `get_db()`. It used to issue one
`PRAGMA table_info` per table against a REMOTE database — 206 sequential round
trips at ~258 ms. Measured 2026-08-28: 38 of the 43 seconds each briefing engine
spent connecting, and the daily brief fans out ten of them. That is what
rendered "Client health: unavailable" in CC's brief while `client_health.py`
itself returned `status: ok` — the data was fine, the connect was not.

The single-query form measures 0.23 s for the same 145 tables.

WHY THESE TESTS ARE NOT OPTIONAL: the set this returns is exported by
`unscoped_tables()` as the tenant-scoping predicate. A short or empty result
does not read as an error — it reads as "nothing is tenant-scoped", and the
guard then waves through a cross-tenant query. A fast wrong answer here is
categorically worse than a slow right one, so the fast path is only ever
trusted when it is non-empty, and everything else falls back.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import db_turso  # noqa: E402


class _FakeConn:
    """Answers the two discovery shapes; records which was asked."""

    def __init__(self, *, tvf_rows=None, tvf_error=None, tables=None, cols=None):
        self.tvf_rows, self.tvf_error = tvf_rows, tvf_error
        self.tables, self.cols = tables or [], cols or {}
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append(sql)
        if "pragma_table_info" in sql:
            if self.tvf_error:
                raise self.tvf_error
            return _Rows(self.tvf_rows or [])
        if "sqlite_master" in sql:
            return _Rows([(t,) for t in self.tables])
        name = sql.split("(", 1)[1].rstrip(")").strip('"')
        return _Rows([(0, c, "TEXT", 0, None, 0) for c in self.cols.get(name, [])])


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _db(conn) -> db_turso.TursoDB:
    db = db_turso.TursoDB.__new__(db_turso.TursoDB)
    db._conn = conn
    return db


def test_the_fast_path_is_used_when_it_answers():
    conn = _FakeConn(tvf_rows=[("leads",), ("tenant_records",)])
    assert _db(conn)._discover_tenant_tables() == frozenset({"leads", "tenant_records"})
    assert not any("PRAGMA table_info" in c for c in conn.calls), (
        "the slow walk must not run when one query answered")


def test_an_error_in_the_fast_path_falls_back_and_still_answers():
    """A libsql build without table-valued functions must degrade to correct,
    not to empty."""
    conn = _FakeConn(tvf_error=RuntimeError("no such table-valued function"),
                     tables=["leads", "settings"],
                     cols={"leads": ["id", "tenant_id"], "settings": ["id"]})
    assert _db(conn)._discover_tenant_tables() == frozenset({"leads"})
    assert any("PRAGMA table_info" in c for c in conn.calls), "the fallback must run"


def test_an_EMPTY_fast_result_is_not_trusted():
    """THE ONE THAT MATTERS. An empty set does not read as an error downstream —
    it reads as 'nothing is tenant-scoped', and unscoped_tables() then waves a
    cross-tenant query through. Empty means fall back, never means answer."""
    conn = _FakeConn(tvf_rows=[], tables=["leads"], cols={"leads": ["id", "tenant_id"]})
    assert _db(conn)._discover_tenant_tables() == frozenset({"leads"})
    assert any("PRAGMA table_info" in c for c in conn.calls)


def test_the_fast_path_never_raises_through_get_db():
    """A connect that dies here takes down every caller of get_db(). Whatever
    the driver throws, discovery must return a set."""
    for exc in (RuntimeError("boom"), ValueError("hrana"), TypeError("nope")):
        conn = _FakeConn(tvf_error=exc, tables=[], cols={})
        assert _db(conn)._discover_tenant_tables() == frozenset()


def test_both_paths_apply_the_global_table_exemption():
    """GLOBAL_TABLES are exempt by policy. If only one path honours it, the
    scoping predicate changes meaning depending on which path ran."""
    if not db_turso.GLOBAL_TABLES:
        pytest.skip("no global tables configured")
    exempt = sorted(db_turso.GLOBAL_TABLES)[0]

    fast = _FakeConn(tvf_rows=[(exempt,), ("leads",)])
    slow = _FakeConn(tvf_error=RuntimeError("x"), tables=[exempt, "leads"],
                     cols={exempt: ["id", "tenant_id"], "leads": ["id", "tenant_id"]})
    assert _db(fast)._discover_tenant_tables_fast() == frozenset({"leads"})
    assert _db(slow)._discover_tenant_tables_slow() == frozenset({"leads"})


def test_names_are_lowercased_by_both_paths():
    """unscoped_tables() compares lowercased names. A path that returned mixed
    case would silently stop matching."""
    fast = _FakeConn(tvf_rows=[("TenantRecords",)])
    slow = _FakeConn(tvf_error=RuntimeError("x"), tables=["TenantRecords"],
                     cols={"TenantRecords": ["tenant_id"]})
    assert _db(fast)._discover_tenant_tables_fast() == frozenset({"tenantrecords"})
    assert _db(slow)._discover_tenant_tables_slow() == frozenset({"tenantrecords"})


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2] / ".env.agents").exists(),
                    reason="needs live Turso credentials")
def test_live_fast_and_slow_agree_exactly():
    """The only assertion that proves the optimisation did not change meaning:
    run BOTH against the real schema and compare the sets, not the counts."""
    db = db_turso.get_db()
    fast = db._discover_tenant_tables_fast()
    slow = db._discover_tenant_tables_slow()
    assert fast, "the fast path returned nothing against the live schema"
    assert fast == slow, f"discovery paths disagree: {fast ^ slow}"
