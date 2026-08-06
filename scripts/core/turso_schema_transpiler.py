"""Postgres → libSQL schema transpiler — live-introspection based.

WHY LIVE INTROSPECTION. database/*.sql defines 69 tables; the live Bravo
project has 162. The .sql files are 43% of the truth. Transpiling them would
silently produce an incomplete Turso schema, so this tool asks the running
database what actually exists (information_schema + pg_catalog via the
Supabase Management API — the same path apply_migration.py already uses)
and emits libSQL DDL from that.

WHAT IT EMITS. One `database/turso_migrations/<project>__000_master_schema.sql`
per Supabase project: CREATE TABLE statements in FK-dependency order, indexes,
and a header documenting every lossy conversion it made. PL/pgSQL functions,
triggers with function bodies, RLS policies, and views are NOT transpiled —
they are listed in the header as DAL responsibilities (see plan Phase 2).

TYPE MAP (Postgres → libSQL):
  uuid                → TEXT            (UUIDv4 generated in app code)
  timestamptz/date    → TEXT            (ISO-8601 UTC; SQLite has no tz type)
  jsonb/json          → TEXT            (query via json_extract())
  text[]/_text/arrays → TEXT            (JSON array encoding)
  numeric/decimal     → TEXT            (money — never float)
  int2/int4/int8      → INTEGER
  bool                → INTEGER         (0/1)
  float4/float8       → REAL
  bytea               → BLOB
  vector(N)           → F32_BLOB(N)     (Turso native vector type)
  enums               → TEXT + CHECK(col IN (...))

CLI:
  python scripts/core/turso_schema_transpiler.py --project bravo            # emit
  python scripts/core/turso_schema_transpiler.py --project bravo --verify   # emit + assert table-count parity with live
  python scripts/core/turso_schema_transpiler.py --project breeze --verify
  python scripts/core/turso_schema_transpiler.py --project oasis --verify

Requires SUPABASE_ACCESS_TOKEN in the agents env (Management API token —
same credential apply_migration.py uses).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import requests  # noqa: E402

from lib.secret_loader import load_env  # noqa: E402

OUT_DIR = PROJECT_ROOT / "database" / "turso_migrations"
MGMT_API = "https://api.supabase.com"
TIMEOUT_S = 60

# Supabase project registry — refs verified live 2026-08-05 (plan file:
# oasis-ai-platform's real ref is skgrbweyscysyetubemg, NOT the
# sajanpiqysuwviucycjh the original spec named).
PROJECTS = {
    "bravo": {"ref": "phctllmtsogkovoilwos", "turso_db": "bravo-empire"},
    "breeze": {"ref": "xugwrhvaoihyidtdgwkq", "turso_db": "breeze-portal"},
    "nostalgic": {"ref": "jqybbrtzpvmefgzzdagz", "turso_db": "nostalgic-requests"},
    "propflow": {"ref": "xusnasmzoxkaimyjqbie", "turso_db": "propflow"},
    "oasis": {"ref": "skgrbweyscysyetubemg", "turso_db": "oasis-platform"},
}


def _mgmt_query(ref: str, sql: str, token: str) -> list[dict]:
    """Run a read-only SQL query via the Supabase Management API."""
    r = requests.post(
        f"{MGMT_API}/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": sql},
        timeout=TIMEOUT_S,
    )
    if r.status_code != 201 and r.status_code != 200:
        raise RuntimeError(f"Management API query failed ({r.status_code}): {r.text[:500]}")
    body = r.json()
    # The API returns either a bare list of rows or {"result": [...]}
    if isinstance(body, dict) and "result" in body:
        return body["result"]
    return body


# ---------------------------------------------------------------- introspection

COLUMNS_SQL = """
select c.table_name, c.column_name, c.ordinal_position, c.data_type, c.udt_name,
       c.is_nullable, c.column_default, c.character_maximum_length
from information_schema.columns c
join information_schema.tables t
  on t.table_schema = c.table_schema and t.table_name = c.table_name
where c.table_schema = 'public' and t.table_type = 'BASE TABLE'
order by c.table_name, c.ordinal_position
"""

PK_SQL = """
select tc.table_name, kcu.column_name, kcu.ordinal_position
from information_schema.table_constraints tc
join information_schema.key_column_usage kcu
  on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema
