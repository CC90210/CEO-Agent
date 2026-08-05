"""Turso Cloud provisioning — create the empire databases and wire their tokens.

WHY THIS EXISTS. Everything else in the Turso migration works against a local
libSQL file, which is why the pilot could be built and proven before any cloud
account existed. This is the one piece that needs Turso Cloud: creating the five
databases and minting a token for each.

THE CREDENTIAL SPLIT — the thing that blocks a fresh machine:
  TURSO_PLATFORM_TOKEN   organization-scoped. Creates/lists/deletes databases and
                         mints database tokens. Minted by `turso auth api-tokens
                         mint <name>` after `turso auth login` (a browser flow).
  TURSO_AUTH_TOKEN       database-scoped (JWT claims a/id/rid). Connects to ONE
                         database. Cannot create anything.
The TURSO_API_KEY already in the agents env is the SECOND kind, and it belongs to
the ig-setter-pro database — which is why it 401s here and why db_turso refuses to
treat it as a default connection target.

CREDENTIAL HYGIENE. `create --write-env` writes the minted database token straight
into the agents env file and prints only a redacted confirmation. The token never
passes through the agent's context, same principle as vercel_env_tool's set-random.

CLI:
  python scripts/integrations/turso_admin.py status [--json]
  python scripts/integrations/turso_admin.py list [--json]
  python scripts/integrations/turso_admin.py create --db bravo-empire [--group default]
  python scripts/integrations/turso_admin.py create --all --write-env
  python scripts/integrations/turso_admin.py token --db bravo-empire --write-env
  python scripts/integrations/turso_admin.py destroy --db <name> --confirm <name>

Exit codes: 0 ok · 1 API/operation error · 2 not configured.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import requests  # noqa: E402

from lib.secret_loader import ENV_FILE, load_env  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("turso_admin")

API = "https://api.turso.tech"
TIMEOUT_S = 45

# Database name -> the env var db_turso should read its URL from. One database
# per Supabase project, matching the existing trust boundaries: Breeze holds
# merchant bank data and must not share a database with anything else.
EMPIRE_DATABASES = {
    "bravo-empire": "TURSO_DATABASE_URL",
    "breeze-portal": "BREEZE_TURSO_DATABASE_URL",
    "nostalgic-requests": "NOSTALGIC_TURSO_DATABASE_URL",
    "propflow": "PROPFLOW_TURSO_DATABASE_URL",
    "oasis-platform": "OASIS_TURSO_DATABASE_URL",
}
TOKEN_VAR = {name: url_var.replace("DATABASE_URL", "AUTH_TOKEN")
             for name, url_var in EMPIRE_DATABASES.items()}


class NotConfigured(RuntimeError):
    pass


class TursoAPIError(RuntimeError):
    pass


def _creds() -> tuple[str, str]:
    env = load_env()
    token = env.get("TURSO_PLATFORM_TOKEN")
    org = env.get("TURSO_ORG")
    if not token or not org:
        missing = [k for k, v in (("TURSO_PLATFORM_TOKEN", token), ("TURSO_ORG", org)) if not v]
        raise NotConfigured(
            f"missing {', '.join(missing)} in the agents env.\n"
            "Mint them with:\n"
            "  irm https://github.com/tursodatabase/turso/releases/latest/download/"
            "turso_cli-installer.ps1 | iex\n"
            "  turso auth login\n"
            "  turso auth api-tokens mint bravo-empire   -> TURSO_PLATFORM_TOKEN\n"
            "  turso org list                            -> TURSO_ORG\n"
            "NOTE: TURSO_API_KEY is NOT this credential — it is a database-scoped "
            "token for the ig-setter-pro database and cannot create databases."
        )
    return token, org


def _call(method: str, path: str, token: str, **kw) -> dict:
    r = requests.request(method, f"{API}{path}",
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"},
                         timeout=TIMEOUT_S, **kw)
    if r.status_code >= 400:
        hint = ""
        if r.status_code == 401:
            hint = ("\nHINT: 401 usually means the token is a DATABASE token, not a "
                    "Platform API token. Only `turso auth api-tokens mint` produces "
                    "the latter.")
        raise TursoAPIError(f"{method} {path} -> {r.status_code}: {r.text[:300]}{hint}")
    return r.json() if r.content else {}


def _write_env(pairs: dict[str, str]) -> list[str]:
    """Append/replace keys in the agents env file WITHOUT returning their values.

    The caller gets back key names only. Values never enter the agent's context —
    that is the entire point of doing the write here instead of printing the token
    and asking a human to paste it back.
    """
    existing = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out: list[str] = []
    replaced: set[str] = set()
    for line in existing:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in pairs:
            out.append(f"{key}={pairs[key]}")
            replaced.add(key)
        else:
            out.append(line)
    for key, val in pairs.items():
        if key not in replaced:
            out.append(f"{key}={val}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    return sorted(pairs)


# ------------------------------------------------------------------- commands

def cmd_status(args) -> int:
    try:
        token, org = _creds()
    except NotConfigured as exc:
        payload = {"ok": False, "configured": False, "error": str(exc)}
        print(json.dumps(payload, indent=2) if args.json else f"NOT CONFIGURED: {exc}")
        return 2
    try:
        dbs = _call("GET", f"/v1/organizations/{org}/databases", token).get("databases", [])
    except TursoAPIError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2) if args.json
              else f"ERROR: {exc}")
        return 1
    present = {d["Name"] if "Name" in d else d.get("name") for d in dbs}
    expected = set(EMPIRE_DATABASES)
    payload = {"ok": True, "org": org, "databases": sorted(present),
               "empire_present": sorted(expected & present),
               "empire_missing": sorted(expected - present)}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"org: {org}  |  {len(present)} database(s)")
        for name in sorted(present):
            mark = "empire" if name in expected else "other"
            print(f"  {name:28} [{mark}]")
        if payload["empire_missing"]:
            print(f"MISSING empire databases: {', '.join(payload['empire_missing'])}")
            print("  create them with: python scripts/integrations/turso_admin.py "
                  "create --all --write-env")
    return 0


def cmd_list(args) -> int:
    return cmd_status(args)


def _create_one(token: str, org: str, name: str, group: str | None) -> dict:
    body: dict = {"name": name}
    if group:
        body["group"] = group
    res = _call("POST", f"/v1/organizations/{org}/databases", token, json=body)
    return res.get("database", res)


def _mint_token(token: str, org: str, name: str) -> str:
    res = _call("POST", f"/v1/organizations/{org}/databases/{name}/auth/tokens"
                        "?authorization=full-access", token)
    jwt = res.get("jwt")
    if not jwt:
        raise TursoAPIError(f"token mint for {name} returned no jwt: {str(res)[:200]}")
    return jwt


def cmd_create(args) -> int:
    try:
        token, org = _creds()
    except NotConfigured as exc:
        print(f"NOT CONFIGURED: {exc}", file=sys.stderr)
        return 2

    names = sorted(EMPIRE_DATABASES) if args.all else [args.db]
    if not names or names == [None]:
        print("ERROR: give --db <name> or --all", file=sys.stderr)
        return 2

    existing = {d.get("Name") or d.get("name")
                for d in _call("GET", f"/v1/organizations/{org}/databases", token)
                .get("databases", [])}

    results = []
    env_pairs: dict[str, str] = {}
    failed = False
    for name in names:
        try:
            if name in existing:
                results.append({"database": name, "status": "already exists"})
                hostname = next(
                    (d.get("Hostname") or d.get("hostname")
                     for d in _call("GET", f"/v1/organizations/{org}/databases", token)
                     .get("databases", []) if (d.get("Name") or d.get("name")) == name), None)
            else:
                db = _create_one(token, org, name, args.group)
                hostname = db.get("Hostname") or db.get("hostname")
                results.append({"database": name, "status": "created", "hostname": hostname})
                log.info("database created", database=name, hostname=hostname)
            if hostname and args.write_env:
                env_pairs[EMPIRE_DATABASES[name]] = f"libsql://{hostname}"
                env_pairs[TOKEN_VAR[name]] = _mint_token(token, org, name)
        except TursoAPIError as exc:
            failed = True
            results.append({"database": name, "status": "ERROR", "error": str(exc)})
            log.error("provisioning failed", database=name, error=str(exc))

    written: list[str] = []
    if env_pairs:
        written = _write_env(env_pairs)

    if args.json:
        print(json.dumps({"ok": not failed, "org": org, "results": results,
                          "env_keys_written": written}, indent=2))
    else:
        for r in results:
            if r["status"] == "ERROR":
                print(f"  FAIL {r['database']}: {r['error'][:300]}")
            else:
                print(f"  {r['status']:15} {r['database']}"
                      + (f"  ({r.get('hostname')})" if r.get("hostname") else ""))
        if written:
            # Names only. The values are secrets and are never echoed.
            print(f"  wrote {len(written)} key(s) to the agents env: {', '.join(written)}")
            print("  (values not shown — they were written directly, never displayed)")
        if not failed:
            print("\nNext: python scripts/apply_turso_migration.py "
                  "database/turso_migrations/bravo__000_master_schema.sql")
            print("Then: python scripts/etl_supabase_to_turso.py --project bravo")
            print("Then: python scripts/etl_supabase_to_turso.py --verify-parity --project bravo")
    return 1 if failed else 0


def cmd_token(args) -> int:
    # Argument validity is checked before credentials for the same reason as
    # destroy: the refusal should not depend on machine state.
    if args.db not in EMPIRE_DATABASES:
        print(f"ERROR: unknown empire database {args.db!r}. "
              f"Known: {', '.join(sorted(EMPIRE_DATABASES))}", file=sys.stderr)
        return 2
    if not args.write_env:
        print("Refusing to print a database token to stdout — it would land in the "
              "agent's context and the transcript. Re-run with --write-env.",
              file=sys.stderr)
        return 2
    try:
        token, org = _creds()
    except NotConfigured as exc:
        print(f"NOT CONFIGURED: {exc}", file=sys.stderr)
        return 2
    try:
        jwt = _mint_token(token, org, args.db)
    except TursoAPIError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    written = _write_env({TOKEN_VAR[args.db]: jwt})
    print(f"wrote {', '.join(written)} to the agents env (value not shown)")
    return 0


def cmd_destroy(args) -> int:
    """Deleting a database is irreversible; require the name typed twice.

    The confirmation is checked BEFORE credentials on purpose: a malformed
    destructive command should be refused on its own terms, not accidentally
    "pass" review because the machine happened to be unconfigured that day.
    """
    if args.confirm != args.db:
        print(f"REFUSED: --confirm must repeat the database name exactly. "
              f"Deleting {args.db!r} destroys its data with no undo.", file=sys.stderr)
        return 2
    try:
        token, org = _creds()
    except NotConfigured as exc:
        print(f"NOT CONFIGURED: {exc}", file=sys.stderr)
        return 2
    try:
        _call("DELETE", f"/v1/organizations/{org}/databases/{args.db}", token)
    except TursoAPIError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    log.warn("database destroyed", database=args.db)
    print(f"destroyed {args.db}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common], help="org + which empire databases exist")
    sub.add_parser("list", parents=[common], help="alias for status")

    p_create = sub.add_parser("create", parents=[common], help="create database(s)")
    p_create.add_argument("--db", help=f"one of: {', '.join(sorted(EMPIRE_DATABASES))}")
    p_create.add_argument("--all", action="store_true", help="create all five")
    p_create.add_argument("--group", default="default")
    p_create.add_argument("--write-env", action="store_true",
                          help="mint a token per database and write URL+token to the "
                               "agents env (values never displayed)")

    p_token = sub.add_parser("token", parents=[common], help="mint a database token")
    p_token.add_argument("--db", required=True)
    p_token.add_argument("--write-env", action="store_true")

    p_destroy = sub.add_parser("destroy", parents=[common], help="delete a database (irreversible)")
    p_destroy.add_argument("--db", required=True)
    p_destroy.add_argument("--confirm", required=True, help="repeat the database name")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return {"status": cmd_status, "list": cmd_list, "create": cmd_create,
            "token": cmd_token, "destroy": cmd_destroy}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
