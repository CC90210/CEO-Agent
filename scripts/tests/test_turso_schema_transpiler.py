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
    transpile_view,
)


def _intro(**over):
    base = {"columns": [], "pks": [], "fks": [], "enums": [], "indexes": [],
            "vectors": [], "functions": [], "triggers": [], "checks": []}
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


def test_check_constraints_are_emitted():
    """226 CHECK constraints were dropped fleet-wide by the first version —
    including breeze's money guards. SQLite enforces CHECK natively."""
    intro = _intro(
        columns=[col("advances", "factor_rate", "numeric", "numeric")],
        checks=[{"table_name": "advances", "name": "advances_factor_rate_check",
                 "def": "CHECK (((factor_rate >= 1.000) AND (factor_rate <= 4.000)))"}],
    )
    sql, _ = build_schema(intro, "breeze")
    assert 'CONSTRAINT "advances_factor_rate_check" CHECK' in sql
    assert "factor_rate >= 1.000" in sql


def test_check_with_any_array_is_translated():
    intro = _intro(
        columns=[col("agent_events", "status")],
        checks=[{"table_name": "agent_events", "name": "agent_events_status_check",
                 "def": "CHECK ((status = ANY (ARRAY['pending'::text, 'done'::text])))"}],
    )
    sql, _ = build_schema(intro, "bravo")
    assert "status IN ('pending', 'done')" in sql
    assert "::text" not in sql.split("-- indexes")[0]


def test_char_length_becomes_length_not_a_dead_table():
    """char_length() has no SQLite equivalent by that name. Emitting it inside a
    CHECK made the whole CREATE TABLE fail, so sunbiz_reply_drafts did not exist
    at all — every index on it then failed with 'no such table'. A dropped
    constraint is survivable; a dropped table is not."""
    intro = _intro(
        columns=[col("sunbiz_reply_drafts", "body")],
        checks=[{"table_name": "sunbiz_reply_drafts", "name": "body_len_check",
                 "def": "CHECK ((char_length(body) > 0))"}],
    )
    sql, _ = build_schema(intro, "bravo")
    assert "length(body) > 0" in sql
    assert "char_length" not in sql


def test_nulls_first_last_is_stripped_from_index():
    """SQLite rejects NULLS FIRST/LAST outright ('unsupported use of NULLS').
    The clause only tunes ordering, so stripping keeps a valid, useful index."""
    out = transpile_index(
        "CREATE INDEX i ON public.t USING btree (created_at DESC NULLS LAST)", "t", set())
    assert out == 'CREATE INDEX IF NOT EXISTS "i" ON "t" (created_at DESC);'


@pytest.mark.parametrize("expr", [
    "regexp_replace(phone, '[^0-9]', '')",          # no SQLite regexp_replace
    "(recorded_at AT TIME ZONE 'utc')",             # no AT TIME ZONE
    "(tags || ARRAY['x'])",                         # array literal
])
def test_unportable_index_expression_is_dropped_not_emitted(expr):
    """Emitting these produced a syntax error that killed the statement. Better
    to drop the index loudly than to break the schema load."""
    assert transpile_index(
        f"CREATE INDEX i ON public.t USING btree ({expr})", "t", set()) is None


def test_untranslatable_check_is_reported_not_silent():
    intro = _intro(
        columns=[col("t", "a")],
        checks=[{"table_name": "t", "name": "t_regex_check",
                 "def": "CHECK ((a ~ '^[0-9]+$'))"}],
    )
    sql, report = build_schema(intro, "bravo")
    assert "t_regex_check" not in sql
    assert report["lossy"]["checks_skipped"], "a dropped CHECK must be reported"


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


# --- views ------------------------------------------------------------------
# Nine Postgres views were never transpiled at all. On the already-flipped apps
# every SELECT against one returned "no such table" — including
# merchant_advance_summary, which five merchant-facing breeze pages read.


def test_cast_strip_does_not_swallow_the_following_keyword():
    """The original `::[a-z_ ]+` matched spaces, so it ran through the next
    keyword: `'commission'::text AND c.status <> 'voided'` collapsed to
    `'commission'.status <> 'voided'` — silently DELETING the AND-guard. In
    iso_clawback_candidates that guard is what excludes voided commissions from
    clawback, so a syntactically-valid version of this bug is a money bug."""
    out = transpile_view("v", "SELECT * FROM t WHERE a = 'commission'::text "
                              "AND b <> 'voided'::text AND c > 0")
    assert "AND b <> 'voided'" in out
    assert "AND c > 0" in out
    assert "'commission'.b" not in out


