"""Preserve Supabase auth.users + auth.identities into each Turso database.

WHY. The public-table ETL never touches the `auth` schema, but that schema holds
the only copy of every user identity created in 8 months: 82 accounts across the
five projects, including bcrypt password hashes and OAuth provider links.
Cancelling Supabase without this export destroys every login. With it, Better
Auth can be seeded later (it verifies bcrypt via a custom hasher, so users keep
their passwords), and no identity data has a single point of failure meanwhile.

WHAT IT WRITES. Two tables per Turso database, deliberately underscore-prefixed
so no app ORM picks them up as domain tables:

  _supabase_auth_users       full auth.users rows (id, email, encrypted_password,
                             confirmed/created/updated timestamps, raw_user_meta_data, ...)
  _supabase_auth_identities  provider links (google/email) with provider ids

Hashes are bcrypt — already one-way; they are copied verbatim, never printed.
Reads go through the Supabase Management API (org token), so stale/absent
per-project service keys don't matter.

CLI:
  python scripts/etl_auth_to_turso.py --project bravo
  python scripts/etl_auth_to_turso.py --all
  python scripts/etl_auth_to_turso.py --all --verify   # copy, then count-compare
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from core.turso_schema_transpiler import PROJECTS as REFS, _mgmt_query  # noqa: E402
from lib.db_turso import TursoDB, resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("etl_auth_to_turso")

USERS_COLS = [
    "id", "email", "phone", "encrypted_password", "email_confirmed_at",
    "phone_confirmed_at", "invited_at", "confirmation_sent_at", "recovery_sent_at",
    "last_sign_in_at", "raw_app_meta_data", "raw_user_meta_data", "is_super_admin",
    "created_at", "updated_at", "banned_until", "deleted_at", "is_anonymous",
]
IDENT_COLS = [
    "id", "user_id", "provider", "provider_id", "identity_data",
    "last_sign_in_at", "created_at", "updated_at",
]

USERS_DDL = (
    'CREATE TABLE IF NOT EXISTS "_supabase_auth_users" ('
    + ", ".join(f'"{c}" TEXT' for c in USERS_COLS)
    + ', PRIMARY KEY ("id"))'
)
IDENT_DDL = (
    'CREATE TABLE IF NOT EXISTS "_supabase_auth_identities" ('
    + ", ".join(f'"{c}" TEXT' for c in IDENT_COLS)
    + ', PRIMARY KEY ("provider", "provider_id"))'
)


def to_text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"))
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def copy_project(project: str, token: str, verify: bool) -> dict:
    ref = REFS[project]["ref"]
    users = _mgmt_query(ref, f"select {', '.join(USERS_COLS)} from auth.users", token)
    idents = _mgmt_query(ref, f"select {', '.join(IDENT_COLS)} from auth.identities", token)

    url, tok, mode = resolve_project_target(project)
    db = TursoDB(url, tok, mode)
    db.execute(USERS_DDL, allow_unscoped=True, reason="auth preservation DDL")
    db.execute(IDENT_DDL, allow_unscoped=True, reason="auth preservation DDL")

    for table, cols, rows in (("_supabase_auth_users", USERS_COLS, users),
                              ("_supabase_auth_identities", IDENT_COLS, idents)):
        if not rows:
            continue
        col_sql = ", ".join(f'"{c}"' for c in cols)
        one = "(" + ", ".join("?" for _ in cols) + ")"
        sql = (f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES '
               + ", ".join(one for _ in rows))
        args = [to_text(r.get(c)) for r in rows for c in cols]
        db.execute(sql, args, allow_unscoped=True,
                   reason="auth preservation — identity data has no tenant column")
    db.commit()

    result = {"project": project, "users": len(users), "identities": len(idents)}
    if verify:
        got_u = db.query('SELECT count(*) AS n FROM "_supabase_auth_users"',
                         allow_unscoped=True, reason="auth verify")[0]["n"]
        got_i = db.query('SELECT count(*) AS n FROM "_supabase_auth_identities"',
                         allow_unscoped=True, reason="auth verify")[0]["n"]
        result["verified"] = (got_u == len(users) and got_i == len(idents))
        result["turso_users"], result["turso_identities"] = got_u, got_i
    log.info("auth preserved", **result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=sorted(REFS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.project and not args.all:
        ap.error("give --project or --all")

    token = load_env().get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("ERROR: SUPABASE_ACCESS_TOKEN absent", file=sys.stderr)
        return 2

    projects = sorted(REFS) if args.all else [args.project]
    results = []
    failed = False
    for p in projects:
        try:
            results.append(copy_project(p, token, args.verify))
        except Exception as exc:  # noqa: BLE001 - report and continue, never silent
            failed = True
            results.append({"project": p, "error": str(exc)[:300]})
            log.error("auth preservation failed", project=p, error=str(exc))

    if args.json:
        print(json.dumps({"ok": not failed, "results": results}, indent=2))
    else:
        for r in results:
            if "error" in r:
                print(f"  FAIL {r['project']}: {r['error']}")
            else:
                extra = "" if "verified" not in r else \
                    f"  verified={'PASS' if r['verified'] else 'FAIL'}"
                print(f"  {r['project']}: {r['users']} users, {r['identities']} identities{extra}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
