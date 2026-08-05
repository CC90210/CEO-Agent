"""Turso / libSQL CLI tool — the sanctioned way for an agent to touch Turso.

Mirrors supabase_tool.py's shape so routing stays muscle-memory: credentials
load via lib.secret_loader (the agent never sees TURSO_AUTH_TOKEN), every verb
takes --json, and reads go through lib.db_turso so the tenant-scoping guard
applies here exactly as it does in application code. A CLI that could bypass the
guard would make the guard optional.

Usage:
  python scripts/integrations/turso_tool.py status [--json]
  python scripts/integrations/turso_tool.py tables [--json]
  python scripts/integrations/turso_tool.py schema <table> [--json]
  python scripts/integrations/turso_tool.py select <table> --tenant <id> [--columns c1,c2]
                                                   [--where "status = ?"] [--param warm]
                                                   [--limit 20] [--json]
  python scripts/integrations/turso_tool.py sql "SELECT ..." [--param x] [--json]
                                                   [--allow-unscoped --reason "..."]

  --db-path FILE   run against a local libSQL file instead of the configured target
                   (used by tests and by the pre-Phase-0 dry runs)

Exit codes: 0 ok · 1 query/guard error · 2 not configured.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from lib.db_turso import (  # noqa: E402
    TursoConfigError,
    TursoDB,
    UnscopedQueryError,
    get_db,
    resolve_target,
)


def _db(args) -> TursoDB:
    if args.db_path:
        return TursoDB(args.db_path, None, f"local({args.db_path})")
    return get_db()


def _emit(args, payload: dict, human: str) -> None:
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(human)


def cmd_status(args) -> int:
    try:
        url, token, mode = (args.db_path, None, f"local({args.db_path})") if args.db_path \
            else resolve_target()
    except TursoConfigError as exc:
        _emit(args, {"ok": False, "configured": False, "error": str(exc)},
              f"NOT CONFIGURED: {exc}")
        return 2
    try:
        db = _db(args)
        tables = db.query(
            "select count(*) as n from sqlite_master where type='table' and name not like 'sqlite_%'",
            allow_unscoped=True, reason="status metadata read",
        )[0]["n"]
    except Exception as exc:  # noqa: BLE001
        _emit(args, {"ok": False, "configured": True, "mode": mode, "error": str(exc)},
              f"CONFIGURED but unreachable ({mode}): {exc}")
        return 1
    payload = {"ok": True, "configured": True, "mode": mode, "tables": tables,
               "tenant_scoped_tables": len(db.tenant_tables),
               "auth": "token" if token else "none (local file)"}
    _emit(args, payload,
          f"Turso OK — mode={mode} tables={tables} "
          f"tenant-scoped={len(db.tenant_tables)}")
    return 0


def cmd_tables(args) -> int:
    db = _db(args)
    rows = db.query(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name",
        allow_unscoped=True, reason="schema listing",
    )
    names = [r["name"] for r in rows]
    scoped = sorted(db.tenant_tables)
    _emit(args, {"ok": True, "count": len(names), "tables": names, "tenant_scoped": scoped},
          f"{len(names)} tables ({len(scoped)} tenant-scoped):\n  " + "\n  ".join(
              f"{n}{'  [tenant-scoped]' if n.lower() in db.tenant_tables else ''}" for n in names))
    return 0


def cmd_schema(args) -> int:
    db = _db(args)
    cols = db.query(f'PRAGMA table_info("{args.table}")', allow_unscoped=True,
                    reason="schema introspection")
    if not cols:
        _emit(args, {"ok": False, "error": f"no such table: {args.table}"},
              f"ERROR: no such table: {args.table}")
        return 1
    _emit(args, {"ok": True, "table": args.table, "columns": cols,
                 "tenant_scoped": db.is_tenant_scoped(args.table)},
          f"{args.table} ({'tenant-scoped' if db.is_tenant_scoped(args.table) else 'global'}):\n  "
          + "\n  ".join(f"{c['name']:32} {c['type']}"
                        f"{' NOT NULL' if c['notnull'] else ''}"
                        f"{'  PK' if c['pk'] else ''}" for c in cols))
    return 0


def cmd_select(args) -> int:
    db = _db(args)
    try:
        rows = db.select(
            args.table, tenant_id=args.tenant, columns=args.columns or "*",
            where=args.where, params=args.param or [], order_by=args.order_by,
            limit=args.limit, allow_unscoped=args.allow_unscoped, reason=args.reason,
        )
    except UnscopedQueryError as exc:
        _emit(args, {"ok": False, "error": str(exc), "kind": "unscoped"}, f"REFUSED: {exc}")
        return 1
    _emit(args, {"ok": True, "count": len(rows), "rows": rows},
          f"{len(rows)} rows\n" + "\n".join(json.dumps(r, default=str) for r in rows))
    return 0


# The `sql` verb advertises itself as read-only, so it has to actually be
# read-only — a documented safety property that isn't enforced is worse than no
# property, because callers rely on it. Same posture as supabase_tool.py, which
# blocks destructive keywords unless --dangerous-raw-query is passed.
_WRITE_SQL = re.compile(
    r"^\s*(insert|update|delete|drop|truncate|alter|create|replace|grant|revoke|vacuum|attach|detach|pragma)\b",
    re.IGNORECASE,
)


def cmd_sql(args) -> int:
    if _WRITE_SQL.match(args.query) and not args.dangerous_write:
        _emit(args,
              {"ok": False, "kind": "write_blocked",
               "error": "the sql verb is read-only; pass --dangerous-write to override"},
              "REFUSED: the `sql` verb is read-only. Re-run with --dangerous-write "
              "if you really mean to mutate data.")
        return 1
    db = _db(args)
    try:
        rows = db.query(args.query, args.param or [],
                        allow_unscoped=args.allow_unscoped, reason=args.reason)
    except UnscopedQueryError as exc:
        _emit(args, {"ok": False, "error": str(exc), "kind": "unscoped"}, f"REFUSED: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        _emit(args, {"ok": False, "error": str(exc)}, f"ERROR: {exc}")
        return 1
    _emit(args, {"ok": True, "count": len(rows), "rows": rows},
          f"{len(rows)} rows\n" + "\n".join(json.dumps(r, default=str) for r in rows))
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Global flags live on a parent parser so they are accepted both before and
    # after the subcommand — `turso_tool.py status --json` and
    # `turso_tool.py --json status` both work. argparse only honours top-level
    # options before the subcommand, and that trips people up every time.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--db-path", help="local libSQL file instead of the configured target")
    common.add_argument("--allow-unscoped", action="store_true",
                        help="permit a query with no tenant filter (logged; requires --reason)")
    common.add_argument("--reason", help="why the unscoped query is legitimate")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common], help="connection + schema summary")
    sub.add_parser("tables", parents=[common], help="list tables, flagging tenant-scoped ones")

    p_schema = sub.add_parser("schema", parents=[common], help="column list for one table")
    p_schema.add_argument("table")

    p_sel = sub.add_parser("select", parents=[common], help="scoped read from one table")
    p_sel.add_argument("table")
    p_sel.add_argument("--tenant", help="tenant_id — required for tenant-scoped tables")
    p_sel.add_argument("--columns")
    p_sel.add_argument("--where", help="SQL predicate with ? placeholders")
    p_sel.add_argument("--param", action="append", help="value for a ? placeholder (repeatable)")
    p_sel.add_argument("--order-by")
    p_sel.add_argument("--limit", type=int, default=50)

    p_sql = sub.add_parser("sql", parents=[common], help="raw read-only SQL (guard still applies)")
    p_sql.add_argument("query")
    p_sql.add_argument("--dangerous-write", action="store_true",
                       help="permit a mutating statement (default: reads only)")
    p_sql.add_argument("--param", action="append")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    if args.allow_unscoped and not args.reason:
        print("ERROR: --allow-unscoped requires --reason (it is written to the audit log)",
              file=sys.stderr)
        return 2
    handlers = {"status": cmd_status, "tables": cmd_tables, "schema": cmd_schema,
                "select": cmd_select, "sql": cmd_sql}
    try:
        return handlers[args.command](args)
    except TursoConfigError as exc:
        print(f"NOT CONFIGURED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
