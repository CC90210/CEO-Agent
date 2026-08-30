#!/usr/bin/env python3
"""Restore the ON DELETE / ON UPDATE actions the transpiler dropped.

WHY THIS EXISTS
    The first transpiler emitted every foreign key as a bare
    `FOREIGN KEY (x) REFERENCES parent (id)`, discarding Postgres's referential
    action. SQLite treats a missing action as NO ACTION and *does* enforce it,
    so a DELETE that used to cascade now fails with "FOREIGN KEY constraint
    failed" instead. 384 constraints across 192 tables in all five databases
    were affected.

    Row-count parity could never have caught this — the schemas match, the data
    matches, and the break only appears when something is deleted.

APPROACH
    Patch each table's OWN stored DDL rather than regenerating it from the
    transpiler. That guarantees the rebuilt table has byte-identical column
    order, so `INSERT INTO new SELECT * FROM old` cannot silently transpose
    columns — the failure mode that would be both catastrophic and invisible.

    Turso rejects `PRAGMA writable_schema`, so the schema change needs SQLite's
    12-step rebuild: create, copy, drop, rename, restore indexes and triggers.

TWO TRAPS THIS ENCODES (both hit during development)
    1. On Turso, `PRAGMA foreign_keys` persists PER DATABASE, not per
       connection. A rebuild that turns it off and exits leaves the whole
       database unprotected. Every apply re-enables it and re-checks from a
       FRESH connection, because the setting is invisible from the one that
       changed it.
    2. `ALTER TABLE ... RENAME` reparses the WHOLE schema, and any trigger or
       view that references a momentarily-absent table aborts it. On breeze
       that failed 27 renames in a row, each leaving its table dropped and its
       rows stranded in <table>__fkfix. So the rename is gone: the table is
       recreated under its own name and the rows copied back. CREATE TABLE and
       DROP TABLE do not reparse, so no trigger can veto the rebuild.

USAGE
    python scripts/repair_turso_fk_actions.py --project nostalgic
    python scripts/repair_turso_fk_actions.py --project nostalgic --rehearse
    python scripts/repair_turso_fk_actions.py --project nostalgic --apply
    python scripts/repair_turso_fk_actions.py --all --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import libsql  # noqa: E402
import requests  # noqa: E402

from lib.db_turso import resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

MGMT_API = "https://api.supabase.com"
PROJECTS = {
    "nostalgic": "jqybbrtzpvmefgzzdagz",
    "oasis": "skgrbweyscysyetubemg",
    "propflow": "xusnasmzoxkaimyjqbie",
    "breeze": "xugwrhvaoihyidtdgwkq",
    "bravo": "phctllmtsogkovoilwos",
}
# Smallest first: prove the procedure on 2 tables before touching 94.
ORDER = ["nostalgic", "oasis", "propflow", "breeze", "bravo"]

BACKUP_ROOT = REPO / "state" / "fk_repair_backup"
PAGE = 500

ACTION = {"a": "", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}

FK_SQL = """
select con.conname as constraint_name,
       cl.relname  as table_name,
       fcl.relname as foreign_table,
       (select string_agg(att.attname, ',' order by u.ord)
          from unnest(con.conkey) with ordinality u(attnum, ord)
          join pg_attribute att
            on att.attrelid = con.conrelid and att.attnum = u.attnum) as columns,
       (select string_agg(att.attname, ',' order by u.ord)
          from unnest(con.confkey) with ordinality u(attnum, ord)
          join pg_attribute att
            on att.attrelid = con.confrelid and att.attnum = u.attnum) as foreign_columns,
       con.confdeltype as del_action,
       con.confupdtype as upd_action
