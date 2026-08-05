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

Take a restore point first — `python scripts/db_snapshot.py create --name pre-etl`.
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

from lib.db_turso import TursoDB, get_db  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("etl_supabase_to_turso")

PAGE = 1000
TIMEOUT_S = 60

# url_key / key_key pairs as they exist in the agents env. Breeze's are
# deliberately mixed-case — see supabase_tool.py:133.
PROJECTS = {
    "bravo": ("BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_SERVICE_ROLE_KEY"),
    "oasis": ("OASIS_SUPABASE_URL", "OASIS_SUPABASE_SERVICE_ROLE_KEY"),
    "nostalgic": ("NOSTALGIC_SUPABASE_URL", "NOSTALGIC_SUPABASE_SERVICE_ROLE_KEY"),
    "breeze": ("Breeze_SUPABASE_URL", "Breeze_SUPABASE_SERVICE_ROLE_KEY"),
}


class SourceUnavailable(RuntimeError):
    """Supabase side could not be read — never silently treated as 'no rows'."""


# ------------------------------------------------------------------- source

def _headers(key: str, **extra: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}", **extra}


def source_config(project: str) -> tuple[str, str]:
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
    usable = [c for c in cols]
    placeholders = ", ".join(
        f"vector32(?)" if c in vec_cols else "?" for c in usable
    )
    col_sql = ", ".join(f'"{c}"' for c in usable)
    sql = f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES ({placeholders})'
    inserted = 0
    for row in rows:
        params = []
        for c in usable:
            v = row.get(c)
            params.append(json.dumps(v) if (c in vec_cols and isinstance(v, list)) else to_libsql(v))
        db.execute(sql, params, allow_unscoped=True,
                   reason="bulk ETL — tenant_id copied verbatim from source rows")
        inserted += 1
    db.commit()
    return inserted


# -------------------------------------------------------------------- parity

def verify_parity(db: TursoDB, url: str, key: str, tables: list[str]) -> dict:
    report = {"checked": 0, "ok": 0, "mismatched": 0, "tables": []}
    for t in tables:
        try:
            src_n = source_count(url, key, t)
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
                page = fetch_page(url, key, t, off, PAGE)
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
    ap.add_argument("--project", choices=sorted(PROJECTS), default="bravo")
    ap.add_argument("--tables", help="comma-separated subset (default: every table present on both sides)")
    ap.add_argument("--db-path", help="local libSQL file instead of the configured Turso target")
    ap.add_argument("--dry-run", action="store_true", help="report what would move, copy nothing")
    ap.add_argument("--verify-parity", action="store_true", help="compare only; do not copy")
    ap.add_argument("--limit-per-table", type=int, help="cap rows per table (smoke tests)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        url, key = source_config(args.project)
    except SourceUnavailable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    db = TursoDB(args.db_path, None, f"local({args.db_path})") if args.db_path else get_db()

    try:
        src_tables = set(list_source_tables(url, key))
    except SourceUnavailable as exc:
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
        report = verify_parity(db, url, key, wanted)
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

    moved = {"tables": 0, "rows": 0, "details": []}
    if not args.dry_run:
        set_fk_enforcement(db, False)
    for t in wanted:
        if t not in tgt_tables:
            continue
        cols, _pks, vec = target_schema(db, t)
        try:
            n = source_count(url, key, t)
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
            page = fetch_page(url, key, t, off, min(PAGE, n - off))
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
