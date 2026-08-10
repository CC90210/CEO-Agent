#!/usr/bin/env python3
"""Check that everything the transpiler could not port has actually been dealt with.

WHY THIS EXISTS. The Supabase -> Turso transpiler writes a `lossy` section into
database/turso_migrations/<project>__transpile_report.json listing what it could
not carry across. It did its job honestly. Nobody read it.

One entry said:

    "VIEWS_LOST": ["merchant_summary: needs manual port - WITH ranked_apps AS ..."]

merchant_summary drives the SunBiz sales Pipeline. It was missing from Turso for
the entire migration window, and the UI swallows exactly that error and renders
an empty board -- so 2,373 merchant records were invisible with nothing shown to
anyone. It was found by accident weeks later, then confirmed by finally reading
this file.

A report that records a gap but is never read is the same as no report. This
turns it into a check that fails.

WHAT IT CHECKS
  VIEWS_LOST          the named object must now EXIST in the target database.
                      This is the hard failure -- a lost view is a feature that
                      silently returns nothing.
  indexes_skipped     reported. Postgres-only index types (gin/gist/hnsw/trgm)
                      are expected and listed separately from plain btree ones,
                      because a skipped btree may be a real dedup or performance
                      loss while a skipped gin index simply has no SQLite
                      equivalent.
  checks_skipped      reported, and flagged louder when the constraint looks
                      like a security or format boundary (tenant prefixes,
                      regex shape checks) -- those need application-level
                      enforcement instead, and somebody has to confirm it.
  defaults_dropped    reported, and flagged louder when the default minted a
                      SECRET (gen_random_bytes) or set an EXPIRY (now() +
                      interval), since a NULL there fails open or closed in ways
                      only the calling code decides. Columns are checked for
                      actual NULLs in live data.
  cross_schema_fks    reported only. These pointed at Supabase's auth.users,
                      which deliberately does not exist on Turso.

EXIT CODES
  0  nothing lost, or everything lost has been accounted for
  1  a VIEWS_LOST object is still missing, or a secret/expiry column is NULL
  2  a report or database could not be read (do not treat as a pass)

USAGE
  python scripts/turso_lossy_audit.py                 # all projects
  python scripts/turso_lossy_audit.py --project bravo
  python scripts/turso_lossy_audit.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

MIGRATIONS = ROOT / "database" / "turso_migrations"

# Index types Postgres has and SQLite does not. Skipping these is expected.
PG_ONLY_INDEX = re.compile(r"USING\s+(gin|gist|hnsw|ivfflat|brin|spgist)\b", re.I)

# A dropped default that minted a secret or set an expiry is not cosmetic.
SECRET_DEFAULT = re.compile(r"gen_random_bytes|uuid_generate|gen_random_uuid", re.I)
EXPIRY_DEFAULT = re.compile(r"now\(\)\s*\+|CURRENT_(DATE|TIMESTAMP)|timezone\(", re.I)

# A dropped CHECK that enforced a tenant prefix or a strict format was a
# boundary, not a nicety.
BOUNDARY_CHECK = re.compile(r"tenant_id|~\s*'|~~|storage_path", re.I)


def load_reports(project: str | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not MIGRATIONS.is_dir():
        print(f"FATAL: {MIGRATIONS} not found", file=sys.stderr)
        raise SystemExit(2)
    for path in sorted(MIGRATIONS.glob("*__transpile_report.json")):
        name = path.name.split("__")[0]
        if project and name != project:
            continue
        try:
            out[name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"FATAL: cannot read {path.name}: {exc}", file=sys.stderr)
            raise SystemExit(2)
    if not out:
        print(f"FATAL: no transpile reports{' for ' + project if project else ''}",
              file=sys.stderr)
        raise SystemExit(2)
    return out


def connect(project: str):
    """Open the project's Turso database, or return None with a reason."""
    try:
        import libsql  # noqa: PLC0415
        from lib.db_turso import resolve_project_target  # noqa: PLC0415

        url, token, _ = resolve_project_target(project)
        return libsql.connect(database=url, auth_token=token), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:120]


def objects_in(conn) -> dict[str, str]:
    cur = conn.execute("SELECT name, type FROM sqlite_master")
    return {r[0]: r[1] for r in cur.fetchall()}


def null_count(conn, table: str, column: str) -> int | None:
    try:
        cur = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL')
        return int(cur.fetchone()[0])
    except Exception:  # noqa: BLE001
        return None


