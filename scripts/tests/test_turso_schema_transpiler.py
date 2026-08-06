"""Transpiler unit tests — anchored on the bugs that actually bit.

The composite-FK case is a regression test, not a hypothetical. The first
implementation read foreign keys through
information_schema.constraint_column_usage, which cartesian-products a
2-column FK into 4 bogus single-column ones. The emitted DDL created fine and
then blew up at the first INSERT with "foreign key mismatch". Schema that
*applies* is not schema that *works*.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.turso_schema_transpiler import (  # noqa: E402
    _unique_column_sets,
    build_schema,
    map_default,
    map_type,
    topo_order,
    transpile_index,
)


def _intro(**over):
    base = {"columns": [], "pks": [], "fks": [], "enums": [], "indexes": [],
            "vectors": [], "functions": [], "triggers": []}
    base.update(over)
    return base


def col(table, name, data_type="text", udt="text", nullable="YES", default=None):
    return {"table_name": table, "column_name": name, "ordinal_position": 1,
            "data_type": data_type, "udt_name": udt, "is_nullable": nullable,
            "column_default": default, "character_maximum_length": None}


# ------------------------------------------------------------------ type map

@pytest.mark.parametrize("dt,udt,expected", [
    ("uuid", "uuid", "TEXT"),
    ("timestamp with time zone", "timestamptz", "TEXT"),
    ("jsonb", "jsonb", "TEXT"),
    ("ARRAY", "_text", "TEXT"),
    ("numeric", "numeric", "TEXT"),      # money must not become a float
    ("bigint", "int8", "INTEGER"),
    ("boolean", "bool", "INTEGER"),
    ("double precision", "float8", "REAL"),
    ("bytea", "bytea", "BLOB"),
])
def test_map_type(dt, udt, expected):
    assert map_type(dt, udt, {}, None)[0] == expected


def test_vector_maps_to_f32_blob_with_dimensions():
    assert map_type("USER-DEFINED", "vector", {}, 1536)[0] == "F32_BLOB(1536)"


def test_enum_becomes_text_with_check():
    typ, check = map_type("USER-DEFINED", "lead_status", {"lead_status": ["cold", "warm"]}, None)
    assert typ == "TEXT"
    assert "'cold', 'warm'" in check


def test_enum_labels_are_quote_escaped():
    _, check = map_type("USER-DEFINED", "s", {"s": ["it's"]}, None)
    assert "'it''s'" in check


# ------------------------------------------------------------------ defaults

@pytest.mark.parametrize("pg,expected", [
    ("now()", "(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
    ("true", "1"),
    ("false", "0"),
    ("'draft'::text", "'draft'"),
    ("0", "0"),
    ("'{}'::jsonb", "'{}'"),
])
def test_map_default(pg, expected):
    assert map_default(pg) == expected


def test_unportable_default_is_dropped_not_guessed():
    assert map_default("nextval('x_seq'::regclass)") is None


# ----------------------------------------------------- composite FK regression

def test_composite_fk_emits_paired_columns_not_cartesian_product():
    intro = _intro(
        columns=[col("child", "tenant_id"), col("child", "asset_id"),
                 col("parent", "tenant_id"), col("parent", "id")],
        pks=[{"table_name": "parent", "column_name": "id", "ordinal_position": 1}],
        indexes=[{"schemaname": "public", "tablename": "parent",
                  "indexname": "parent_tenant_id_key",
                  "indexdef": 'CREATE UNIQUE INDEX parent_tenant_id_key ON public.parent '
                              "USING btree (tenant_id, id)"}],
        fks=[{"constraint_name": "child_parent_fk", "table_name": "child",
              "foreign_schema": "public", "foreign_table": "parent",
              "columns": "tenant_id,asset_id", "foreign_columns": "tenant_id,id"}],
    )
    sql, _ = build_schema(intro, "bravo")
    assert 'FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "parent" ("tenant_id", "id")' in sql
    # the cartesian-product artefacts must NOT appear
    assert 'FOREIGN KEY ("tenant_id") REFERENCES "parent" ("id")' not in sql
    assert sql.count("FOREIGN KEY") == 1


def test_fk_to_non_unique_parent_is_dropped_and_reported():
    intro = _intro(
        columns=[col("child", "pid"), col("parent", "name")],
        fks=[{"constraint_name": "fk1", "table_name": "child", "foreign_schema": "public",
              "foreign_table": "parent", "columns": "pid", "foreign_columns": "name"}],
    )
    sql, report = build_schema(intro, "bravo")
    assert "FOREIGN KEY" not in sql
    assert len(report["lossy"]["unenforceable_fks_dropped"]) == 1


def test_cross_schema_fk_is_dropped_and_reported():
    intro = _intro(
        columns=[col("profiles", "user_id")],
        fks=[{"constraint_name": "fk_auth", "table_name": "profiles", "foreign_schema": "auth",
              "foreign_table": "users", "columns": "user_id", "foreign_columns": "id"}],
    )
    sql, report = build_schema(intro, "bravo")
    assert "FOREIGN KEY" not in sql
    assert report["lossy"]["cross_schema_fks_dropped"] == ["profiles(user_id) -> auth.users"]


def test_unique_column_sets_includes_pk_and_unique_indexes():
    intro = _intro(
        pks=[{"table_name": "t", "column_name": "id", "ordinal_position": 1}],
        indexes=[{"schemaname": "public", "tablename": "t", "indexname": "t_a_b_key",
                  "indexdef": "CREATE UNIQUE INDEX t_a_b_key ON public.t USING btree (a, b)"},
                 {"schemaname": "public", "tablename": "t", "indexname": "t_c_idx",
                  "indexdef": "CREATE INDEX t_c_idx ON public.t USING btree (c)"}],
    )
    sets = _unique_column_sets(intro)
    assert ("id",) in sets["t"]
    assert ("a", "b") in sets["t"]
    assert ("c",) not in sets["t"]  # non-unique index is not a valid FK target


# --------------------------------------------------------------- ordering

def test_topo_order_puts_parents_first():
    order = topo_order(["child", "parent"], [
        {"table_name": "child", "foreign_table": "parent", "foreign_schema": "public"}])
    assert order.index("parent") < order.index("child")


def test_topo_order_survives_cycles():
    order = topo_order(["a", "b"], [
        {"table_name": "a", "foreign_table": "b", "foreign_schema": "public"},
        {"table_name": "b", "foreign_table": "a", "foreign_schema": "public"}])
    assert sorted(order) == ["a", "b"]


# ---------------------------------------------------------------- indexes

def test_btree_index_transpiles():
    out = transpile_index("CREATE INDEX i ON public.t USING btree (a, b)", "t", set())
    assert out == 'CREATE INDEX IF NOT EXISTS "i" ON "t" (a, b);'


def test_gin_index_is_skipped_not_mistranslated():
    assert transpile_index("CREATE INDEX i ON public.t USING gin (tags)", "t", set()) is None


def test_expression_index_is_emitted_not_skipped():
    """SQLite has expression indexes (3.9+). Skipping them silently dropped 20
    UNIQUE constraints across five live databases — including the
    double-commission guard on merchant money."""
    out = transpile_index("CREATE INDEX i ON public.t USING btree (lower(email))",
                          "t", set())
    assert out == 'CREATE INDEX IF NOT EXISTS "i" ON "t" (lower(email));'


def test_partial_index_with_cast_is_emitted():
    """SQLite has partial indexes (3.8+); ::casts are no-ops here and strip cleanly."""
    out = transpile_index(
        "CREATE INDEX i ON public.t USING btree (a) WHERE (status = 'x'::text)",
        "t", set())
    assert out == 'CREATE INDEX IF NOT EXISTS "i" ON "t" (a) WHERE (status = \'x\');'


def test_any_array_predicate_becomes_in_list():
    out = transpile_index(
        "CREATE UNIQUE INDEX i ON public.t USING btree (lead_id) "
        "WHERE (status = ANY (ARRAY['pending', 'running']))", "t", set())
    assert out == ('CREATE UNIQUE INDEX IF NOT EXISTS "i" ON "t" (lead_id) '
                   "WHERE (status IN ('pending', 'running'));")


def test_btrim_becomes_trim():
    out = transpile_index(
        "CREATE UNIQUE INDEX i ON public.t USING btree (tenant_id, lower(btrim(email)))",
        "t", set())
    assert "trim(email)" in out and "btrim" not in out


def test_nulls_not_distinct_coalesces_bare_columns():
    """Postgres 15 NULLS NOT DISTINCT treats NULLs as EQUAL; SQLite does not.
    Without COALESCE, duplicate suppression rows slip through wherever
    tenant/brand is NULL — i.e. an unsubscribed person gets emailed again."""
    out = transpile_index(
        "CREATE UNIQUE INDEX i ON public.email_suppressions USING btree "
        "(email, tenant_id, brand) NULLS NOT DISTINCT", "email_suppressions", set())
    assert "COALESCE(email," in out
    assert "COALESCE(tenant_id," in out
    assert "COALESCE(brand," in out


def test_nondeterministic_predicate_still_skipped():
    """now()-dependent predicates are genuinely non-portable — a partial index
    whose membership changes with the clock is not a stable index."""
    assert transpile_index(
        "CREATE INDEX i ON public.t USING btree (a) WHERE (expires_at > now())",
        "t", set()) is None


def test_unique_loss_is_reported_loudly():
    """A dropped UNIQUE is a lost CONSTRAINT, not a lost optimization."""
    intro = _intro(
        columns=[col("t", "a")],
        indexes=[{"schemaname": "public", "tablename": "t", "indexname": "u_gin",
                  "indexdef": "CREATE UNIQUE INDEX u_gin ON public.t USING gin (tags)"}],
    )
    _sql, report = build_schema(intro, "bravo")
    assert report["lossy"]["UNIQUE_CONSTRAINTS_LOST"], "silent UNIQUE loss must be impossible"


# ------------------------------------------------------------------- output

def test_emitted_table_count_matches_input():
    intro = _intro(columns=[col("a", "x"), col("b", "y"), col("c", "z")])
    sql, report = build_schema(intro, "bravo")
    assert sql.count("CREATE TABLE IF NOT EXISTS") == 3
    assert report["table_count"] == 3


def test_header_records_untranspiled_plpgsql_and_triggers():
    intro = _intro(
        columns=[col("a", "x")],
        functions=[{"proname": "reserve_send_slot", "lanname": "plpgsql"},
                   {"proname": "safe_int", "lanname": "sql"}],
        triggers=[{"table_name": "a", "trigger_name": "touch_updated_at"}],
    )
    sql, report = build_schema(intro, "bravo")
    assert "reserve_send_slot" in sql
    assert report["plpgsql_functions"] == ["reserve_send_slot"]  # sql-language fn excluded
    assert report["triggers"] == ["a.touch_updated_at"]
