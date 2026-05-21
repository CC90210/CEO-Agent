"""
Vercel Environment Variable CLI Tool.

Sets / lists / deletes env vars on Vercel projects via the REST API.
Credentials load via lib.secret_loader (canonical V6 path); the agent
never sees VERCEL_TOKEN directly — secret_guard would block it
anyway. Same wrapper-pattern as stripe_tool / kixie_tool / etc.

Usage:
  python scripts/integrations/vercel_env_tool.py list --project <slug> [--env production|preview|development]
  python scripts/integrations/vercel_env_tool.py set --project <slug> --key NAME --value VALUE [--env production]
  python scripts/integrations/vercel_env_tool.py set-random --project <slug> --key NAME [--env production] [--bytes 48]
  python scripts/integrations/vercel_env_tool.py delete --project <slug> --key NAME [--env production]
  python scripts/integrations/vercel_env_tool.py projects

set-random generates a cryptographically-strong base64-url random
value (default 48 bytes -> ~64-char string), useful for HMAC keys
where the agent shouldn't see the value either.

Credentials (in agents env file, loaded via lib.secret_loader):
  VERCEL_TOKEN    Personal access token from https://vercel.com/account/tokens
  VERCEL_TEAM_ID  Optional. Required when the project belongs to a team.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERCEL_API = "https://api.vercel.com"
DEFAULT_TIMEOUT_S = 30


def load_env() -> dict:
    """Load env via the canonical secret loader. Never reads the
    agents env file directly — secret_guard would block."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env as _load  # type: ignore
        return _load()
    except Exception:
        # Last-resort fallback: process env only. Operators running
        # this from a shell with VERCEL_TOKEN exported still work.
        return dict(os.environ)


def resolve_credentials() -> tuple[str, str | None]:
    env = load_env()
    token = (env.get("VERCEL_TOKEN") or os.environ.get("VERCEL_TOKEN") or "").strip()
    if not token:
        print(
            "ERROR: VERCEL_TOKEN missing. Create one at https://vercel.com/account/tokens "
            "and add to your agents env file as VERCEL_TOKEN=<value>.",
            file=sys.stderr,
        )
        sys.exit(1)
    team_id = (env.get("VERCEL_TEAM_ID") or os.environ.get("VERCEL_TEAM_ID") or "").strip() or None
    return token, team_id


class VercelError(Exception):
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


def _request(method: str, path: str, *, json_body: Any = None, params: dict | None = None) -> Any:
    token, team_id = resolve_credentials()
    url = f"{VERCEL_API}{path}"
    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "user-agent": "oasis-bravo/vercel-env-tool/1.0",
    }
    full_params = dict(params or {})
    if team_id and "teamId" not in full_params:
        full_params["teamId"] = team_id
    try:
        r = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=full_params,
            timeout=DEFAULT_TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise VercelError(f"network error contacting Vercel: {e}", 3) from e

    if r.status_code >= 400:
        try:
            body = r.json()
        except ValueError:
            body = r.text[:600]
        raise VercelError(f"HTTP {r.status_code} from Vercel: {body}", 2)
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


# ─────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────


def cmd_projects(_args) -> Any:
    """List operator's Vercel projects."""
    return _request("GET", "/v10/projects", params={"limit": 100})


def cmd_list(args) -> Any:
    """List env vars on one project."""
    res = _request("GET", f"/v10/projects/{args.project}/env", params={"decrypt": "false"})
    # Mask values — secret_guard blocks reading them anyway, but the
    # response from Vercel doesn't carry them unless decrypt=true.
    # Strip whatever leaks through.
    if isinstance(res, dict) and "envs" in res:
        for entry in res["envs"]:
            if "value" in entry:
                entry["value"] = "***"
    return res


