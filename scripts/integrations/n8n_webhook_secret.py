#!/usr/bin/env python3
"""n8n_webhook_secret.py — manage shared secrets for the OASIS Command Center
inbound webhook.

The OASIS Inbound Qualifier (n8n workflow ID 1cGIN32alM8sf8OV) posts every
classified email to /api/inbound/n8n. The route handler authenticates on a
sha256-hashed secret. This CLI issues, lists, and revokes those secrets.

Subcommands:
  issue   --profile-email EMAIL [--label LABEL]   issue a new secret
  list    --profile-email EMAIL                   list active secrets (hash + label)
  revoke  --secret-id UUID                        revoke a secret

Env: BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY (from .env.agents)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets as pysecrets
import sys
from pathlib import Path

# Make scripts/ importable
SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(ROOT))

# Load .env.agents
# V6.8.3: migrated from python-dotenv to lib.secret_loader.
# scripts/integrations/<file>.py → parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_REPO / 'scripts'))
from lib.secret_loader import load_env as _load_env  # noqa: E402

_env = _load_env()
import os as _os
for _k, _v in _env.items():
    _os.environ.setdefault(_k, str(_v))

try:
    from supabase import create_client, Client  # type: ignore
except ImportError:
    print("ERROR: pip install supabase", file=sys.stderr)
    sys.exit(2)


def db() -> "Client":
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def find_profile(client: "Client", email: str) -> dict | None:
    r = (
        client.table("user_profiles")
        .select("id, email, full_name, brand, tenant_id")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def _save_to_env_agents(*, profile_id: str, raw_secret: str, dashboard_url: str) -> str:
    """Append/update OASIS_PROFILE_ID + OASIS_OUTBOUND_HMAC_SECRET +
    OASIS_DASHBOARD_URL in .env.agents. Idempotent: re-running rotates
    the secret cleanly. Returns the path written.
    """
    env_path = ROOT / ".env.agents"
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    keys_to_set = {
        "OASIS_PROFILE_ID": profile_id,
        "OASIS_OUTBOUND_HMAC_SECRET": raw_secret,
        "OASIS_DASHBOARD_URL": dashboard_url,
    }

    out_lines: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in keys_to_set:
                out_lines.append(f"{key}={keys_to_set[key]}")
                seen.add(key)
                continue
        out_lines.append(line)

    # Append any keys we didn't find under a labeled section
    missing = [k for k in keys_to_set if k not in seen]
    if missing:
        if out_lines and out_lines[-1].strip() != "":
            out_lines.append("")
        out_lines.append("# OASIS Command Center outbound write-through (managed by n8n_webhook_secret.py)")
        for key in missing:
            out_lines.append(f"{key}={keys_to_set[key]}")

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass
    return str(env_path)


def cmd_issue(args: argparse.Namespace) -> int:
    client = db()
    profile = find_profile(client, args.profile_email)
    if not profile:
        print(f"ERROR: no user_profile for {args.profile_email}", file=sys.stderr)
        return 1

    raw = pysecrets.token_urlsafe(32)
    h = sha256(raw)
    r = (
        client.table("n8n_webhook_secrets")
        .insert(
            {
                "profile_id": profile["id"],
                "tenant_id": profile.get("tenant_id"),
                "secret_hash": h,
                "label": args.label or "OASIS Inbound Qualifier",
            }
        )
        .execute()
    )
    if not r.data:
        print("ERROR: insert failed", file=sys.stderr)
        return 1

    saved_env_path: str | None = None
    if args.save_env:
        try:
            saved_env_path = _save_to_env_agents(
                profile_id=profile["id"],
                raw_secret=raw,
                dashboard_url=args.dashboard_url,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: --save-env failed: {exc}", file=sys.stderr)
            saved_env_path = None

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "secret": raw,
                    "secret_id": r.data[0]["id"],
                    "profile_id": profile["id"],
                    "header_examples": {
                        "x-oasis-profile-id": profile["id"],
                        "x-oasis-secret": raw,
                    },
                    "saved_to_env": saved_env_path,
                },
                indent=2,
            )
        )
    else:
        print()
        print("=== OASIS n8n webhook secret issued ===")
        print()
        print(f"  profile email :  {profile['email']}")
        print(f"  profile id    :  {profile['id']}")
        print(f"  label         :  {r.data[0]['label']}")
        print(f"  secret_id     :  {r.data[0]['id']}")
        print()
        if saved_env_path:
            print(f"  saved to      :  {saved_env_path}")
            print(f"  keys written  :  OASIS_PROFILE_ID, OASIS_OUTBOUND_HMAC_SECRET, OASIS_DASHBOARD_URL")
            print()
            print("Outbound write-through is now active. Next send_gateway run will")
            print("publish to the dashboard's Activity Tape automatically.")
        else:
            print("=== HEADERS — paste into n8n HTTP Request node ===")
            print()
            print(f"  x-oasis-profile-id:  {profile['id']}")
            print(f"  x-oasis-secret:      {raw}")
            print()
            print("Save the secret NOW — only the hash is stored, you can't")
            print("recover the raw value. Re-issue if you lose it.")
        print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    client = db()
    profile = find_profile(client, args.profile_email)
    if not profile:
        print(f"ERROR: no user_profile for {args.profile_email}", file=sys.stderr)
        return 1
    r = (
        client.table("n8n_webhook_secrets")
        .select("id, label, last_used_at, use_count, created_at, revoked_at")
        .eq("profile_id", profile["id"])
        .order("created_at", desc=True)
        .execute()
    )
    if args.json:
        print(json.dumps(r.data or [], indent=2, default=str))
        return 0
    if not r.data:
        print("(no secrets)")
        return 0
    for row in r.data:
        active = "REVOKED" if row.get("revoked_at") else "active"
        print(
            f"  {row['id']}  {active:>8}  used={row.get('use_count') or 0:<5}  "
            f"label={row.get('label') or '-':<32}  last_used={row.get('last_used_at') or '-'}"
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    client = db()
    from datetime import datetime, timezone
    r = (
        client.table("n8n_webhook_secrets")
        .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", args.secret_id)
        .execute()
    )
    if not r.data:
        print(f"ERROR: no secret with id {args.secret_id}", file=sys.stderr)
        return 1
    print(f"Revoked {args.secret_id}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Manage OASIS Command Center n8n webhook secrets")
    p.add_argument("--json", action="store_true", help="JSON output")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="issue a new secret")
    p_issue.add_argument("--profile-email", required=True)
    p_issue.add_argument("--label", default=None)
    p_issue.add_argument(
        "--save-env",
        action="store_true",
        help="Append OASIS_PROFILE_ID + OASIS_OUTBOUND_HMAC_SECRET to .env.agents (chmod 600)",
    )
    p_issue.add_argument(
        "--dashboard-url",
        default="https://agent-dashboard-cc90210.vercel.app",
        help="OASIS_DASHBOARD_URL value to write when --save-env is used",
    )
    p_issue.set_defaults(func=cmd_issue)

    p_list = sub.add_parser("list", help="list secrets for a profile")
    p_list.add_argument("--profile-email", required=True)
    p_list.set_defaults(func=cmd_list)

    p_revoke = sub.add_parser("revoke", help="revoke a secret by id")
    p_revoke.add_argument("--secret-id", required=True)
    p_revoke.set_defaults(func=cmd_revoke)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
