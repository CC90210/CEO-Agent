#!/usr/bin/env python3
"""Create tables that exist in Postgres but not yet in Turso.

WHY NOT just re-run apply_turso_migration.py: the master schema file changed
after it was applied (the transpiler now emits ON DELETE / ON UPDATE actions),
so the ledger refuses on a checksum mismatch — correctly. Re-applying the whole
file would also be the wrong instrument: the 166 existing tables have had their
foreign-key actions repaired IN PLACE, and `CREATE TABLE IF NOT EXISTS` would
skip them silently, which reads like success without being it.

This does the narrow thing instead: find tables Postgres has and Turso does not,
and create ONLY those, with their indexes and triggers, from the freshly
emitted schema.

New tables appear because Supabase is still live and still being written to —
which is the actual reason the migration is not finished.

    python scripts/apply_missing_tables.py --project bravo
    python scripts/apply_missing_tables.py --project bravo --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import libsql  # noqa: E402
import requests  # noqa: E402

from core.turso_schema_transpiler import PROJECTS  # noqa: E402
from lib.db_turso import resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

MIGRATIONS = REPO / "database" / "turso_migrations"


def split_sql(text: str) -> list[str]:
    """Split on ';' while keeping trigger bodies (BEGIN ... END;) whole."""
    out, buf, depth = [], [], 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        up = s.upper()
        if re.search(r"\bBEGIN\b", up):
            depth += 1
        if re.search(r"\bEND\s*;", up):
            depth = max(0, depth - 1)
            if depth == 0:
                out.append("\n".join(buf).strip().rstrip(";"))
                buf = []
                continue
        if depth == 0 and s.endswith(";"):
            out.append("\n".join(buf).strip().rstrip(";"))
            buf = []
    if buf:
        out.append("\n".join(buf).strip().rstrip(";"))
    return [s for s in out if s.strip()]


def _stmt_table(stmt: str) -> str | None:
    m = re.match(
        r'CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'"?([\w]+)"?', stmt, re.I)
    if not m:
        return None
    if re.match(r"CREATE\s+TABLE", stmt, re.I):
        return m.group(1)
    m2 = re.search(r'\bON\s+"?([\w]+)"?', stmt, re.I)
    return m2.group(1) if m2 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, choices=sorted(PROJECTS))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    token = load_env().get("SUPABASE_ACCESS_TOKEN")
    ref = PROJECTS[args.project]["ref"]
    r = requests.post(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": "select tablename from pg_tables where schemaname='public'"},
        timeout=90)
    body = r.json()
    rows = body["result"] if isinstance(body, dict) and "result" in body else body
    pg_tables = {x["tablename"] for x in rows}

    url, tok, _ = resolve_project_target(args.project)
    conn = libsql.connect(database=url, auth_token=tok)
    turso_tables = {x[0] for x in conn.execute(
        "select name from sqlite_master where type='table'").fetchall()}

    missing = sorted(pg_tables - turso_tables)
    print(f"{args.project}: postgres={len(pg_tables)} turso={len(turso_tables)} "
          f"missing={len(missing)}")
    if not missing:
        print("nothing to do")
        return 0
    for t in missing:
        print(f"    MISSING: {t}")

    schema = MIGRATIONS / f"{args.project}__000_master_schema.sql"
    if not schema.exists():
        print(f"ERROR: {schema} not found — run the transpiler first", file=sys.stderr)
        return 2
    stmts = [s for s in split_sql(schema.read_text(encoding="utf-8"))
             if _stmt_table(s) in set(missing)]
    print(f"\nstatements for those tables: {len(stmts)}")
    if not args.apply:
        for s in stmts:
            print(f"    {s.splitlines()[0][:100]}")
        print("\n(dry run — pass --apply)")
        return 0

    applied, failed = 0, []
    for s in stmts:
        try:
            conn.execute(s)
            applied += 1
        except Exception as exc:
            failed.append(f"{s.splitlines()[0][:70]}: {str(exc)[:120]}")
    conn.commit()

    verify = libsql.connect(database=url, auth_token=tok)
    now = {x[0] for x in verify.execute(
        "select name from sqlite_master where type='table'").fetchall()}
    still = sorted(set(missing) - now)
    print(f"applied {applied}, failed {len(failed)}")
    for f in failed:
        print(f"    FAIL {f}")
    print(f"still missing after apply: {still or 'none'}")
    # A created table with no enforcement is worse than no table.
    fk = verify.execute("PRAGMA foreign_keys").fetchall()[0][0]
    viol = verify.execute("PRAGMA foreign_key_check").fetchall()
    print(f"foreign_keys={fk} violations={len(viol)}")
    return 1 if (still or failed or fk != 1 or viol) else 0


if __name__ == "__main__":
    raise SystemExit(main())