def test_cast_strip_preserves_then_and_or():
    out = transpile_view("v", "SELECT CASE WHEN s = 'pending'::text THEN 1 ELSE NULL END "
                              "FROM t WHERE x = 'a'::text OR y = 'b'::text")
    assert "THEN 1" in out
    assert "OR y = 'b'" in out


def test_greatest_least_become_sqlite_max_min():
    """SQLite spells GREATEST/LEAST as multi-arg max()/min(). Without this,
    merchant_advance_summary CREATEs fine and fails only when SELECTed — which
    is exactly how it reached a live database broken."""
    out = transpile_view("v", "SELECT GREATEST(a, 0) AS x, LEAST(b, c) AS y FROM t")
    assert "max(a, 0)" in out and "min(b, c)" in out
    assert "GREATEST" not in out


def test_pg_like_operator_becomes_like():
    out = transpile_view("v", "SELECT * FROM t WHERE ty ~~ '%_received'")
    assert "ty LIKE '%_received'" in out


def test_extract_epoch_becomes_julianday_seconds():
    out = transpile_view("v", "SELECT EXTRACT(epoch FROM now() - created_at) AS age FROM t")
    assert "julianday('now')" in out and "86400.0" in out
    assert "EXTRACT" not in out


@pytest.mark.parametrize("body", [
    "SELECT DISTINCT ON (a) a, b FROM t",                    # no SQLite equivalent
    "SELECT * FROM t WHERE d <= (f + make_interval(weeks => n))",  # only days is ported
    "SELECT * FROM t WHERE ty ~ '^[0-9]+$'",                 # posix regex
    "SELECT * FROM t, LATERAL (SELECT 1) x",
])
def test_unportable_view_is_reported_not_emitted(body):
    """Better a loudly-missing view than one that silently means something else."""
    assert transpile_view("v", body) is None


def test_lost_view_is_recorded_in_the_report():
    intro = _intro(
        columns=[col("t", "a")],
        views=[{"name": "v_hard", "relkind": "v",
                "def": "SELECT DISTINCT ON (a) a FROM t"}],
    )
    sql, report = build_schema(intro, "bravo")
    assert "v_hard" not in sql
    assert any("v_hard" in e for e in report["lossy"]["VIEWS_LOST"])


def test_portable_view_is_emitted_after_the_tables():
    intro = _intro(
        columns=[col("client_automations", "id")],
        views=[{"name": "automations", "relkind": "v",
                "def": "SELECT id, status FROM client_automations;"}],
    )
    sql, report = build_schema(intro, "oasis")
    assert 'CREATE VIEW IF NOT EXISTS "automations" AS' in sql
    assert report["view_count"] == 1
    assert sql.index("CREATE TABLE") < sql.index("CREATE VIEW")


def test_epoch_of_a_timestamp_uses_unixepoch_not_julianday():
    """julianday is a double: 1784651861.928 needs 13 significant digits, so the
    arithmetic form lands ~11us off. deal_board_view uses this as `position`,
    the board's sort key, so it must be exact — unixepoch(x,'subsec') is."""
    out = transpile_view("v", "SELECT EXTRACT(epoch FROM a.funded_at) AS position FROM t a")
    assert "unixepoch(a.funded_at, 'subsec')" in out
    assert "julianday" not in out


def test_extract_day_difference_truncates_like_postgres():
    out = transpile_view("v", "SELECT EXTRACT(day FROM now() - x) AS d FROM t")
    assert "CAST((julianday('now') - julianday(x)) AS INTEGER)" in out


def test_make_interval_days_becomes_datetime_modifier():
    out = transpile_view(
        "v", "SELECT * FROM t WHERE a <= (d.funded_at + make_interval(days => ip.n))")
    assert "datetime(d.funded_at, '+' || ip.n || ' days')" in out
    assert "make_interval" not in out