where tc.table_schema = 'public' and tc.constraint_type = 'PRIMARY KEY'
order by tc.table_name, kcu.ordinal_position
"""

# Composite foreign keys MUST come from pg_catalog, not information_schema.
# Joining table_constraints -> key_column_usage -> constraint_column_usage
# cartesian-products a 2-column FK into 4 bogus single-column FKs: a real
# (tenant_id, asset_id) -> (tenant_id, id) constraint came out as
# tenant_id -> id, tenant_id -> tenant_id, asset_id -> id, asset_id -> tenant_id.
# SQLite then rejects the table at DML time with "foreign key mismatch".
# pg_constraint.conkey/confkey are ordinal arrays, so unnest WITH ORDINALITY
# preserves the column pairing.
FK_SQL = """
select con.conname as constraint_name,
       cl.relname as table_name,
       fns.nspname as foreign_schema,
       fcl.relname as foreign_table,
       (select string_agg(att.attname, ',' order by u.ord)
          from unnest(con.conkey) with ordinality u(attnum, ord)
          join pg_attribute att
            on att.attrelid = con.conrelid and att.attnum = u.attnum) as columns,
       (select string_agg(att.attname, ',' order by u.ord)
          from unnest(con.confkey) with ordinality u(attnum, ord)
          join pg_attribute att
            on att.attrelid = con.confrelid and att.attnum = u.attnum) as foreign_columns
from pg_constraint con
join pg_class cl on cl.oid = con.conrelid
join pg_namespace ns on ns.oid = cl.relnamespace
join pg_class fcl on fcl.oid = con.confrelid
join pg_namespace fns on fns.oid = fcl.relnamespace
where con.contype = 'f' and ns.nspname = 'public'
"""

ENUM_SQL = """
select t.typname, e.enumlabel, e.enumsortorder
from pg_type t
join pg_enum e on e.enumtypid = t.oid
join pg_namespace n on n.oid = t.typnamespace
where n.nspname = 'public'
order by t.typname, e.enumsortorder
"""

INDEX_SQL = """
select schemaname, tablename, indexname, indexdef
from pg_indexes
where schemaname = 'public'
"""

VECTOR_SQL = """
select c.relname as table_name, a.attname as column_name,
       coalesce(a.atttypmod, -1) as typmod