from pg_constraint con
join pg_class cl on cl.oid = con.conrelid
join pg_namespace ns on ns.oid = cl.relnamespace
join pg_class fcl on fcl.oid = con.confrelid
join pg_namespace fns on fns.oid = fcl.relnamespace
where con.contype = 'f' and ns.nspname = 'public' and fns.nspname = 'public'
"""

# One `FOREIGN KEY (...) REFERENCES "tbl" (...)` clause, plus any actions that
# already follow it. Non-greedy so consecutive clauses do not merge.
FK_CLAUSE = re.compile(
    r'FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s*("?[A-Za-z_][\w]*"?)\s*\(([^)]*)\)'
    r'((?:\s+ON\s+(?:DELETE|UPDATE)\s+(?:NO\s+ACTION|RESTRICT|CASCADE|SET\s+NULL|SET\s+DEFAULT))*)',
    re.I)


def _cols(raw: str) -> tuple[str, ...]:
    return tuple(c.strip().strip('"').lower() for c in raw.split(",") if c.strip())


def _pg_fks(ref: str, token: str) -> list[dict]:
    r = requests.post(
        f"{MGMT_API}/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": FK_SQL}, timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Management API {r.status_code}: {r.text[:300]}")
    body = r.json()
    return body["result"] if isinstance(body, dict) and "result" in body else body


def plan_table(ddl: str, wanted: list[dict]) -> tuple[str | None, list[str]]:
    """Return (patched DDL or None if nothing to change, human-readable notes).

    Matches a Postgres FK to a SQLite clause on (child columns, parent table,
    parent columns) — the constraint NAME is not carried into SQLite, so it
    cannot be the key.
    """
    notes: list[str] = []
    index: dict[tuple, dict] = {}
    for fk in wanted:
        key = (_cols(fk["columns"] or ""), (fk["foreign_table"] or "").lower(),
               _cols(fk["foreign_columns"] or ""))
        index[key] = fk

    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        key = (_cols(m.group(1)), m.group(2).strip('"').lower(), _cols(m.group(3)))
        fk = index.get(key)
        if not fk:
            return m.group(0)
        existing = (m.group(4) or "").strip()
        dele = ACTION.get(fk.get("del_action", "a"), "")
        upd = ACTION.get(fk.get("upd_action", "a"), "")
        if not dele and not upd:
            return m.group(0)
        # Never stack a second action onto a clause that already has one.
        actions = ""
        if dele and not re.search(r"ON\s+DELETE", existing, re.I):
            actions += f" ON DELETE {dele}"
        if upd and not re.search(r"ON\s+UPDATE", existing, re.I):
            actions += f" ON UPDATE {upd}"
        if not actions:
            return m.group(0)
        changed = True
        notes.append(
            f"{'.'.join(key[0])} -> {key[1]}({','.join(key[2])}):{actions}")
        return (f'FOREIGN KEY ({m.group(1)}) REFERENCES {m.group(2)} '
                f'({m.group(3)}){existing}{actions}')

    patched = FK_CLAUSE.sub(repl, ddl)
    return (patched if changed else None), notes


def _rename_in_ddl(ddl: str, old: str, new: str) -> str:
    """Rewrite only the table name in `CREATE TABLE <name> (`.

    A blind string replace would also hit the name where it appears inside a
    CHECK expression or a self-referencing FK.
    """
    pat = re.compile(r'(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)("?)' +
                     re.escape(old) + r'\2(\s*\()', re.I)
    out, n = pat.subn(lambda m: f'{m.group(1)}"{new}"{m.group(3)}', ddl, count=1)
    if n != 1:
        raise RuntimeError(f"could not rewrite CREATE TABLE name for {old!r}")
    return out


def _real_columns(conn, table: str) -> list[str]:
    """Columns that can actually be written to.

    PRAGMA table_info omits GENERATED columns while `SELECT *` returns them, so
    the two disagree on width — breeze.draws has a STORED
    `net_deposit_cents` and that mismatch is what made
    `INSERT INTO new SELECT * FROM old` supply 22 values to 21 columns.
    Enumerating columns also removes the reliance on positional ordering.
    """
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _backup(conn, table: str, dest: Path) -> int:
    """Page the table to JSON so there is a restore point off Turso entirely."""
    cols = _real_columns(conn, table)
    sel = ", ".join(f'"{c}"' for c in cols)
    rows, off = [], 0
    while True:
        page = conn.execute(
            f'SELECT {sel} FROM "{table}" LIMIT {PAGE} OFFSET {off}').fetchall()
        if not page:
            break
        rows.extend([list(r) for r in page])
        off += PAGE
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"table": table, "columns": cols, "rows": rows},
                               default=str), encoding="utf-8")
    return len(rows)


def repair_table(conn, table: str, patched_ddl: str, backup_dir: Path,
                 dry: bool) -> dict:
    """12-step rebuild of one table. Returns a result record."""
    tmp = f"{table}__fkfix"
    before = conn.execute(f'SELECT count(*) FROM "{table}"').fetchall()[0][0]

    idx = [r[0] for r in conn.execute(
        "select sql from sqlite_master where type='index' and tbl_name=? "
        "and sql is not null", (table,)).fetchall()]
    # DROP TABLE takes the table's own triggers with it, so they are captured
    # and reinstated. Triggers on OTHER tables are untouched and stay live
    # throughout — that is the point of not renaming.
    trg = [r[0] for r in conn.execute(
        "select sql from sqlite_master where type='trigger' and tbl_name=? "
        "and sql is not null", (table,)).fetchall()]
    # Views over this table are reported for visibility only. They survive
    # untouched: without a rename nothing reparses the schema, so a view is
    # merely unqueryable for the moment the table is absent, never invalidated.
    views = [r[0] for r in conn.execute(
        "select name, sql from sqlite_master where type='view' and sql is not null"
    ).fetchall() if re.search(rf'\b"?{re.escape(table)}"?\b', r[1] or "")]

    if dry:
        return {"table": table, "rows": before, "indexes": len(idx),
                "triggers": len(trg), "views": len(views), "applied": False}

    backed = _backup(conn, table, backup_dir / f"{table}.json")
    if backed != before:
        raise RuntimeError(f"{table}: backup wrote {backed} of {before} rows")

    collist = ", ".join(f'"{c}"' for c in _real_columns(conn, table))

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{tmp}"')
        conn.execute(_rename_in_ddl(patched_ddl, table, tmp))
        conn.execute(f'INSERT INTO "{tmp}" ({collist}) '
                     f'SELECT {collist} FROM "{table}"')
        moved = conn.execute(f'SELECT count(*) FROM "{tmp}"').fetchall()[0][0]
        if moved != before:
            raise RuntimeError(f"{table}: copied {moved} of {before} rows — aborted")

        # Recreate under the real name and copy back, rather than renaming the
        # temp into place. ALTER TABLE RENAME would reparse every trigger and
        # view in the database and abort if any referenced a table that is
        # absent at that instant — which is exactly how 27 breeze tables ended
        # up dropped with their rows stranded.
        conn.execute(f'DROP TABLE "{table}"')
        conn.execute(patched_ddl)
        conn.execute(f'INSERT INTO "{table}" ({collist}) '
                     f'SELECT {collist} FROM "{tmp}"')
        restored = conn.execute(f'SELECT count(*) FROM "{table}"').fetchall()[0][0]
        if restored != before:
            raise RuntimeError(
                f"{table}: restored {restored} of {before} rows — "
                f'source rows are still in "{tmp}"')
        for stmt in idx + trg:
            conn.execute(stmt)
        conn.execute(f'DROP TABLE "{tmp}"')
        conn.commit()
    except Exception:
        # Drop the temp copy ONLY when the real table is provably whole. Once
        # the original has been dropped — or recreated but not yet refilled —
        # `tmp` holds the sole copy of the rows, and deleting it is the single
        # unrecoverable move available in this function.
        safe_to_drop_tmp = False
        try:
            exists = conn.execute(
                "select count(*) from sqlite_master where type='table' and name=?",
                (table,)).fetchall()[0][0]
            if exists:
                live = conn.execute(
                    f'SELECT count(*) FROM "{table}"').fetchall()[0][0]
                safe_to_drop_tmp = live == before
        except Exception:
            safe_to_drop_tmp = False

        if safe_to_drop_tmp:
            try:
                conn.execute(f'DROP TABLE IF EXISTS "{tmp}"')
                conn.commit()
            except Exception:
                pass
        else:
            print(f"    !! {table}: failed AFTER the original was dropped. The "
                  f"rows are in \"{tmp}\"; a JSON copy is at "
                  f"{backup_dir / (table + '.json')}. Do not re-run until "
                  f"resolved.", file=sys.stderr)
        raise
    finally:
        # Per-database setting on Turso — leaving it off would disable
        # enforcement for every client, not just this script.
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()

    after = conn.execute(f'SELECT count(*) FROM "{table}"').fetchall()[0][0]
    if after != before:
        raise RuntimeError(f"{table}: {before} rows before, {after} after")
    return {"table": table, "rows": before, "indexes": len(idx),
            "triggers": len(trg), "views": len(views), "applied": True}


def run_project(proj: str, token: str, dry: bool, verbose: bool) -> dict:
    ref = PROJECTS[proj]
    url, tok, _ = resolve_project_target(proj)
    conn = libsql.connect(database=url, auth_token=tok)

    wanted_by_table: dict[str, list[dict]] = {}
    for fk in _pg_fks(ref, token):
        if fk.get("del_action", "a") == "a" and fk.get("upd_action", "a") == "a":
            continue
        wanted_by_table.setdefault(fk["table_name"], []).append(fk)

    ddls = {r[0]: r[1] for r in conn.execute(
        "select name, sql from sqlite_master where type='table' and sql is not null"
    ).fetchall()}

    todo: list[tuple[str, str, list[str]]] = []
    missing: list[str] = []
    for table, fks in sorted(wanted_by_table.items()):
        ddl = ddls.get(table)
        if ddl is None:
            missing.append(table)
            continue
        patched, notes = plan_table(ddl, fks)
        if patched:
            todo.append((table, patched, notes))

    print(f"\n=== {proj}: {len(wanted_by_table)} table(s) want actions, "
          f"{len(todo)} need repair"
          f"{f', {len(missing)} absent from Turso' if missing else ''}")
    if missing and verbose:
        print(f"    absent: {', '.join(sorted(missing)[:10])}")

    results, failures = [], []
    backup_dir = BACKUP_ROOT / proj
    for table, patched, notes in todo:
        try:
            r = repair_table(conn, table, patched, backup_dir, dry)
            results.append(r)
            flag = "would fix" if dry else "REPAIRED"
            print(f"    {flag:<9} {table:<34} rows={r['rows']:<7} "
                  f"idx={r['indexes']} trg={r['triggers']} views={r['views']}")
            if verbose:
                for n in notes:
                    print(f"                  + {n}")
        except Exception as e:
            failures.append((table, str(e)))
            print(f"    FAILED    {table:<34} {str(e)[:110]}")

    if not dry:
        # Verify from a connection that did not run the pragma — the only way
        # to see what other clients will see.
        fresh = libsql.connect(database=url, auth_token=tok)
        fk_on = fresh.execute("PRAGMA foreign_keys").fetchall()[0][0]
        violations = fresh.execute("PRAGMA foreign_key_check").fetchall()
        still = 0
        for table, _p, _n in todo:
            ddl = fresh.execute(
                "select sql from sqlite_master where type='table' and name=?",
                (table,)).fetchall()
            if ddl and not re.search(r"ON\s+DELETE", ddl[0][0], re.I):
                still += 1
        print(f"    foreign_keys={fk_on} (fresh conn) · "
              f"foreign_key_check violations={len(violations)} · "
              f"tables still missing ON DELETE={still}")
        if fk_on != 1:
            failures.append(("<database>", "foreign_keys left OFF"))
        if violations:
            failures.append(("<database>", f"{len(violations)} FK violations"))

    return {"project": proj, "planned": len(todo), "ok": len(results),
            "failed": failures}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", choices=sorted(PROJECTS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="actually rebuild (default is a dry run)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if not args.project and not args.all:
        ap.error("give --project NAME or --all")

    token = load_env().get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("ERROR: SUPABASE_ACCESS_TOKEN absent from agents env", file=sys.stderr)
        return 2

    targets = ORDER if args.all else [args.project]
    dry = not args.apply
    print("DRY RUN — nothing will be written" if dry
          else f"APPLYING — backups under {BACKUP_ROOT}")

    summary = []
    for proj in targets:
        try:
            summary.append(run_project(proj, token, dry, args.verbose))
        except Exception as e:
            print(f"\n=== {proj}: ERROR {e}")
            summary.append({"project": proj, "planned": 0, "ok": 0,
                            "failed": [("<project>", str(e))]})

    print("\n" + "=" * 62)
    bad = 0
    for s in summary:
        n_fail = len(s["failed"])
        bad += n_fail
        print(f"  {s['project']:<11} planned={s['planned']:<4} "
              f"{'ok' if not dry else 'would fix'}={s['ok']:<4} failed={n_fail}")
        for t, e in s["failed"]:
            print(f"      {t}: {e[:120]}")
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
