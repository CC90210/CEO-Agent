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
from dotenv import load_dotenv  # type: ignore

load_dotenv(ROOT / ".env.agents")

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