from pg_attribute a
join pg_class c on c.oid = a.attrelid
join pg_namespace n on n.oid = c.relnamespace
join pg_type t on t.oid = a.atttypid
where n.nspname = 'public' and t.typname = 'vector' and a.attnum > 0
"""

FUNCTION_SQL = """
select p.proname, l.lanname
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
join pg_language l on l.oid = p.prolang
where n.nspname = 'public'
order by p.proname
"""

TRIGGER_SQL = """
select event_object_table as table_name, trigger_name
from information_schema.triggers
where trigger_schema = 'public'
group by event_object_table, trigger_name
order by event_object_table
"""


def introspect(ref: str, token: str) -> dict:
    return {
        "columns": _mgmt_query(ref, COLUMNS_SQL, token),
        "pks": _mgmt_query(ref, PK_SQL, token),
        "fks": _mgmt_query(ref, FK_SQL, token),
        "enums": _mgmt_query(ref, ENUM_SQL, token),
        "indexes": _mgmt_query(ref, INDEX_SQL, token),
        "vectors": _mgmt_query(ref, VECTOR_SQL, token),
        "functions": _mgmt_query(ref, FUNCTION_SQL, token),
        "triggers": _mgmt_query(ref, TRIGGER_SQL, token),
    }


# ---------------------------------------------------------------- transpilation

def map_type(data_type: str, udt_name: str, enums: dict[str, list[str]],
             vector_dims: int | None) -> tuple[str, str | None]:
    """Return (libsql_type, check_clause_or_None)."""
    dt = (data_type or "").lower()
    udt = (udt_name or "").lower()

    if udt == "vector":
        dims = vector_dims if vector_dims and vector_dims > 0 else 1536
        return f"F32_BLOB({dims})", None
    if udt in enums:
        labels = ", ".join("'" + label.replace("'", "''") + "'" for label in enums[udt])
        return "TEXT", f"CHECK (%COL% IN ({labels}))"
    if dt == "array" or udt.startswith("_"):
        return "TEXT", None  # JSON array encoding
    if dt in ("jsonb", "json"):
        return "TEXT", None
    if dt == "uuid":
        return "TEXT", None
    if dt in ("timestamp with time zone", "timestamp without time zone", "date",
              "time with time zone", "time without time zone"):
        return "TEXT", None
    if dt in ("numeric", "decimal", "money"):
        return "TEXT", None  # money — never float
    if dt in ("smallint", "integer", "bigint") or udt in ("int2", "int4", "int8"):
        return "INTEGER", None
    if dt == "boolean":
        return "INTEGER", None
    if dt in ("real", "double precision") or udt in ("float4", "float8"):
        return "REAL", None
    if dt == "bytea":
        return "BLOB", None
    if dt in ("text", "character varying", "character", "citext", "inet", "cidr",
              "macaddr", "tsvector", "interval", "name") or udt in ("text", "varchar"):
        return "TEXT", None
    return "TEXT", None  # conservative default: everything round-trips as TEXT


DEFAULT_MAP = [
    # (regex on the Postgres default, libSQL default or None to drop)
    (re.compile(r"^now\(\)|^CURRENT_TIMESTAMP", re.I), "(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
    (re.compile(r"gen_random_uuid\(\)|uuid_generate_v4\(\)", re.I),
     "(lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
     "substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || "
     "substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6))))"),
    (re.compile(r"^true$", re.I), "1"),
    (re.compile(r"^false$", re.I), "0"),
    (re.compile(r"^'\{\}'::jsonb$|^'\{\}'::json$", re.I), "'{}'"),
    (re.compile(r"^'\[\]'::jsonb$|^'\[\]'::json$", re.I), "'[]'"),
    (re.compile(r"^ARRAY\[\]|^'\{\}'::text\[\]", re.I), "'[]'"),
]

_NUM_DEFAULT = re.compile(r"^\(?(-?\d+(\.\d+)?)\)?(::[a-z_ ]+)?$", re.I)
_STR_DEFAULT = re.compile(r"^('(?:[^']|'')*')(::[a-z_ ]+)?$")


def map_default(pg_default: str | None) -> str | None:
    if not pg_default:
        return None
    d = pg_default.strip()
    for rx, repl in DEFAULT_MAP:
        if rx.search(d):
            return repl
    m = _NUM_DEFAULT.match(d)
    if m:
        return m.group(1)
    m = _STR_DEFAULT.match(d)
    if m:
        return m.group(1)
    return None  # sequences/nextval, complex expressions → app-code concern


def topo_order(tables: list[str], fks: list[dict]) -> list[str]:
    """FK-dependency order (parents first). Cycles fall back to name order."""
    deps: dict[str, set[str]] = {t: set() for t in tables}
    for fk in fks:
        child, parent = fk["table_name"], fk["foreign_table"]
        if fk.get("foreign_schema") != "public":
            continue  # e.g. auth.users — dropped, noted in header
        if child in deps and parent in deps and child != parent:
            deps[child].add(parent)
    ordered: list[str] = []
    remaining = dict(deps)
    while remaining:
        ready = sorted(t for t, d in remaining.items() if not (d & set(remaining)))
        if not ready:  # cycle — emit rest alphabetically (FKs are unenforced anyway)
            ordered.extend(sorted(remaining))
            break
        ordered.extend(ready)
        for t in ready:
            remaining.pop(t)
    return ordered


_IDX_RE = re.compile(
    r"CREATE\s+(UNIQUE\s+)?INDEX\s+(\S+)\s+ON\s+(?:ONLY\s+)?\S+\s+USING\s+(\w+)\s+\((.*?)\)(\s+WHERE\s+(.*))?$",
    re.I | re.S,
)
_SIMPLE_COLS = re.compile(r"^[a-z_][a-z0-9_]*(\s+(ASC|DESC))?(\s*,\s*[a-z_][a-z0-9_]*(\s+(ASC|DESC))?)*$", re.I)


def _pg_expr_to_sqlite(s: str) -> str:
    """Translate the Postgres expression dialect SQLite doesn't share.

    SQLite HAS expression indexes (3.9+) and partial indexes (3.8+), so most
    "exotic" index definitions are portable after this rewrite. The first
    version of this transpiler skipped them wholesale and silently dropped 20
    UNIQUE constraints across five databases — dedup guards, one-active-run
    guards, and the double-commission guard on live merchant money. Never skip a
    UNIQUE index quietly again.
    """
    s = re.sub(r"::[a-z ]+(\[\])?", "", s)              # casts are no-ops here
    s = re.sub(r"\bbtrim\s*\(", "trim(", s, flags=re.I)  # btrim -> trim
    s = re.sub(r"=\s*ANY\s*\(\s*ARRAY\[(.*?)\]\s*\)", r"IN (\1)", s, flags=re.S | re.I)
    s = re.sub(r"\bIS TRUE\b", "= 1", s, flags=re.I)
    s = re.sub(r"\bIS FALSE\b", "= 0", s, flags=re.I)
    return s


# Postgres 15 NULLS NOT DISTINCT: NULLs compare EQUAL for uniqueness. SQLite
# follows the standard (NULLs distinct), so the columns must be COALESCEd to a
# sentinel or duplicates slip through wherever a key column is NULL.
_NULL_SENTINEL = "\\u001f__null__"


def transpile_index(indexdef: str, table: str, pk_names: set[str]) -> str | None:
    raw = indexdef.strip()
    nulls_not_distinct = bool(re.search(r"NULLS\s+NOT\s+DISTINCT\s*$", raw, re.I))
    raw = re.sub(r"\s*NULLS\s+NOT\s+DISTINCT\s*$", "", raw, flags=re.I)
    m = _IDX_RE.match(raw)
    if not m:
        return None
    unique, name, method, cols, _, where = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
    name = name.strip('"')
    if name in pk_names:
        return None  # PK is inline in CREATE TABLE
    if method.lower() not in ("btree",):
        return None  # gin/gist/ivfflat/hnsw have no SQLite equivalent
    cols = _pg_expr_to_sqlite(cols.strip())
    if nulls_not_distinct:
        cols = ", ".join(
            c.strip() if "(" in c else f"COALESCE({c.strip()}, '{_NULL_SENTINEL}')"
            for c in cols.split(","))
    stmt = f"CREATE {'UNIQUE ' if unique else ''}INDEX IF NOT EXISTS \"{name}\" ON \"{table}\" ({cols})"
    if where:
        w = _pg_expr_to_sqlite(where.strip())
        # now()/regex predicates are genuinely non-portable (non-deterministic
        # or unsupported); everything else survives the rewrite above.
        if re.search(r"~|\bILIKE\b|\bnow\(\)", w, re.I):
            return None
        stmt += f" WHERE {w}"
    return stmt + ";"


_UNIQUE_IDX = re.compile(r"CREATE\s+UNIQUE\s+INDEX\s+\S+\s+ON\s+(?:ONLY\s+)?(\S+)\s+USING\s+\w+\s+\((.*?)\)\s*$",
                         re.I | re.S)


def _unique_column_sets(intro: dict) -> dict[str, set[tuple[str, ...]]]:
    """Column tuples a FK may legally reference: primary keys + unique indexes."""
    out: dict[str, set[tuple[str, ...]]] = {}
    pk_cols: dict[str, list[str]] = {}
    for pk in intro["pks"]:
        pk_cols.setdefault(pk["table_name"], []).append(pk["column_name"])
    for t, cols in pk_cols.items():
        out.setdefault(t, set()).add(tuple(cols))
    for idx in intro["indexes"]:
        m = _UNIQUE_IDX.match(idx["indexdef"].strip())
        if not m:
            continue
        cols = tuple(c.strip().strip('"').split()[0] for c in m.group(2).split(","))
        if all(re.fullmatch(r"[a-z_][a-z0-9_]*", c, re.I) for c in cols):
            out.setdefault(idx["tablename"], set()).add(cols)
    return out


def build_schema(intro: dict, project: str) -> tuple[str, dict]:
    enums: dict[str, list[str]] = {}
    for row in intro["enums"]:
        enums.setdefault(row["typname"], []).append(row["enumlabel"])

    vector_dims = {(v["table_name"], v["column_name"]): (v["typmod"] - 4 if v["typmod"] and v["typmod"] > 4 else None)
                   for v in intro["vectors"]}

    tables: dict[str, list[dict]] = {}
    for col in intro["columns"]:
        tables.setdefault(col["table_name"], []).append(col)

    pks: dict[str, list[str]] = {}
    pk_index_names: set[str] = set()
    for pk in intro["pks"]:
        pks.setdefault(pk["table_name"], []).append(pk["column_name"])

    fks_by_table: dict[str, list[dict]] = {}
    auth_fk_tables: list[str] = []
    unique_sets = _unique_column_sets(intro)
    unenforceable_fks: list[str] = []
    for fk in intro["fks"]:
        cols = [c for c in (fk.get("columns") or "").split(",") if c]
        fcols = [c for c in (fk.get("foreign_columns") or "").split(",") if c]
        if not cols or not fcols or len(cols) != len(fcols):
            continue
        if fk.get("foreign_schema") != "public":
            auth_fk_tables.append(
                f"{fk['table_name']}({','.join(cols)}) -> "
                f"{fk.get('foreign_schema')}.{fk['foreign_table']}"
            )
            continue
        # SQLite requires the parent columns to be a PK or carry a UNIQUE index.
        # Postgres is no laxer, but our emitted schema drops some expression /
        # non-btree indexes, so re-check against what we actually emit.
        if tuple(fcols) not in unique_sets.get(fk["foreign_table"], set()):
            unenforceable_fks.append(
                f"{fk['constraint_name']}: {fk['table_name']}({','.join(cols)}) -> "
                f"{fk['foreign_table']}({','.join(fcols)}) — parent columns not unique in target"
            )
            continue
        fks_by_table.setdefault(fk["table_name"], []).append(
            {"columns": cols, "foreign_table": fk["foreign_table"], "foreign_columns": fcols}
        )

    order = topo_order(sorted(tables), intro["fks"])
    lossy: dict[str, list[str]] = {"defaults_dropped": [], "indexes_skipped": [],
                                   "cross_schema_fks_dropped": sorted(set(auth_fk_tables)),
                                   "unenforceable_fks_dropped": sorted(set(unenforceable_fks))}

    out: list[str] = []
    for t in order:
        cols = tables[t]
        pk_cols = pks.get(t, [])
        lines: list[str] = []
        for c in cols:
            name = c["column_name"]
            typ, check = map_type(c["data_type"], c["udt_name"], enums,
                                  vector_dims.get((t, name)))
            parts = [f'  "{name}" {typ}']
            single_int_pk = (pk_cols == [name] and typ == "INTEGER")
            if single_int_pk:
                parts[0] += " PRIMARY KEY"
            if c["is_nullable"] == "NO" and not single_int_pk:
                parts.append("NOT NULL")
            dflt = map_default(c.get("column_default"))
            if dflt:
                parts.append(f"DEFAULT {dflt}")
            elif c.get("column_default"):
                lossy["defaults_dropped"].append(f"{t}.{name}: {c['column_default'][:80]}")
            if check:
                parts.append(check.replace("%COL%", f'"{name}"'))
            lines.append(" ".join(parts))
        if pk_cols and not (len(pk_cols) == 1 and any(
                c["column_name"] == pk_cols[0] and map_type(c["data_type"], c["udt_name"], enums,
                                                            vector_dims.get((t, pk_cols[0])))[0] == "INTEGER"
                for c in cols)):
            qcols = ", ".join(f'"{c}"' for c in pk_cols)
            lines.append(f"  PRIMARY KEY ({qcols})")
        for fk in fks_by_table.get(t, []):
            child = ", ".join(f'"{c}"' for c in fk["columns"])
            parent = ", ".join(f'"{c}"' for c in fk["foreign_columns"])
            lines.append(f'  FOREIGN KEY ({child}) REFERENCES "{fk["foreign_table"]}" ({parent})')
        body = ",\n".join(lines)
        out.append(f'CREATE TABLE IF NOT EXISTS "{t}" (\n{body}\n);')

    idx_out: list[str] = []
    for idx in intro["indexes"]:
        t = idx["tablename"]
        if t not in tables:
            continue
        stmt = transpile_index(idx["indexdef"], t, pk_index_names)
        if stmt:
            idx_out.append(stmt)
        elif "_pkey" not in idx["indexname"]:
            lossy["indexes_skipped"].append(f"{idx['indexname']}: {idx['indexdef'][:100]}")
            # A dropped UNIQUE index is a lost integrity CONSTRAINT, not a lost
            # optimization — it must be impossible to miss in the report.
            if "UNIQUE INDEX" in idx["indexdef"]:
                lossy.setdefault("UNIQUE_CONSTRAINTS_LOST", []).append(
                    f"{idx['indexname']} ON {t}: {idx['indexdef'][:140]}")

    plpgsql = [f["proname"] for f in intro["functions"] if f["lanname"] == "plpgsql"]
    triggers = [f"{tr['table_name']}.{tr['trigger_name']}" for tr in intro["triggers"]]

    header = "\n".join([
        f"-- {PROJECTS[project]['turso_db']} master schema — transpiled from live Supabase",
        f"-- project ref: {PROJECTS[project]['ref']}  generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"-- tables: {len(tables)}  indexes emitted: {len(idx_out)}",
        "--",
        "-- NOT TRANSPILED (DAL responsibility — see scripts/lib/db_turso.py):",
        f"--   PL/pgSQL functions ({len(plpgsql)}): {', '.join(plpgsql[:20])}{'...' if len(plpgsql) > 20 else ''}",
        f"--   Triggers ({len(triggers)}): {', '.join(triggers[:10])}{'...' if len(triggers) > 10 else ''}",
        f"--   RLS policies: replaced by mandatory tenant scoping in db_turso.py",
        f"--   cross-schema FKs dropped ({len(lossy['cross_schema_fks_dropped'])}, e.g. auth.users): "
        f"{'; '.join(lossy['cross_schema_fks_dropped'][:6])}",
        f"--   FKs dropped as unenforceable in SQLite ({len(lossy['unenforceable_fks_dropped'])}) — "
        f"parent columns not unique in the emitted schema; enforce in the DAL",
        f"--   defaults dropped ({len(lossy['defaults_dropped'])}) and non-btree/expression indexes skipped "
        f"({len(lossy['indexes_skipped'])}): see {OUT_DIR.name}/{project}__transpile_report.json",
        "--",
        "PRAGMA foreign_keys = ON;",
        "",
    ])
    sql = header + "\n\n".join(out) + "\n\n-- indexes\n" + "\n".join(idx_out) + "\n"
    report = {
        "project": project,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "table_count": len(tables),
        "index_count": len(idx_out),
        "plpgsql_functions": plpgsql,
        "triggers": triggers,
        "lossy": lossy,
    }
    return sql, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=sorted(PROJECTS), default="bravo")
    ap.add_argument("--verify", action="store_true",
                    help="after emitting, assert emitted table count == live table count")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    token = load_env().get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("ERROR: SUPABASE_ACCESS_TOKEN absent from agents env", file=sys.stderr)
        return 2

    ref = PROJECTS[args.project]["ref"]
    intro = introspect(ref, token)
    live_tables = {c["table_name"] for c in intro["columns"]}
    sql, report = build_schema(intro, args.project)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sql_path = OUT_DIR / f"{args.project}__000_master_schema.sql"
    sql_path.write_text(sql, encoding="utf-8")
    report_path = OUT_DIR / f"{args.project}__transpile_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    emitted = sql.count("CREATE TABLE IF NOT EXISTS")
    ok = emitted == len(live_tables)
    if args.json:
        print(json.dumps({"ok": ok, "live_tables": len(live_tables), "emitted_tables": emitted,
                          "sql": str(sql_path), "report": str(report_path)}))
    else:
        print(f"live tables: {len(live_tables)}  emitted: {emitted}  -> {sql_path}")
        print(f"report: {report_path}")
        if args.verify:
            print(f"VERIFY: {'PASS' if ok else 'FAIL'} — emitted {emitted}/{len(live_tables)} tables")
    return 0 if (ok or not args.verify) else 1


if __name__ == "__main__":
    sys.exit(main())
