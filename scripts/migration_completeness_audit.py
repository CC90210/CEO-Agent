"""THE answer to "is every single piece of data migrated off Supabase?"

One command, one verdict table. For each of the five projects it compares
Supabase (source of truth) against Turso + the local storage archive across
every category of data that exists:

  tables    every public base table present in Turso, row counts equal
  auth      auth.users / auth.identities counts equal _supabase_auth_* in Turso
  storage   storage.objects count+bytes equal the local archive manifest
            (bytes live on disk under state/backups/supabase_storage/ —
             Turso holds the manifest, not the blobs)

Sources read via the Supabase Management API (org token — immune to stale
per-project keys). Anything that cannot be verified is FAIL, never a shrug.

Exit 0 only when EVERY project passes EVERY category. This is the gate for
"we can cancel Supabase" — run it, read the verdict, no vibes.

  python scripts/migration_completeness_audit.py
  python scripts/migration_completeness_audit.py --project bravo --json
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

ARCHIVE_ROOT = PROJECT_ROOT / "state" / "backups" / "supabase_storage"


def audit_tables(ref: str, token: str, db: TursoDB) -> dict:
    src = _mgmt_query(ref, (
        "select c.relname as t, c.reltuples::bigint as est "
        "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relkind='r'"
    ), token)
    # reltuples is an estimate; get exact counts (fine at this scale)
    exact: dict[str, int] = {}
    for row in src:
        t = row["t"]
        exact[t] = int(_mgmt_query(ref, f'select count(*) as n from "{t}"', token)[0]["n"])

    tgt_tables = {r["name"] for r in db.query(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'",
        allow_unscoped=True, reason="audit")}
    missing_tables = sorted(set(exact) - tgt_tables)
    mismatched: list[dict] = []
    equal = 0
    for t, n in sorted(exact.items()):
        if t not in tgt_tables:
            continue
        got = db.query(f'SELECT count(*) AS n FROM "{t}"', allow_unscoped=True,
                       reason="audit")[0]["n"]
        if got == n:
            equal += 1
        else:
            mismatched.append({"table": t, "supabase": n, "turso": got})
    return {
        "source_tables": len(exact),
        "count_equal": equal,
        "missing_in_turso": missing_tables,
        "count_mismatched": mismatched,
        "ok": not missing_tables and not mismatched,
    }


def audit_auth(ref: str, token: str, db: TursoDB) -> dict:
    src_u = int(_mgmt_query(ref, "select count(*) as n from auth.users", token)[0]["n"])
    src_i = int(_mgmt_query(ref, "select count(*) as n from auth.identities", token)[0]["n"])

    def turso_count(table: str) -> int:
        try:
            return db.query(f'SELECT count(*) AS n FROM "{table}"',
                            allow_unscoped=True, reason="audit")[0]["n"]
        except Exception:  # noqa: BLE001 - table absent = 0 preserved
            return -1

    tgt_u = turso_count("_supabase_auth_users")
    tgt_i = turso_count("_supabase_auth_identities")
    return {"supabase_users": src_u, "turso_users": tgt_u,
            "supabase_identities": src_i, "turso_identities": tgt_i,
            "ok": src_u == tgt_u and src_i == tgt_i}


def audit_storage(project: str, ref: str, token: str) -> dict:
    rows = _mgmt_query(ref, (
        "select count(*) as n, coalesce(sum((metadata->>'size')::bigint),0) as bytes "
        "from storage.objects where metadata is not null"
    ), token)[0]
    src_n, src_bytes = int(rows["n"]), int(rows["bytes"])
    manifest = ARCHIVE_ROOT / f"{project}__manifest.jsonl"
    arch_n = arch_bytes = 0
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                arch_n += 1
                arch_bytes += int(e.get("size", 0))
    return {"supabase_objects": src_n, "supabase_bytes": src_bytes,
            "archived_objects": arch_n, "archived_bytes": arch_bytes,
            "ok": src_n == arch_n and src_bytes == arch_bytes}


def audit_project(project: str, token: str) -> dict:
    ref = REFS[project]["ref"]
    out: dict = {"project": project, "ref": ref}
    try:
        url, tok, mode = resolve_project_target(project)
        db = TursoDB(url, tok, mode)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"no Turso target: {str(exc)[:160]}"
        out["ok"] = False
        return out
    try:
        out["tables"] = audit_tables(ref, token, db)
        out["auth"] = audit_auth(ref, token, db)
        out["storage"] = audit_storage(project, ref, token)
        out["ok"] = out["tables"]["ok"] and out["auth"]["ok"] and out["storage"]["ok"]
    except Exception as exc:  # noqa: BLE001 - an unverifiable project FAILS
        out["error"] = str(exc)[:300]
        out["ok"] = False
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=sorted(REFS))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    token = load_env().get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("ERROR: SUPABASE_ACCESS_TOKEN absent", file=sys.stderr)
        return 2

    projects = [args.project] if args.project else sorted(REFS)
    results = [audit_project(p, token) for p in projects]
    all_ok = all(r["ok"] for r in results)

    if args.json:
        print(json.dumps({"cancel_safe_data": all_ok, "results": results}, indent=2))
        return 0 if all_ok else 1

    print(f"{'project':12} {'tables':>14} {'auth':>12} {'storage':>20} verdict")
    for r in results:
        if "error" in r and "tables" not in r:
            print(f"{r['project']:12} {'—':>14} {'—':>12} {'—':>20} FAIL ({r['error'][:60]})")
            continue
        t, a, s = r["tables"], r["auth"], r["storage"]
        t_s = f"{t['count_equal']}/{t['source_tables']}"
        a_s = f"{a['turso_users']}/{a['supabase_users']}u"
        s_s = f"{s['archived_objects']}/{s['supabase_objects']} obj"
        print(f"{r['project']:12} {t_s:>14} {a_s:>12} {s_s:>20} "
              f"{'PASS' if r['ok'] else 'FAIL'}")
        for m in t["count_mismatched"][:5]:
            print(f"{'':12}   mismatch {m['table']}: supabase={m['supabase']} turso={m['turso']}")
        if t["missing_in_turso"]:
            print(f"{'':12}   missing tables: {t['missing_in_turso'][:6]}")
    print(f"\nDATA VERDICT: {'ALL DATA ACCOUNTED FOR' if all_ok else 'NOT COMPLETE — do not cancel'}")
    print("(Data parity is necessary but NOT sufficient to cancel — auth/rpc/app cutover "
          "must also be live. See the cancel checklist in the migration notes.)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
