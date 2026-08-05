"""Apply transpiled libSQL DDL to a Turso database (or a local libSQL file).

Counterpart to apply_migration.py, which drives Supabase via the Management
API. This one drives libSQL directly through the `libsql` client, so it works
identically against Turso Cloud (libsql:// + auth token) and a local file —
which is what makes the whole migration testable before any cloud account
exists.

Like apply_migration.py it keeps a ledger (`schema_migrations`) so re-running is
idempotent, and it refuses destructive statements client-side.

CLI:
  python scripts/apply_turso_migration.py --test-mode
      Apply every database/turso_migrations/*.sql to a throwaway local file and
      report per-statement results. Touches no cloud resource. This is the gate
      to run before Phase 0 credentials exist.

  python scripts/apply_turso_migration.py database/turso_migrations/bravo__000_master_schema.sql
      Apply one file to the configured Turso target (TURSO_DATABASE_URL).

  python scripts/apply_turso_migration.py <file> --dry-run
  python scripts/apply_turso_migration.py <file> --db-path ./local.db
  python scripts/apply_turso_migration.py --test-mode --json

Safety: statements matching DROP TABLE / DROP DATABASE / DELETE-without-WHERE /
TRUNCATE are blocked before execution. As apply_migration.py says of its own
guard, this is a client-side check, not a substitute for a backup — take a
restore point with scripts/db_snapshot.py first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.structured_log import get_logger  # noqa: E402

log = get_logger("apply_turso_migration")

MIGRATIONS_DIR = PROJECT_ROOT / "database" / "turso_migrations"
LEDGER_TABLE = "schema_migrations"

BLOCKED_PATTERNS = [
    (re.compile(r"\bDROP\s+TABLE\b", re.I), "DROP TABLE"),
    (re.compile(r"\bDROP\s+DATABASE\b", re.I), "DROP DATABASE"),
    (re.compile(r"\bTRUNCATE\b", re.I), "TRUNCATE"),
    (re.compile(r"\bDELETE\s+FROM\s+\S+\s*(;|$)", re.I), "DELETE without WHERE"),
    (re.compile(r"\bDROP\s+COLUMN\b", re.I), "DROP COLUMN"),
]

_LINE_COMMENT = re.compile(r"--[^\n]*")


def split_statements(sql: str) -> list[str]:
    """Split on statement terminators, dropping comment-only chunks."""
    out: list[str] = []
    for chunk in sql.split(";\n"):
        body = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            out.append(body)
    return out


def check_blocked(statements: list[str]) -> list[str]:
    problems: list[str] = []
    for stmt in statements:
        bare = _LINE_COMMENT.sub(" ", stmt)
        for rx, label in BLOCKED_PATTERNS:
            if rx.search(bare):
                problems.append(f"{label}: {stmt.splitlines()[0][:90]}")
    return problems


def connect(db_path: str | None, project: str | None = None):
    import libsql  # noqa: PLC0415

    if db_path:
        return libsql.connect(db_path), f"local({db_path})"

    from lib.db_turso import resolve_project_target, resolve_target  # noqa: PLC0415

    if project:
        url, token, mode = resolve_project_target(project)
        return libsql.connect(database=url, auth_token=token), mode
    url, token, mode = resolve_target()
    if token:
        return libsql.connect(database=url, auth_token=token), mode
    return libsql.connect(url), mode


def ensure_ledger(conn) -> None:
    conn.execute(
        f'CREATE TABLE IF NOT EXISTS "{LEDGER_TABLE}" ('
        '"filename" TEXT PRIMARY KEY, "checksum" TEXT NOT NULL, '
        '"applied_at" TEXT NOT NULL, "statements" INTEGER NOT NULL)'
    )
    conn.commit()


def already_applied(conn, filename: str, checksum: str) -> bool:
    rows = conn.execute(
        f'SELECT checksum FROM "{LEDGER_TABLE}" WHERE filename = ?', (filename,)
    ).fetchall()
    if not rows:
        return False
    if rows[0][0] != checksum:
        raise RuntimeError(
            f"{filename} was already applied with a DIFFERENT checksum "
            f"(ledger={rows[0][0][:12]}, file={checksum[:12]}). The migration file "
            f"changed after being applied — resolve by hand, do not re-run blindly."
        )
    return True


def apply_file(conn, path: Path, *, dry_run: bool) -> dict:
    sql = path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    statements = split_statements(sql)

    blocked = check_blocked(statements)
    if blocked:
        raise RuntimeError(
            f"{path.name} contains destructive statements — refusing to apply:\n  "
            + "\n  ".join(blocked)
        )

    if dry_run:
        return {"file": path.name, "statements": len(statements), "applied": 0,
                "skipped": True, "reason": "dry-run"}

    if already_applied(conn, path.name, checksum):
        return {"file": path.name, "statements": len(statements), "applied": 0,
                "skipped": True, "reason": "already in ledger"}

    ok = 0
    failures: list[dict] = []
    for stmt in statements:
        try:
            conn.execute(stmt)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - record every failure, never swallow
            failures.append({"statement": stmt.splitlines()[0][:120], "error": str(exc)[:300]})
            log.error("statement failed", file=path.name,
                      statement=stmt.splitlines()[0][:120], error=str(exc))
    conn.commit()

    if failures:
        raise RuntimeError(
            f"{path.name}: {len(failures)} of {len(statements)} statements failed. "
            f"Ledger NOT updated so the file can be re-run after a fix.\n"
            + "\n".join(f"  {f['statement']} -> {f['error']}" for f in failures[:10])
        )

    conn.execute(
        f'INSERT INTO "{LEDGER_TABLE}" (filename, checksum, applied_at, statements) '
        "VALUES (?, ?, ?, ?)",
        (path.name, checksum, datetime.now(timezone.utc).isoformat(timespec="seconds"), ok),
    )
    conn.commit()
    return {"file": path.name, "statements": len(statements), "applied": ok, "skipped": False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("migration", nargs="?", help="path to a .sql file under database/turso_migrations/")
    ap.add_argument("--test-mode", action="store_true",
                    help="apply ALL turso_migrations to a throwaway local libSQL file")
    ap.add_argument("--dry-run", action="store_true", help="parse and validate only")
    ap.add_argument("--db-path", help="apply to this local libSQL file instead of the configured target")
    ap.add_argument("--target-project",
                    help="apply to a named empire project's Turso database "
                         "(bravo/breeze/nostalgic/propflow/oasis) instead of the default")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.migration and not args.test_mode:
        ap.error("give a migration file, or --test-mode")

    if args.test_mode:
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            print(f"ERROR: no .sql files in {MIGRATIONS_DIR} — run turso_schema_transpiler.py first",
                  file=sys.stderr)
            return 2
        tmp = Path(tempfile.mkdtemp(prefix="turso_test_")) / "test.db"
        db_path = str(tmp)
    else:
        files = [Path(args.migration)]
        if not files[0].exists():
            print(f"ERROR: {files[0]} not found", file=sys.stderr)
            return 2
        db_path = args.db_path

    try:
        conn, mode = connect(db_path, getattr(args, "target_project", None))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot connect ({exc})", file=sys.stderr)
        return 2

    ensure_ledger(conn)

    results: list[dict] = []
    failed = False
    for f in files:
        try:
            results.append(apply_file(conn, f, dry_run=args.dry_run))
        except Exception as exc:  # noqa: BLE001 - report, mark failure, keep going
            failed = True
            results.append({"file": f.name, "error": str(exc)})

    tables = conn.execute(
        "select count(*) from sqlite_master where type='table' and name not like 'sqlite_%'"
    ).fetchall()[0][0]

    if args.json:
        print(json.dumps({"ok": not failed, "mode": mode, "tables": tables,
                          "results": results}, indent=2))
    else:
        print(f"target: {mode}")
        for r in results:
            if "error" in r:
                print(f"  FAIL {r['file']}: {r['error'][:400]}")
            elif r.get("skipped"):
                print(f"  skip {r['file']} ({r['reason']}) — {r['statements']} statements")
            else:
                print(f"  ok   {r['file']}: {r['applied']}/{r['statements']} statements")
        print(f"tables now present: {tables}")
        if args.test_mode:
            print(f"TEST-MODE: {'PASS' if not failed else 'FAIL'} (throwaway db at {db_path})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
