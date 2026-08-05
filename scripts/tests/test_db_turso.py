"""Tests for the Turso DAL — chiefly that the tenant guard FAILS CLOSED.

This file exists because Turso has no RLS. Supabase refused a cross-tenant read
in the database; here the only thing standing between a bug and a cross-tenant
leak is db_turso's guard. So these tests do not merely assert the happy path —
they attempt the leak and require an exception.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.db_turso import (  # noqa: E402
    TursoConfigError,
    TursoDB,
    UnscopedQueryError,
    mentions_tenant_filter,
    referenced_tables,
    resolve_target,
)

TENANT_A = "tenant-aaaa"
TENANT_B = "tenant-bbbb"


@pytest.fixture()
def db(tmp_path) -> TursoDB:
    conn_path = str(tmp_path / "t.db")
    d = TursoDB(conn_path, None, "local(test)")
    d.execute(
        'CREATE TABLE "leads" ("id" TEXT PRIMARY KEY, "tenant_id" TEXT NOT NULL, '
        '"email" TEXT, "status" TEXT)',
        allow_unscoped=True, reason="test setup",
    )
    d.execute(
        'CREATE TABLE "skills_registry" ("id" TEXT PRIMARY KEY, "name" TEXT)',
        allow_unscoped=True, reason="test setup",
    )
    d.execute(
        'CREATE TABLE "scheduled_sends" ("id" TEXT PRIMARY KEY, "tenant_id" TEXT NOT NULL, '
        '"claimed_by" TEXT)',
        allow_unscoped=True, reason="test setup",
    )
    d.commit()
    d._tenant_tables = d._discover_tenant_tables()  # re-scan after DDL
    return d


# ----------------------------------------------------------------- discovery

def test_tenant_tables_discovered_from_live_schema(db):
    assert "leads" in db.tenant_tables
    assert "scheduled_sends" in db.tenant_tables
    assert "skills_registry" not in db.tenant_tables


# ------------------------------------------------------------ the guard bites

def test_select_without_tenant_id_raises(db):
    with pytest.raises(UnscopedQueryError, match="requires tenant_id"):
        db.select("leads")


def test_raw_sql_without_tenant_filter_raises(db):
    with pytest.raises(UnscopedQueryError, match="without a tenant_id filter"):
        db.query("SELECT * FROM leads WHERE status = ?", ["warm"])


def test_raw_join_touching_scoped_table_raises(db):
    with pytest.raises(UnscopedQueryError):
        db.query("SELECT s.name FROM skills_registry s JOIN leads l ON l.id = s.id")


def test_update_without_tenant_filter_raises(db):
    with pytest.raises(UnscopedQueryError):
        db.execute("UPDATE leads SET status = 'dead'")


def test_delete_without_tenant_filter_raises(db):
    with pytest.raises(UnscopedQueryError):
        db.execute("DELETE FROM leads")


def test_insert_without_tenant_id_raises(db):
    with pytest.raises(UnscopedQueryError, match="must stamp tenant_id"):
        db.insert("leads", {"id": "1", "email": "a@b.com"})


def test_claim_without_tenant_id_raises(db):
    with pytest.raises(UnscopedQueryError):
        db.claim("scheduled_sends", key={"id": "1"},
                 set_values={"claimed_by": "w1"}, unclaimed_col="claimed_by")


# ------------------------------------------------------- the guard lets through

def test_unscoped_table_needs_no_tenant(db):
    db.insert("skills_registry", {"id": "s1", "name": "ship"})
    db.commit()
    assert db.select("skills_registry")[0]["name"] == "ship"


def test_scoped_read_returns_only_that_tenant(db):
    db.insert("leads", {"id": "1", "email": "a@a.com"}, tenant_id=TENANT_A)
    db.insert("leads", {"id": "2", "email": "b@b.com"}, tenant_id=TENANT_B)
    db.commit()
    rows = db.select("leads", tenant_id=TENANT_A)
    assert [r["email"] for r in rows] == ["a@a.com"]


def test_explicit_bypass_is_allowed_but_must_be_deliberate(db):
    db.insert("leads", {"id": "1", "email": "a@a.com"}, tenant_id=TENANT_A)
    db.insert("leads", {"id": "2", "email": "b@b.com"}, tenant_id=TENANT_B)
    db.commit()
    rows = db.select("leads", allow_unscoped=True, reason="admin cross-tenant audit")
    assert len(rows) == 2


# ------------------------------------------------- compare-and-swap (send slot)

def test_claim_succeeds_once_and_only_once(db):
    db.insert("scheduled_sends", {"id": "s1"}, tenant_id=TENANT_A)
    db.commit()
    first = db.claim("scheduled_sends", key={"id": "s1"},
                     set_values={"claimed_by": "worker-1"},
                     unclaimed_col="claimed_by", tenant_id=TENANT_A)
    second = db.claim("scheduled_sends", key={"id": "s1"},
                      set_values={"claimed_by": "worker-2"},
                      unclaimed_col="claimed_by", tenant_id=TENANT_A)
    assert first is True, "first claim must win"
    assert second is False, "second claim must lose — double-send otherwise"
    row = db.select("scheduled_sends", tenant_id=TENANT_A)[0]
    assert row["claimed_by"] == "worker-1"


def test_claim_cannot_cross_tenant(db):
    db.insert("scheduled_sends", {"id": "s1"}, tenant_id=TENANT_A)
    db.commit()
    won = db.claim("scheduled_sends", key={"id": "s1"},
                   set_values={"claimed_by": "intruder"},
                   unclaimed_col="claimed_by", tenant_id=TENANT_B)
    assert won is False
    assert db.select("scheduled_sends", tenant_id=TENANT_A)[0]["claimed_by"] is None


def test_concurrent_claims_yield_exactly_one_winner(db):
    """The property reserve_send_slot exists to guarantee: no double-send."""
    import threading

    db.insert("scheduled_sends", {"id": "race"}, tenant_id=TENANT_A)
    db.commit()
    wins: list[bool] = []
    lock = threading.Lock()

    def attempt(worker: str) -> None:
        got = db.claim("scheduled_sends", key={"id": "race"},
                       set_values={"claimed_by": worker},
                       unclaimed_col="claimed_by", tenant_id=TENANT_A)
        with lock:
            wins.append(got)

    threads = [threading.Thread(target=attempt, args=(f"w{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for w in wins if w) == 1, f"exactly one winner required, got {wins}"


# ------------------------------------------------------------- SQL inspection

@pytest.mark.parametrize("sql,expected", [
    ("SELECT * FROM leads", {"leads"}),
    ("select a from Leads l join interactions i on 1=1", {"leads", "interactions"}),
    ("DELETE FROM leads WHERE x=1", {"leads"}),
    ("UPDATE leads SET a=1", {"leads"}),
    ("INSERT INTO leads (a) VALUES (1)", {"leads"}),
])
def test_referenced_tables(sql, expected):
    assert referenced_tables(sql) == expected


def test_tenant_mention_ignores_string_literals_and_comments():
    assert mentions_tenant_filter("SELECT * FROM leads WHERE tenant_id = ?")
    assert not mentions_tenant_filter("SELECT * FROM leads -- tenant_id handled upstream")
    assert not mentions_tenant_filter("SELECT * FROM leads WHERE note = 'tenant_id'")


# ------------------------------------------------------------------- config

def test_resolve_target_prefers_canonical_name():
    url, token, mode = resolve_target(
        {"TURSO_DATABASE_URL": "libsql://x", "TURSO_DB_URL": "libsql://legacy",
         "TURSO_AUTH_TOKEN": "tok"}
    )
    assert url == "libsql://x" and token == "tok" and "TURSO_DATABASE_URL" in mode


def test_resolve_target_falls_back_to_command_center_legacy_name():
    url, _, mode = resolve_target({"TURSO_DB_URL": "libsql://legacy",
                                   "TURSO_AUTH_TOKEN": "tok"})
    assert url == "libsql://legacy" and "TURSO_DB_URL" in mode


def test_data_base_url_is_not_an_implicit_fallback():
    """TURSO_DATA_BASE_URL in the agents env points at the ig-setter-pro
    database. Treating it as a fallback would silently connect the Bravo
    harness to an unrelated product's data."""
    with pytest.raises(TursoConfigError, match="No Turso target configured"):
        resolve_target({"TURSO_DATA_BASE_URL": "libsql://ig-setter",
                        "TURSO_AUTH_TOKEN": "tok"})


def test_empty_env_dict_is_not_treated_as_unset():
    """env={} means 'nothing configured', not 'go load the real credentials'."""
    with pytest.raises(TursoConfigError):
        resolve_target({})


def test_remote_url_without_token_fails_loudly():
    with pytest.raises(TursoConfigError, match="cannot authenticate"):
        resolve_target({"TURSO_DATABASE_URL": "libsql://x"})


def test_unconfigured_raises_rather_than_defaulting():
    with pytest.raises(TursoConfigError, match="No Turso target configured"):
        resolve_target({})