def cmd_set(args) -> Any:
    """Create or update an env var on a project. Vercel's API has
    separate POST (create) and PATCH (update) endpoints — we attempt
    POST first; on 409 (already exists) we PATCH."""
    targets = args.env.split(",")
    payload = {
        "key": args.key,
        "value": args.value,
        "type": args.type,  # "encrypted" (default) | "plain" | "secret"
        "target": targets,
    }
    try:
        return _request("POST", f"/v10/projects/{args.project}/env", json_body=payload)
    except VercelError as e:
        # Conflict — env var exists already. Find its id then PATCH.
        if "409" in str(e) or "already exists" in str(e).lower():
            existing = _request("GET", f"/v10/projects/{args.project}/env", params={"decrypt": "false"})
            envs = existing.get("envs", []) if isinstance(existing, dict) else []
            match = next(
                (e2 for e2 in envs if e2.get("key") == args.key and set(e2.get("target") or []) & set(targets)),
                None,
            )
            if not match:
                raise
            patch = {"value": args.value, "type": args.type, "target": targets}
            return _request("PATCH", f"/v10/projects/{args.project}/env/{match['id']}", json_body=patch)
        raise


def cmd_set_random(args) -> Any:
    """Generate a cryptographically-strong random value and set it as
    an env var. Default 48 bytes -> base64-url ~64 chars. The agent
    never sees the value itself — it's generated locally + posted
    straight to Vercel + the response masks it. Useful for HMAC keys.
    """
    raw = secrets.token_urlsafe(args.bytes)
    set_args = argparse.Namespace(
        project=args.project,
        key=args.key,
        value=raw,
        type=args.type,
        env=args.env,
    )
    result = cmd_set(set_args)
    # Strip the value from the response so it doesn't end up in
    # console / logs. The operator can retrieve via Vercel dashboard
    # if needed — but for HMAC keys, no human ever needs to see it.
    if isinstance(result, dict):
        result.pop("value", None)
        if "created" in result and isinstance(result["created"], dict):
            result["created"].pop("value", None)
    return {"ok": True, "key": args.key, "target": args.env.split(","), "value_length": len(raw), "note": "value generated + posted to Vercel; not echoed"}


def cmd_delete(args) -> Any:
    """Delete an env var by key. Idempotent — already-absent returns
    a clean "not found" status code."""
    existing = _request("GET", f"/v10/projects/{args.project}/env", params={"decrypt": "false"})
    envs = existing.get("envs", []) if isinstance(existing, dict) else []
    targets = args.env.split(",")
    match = next(
        (e for e in envs if e.get("key") == args.key and set(e.get("target") or []) & set(targets)),
        None,
    )
    if not match:
        return {"ok": True, "key": args.key, "status": "not_found"}
    return _request("DELETE", f"/v10/projects/{args.project}/env/{match['id']}")


# ─────────────────────────────────────────────────────────────────────
# Argparse
# ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vercel_env_tool", description="Vercel env-var CLI (loads VERCEL_TOKEN via secret_loader).")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("projects", help="List operator's Vercel projects").set_defaults(func=cmd_projects)

    lst = sub.add_parser("list", help="List env vars on a project")
    lst.add_argument("--project", required=True, help="Project slug or ID")
    lst.add_argument("--env", default="production,preview,development", help="Comma-separated environments")
    lst.set_defaults(func=cmd_list)

    s = sub.add_parser("set", help="Create or update an env var")
    s.add_argument("--project", required=True)
    s.add_argument("--key", required=True, help="Env var name")
    s.add_argument("--value", required=True, help="Env var value")
    s.add_argument("--env", default="production", help="Comma-separated: production,preview,development")
    s.add_argument("--type", default="encrypted", choices=["encrypted", "plain", "secret"])
    s.set_defaults(func=cmd_set)

    sr = sub.add_parser("set-random", help="Generate a strong random value + set it")
    sr.add_argument("--project", required=True)
    sr.add_argument("--key", required=True)
    sr.add_argument("--env", default="production,preview,development")
    sr.add_argument("--type", default="encrypted", choices=["encrypted", "plain", "secret"])
    sr.add_argument("--bytes", type=int, default=48, help="random byte length pre-encoding (default 48 -> ~64 char base64url)")
    sr.set_defaults(func=cmd_set_random)

    d = sub.add_parser("delete", help="Delete an env var by key")
    d.add_argument("--project", required=True)
    d.add_argument("--key", required=True)
    d.add_argument("--env", default="production,preview,development")
    d.set_defaults(func=cmd_delete)

    args = p.parse_args(argv)
    try:
        result = args.func(args)
    except VercelError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps({"ok": True, "result": result}, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
