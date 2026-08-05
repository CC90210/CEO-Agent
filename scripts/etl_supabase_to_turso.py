"""Supabase → Turso row ETL, with primary-key parity verification.

WHY PK PARITY AND NOT ROW COUNTS. Equal counts prove nothing: drop row A, insert
row B, the count matches and the data is wrong. This tool compares the actual
primary-key SETS on both sides and reports which keys are missing or extra. A
migration that "verified" on counts alone is how you discover the loss weeks
later, from a customer.

TYPE TRANSFORMS applied on the way across (mirroring turso_schema_transpiler):
  bool           -> 0 / 1
  dict / list    -> JSON text            (jsonb, json, text[] and other arrays)
  None           -> NULL
  vector(N)      -> vector32(<json>)     (F32_BLOB column, via libSQL's own fn)
  everything else passes through as-is (numerics stay TEXT, so no float rounding)

CLI:
  python scripts/etl_supabase_to_turso.py --project bravo --db-path ./local.db
  python scripts/etl_supabase_to_turso.py --project bravo --tables leads,tenants
  python scripts/etl_supabase_to_turso.py --project bravo --dry-run
  python scripts/etl_supabase_to_turso.py --verify-parity --project bravo --db-path ./local.db
  python scripts/etl_supabase_to_turso.py --verify-parity --json

--db-path targets a local libSQL file (the pre-Phase-0 path). Without it the
configured Turso target is used.

OVERWRITE SAFETY. Rows are written with INSERT OR REPLACE, so re-running against
a table that already holds data silently overwrites it — including data that did
NOT come from Supabase. The tool therefore refuses to write into a non-empty
target table unless --allow-overwrite is passed, and names the tables it stopped
on. (An earlier version only *advised* taking a restore point in this docstring;
an unenforced safety instruction is decoration, so it is now a gate.)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import requests  # noqa: E402

from lib.db_turso import TursoDB, resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("etl_supabase_to_turso")

PAGE = 1000
TIMEOUT_S = 60
# SQLite's SQLITE_MAX_VARIABLE_NUMBER is 32,766 on modern builds. Batch sizing
# divides this by the column count so a 60-column table cannot overflow it.
MAX_SQL_VARS = 30_000

# The project -> env-key registry is NOT redeclared here. supabase_tool.py owns
# it, including the deliberately mixed-case "Breeze_" prefix (its comment at
# :133 explains why). A second copy would drift the day a project is renamed and
# send this ETL at the wrong database.
from integrations.supabase_tool import PROJECTS as _SUPABASE_PROJECTS  # noqa: E402

PROJECTS = {name: (cfg["url_key"], cfg["key_key"])
            for name, cfg in _SUPABASE_PROJECTS.items()}

# All migratable projects — a superset of the PostgREST-configured ones. PropFlow
# has no service-role key stored, so it is reachable only via the Management API;
# excluding it from --project made the tool claim the project didn't exist.
from core.turso_schema_transpiler import PROJECTS as _ALL_PROJECTS  # noqa: E402

PROJECT_CHOICES = sorted(_ALL_PROJECTS)


class SourceUnavailable(RuntimeError):
    """Supabase side could not be read — never silently treated as 'no rows'."""


class MgmtSource:
    """Row source via the Supabase Management API (org-wide token).

    Exists for projects whose PostgREST service-role key is stale or absent
    (nostalgic: 401 since before 2026-08-05; propflow: never stored). The
    Management API's /database/query endpoint runs plain SQL with the org token
    apply_migration.py already uses, so these projects need no key rotation to
    migrate. Slower than PostgREST — fine for the row counts involved.
    """

    def __init__(self, project: str):
        from core.turso_schema_transpiler import PROJECTS as REFS, _mgmt_query  # noqa: PLC0415

        if project not in REFS:
            raise SourceUnavailable(f"{project}: no Management-API ref registered")
        self._ref = REFS[project]["ref"]
        self._q = _mgmt_query
        self._token = load_env().get("SUPABASE_ACCESS_TOKEN")
        if not self._token:
            raise SourceUnavailable("SUPABASE_ACCESS_TOKEN absent from agents env")

    def list_tables(self) -> list[str]:
        rows = self._q(self._ref,
                       "select tablename from pg_tables where schemaname='public' "
                       "order by tablename", self._token)
        return [r["tablename"] for r in rows]

    def count(self, table: str) -> int:
        rows = self._q(self._ref, f'select count(*) as n from "{table}"', self._token)
        return int(rows[0]["n"]) if rows else 0

    def page(self, table: str, offset: int, limit: int) -> list[dict]:
        # Deterministic paging needs a stable order; ctid is always present.
        return self._q(self._ref,
                       f'select * from "{table}" order by ctid '
                       f"limit {int(limit)} offset {int(offset)}", self._token)


# ------------------------------------------------------------------- source

def _headers(key: str, **extra: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}", **extra}


def source_config(project: str) -> tuple[str, str]:
    if project not in PROJECTS:
        raise SourceUnavailable(
            f"{project}: no PostgREST env-key pair registered (Management API only)")
    url_key, key_key = PROJECTS[project]
    env = load_env()
    url, key = env.get(url_key), env.get(key_key)
    if not url or not key:
        raise SourceUnavailable(
            f"{project}: missing {url_key} and/or {key_key} in the agents env. "
            f"(The nostalgic service-role key is known-stale as of 2026-08-05 — rotate it.)"
        )
    return url.rstrip("/"), key


def list_source_tables(url: str, key: str) -> list[str]:
    r = requests.get(f"{url}/rest/v1/",
                     headers=_headers(key, Accept="application/openapi+json"),
                     timeout=TIMEOUT_S)
    if r.status_code != 200:
        raise SourceUnavailable(f"OpenAPI root returned {r.status_code}: {r.text[:200]}")
    paths = r.json().get("paths", {})
    return sorted(p.lstrip("/") for p in paths if p != "/" and not p.startswith("/rpc/"))


def source_count(url: str, key: str, table: str) -> int:
    r = requests.get(f"{url}/rest/v1/{table}?select=*",
                     headers=_headers(key, Prefer="count=exact", Range="0-0"),
                     timeout=TIMEOUT_S)
    if r.status_code not in (200, 206):
        raise SourceUnavailable(f"{table}: count returned {r.status_code}: {r.text[:200]}")
    cr = r.headers.get("content-range", "")
    tail = cr.split("/")[-1] if "/" in cr else ""
    return int(tail) if tail.isdigit() else 0


def fetch_page(url: str, key: str, table: str, offset: int, limit: int) -> list[dict]:
    r = requests.get(
        f"{url}/rest/v1/{table}?select=*",
        headers=_headers(key, Range=f"{offset}-{offset + limit - 1}"),
        timeout=TIMEOUT_S,
    )
    if r.status_code not in (200, 206):
        raise SourceUnavailable(f"{table}: page {offset} returned {r.status_code}: {r.text[:200]}")
    return r.json()


# --------------------------------------------------------------- transform

def to_libsql(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return value


# ------------------------------------------------------------------- target

def target_schema(db: TursoDB, table: str) -> tuple[list[str], list[str], set[str]]:
    """Return (columns, primary_key_columns, f32_blob_columns)."""
    cols = db.query(f'PRAGMA table_info("{table}")', allow_unscoped=True,
                    reason="ETL schema introspection")
    names = [c["name"] for c in cols]
    pks = [c["name"] for c in sorted(cols, key=lambda c: c["pk"]) if c["pk"]]
    vec = {c["name"] for c in cols if str(c["type"]).upper().startswith("F32_BLOB")}
    return names, pks, vec


def set_fk_enforcement(db: TursoDB, on: bool) -> None:
    """Bulk load cannot honour FK order — a child table is often copied before its
    parent. Rather than guess a topological order (and get it wrong on cycles),
    enforcement is suspended for the load and then verified in full by
    fk_violations() afterwards. Deferring the check is safe; skipping it is not."""
    db.execute(f"PRAGMA foreign_keys = {'ON' if on else 'OFF'}",
               allow_unscoped=True, reason="ETL FK enforcement toggle")


def dependency_order(db: TursoDB, tables: list[str]) -> list[str]:
    """Order tables parents-first, from the TARGET schema's own foreign keys.

    Suspending enforcement is not enough on its own: SQLite treats
    `PRAGMA foreign_keys` as a no-op inside a transaction, and remote Turso showed
    exactly that — the pre-flight counts open one, the PRAGMA silently does
    nothing, and the first child row fails with SQLITE_CONSTRAINT. Ordering the
    copy is driver-independent and correct whether or not the PRAGMA takes.

    Cycles fall back to alphabetical for the remainder; the post-load
    foreign_key_check is what actually proves integrity either way.
    """
    wanted = set(tables)
    deps: dict[str, set[str]] = {t: set() for t in tables}
    for t in tables:
        for fk in db.query(f'PRAGMA foreign_key_list("{t}")', allow_unscoped=True,
                           reason="ETL dependency ordering"):
            parent = fk.get("table")
            if parent in wanted and parent != t:
                deps[t].add(parent)
    ordered: list[str] = []
    remaining = dict(deps)
    while remaining:
        ready = sorted(t for t, d in remaining.items() if not (d & set(remaining)))
        if not ready:
            ordered.extend(sorted(remaining))
            break
        ordered.extend(ready)
        for t in ready:
            remaining.pop(t)
    return ordered


def fk_violations(db: TursoDB) -> list[dict]:
    """Every row whose foreign key does not resolve, after the load."""
    rows = db.query("PRAGMA foreign_key_check", allow_unscoped=True,
                    reason="ETL integrity verification")
    return rows


def target_tables(db: TursoDB) -> set[str]:
    rows = db.query(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'",
        allow_unscoped=True, reason="ETL schema introspection")
    return {r["name"] for r in rows}


def load_rows(db: TursoDB, table: str, rows: list[dict], cols: list[str],
              vec_cols: set[str]) -> int:
    if not rows:
        return 0
    usable = list(cols)
    placeholders = ", ".join("vector32(?)" if c in vec_cols else "?" for c in usable)
    col_sql = ", ".join(f'"{c}"' for c in usable)
    payload = []
    for row in rows:
        params = []
        for c in usable:
            v = row.get(c)
            params.append(json.dumps(v) if (c in vec_cols and isinstance(v, list)) else to_libsql(v))
        payload.append(params)

    # MULTI-ROW VALUES, not executemany. Measured against remote Turso: libsql's
    # executemany still issues one round trip per row (~2,400 rows in 13 min, i.e.
    # ~8h for the Bravo project). A single INSERT with N value tuples is ONE round
    # trip. SQLite's parameter ceiling is 32,766, so N is sized from the column
    # count and clamped so a wide table cannot overflow it.
    per_stmt = max(1, min(len(rows), MAX_SQL_VARS // max(1, len(usable))))
    inserted = 0
    for start in range(0, len(payload), per_stmt):
        chunk = payload[start:start + per_stmt]
        values_sql = ", ".join(f"({placeholders})" for _ in chunk)
        flat: list = [v for params in chunk for v in params]
        db.execute(f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES {values_sql}',
                   flat, allow_unscoped=True,
                   reason="bulk ETL — tenant_id copied verbatim from source rows")
        inserted += len(chunk)
    db.commit()
    return inserted


# -------------------------------------------------------------------- parity

def verify_parity(db: TursoDB, src_count, src_page, tables: list[str]) -> dict:
    """src_count/src_page are source-backend closures (PostgREST or Mgmt API)."""
    report = {"checked": 0, "ok": 0, "mismatched": 0, "tables": []}
    for t in tables:
        try:
            src_n = src_count(t)
        except SourceUnavailable as exc:
            report["tables"].append({"table": t, "status": "source_error", "error": str(exc)})
            report["mismatched"] += 1
            continue
        try:
            tgt_n = db.query(f'SELECT count(*) AS n FROM "{t}"', allow_unscoped=True,
                             reason="parity count")[0]["n"]
        except Exception as exc:  # noqa: BLE001
            report["tables"].append({"table": t, "status": "target_error", "error": str(exc)[:200]})
            report["mismatched"] += 1
            continue

        entry: dict[str, Any] = {"table": t, "source_rows": src_n, "target_rows": tgt_n}
        _, pks, _ = target_schema(db, t)
        if src_n == 0 and tgt_n == 0:
            entry["status"] = "ok_empty"
        elif not pks:
            entry["status"] = "ok_counts_only" if src_n == tgt_n else "MISMATCH"
            entry["note"] = "no primary key — counts are the only available check"
        else:
            # Compare FULL primary-key tuples. Using only pks[0] would let a
            # composite-key table pass while later components differ — identical
            # first-component sets, mis-associated rows, and a green report.
            # Values are joined with a unit separator that cannot occur in a key,
            # so ("a|b", "c") and ("a", "b|c") stay distinguishable.
            sep = "\x1f"

            def keytuple(row: dict) -> str:
                return sep.join("\x00NULL" if row.get(c) is None else str(row.get(c))
                                for c in pks)

            src_keys: set[str] = set()
            src_rows_seen = 0
            off = 0
            while off < src_n:
                page = src_page(t, off, PAGE)
                if not page:
                    break
                src_keys.update(keytuple(r) for r in page)
                src_rows_seen += len(page)
                off += len(page)
            col_sql = ", ".join(f'"{c}"' for c in pks)
            tgt_rows = db.query(f'SELECT {col_sql} FROM "{t}"', allow_unscoped=True,
                                reason="parity key set")
            tgt_keys = {keytuple(r) for r in tgt_rows}
            missing = src_keys - tgt_keys
            extra = tgt_keys - src_keys
            entry["pk_columns"] = pks
            entry["missing_in_target"] = len(missing)
            entry["extra_in_target"] = len(extra)
            entry["sample_missing"] = [k.replace(sep, " | ") for k in sorted(missing)[:5]]
            # Distinct key tuples must equal the row count on both sides; if they
            # do not, rows collapsed onto a duplicate key somewhere.
            entry["source_distinct_keys"] = len(src_keys)
            entry["target_distinct_keys"] = len(tgt_keys)
            collapsed = (len(src_keys) != src_rows_seen) or (len(tgt_keys) != len(tgt_rows))
            if collapsed:
                entry["note"] = ("distinct key tuples != row count — duplicate primary "
                                 "keys, rows may have been overwritten")
            entry["status"] = "ok" if (not missing and not extra and not collapsed) else "MISMATCH"

        if entry["status"].startswith("ok"):
            report["ok"] += 1
        else:
            report["mismatched"] += 1
        report["checked"] += 1
        report["tables"].append(entry)
    return report


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=PROJECT_CHOICES, default="bravo")
    ap.add_argument("--tables", help="comma-separated subset (default: every table present on both sides)")
    ap.add_argument("--db-path", help="local libSQL file instead of the configured Turso target")
    ap.add_argument("--dry-run", action="store_true", help="report what would move, copy nothing")
    ap.add_argument("--verify-parity", action="store_true", help="compare only; do not copy")
    ap.add_argument("--limit-per-table", type=int, help="cap rows per table (smoke tests)")
    ap.add_argument("--source", choices=["auto", "mgmt"], default="auto",
                    help="row source: auto = PostgREST with Management-API fallback; "
                         "mgmt = force the Management API")
    ap.add_argument("--allow-overwrite", action="store_true",
                    help="permit writing into target tables that already hold rows "
                         "(INSERT OR REPLACE will overwrite them)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # Source selection: PostgREST when this project's service key exists and
    # works; otherwise the Management API. The choice is REPORTED, never silent.
    mgmt: MgmtSource | None = None
    url = key = None
    if args.source != "mgmt":
        try:
            url, key = source_config(args.project)
        except SourceUnavailable as exc:
            print(f"NOTE: PostgREST source unavailable ({exc}) — using Management API",
                  file=sys.stderr)
    if url is None or args.source == "mgmt":
        try:
            mgmt = MgmtSource(args.project)
        except SourceUnavailable as exc:
            print(f"ERROR: no usable source for {args.project}: {exc}", file=sys.stderr)
            return 2

    # Target selection: an explicit --db-path wins (local/test); otherwise the
    # Turso database MATCHING the source project. Falling back to the default
    # (bravo) target for a non-bravo source would quietly load Breeze's merchant
    # rows into the Bravo database — cross-trust-boundary contamination.
    if args.db_path:
        db = TursoDB(args.db_path, None, f"local({args.db_path})")
    else:
        # Distinct names on purpose: `url`/`key` above are the SOURCE (PostgREST).
        # Reusing `url` here clobbered the source URL with the Turso hostname and
        # sent REST reads at libsql://... — InvalidSchema at first contact.
        tgt_url, tgt_token, tgt_mode = resolve_project_target(args.project)
        db = TursoDB(tgt_url, tgt_token, tgt_mode)

    # Uniform source ops over whichever backend won above.
    if mgmt is not None:
        src_list = mgmt.list_tables
        src_count = mgmt.count
        src_page = mgmt.page
    else:
        def src_list(): return list_source_tables(url, key)          # noqa: E731
        def src_count(t): return source_count(url, key, t)           # noqa: E731
        def src_page(t, off, lim): return fetch_page(url, key, t, off, lim)  # noqa: E731

    try:
        src_tables = set(src_list())
    except SourceUnavailable as exc:
        # A key can be PRESENT but dead (nostalgic's 401ed for months). Auto mode
        # falls through to the Management API on first contact failure too.
        if mgmt is None and args.source == "auto":
            print(f"NOTE: PostgREST contact failed ({exc}) — retrying via Management API",
                  file=sys.stderr)
            try:
                mgmt = MgmtSource(args.project)
                src_list, src_count, src_page = mgmt.list_tables, mgmt.count, mgmt.page
                src_tables = set(src_list())
            except SourceUnavailable as exc2:
                print(f"ERROR: no usable source: {exc2}", file=sys.stderr)
                return 2
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    tgt_tables = target_tables(db)

    if args.tables:
        wanted = [t.strip() for t in args.tables.split(",") if t.strip()]
    else:
        wanted = sorted(src_tables & tgt_tables)

    skipped = sorted((src_tables - tgt_tables) & set(wanted or src_tables))
    if skipped:
        # Never silent: a table present in Supabase but absent from the Turso
        # schema would otherwise vanish without a word.
        log.warn("tables present in source but absent in target — NOT migrated",
                 count=len(skipped), tables=skipped[:20])

    if args.verify_parity:
        report = verify_parity(db, src_count, src_page, wanted)
        report["source_only_tables"] = skipped
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"parity: {report['ok']}/{report['checked']} tables OK, "
                  f"{report['mismatched']} mismatched")
            for e in report["tables"]:
                if not str(e.get("status", "")).startswith("ok"):
                    print(f"  {e['status']:14} {e['table']}: "
                          f"src={e.get('source_rows')} tgt={e.get('target_rows')} "
                          f"missing={e.get('missing_in_target')} extra={e.get('extra_in_target')} "
                          f"{e.get('error', '')}")
            if skipped:
                print(f"  NOT MIGRATED (no target table): {len(skipped)} -> {skipped[:10]}")
            print(f"VERIFY-PARITY: {'PASS' if report['mismatched'] == 0 else 'FAIL'}")
        return 0 if report["mismatched"] == 0 else 1

    # Refuse to clobber a populated target before writing anything. Checked up
    # front rather than per-table so the run is all-or-nothing: a half-copied
    # database that aborted midway is worse than one that never started.
    if not args.dry_run and not args.allow_overwrite:
        populated = []
        for t in wanted:
            if t not in tgt_tables:
                continue
            n = db.query(f'SELECT count(*) AS n FROM "{t}"', allow_unscoped=True,
                         reason="overwrite pre-flight")[0]["n"]
            if n:
                populated.append((t, n))
        if populated:
            print("REFUSED: these target tables already hold rows and would be "
                  "overwritten by INSERT OR REPLACE:", file=sys.stderr)
            for t, n in populated[:15]:
                print(f"    {t}: {n} existing row(s)", file=sys.stderr)
            if len(populated) > 15:
                print(f"    ... and {len(populated) - 15} more", file=sys.stderr)
            print("Re-run with --allow-overwrite if replacing them is intended.",
                  file=sys.stderr)
            return 2

    moved = {"tables": 0, "rows": 0, "details": []}
    if not args.dry_run:
        set_fk_enforcement(db, False)          # helps when it takes; not relied upon
        wanted = [t for t in dependency_order(db, [t for t in wanted if t in tgt_tables])]
    for t in wanted:
        if t not in tgt_tables:
            continue
        cols, _pks, vec = target_schema(db, t)
        try:
            n = src_count(t)
        except SourceUnavailable as exc:
            print(f"ERROR reading {t}: {exc}", file=sys.stderr)
            return 1
        if args.limit_per_table:
            n = min(n, args.limit_per_table)
        if args.dry_run:
            moved["details"].append({"table": t, "would_copy": n})
            moved["rows"] += n
            moved["tables"] += 1
            continue

        copied = 0
        off = 0
        while off < n:
            page = src_page(t, off, min(PAGE, n - off))
            if not page:
                break
            copied += load_rows(db, t, page, cols, vec)
            off += len(page)
        moved["details"].append({"table": t, "copied": copied, "source": n})
        moved["rows"] += copied
        moved["tables"] += 1
        log.info("table copied", table=t, rows=copied, source_rows=n)

    violations: list[dict] = []
    if not args.dry_run:
        set_fk_enforcement(db, True)
        violations = fk_violations(db)
        moved["fk_violations"] = len(violations)
        moved["fk_violation_sample"] = violations[:10]
        if violations:
            log.error("post-load foreign-key violations", count=len(violations),
                      sample=violations[:5])

    moved["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    moved["source_only_tables"] = skipped
    if args.json:
        print(json.dumps(moved, indent=2, default=str))
    else:
        verb = "would copy" if args.dry_run else "copied"
        print(f"{verb} {moved['rows']} rows across {moved['tables']} tables")
        if skipped:
            print(f"  NOT MIGRATED (no target table): {len(skipped)} -> {skipped[:10]}")
        if not args.dry_run:
            print(f"  foreign-key violations after load: {len(violations)}"
                  + (f" -> {violations[:5]}" if violations else " (clean)"))
    # A partial copy that leaves dangling references is a failure, not a warning.
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
