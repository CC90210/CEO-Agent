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
    referenced_tables,
    resolve_target,
    unscoped_tables,
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
    with pytest.raises(UnscopedQueryError, match="no tenant_id predicate"):
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


def test_insert_is_durable_from_a_second_connection(tmp_path):
    """insert() must commit, or the row exists only inside the writer.

    Every other insert test in this file reads back through the same TursoDB
    object, which sees its own open transaction and passes whether or not the
    write was ever committed. That is why insert() shipped without a commit for
    as long as it did. This test deliberately opens a SECOND connection to the
    same file — the only reader that can tell durability from illusion.
    """
    conn_path = str(tmp_path / "durable.db")
    writer = TursoDB(conn_path, None, "local(test)")
    writer.execute(
        'CREATE TABLE "leads" ("id" TEXT PRIMARY KEY, "tenant_id" TEXT NOT NULL, '
        '"email" TEXT, "status" TEXT)',
        allow_unscoped=True, reason="test setup",
    )
    writer.commit()
    writer._tenant_tables = writer._discover_tenant_tables()

    writer.insert("leads", {"id": "1", "email": "a@b.com"}, tenant_id=TENANT_A)

    reader = TursoDB(conn_path, None, "local(test)")
    rows = reader.query("SELECT id FROM leads WHERE tenant_id = ?", (TENANT_A,))
    assert [r["id"] for r in rows] == ["1"], (
        "insert() did not commit — the row is invisible outside the writing "
        "connection, so a same-connection read-back would have reported success"
    )


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


def test_claim_must_assign_the_marker_column(db):
    """Updating other columns leaves the row unclaimed — and a second worker wins."""
    db.insert("scheduled_sends", {"id": "s1"}, tenant_id=TENANT_A)
    db.commit()
    with pytest.raises(ValueError, match="IS the claim marker"):
        db.claim("scheduled_sends", key={"id": "s1"},
                 set_values={"id": "s1"}, unclaimed_col="claimed_by",
                 tenant_id=TENANT_A)


def test_claim_rejects_null_owner_token(db):
    db.insert("scheduled_sends", {"id": "s1"}, tenant_id=TENANT_A)
    db.commit()
    with pytest.raises(ValueError, match="non-NULL owner token"):
        db.claim("scheduled_sends", key={"id": "s1"},
                 set_values={"claimed_by": None}, unclaimed_col="claimed_by",
                 tenant_id=TENANT_A)


def test_claim_rejects_empty_key(db):
    """An unkeyed CAS would claim every unclaimed row in the table."""
    with pytest.raises(ValueError, match="non-empty key"):
        db.claim("scheduled_sends", key={}, set_values={"claimed_by": "w"},
                 unclaimed_col="claimed_by", tenant_id=TENANT_A)


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
    # schema-qualified: the terminal name is the table, not the qualifier
    ("SELECT * FROM main.leads", {"leads"}),
    ('SELECT * FROM main."leads"', {"leads"}),
    ("SELECT * FROM temp.leads", {"leads"}),
    # CTE alias is not a physical table; the CTE body's table is
    ("WITH x AS (SELECT * FROM leads) SELECT * FROM x", {"leads"}),
])
def test_referenced_tables(sql, expected):
    assert referenced_tables(sql) == expected


# ------------------------------------------------ adversarial bypass attempts
# Each of these was reported by an independent adversarial review against the
# original regex implementation. Every one returned other tenants' rows.

ADVERSARIAL = [
    pytest.param("SELECT * FROM main.leads", id="schema-qualified"),
    pytest.param('SELECT * FROM main."leads"', id="schema-qualified-quoted"),
    pytest.param("SELECT tenant_id, email FROM leads", id="tenant_id-in-select-list"),
    pytest.param("SELECT * FROM leads ORDER BY tenant_id", id="tenant_id-in-order-by"),
    pytest.param("SELECT count(*) FROM leads GROUP BY tenant_id", id="tenant_id-in-group-by"),
    pytest.param("SELECT email FROM leads WHERE tenant_id = ? "
                 "UNION SELECT email FROM leads", id="second-union-arm-unscoped"),
    pytest.param("WITH scoped AS (SELECT * FROM leads WHERE tenant_id = ?) "
                 "SELECT * FROM leads", id="cte-scoped-outer-unscoped"),
    pytest.param("SELECT * FROM leads WHERE id IN (SELECT id FROM leads)",
                 id="subquery-unscoped"),
    pytest.param("UPDATE leads SET status = 'x' WHERE id IN (SELECT id FROM leads)",
                 id="update-subquery-unscoped"),
]


@pytest.mark.parametrize("sql", ADVERSARIAL)
def test_adversarial_sql_cannot_bypass_the_guard(db, sql):
    with pytest.raises(UnscopedQueryError):
        db.query(sql, ["t"] * sql.count("?"))


@pytest.mark.parametrize("sql", ADVERSARIAL)
def test_adversarial_sql_is_named_by_unscoped_tables(db, sql):
    assert "leads" in unscoped_tables(sql, db.tenant_tables)


def test_every_union_arm_scoped_is_accepted(db):
    rows = db.query("SELECT email FROM leads WHERE tenant_id = ? "
                    "UNION SELECT email FROM leads WHERE tenant_id = ?",
                    [TENANT_A, TENANT_A])
    assert rows == []


def test_scoped_cte_and_scoped_outer_is_accepted(db):
    rows = db.query("WITH s AS (SELECT id FROM leads WHERE tenant_id = ?) "
                    "SELECT id FROM leads WHERE tenant_id = ? AND id IN (SELECT id FROM s)",
                    [TENANT_A, TENANT_A])
    assert rows == []


def test_unparseable_sql_is_refused_not_allowed(db):
    with pytest.raises(UnscopedQueryError, match="Could not parse SQL"):
        db.query("SELECT ... FROM WHERE ((")


def test_global_table_still_needs_no_predicate(db):
    assert unscoped_tables("SELECT * FROM skills_registry", db.tenant_tables) == set()








def test_select_list_mention_still_blocks_the_query(db):
    """End-to-end: the leak vector must raise, not just fail the helper."""
    db.insert("leads", {"id": "1", "email": "a@a.com"}, tenant_id=TENANT_A)
    db.insert("leads", {"id": "2", "email": "b@b.com"}, tenant_id=TENANT_B)
    db.commit()
    with pytest.raises(UnscopedQueryError):
        db.query("SELECT tenant_id, email FROM leads")


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
