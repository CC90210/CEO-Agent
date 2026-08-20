"""Apply SQL migration files to the Bravo legacy Supabase project.

LEGACY PATH (post-2026-08 cutover): the primary backend is Turso — use
`scripts/apply_turso_migration.py` for empire DB DDL. This tool remains for
the legacy Supabase projects only.

Uses the Supabase Management API (https://api.supabase.com) with the
personal access token from .env.agents. This is the only supported path
for DDL against a Supabase project without the raw DB password — PostgREST
(what supabase_tool.py uses) does not expose DDL.

Usage:
  python scripts/apply_migration.py <path/to/migration.sql>
  python scripts/apply_migration.py <path/to/migration.sql> --project bravo
  python scripts/apply_migration.py <path/to/migration.sql> --dry-run
  python scripts/apply_migration.py <path/to/migration.sql> --json

Credentials required in .env.agents:
  SUPABASE_ACCESS_TOKEN      Management API personal access token
  BRAVO_SUPABASE_URL         Project URL (https://<ref>.supabase.co)

Safety:
  - DOES NOT execute SQL that parses as destructive table/schema removal,
    broad data mutation, privilege changes, or policy/RLS weakening.
    These are blocked at the client side after comments and strings are
    stripped.
  - Prints the full statement before sending. Use --dry-run to preview only.
  - On error, prints the Supabase API error body so the failure is debuggable.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# TLS setup. Without it the exec_sql RPC path dies with
# CERTIFICATE_VERIFY_FAILED on this fleet (observed applying migration 105 on
# 2026-07-29) and every migration silently downgrades to the Management API
# fallback. Same canonical helper the rest of the network tools use.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "database"
LEDGER_TABLE = "schema_migrations"

PROJECTS = {
    "bravo": {
        "url_key": "BRAVO_SUPABASE_URL",
        "description": "Bravo — agent intelligence + business ops",
    },
    "oasis": {
        "url_key": "OASIS_SUPABASE_URL",
        "description": "OASIS AI Platform",
    },
    "nostalgic": {
        "url_key": "NOSTALGIC_SUPABASE_URL",
        "description": "Nostalgic Requests",
    },
}

# Hard-blocked patterns — refuses to send even if the file contains them.
# This is a client-side guard, not a substitute for backups.
BLOCKED_PATTERNS = [
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+SCHEMA\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+[\w.\"`]+\s+SET\b", re.IGNORECASE),
    re.compile(r"\bGRANT\b", re.IGNORECASE),
    re.compile(r"\bREVOKE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+(ROLE|USER|DATABASE|SYSTEM)\b", re.IGNORECASE),
    re.compile(r"\b(DROP|ALTER)\s+POLICY\b", re.IGNORECASE),
    re.compile(r"\bDISABLE\s+ROW\s+LEVEL\s+SECURITY\b", re.IGNORECASE),
]

# RLS-touching patterns — not blocked, but warn loudly. RLS misconfiguration is
# a top-tier silent failure: the migration applies cleanly, but the resulting
# policy lets the wrong rows through (or none at all). The verification contract
# in brain/ORCHESTRATION.md says: "test query as anon user AND as authed user".
# This script can't run that test for you — but it can refuse to apply blindly.
RLS_TOUCHING_PATTERNS = [
    re.compile(r"\bCREATE\s+POLICY\b", re.IGNORECASE),
    re.compile(r"\bENABLE\s+ROW\s+LEVEL\s+SECURITY\b", re.IGNORECASE),
    re.compile(r"\bFORCE\s+ROW\s+LEVEL\s+SECURITY\b", re.IGNORECASE),
]


def check_rls_touching(sql: str) -> list[str]:
    """Return a list of RLS-touching pattern names found (ignoring comments)."""
    stripped = strip_sql_comments(sql)
    hits = []
    for pat in RLS_TOUCHING_PATTERNS:
        if pat.search(stripped):
            hits.append(pat.pattern)
    return hits


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    return env_vars


def extract_project_ref(supabase_url: str) -> str:
    """Extract the project ref (e.g., 'abcdefghijk') from a Supabase URL."""
    url = supabase_url.replace("https://", "").replace("http://", "")
    return url.split(".")[0]


def strip_sql_comments(sql: str) -> str:
    """Remove -- line comments, /* block */ comments, AND string literals so
    the guard cannot be defeated by hiding a DROP inside a comment or a
    string literal, but also cannot false-positive on an `exec_sql` function
    body that mentions 'DROP TABLE' only inside a RAISE EXCEPTION message."""
    # Strip block comments first
    sql_no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    # Strip line comments
    lines = [re.sub(r"--.*$", "", line) for line in sql_no_block.splitlines()]
    stripped = "\n".join(lines)
    # Strip $$-quoted function bodies (dollar-quoted strings in Postgres).
    # These are where PL/pgSQL function source lives, and we don't want
    # the guard scanning inside them. Destructive DDL inside a function
    # body only executes if that function is CALLED — the guard is about
    # the outer migration file, not arbitrary code a function might run.
    stripped = re.sub(r"\$\$.*?\$\$", "''", stripped, flags=re.DOTALL)
    stripped = re.sub(r"\$[a-zA-Z_]\w*\$.*?\$[a-zA-Z_]\w*\$", "''",
                      stripped, flags=re.DOTALL)
    # Strip single-quoted string literals (handles escaped '' inside)
    stripped = re.sub(r"'(?:[^']|'')*'", "''", stripped)
    return stripped


def check_blocked(sql: str) -> list[str]:
    """Return a list of blocked pattern names found in the SQL (ignoring comments)."""
    stripped = strip_sql_comments(sql)
    hits = []
    for pat in BLOCKED_PATTERNS:
        if pat.search(stripped):
            hits.append(pat.pattern)
    return hits


def run_query_via_rpc(
    env: dict[str, str],
    sql: str,
) -> tuple[bool, str]:
    """Execute SQL via the exec_sql() RPC (service-role path). Returns (ok, body).

    This path uses BRAVO_SUPABASE_SERVICE_ROLE_KEY which never expires — far
    more robust than the 30-day Management API PAT. Requires migration 004
    (exec_sql RPC) to have been applied once.
    """
    url = env.get("BRAVO_SUPABASE_URL", "")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return False, "RPC path requires BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY"
    try:
        from supabase import create_client
    except ImportError:
        return False, "supabase package not installed"
    try:
        client = create_client(url, key)
        res = client.rpc("exec_sql", {"sql_query": sql}).execute()
        return True, json.dumps(res.data, default=str)
    except Exception as exc:  # noqa: BLE001
        # Most common failure: exec_sql RPC doesn't exist yet (migration 004
        # not applied) or the server-side guard tripped. Caller will fall back.
        return False, f"RPC call failed: {exc}"


def run_query_via_management_api(
    _token: str,                  # unused — kept for backwards-compat callers
    project_ref: str,
    sql: str,
    _timeout: int = 60,           # unused — supabase_admin uses its own default
) -> tuple[bool, str]:
    """POST the SQL to the Management API via the shared supabase_admin client.

    The shared client (scripts/integrations/supabase_admin.py) bakes in the right
    Cloudflare-friendly User-Agent + auth headers + error handling. This
    function used to inline its own urllib call with those headers; that
    duplicate logic was extracted 2026-04-30 after a misdiagnosed
    Cloudflare 1010 incident. See memory/MISTAKES.md.
    """
    try:
        # supabase_admin moved to scripts/integrations/ in the 2026-05-20 reorg.
        # Re-add it to sys.path so the import resolves either before or after
        # the move without changing call-sites.
        import sys as _sys
        _integrations = str(Path(__file__).resolve().parent / "integrations")
        if _integrations not in _sys.path:
            _sys.path.insert(0, _integrations)
        from supabase_admin import api_post

        result = api_post(
            f"/v1/projects/{project_ref}/database/query",
            {"query": sql},
        )
        return True, json.dumps(result)
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"Unexpected error: {e}"


# ── Migration ledger (audit Phase 4, 2026-06-09) ─────────────────────────────
# A per-file applied ledger (public.schema_migrations) so no migration is ever
# blindly re-run. Read/write via the service-role PostgREST client (bypasses RLS).

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ledger_client(env: dict[str, str]):
    """Service-role Supabase client, or None if unavailable."""
    url = env.get("BRAVO_SUPABASE_URL", "")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:  # noqa: BLE001
        return None


def _ledger_fetch(env: dict[str, str]):
    """Return {filename: sha256} from the ledger, or None if unreachable / table
    not seeded yet (so callers can degrade gracefully offline)."""
    client = _ledger_client(env)
    if client is None:
        return None
    try:
        res = client.table(LEDGER_TABLE).select("filename,sha256").execute()
        return {r["filename"]: r.get("sha256", "") for r in (res.data or [])}
    except Exception:  # noqa: BLE001
        return None


def _ledger_upsert(env: dict[str, str], rows: list[dict]) -> tuple[bool, str]:
    client = _ledger_client(env)
    if client is None:
        return False, "no service-role client (BRAVO_SUPABASE_URL / SERVICE_ROLE_KEY missing)"
    try:
        client.table(LEDGER_TABLE).upsert(rows, on_conflict="filename").execute()
        return True, f"upserted {len(rows)} ledger row(s)"
    except Exception as exc:  # noqa: BLE001
        return False, f"ledger upsert failed: {exc}"


def _disk_migrations() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def cmd_status(env: dict[str, str], output_json: bool) -> int:
    files = _disk_migrations()
    ledger = _ledger_fetch(env)
    names = [p.name for p in files]
    if ledger is None:
        msg = {
            "status": "ledger_unreachable",
            "disk_migrations": len(names),
            "note": ("Ledger table not reachable (no DB access this session, or "
                     "100_schema_migrations_ledger.sql not applied + backfilled yet). "
                     "See database/MIGRATION_NOTES.md for the one-time prod seed."),
        }
        print(json.dumps(msg, indent=2) if output_json else
              f"[status] ledger unreachable — {len(names)} migration files on disk, "
              f"applied-state unknown.\n{msg['note']}")
        return 1
    applied = [n for n in names if n in ledger]
    pending = [n for n in names if n not in ledger]
    orphan = [f for f in ledger if f not in set(names)]
    if output_json:
        print(json.dumps({"applied": len(applied), "pending": pending, "orphan": orphan}, indent=2))
    else:
        print(f"[status] {len(applied)} applied, {len(pending)} pending, {len(orphan)} orphan(s)")
        for n in pending:
            print(f"  PENDING {n}")
        for n in orphan:
            print(f"  ORPHAN  {n} (in ledger, not on disk)")
        if not pending and not orphan:
            print("  All on-disk migrations are recorded applied. [OK]")
    return 0 if not pending and not orphan else 1


def cmd_backfill_ledger(env: dict[str, str], output_json: bool) -> int:
    files = _disk_migrations()
    rows = [{"filename": p.name, "sha256": _sha256(p.read_text(encoding="utf-8")),
             "applied_by": "mission-remediation-backfill"} for p in files]
    ok, body = _ledger_upsert(env, rows)
    out = {"status": "backfilled" if ok else "failed", "count": len(rows), "detail": body}
    print(json.dumps(out, indent=2) if output_json else f"[backfill] {out['status']}: {body}")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a SQL migration to a Bravo Supabase project"
    )
    parser.add_argument("migration_file", nargs="?", help="Path to .sql file")
    parser.add_argument("--status", action="store_true",
                        help="Compare database/*.sql to the schema_migrations ledger (applied vs pending)")
    parser.add_argument("--backfill-ledger", dest="backfill_ledger", action="store_true",
                        help="Record every on-disk migration as already-applied. Run ONCE, only when prod is current.")
    parser.add_argument("--force", action="store_true",
                        help="Apply even if the ledger has this filename with a different checksum")
    parser.add_argument(
        "--project",
        default="bravo",
        choices=list(PROJECTS.keys()),
        help="Target Supabase project (default: bravo)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent, don't execute",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Machine-readable JSON output",
    )
    parser.add_argument(
        "--force-api",
        action="store_true",
        help="Skip the exec_sql RPC path and go straight to the Management API",
    )
    parser.add_argument(
        "--allow-rls",
        action="store_true",
        help="Acknowledge that this migration touches RLS (CREATE POLICY / "
             "ENABLE ROW LEVEL SECURITY). Required when RLS_TOUCHING_PATTERNS "
             "match. Confirms the operator has tested the policy as anon AND "
             "authed user per brain/ORCHESTRATION.md verification contract.",
    )
    args = parser.parse_args()

    # Ledger-only commands — no migration file required.
    if args.status or args.backfill_ledger:
        env = load_env()
        if args.status:
            sys.exit(cmd_status(env, args.output_json))
        sys.exit(cmd_backfill_ledger(env, args.output_json))

    if not args.migration_file:
        parser.error("migration_file is required (or use --status / --backfill-ledger)")

    mig_path = Path(args.migration_file).resolve()
    if not mig_path.exists():
        print(f"ERROR: migration file not found: {mig_path}", file=sys.stderr)
        sys.exit(1)

    sql = mig_path.read_text(encoding="utf-8")

    # Safety guard — refuse destructive DDL unconditionally
    hits = check_blocked(sql)
    if hits:
        print(
            f"ABORTED: migration contains blocked pattern(s): {hits}",
            file=sys.stderr,
        )
        print(
            "If this is intentional, run the statement manually via the "
            "Supabase Dashboard SQL editor — this tool refuses by design.",
            file=sys.stderr,
        )
        sys.exit(2)

    # RLS-touching gate — apply only if operator passes --allow-rls.
    # Per brain/ORCHESTRATION.md verification contract, the operator should
    # have tested the policy as anon AND authed user before applying.
    rls_hits = check_rls_touching(sql)
    if rls_hits and not args.allow_rls and not args.dry_run:
        print(
            f"ABORTED: migration touches Row Level Security: {rls_hits}",
            file=sys.stderr,
        )
        print(
            "RLS policies have a high silent-failure rate. Before applying, "
            "verify the policy with anon + authed test queries (see "
            "brain/ORCHESTRATION.md Per-Domain Verification Contracts). "
            "Then re-run with --allow-rls to confirm.",
            file=sys.stderr,
        )
        sys.exit(3)
    if rls_hits and args.dry_run:
        print(f"[dry-run] WARNING: this migration touches RLS: {rls_hits}",
              file=sys.stderr)
        print(
            "[dry-run] On real apply you'll need --allow-rls. "
            "Test as anon + authed user first.",
            file=sys.stderr,
        )

    env = load_env()
    token = env.get("SUPABASE_ACCESS_TOKEN") or os.environ.get("SUPABASE_ACCESS_TOKEN")
    url_key = PROJECTS[args.project]["url_key"]
    supabase_url = env.get(url_key) or os.environ.get(url_key)

    # 2026-06-08 fix (VPS agent diagnosis): the OLD unconditional
    # SUPABASE_ACCESS_TOKEN check blocked the service-role RPC path — which
    # is the PREFERRED path for the bravo project and doesn't use the
    # Management API token at all. Now: only refuse upfront when the
    # operator forced --force-api OR is targeting a non-bravo project
    # (those skip the RPC path entirely). The bravo + default path defers
    # the check to the fallback site, so the RPC can succeed without a PAT.
    api_path_required = args.force_api or args.project != "bravo"
    if api_path_required and not token:
        print(
            "ERROR: SUPABASE_ACCESS_TOKEN missing in .env.agents. "
            "Create a personal access token at https://supabase.com/dashboard/account/tokens",
            file=sys.stderr,
        )
        sys.exit(1)
    if not supabase_url:
        print(f"ERROR: {url_key} missing in .env.agents", file=sys.stderr)
        sys.exit(1)

    project_ref = extract_project_ref(supabase_url)

    if args.dry_run:
        out = {
            "status": "dry_run",
            "project": args.project,
            "project_ref": project_ref,
            "migration_file": str(mig_path),
            "statement_count_approx": sql.count(";"),
            "byte_length": len(sql.encode("utf-8")),
        }
        if args.output_json:
            print(json.dumps(out, indent=2))
        else:
            print(f"[dry-run] {args.project} ({project_ref})")
            print(f"[dry-run] file: {mig_path}")
            print(f"[dry-run] approx statements: {out['statement_count_approx']}")
            print(f"[dry-run] bytes: {out['byte_length']}")
            print("[dry-run] no SQL sent")
        return

    # --- Ledger pre-check (audit Phase 4): refuse a CHANGED re-apply unless --force ---
    file_sha = _sha256(sql)
    _ledger = _ledger_fetch(env)
    if _ledger is not None and mig_path.name in _ledger:
        if _ledger[mig_path.name] == file_sha:
            print(f"[ledger] {mig_path.name} already applied with identical checksum "
                  "(re-applying — ensure it is idempotent).", file=sys.stderr)
        elif not args.force:
            print(f"ABORTED: {mig_path.name} is in the ledger with a DIFFERENT checksum — "
                  "its content changed since it was applied. Re-running a changed (possibly "
                  "non-idempotent) migration can corrupt data. Pass --force only if certain.",
                  file=sys.stderr)
            sys.exit(4)
        else:
            print(f"[ledger] --force: re-applying changed {mig_path.name}.", file=sys.stderr)

    print(f"Applying migration to {args.project} ({project_ref})...")

    # Preferred path: exec_sql RPC via service-role key (never expires).
    # Fallback: Management API PAT (30-day rotation). RPC fails gracefully
    # if migration 004 hasn't been applied yet.
    method = "rpc"
    if args.project == "bravo" and not args.force_api:
        ok, body = run_query_via_rpc(env, sql)
        if not ok:
            # RPC failed — fall back to Management API. NOW we need the PAT.
            if not token:
                print(
                    "[apply_migration] RPC path unavailable AND "
                    "SUPABASE_ACCESS_TOKEN is missing — can't fall back to "
                    "Management API. Either fix the RPC (apply migration 004) "
                    "or set SUPABASE_ACCESS_TOKEN in .env.agents.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"[apply_migration] RPC path unavailable ({body[:160]}) — "
                  "falling back to Management API.", file=sys.stderr)
            ok, body = run_query_via_management_api(token, project_ref, sql)
            method = "management_api_fallback"
    else:
        ok, body = run_query_via_management_api(token, project_ref, sql)
        method = "management_api"

    result = {
        "status": "applied" if ok else "failed",
        "project": args.project,
        "project_ref": project_ref,
        "migration_file": str(mig_path),
        "method": method,
        "response": body[:4000],
    }

    # --- Ledger post-write (audit Phase 4): record the applied file + checksum ---
    if ok:
        lok, lmsg = _ledger_upsert(env, [{
            "filename": mig_path.name, "sha256": file_sha, "applied_by": "apply_migration",
        }])
        result["ledger"] = lmsg if lok else f"WARN ledger not updated: {lmsg}"

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if ok:
            print("Migration applied.")
            print(f"  Project: {args.project} ({project_ref})")
            print(f"  File:    {mig_path.name}")
            if body and body.strip() not in ("[]", "null", ""):
                print(f"  Response: {body[:400]}")
        else:
            print(f"ERROR: {body[:1000]}", file=sys.stderr)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