def test_immutable_pg_function_is_inlined():
    """deal_board_view calls map_advance_stage(), a pure IMMUTABLE SQL function.
    SQLite has no such function, and a view calling it CREATEs fine then fails
    only on SELECT."""
    out = transpile_view(
        "v", "SELECT map_advance_stage(a.repayment_status, a.collection_status, "
             "a.defaulted_at, a.renewal_of) AS stage FROM advances a")
    assert "map_advance_stage" not in out
    assert "a.collection_status IN ('in_house','agency','legal')" in out
    assert "a.repayment_status = 'default' OR a.defaulted_at IS NOT NULL" in out


def test_view_calling_an_unknown_function_is_rejected():
    """CREATE VIEW does not resolve function names — the failure surfaces only
    when an app SELECTs it. Catch it at transpile time instead."""
    assert transpile_view("v", "SELECT some_plpgsql_helper(a) FROM t") is None


def test_sql_keywords_are_not_mistaken_for_functions():
    """`IN (`, `EXISTS (`, `OVER (`, `FILTER (` all look like calls to a naive
    regex; treating them as unknown functions rejected six working views."""
    out = transpile_view(
        "v", "SELECT count(*) FILTER (WHERE a > 0) OVER (PARTITION BY b) AS n "
             "FROM t WHERE c IN (1, 2) AND EXISTS (SELECT 1 FROM u)")
    assert out is not None


def test_generated_column_keeps_its_generated_clause():
    """draws.net_deposit_cents is GENERATED ALWAYS AS (funded_cents -
    platform_fee_cents) — the money a merchant receives on a draw. Emitted as a
    plain column it stops computing, and no breeze-portal code writes it (every
    reference is a read), so a new draw would carry NULL into the
    "money sent to your account" email."""
    intro = _intro(columns=[
        {**col("draws", "funded_cents", "integer", "int4"), "column_name": "funded_cents"},
        {**col("draws", "net_deposit_cents", "integer", "int4"),
         "is_generated": "ALWAYS",
         "generation_expression": "(funded_cents - platform_fee_cents)"},
    ])
    sql, report = build_schema(intro, "breeze")
    assert 'GENERATED ALWAYS AS ((funded_cents - platform_fee_cents)) STORED' in sql
    assert not report["lossy"].get("GENERATED_COLUMNS_LOST")


def test_unportable_generated_expression_is_reported_not_silently_plain():
    intro = _intro(columns=[
        {**col("t", "x"), "is_generated": "ALWAYS",
         "generation_expression": "regexp_replace(y, 'a', 'b')"},
    ])
    sql, report = build_schema(intro, "bravo")
    assert "GENERATED ALWAYS" not in sql
    assert report["lossy"]["GENERATED_COLUMNS_LOST"]


def test_breeze_cross_role_triggers_are_emitted():
    """assert_no_cross_role_binding has NO service_role bypass — it is a pure
    data invariant (one login is either a merchant portal user or a funder team
    member, never both). Nothing enforced it on Turso and breeze is already live,
    so it must survive every schema regeneration."""
    sql, report = build_schema(_intro(columns=[col("merchant_users", "auth_user_id")]),
                               "breeze")
    assert report["ported_trigger_count"] == 4
    for tbl in ("merchant_users", "tenant_users"):
        for evt in ("insert", "update"):
            assert f'"{tbl}_no_cross_role_{evt}"' in sql
    assert "RAISE(ABORT, 'cross_role_conflict" in sql


def test_bravo_append_only_triggers_are_emitted():
    """bravo is LIVE on the Turso data plane, so these were unenforced in
    production. client_signatures holds e-signature records — append-only is the
    property that makes them evidence rather than just rows."""
    sql, report = build_schema(_intro(columns=[col("client_signatures", "id")]), "bravo")
    assert report["ported_trigger_count"] == 3
    assert '"client_signatures_no_mutate_update"' in sql
    assert '"client_signatures_no_mutate_delete"' in sql
    assert '"trg_shop_out_runs_results_append_only"' in sql
    # null-safe comparison — the port of IS DISTINCT FROM
    assert "OLD.results IS NOT NEW.results" in sql


def test_projects_without_ported_triggers_emit_none():
    sql, report = build_schema(_intro(columns=[col("t", "a")]), "nostalgic")
    assert report["ported_trigger_count"] == 0
    assert "CREATE TRIGGER" not in sql