def audit(project: str, report: dict) -> dict:
    lossy = report.get("lossy") or {}
    result = {
        "project": project,
        "views_missing": [],
        "views_ok": [],
        "secret_or_expiry_nulls": [],
        "skipped_btree_indexes": [],
        "skipped_pg_only_indexes": 0,
        "boundary_checks_dropped": [],
        "other_checks_dropped": 0,
        "secret_defaults_dropped": [],
        "expiry_defaults_dropped": [],
        "other_defaults_dropped": 0,
        "cross_schema_fks_dropped": len(lossy.get("cross_schema_fks_dropped") or []),
        "db_error": None,
    }

    conn, err = connect(project)
    if err:
        result["db_error"] = err

    live = objects_in(conn) if conn else {}

    # --- VIEWS_LOST: the hard gate -------------------------------------
    for entry in lossy.get("VIEWS_LOST") or []:
        name = str(entry).split(":", 1)[0].strip()
        if not conn:
            result["views_missing"].append({"name": name, "reason": "database unreachable"})
        elif name in live:
            result["views_ok"].append({"name": name, "type": live[name]})
        else:
            result["views_missing"].append({"name": name, "reason": "absent from target"})

    # --- indexes -------------------------------------------------------
    for ddl in lossy.get("indexes_skipped") or []:
        text = str(ddl)
        if PG_ONLY_INDEX.search(text):
            result["skipped_pg_only_indexes"] += 1
        else:
            result["skipped_btree_indexes"].append(text.split(":", 1)[0].strip())

    # --- checks --------------------------------------------------------
    for entry in lossy.get("checks_skipped") or []:
        text = str(entry)
        if BOUNDARY_CHECK.search(text):
            result["boundary_checks_dropped"].append(text.split(":", 1)[0].strip())
        else:
            result["other_checks_dropped"] += 1

    # --- defaults ------------------------------------------------------
    for entry in lossy.get("defaults_dropped") or []:
        text = str(entry)
        target, _, expr = text.partition(":")
        table, _, column = target.strip().partition(".")
        kind = None
        if SECRET_DEFAULT.search(expr):
            kind = "secret"
            result["secret_defaults_dropped"].append(target.strip())
        elif EXPIRY_DEFAULT.search(expr):
            kind = "expiry"
            result["expiry_defaults_dropped"].append(target.strip())
        else:
            result["other_defaults_dropped"] += 1

        if kind and conn and table and column:
            n = null_count(conn, table, column)
            if n:
                result["secret_or_expiry_nulls"].append(
                    {"column": target.strip(), "kind": kind, "nulls": n})

    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit what the Turso transpiler could not port.")
    ap.add_argument("--project", help="one project instead of all")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    reports = load_reports(args.project)
    results = [audit(name, rep) for name, rep in reports.items()]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print("=" * 72)
            print(f"{r['project']}")
            print("=" * 72)
            if r["db_error"]:
                print(f"  database unreachable: {r['db_error']}")
            for v in r["views_ok"]:
                print(f"  ok       view {v['name']} is present ({v['type']})")
            for v in r["views_missing"]:
                print(f"  MISSING  view {v['name']} -- {v['reason']}")
            for n in r["secret_or_expiry_nulls"]:
                print(f"  NULLS    {n['column']} ({n['kind']}): {n['nulls']} rows")
            if r["skipped_btree_indexes"]:
                print(f"  review   {len(r['skipped_btree_indexes'])} plain index(es) skipped: "
                      f"{', '.join(r['skipped_btree_indexes'][:4])}")
            if r["skipped_pg_only_indexes"]:
                print(f"  expected {r['skipped_pg_only_indexes']} Postgres-only index(es) "
                      f"(gin/gist/hnsw) have no SQLite equivalent")
            if r["boundary_checks_dropped"]:
                print(f"  review   {len(r['boundary_checks_dropped'])} boundary CHECK(s) dropped "
                      f"-- confirm the application enforces them: "
                      f"{', '.join(r['boundary_checks_dropped'][:3])}")
            if r["secret_defaults_dropped"]:
                print(f"  review   {len(r['secret_defaults_dropped'])} secret-minting default(s) "
                      f"dropped: {', '.join(r['secret_defaults_dropped'][:4])}")
            if r["expiry_defaults_dropped"]:
                print(f"  review   {len(r['expiry_defaults_dropped'])} expiry default(s) dropped: "
                      f"{', '.join(r['expiry_defaults_dropped'][:4])}")
            if r["cross_schema_fks_dropped"]:
                print(f"  expected {r['cross_schema_fks_dropped']} cross-schema FK(s) to "
                      f"auth.users (no such schema on Turso)")

    missing = [v for r in results for v in r["views_missing"]]
    nulls = [n for r in results for n in r["secret_or_expiry_nulls"]]
    unreachable = [r for r in results if r["db_error"]]

    print()
    if unreachable and not args.json:
        for r in unreachable:
            print(f"COULD NOT VERIFY {r['project']}: {r['db_error']}")
        return 2
    if missing:
        print(f"FAIL: {len(missing)} transpiled-away object(s) still missing: "
              f"{', '.join(v['name'] for v in missing)}")
        return 1
    if nulls:
        print(f"FAIL: {len(nulls)} secret/expiry column(s) hold NULLs where a "
              f"database default used to fill them")
        return 1
    print("PASS: every object the transpiler could not port has been accounted for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
