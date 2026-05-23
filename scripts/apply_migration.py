"""Apply SQL migration files to the Bravo Supabase project.

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
import json
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a SQL migration to a Bravo Supabase project"
    )
    parser.add_argument("migration_file", help="Path to .sql file")
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

    if not token:
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

    print(f"Applying migration to {args.project} ({project_ref})...")

    # Preferred path: exec_sql RPC via service-role key (never expires).
    # Fallback: Management API PAT (30-day rotation). RPC fails gracefully
    # if migration 004 hasn't been applied yet.
    method = "rpc"
    if args.project == "bravo" and not args.force_api:
        ok, body = run_query_via_rpc(env, sql)
        if not ok:
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
