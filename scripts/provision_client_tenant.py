"""
Provision a client tenant in Supabase: create the auth user with email
pre-confirmed, then create/patch a tenant + user_profile using the same
brand-hint provisioning logic as the dashboard's /api/auth/provision route
(lib/client-provisioning.ts).

Usage:
    CLIENT_EMAIL=ops@example.com \
    CLIENT_PASSWORD='hunter2' \
    CLIENT_BRAND='Sun Biz Funding' \   # brand string drives client-profile match
    CLIENT_FULL_NAME='Ops Team' \
    python scripts/provision_client_tenant.py

Credentials are passed in via env so they never sit in the script body.
Service-role + supabase URL come from the canonical secret loader.

Idempotent: if the auth user already exists by email, we re-use it and
update password + email_confirmed + metadata. Same for tenant + profile.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

# Backward compat: accept SUNBIZ_* env names (the SunBiz client this was
# originally written for) AND the generalized CLIENT_* names.
EMAIL = (os.environ.get("CLIENT_EMAIL") or os.environ["SUNBIZ_EMAIL"]).strip().lower()
PASSWORD = os.environ.get("CLIENT_PASSWORD") or os.environ["SUNBIZ_PASSWORD"]
FULL_NAME = os.environ.get("CLIENT_FULL_NAME") or os.environ.get("SUNBIZ_FULL_NAME", "Client User")
BRAND = os.environ.get("CLIENT_BRAND") or os.environ.get("SUNBIZ_BRAND", "OASIS AI")


def main() -> None:
    secrets = load_env(["BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_SERVICE_ROLE_KEY"])

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase-py not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(2)

    db = create_client(secrets["BRAVO_SUPABASE_URL"], secrets["BRAVO_SUPABASE_SERVICE_ROLE_KEY"])

    # 1) Auth user — create or fetch existing
    existing_resp = db.auth.admin.list_users()
    existing_user = None
    # supabase-py returns either a list or an object with .users; handle both
    user_list = getattr(existing_resp, "users", None) or existing_resp or []
    for u in user_list:
        u_email = (getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None) or "").lower()
        if u_email == EMAIL:
            existing_user = u
            break

    if existing_user is None:
        created = db.auth.admin.create_user({
            "email": EMAIL,
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"full_name": FULL_NAME, "brand": BRAND},
        })
        auth_user = created.user
        auth_user_id = auth_user.id
        print(f"[auth] CREATED user id={auth_user_id} email={EMAIL}")
    else:
        auth_user_id = getattr(existing_user, "id", None) or existing_user["id"]
        # Update password + confirm email + metadata in case the row exists but is stale
        db.auth.admin.update_user_by_id(auth_user_id, {
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"full_name": FULL_NAME, "brand": BRAND},
        })
        print(f"[auth] FOUND existing user id={auth_user_id}; password + email_confirm updated")

    # 2) Tenant — create if no profile yet for this user
    profile_q = db.table("user_profiles").select("id, tenant_id").eq("auth_user_id", auth_user_id).limit(1).execute()
    profile_row = profile_q.data[0] if profile_q.data else None

    if profile_row and profile_row.get("tenant_id"):
        tenant_id = profile_row["tenant_id"]
        profile_id = profile_row["id"]
        print(f"[provision] FOUND existing profile id={profile_id} tenant={tenant_id}")
    else:
        tenant_id = str(uuid.uuid4())
        tenant_insert = db.table("tenants").insert({
            "id": tenant_id,
            "name": BRAND,
            "custom_fields": {
                "command_center_profile_slug": "sun",
                "data_backend": "turso",
                "deployment_mode": "dedicated",
            },
        }).execute()
        if not tenant_insert.data:
            print(f"[provision] tenant insert failed: {tenant_insert}", file=sys.stderr)
            sys.exit(3)
        print(f"[provision] CREATED tenant id={tenant_id} brand={BRAND!r}")

        if profile_row:
            # Profile exists but no tenant — patch it
            profile_id = profile_row["id"]
            db.table("user_profiles").update({"tenant_id": tenant_id}).eq("id", profile_id).execute()
            print(f"[provision] PATCHED existing profile id={profile_id} with tenant_id")
        else:
            profile_id = str(uuid.uuid4())
            db.table("user_profiles").insert({
                "id": profile_id,
                "auth_user_id": auth_user_id,
                "tenant_id": tenant_id,
                "email": EMAIL,
                "full_name": FULL_NAME,
                "brand": BRAND,
                "role": "operator",
            }).execute()
            print(f"[provision] CREATED user_profile id={profile_id} for auth_user={auth_user_id}")

    # 3) Brand-matched provisioning — mirror lib/client-provisioning.ts
    db.table("tenants").update({
        "custom_fields": {
            "command_center_profile_slug": "sun",
            "data_backend": "turso",
            "deployment_mode": "dedicated",
        },
    }).eq("id", tenant_id).execute()

    db.table("user_profiles").update({
        "primary_agent": "solara",
        "agents_enabled": ["solara", "helios"],
        "onboarding_completed_at": "now()",
        "is_owner": True,
        "team_role": "owner",
    }).eq("id", profile_id).execute()
    print(f"[provision] SET primary_agent=solara agents_enabled=[solara,helios] onboarding_completed_at=now() is_owner=true")

    # 4) Verify
    verify = db.table("user_profiles").select(
        "id, auth_user_id, email, tenant_id, primary_agent, agents_enabled, onboarding_completed_at, is_owner, team_role"
    ).eq("id", profile_id).limit(1).execute()
    tenant_verify = db.table("tenants").select("id, name, custom_fields").eq("id", tenant_id).limit(1).execute()
    print("\n=== FINAL STATE ===")
    print(json.dumps({
        "auth_user_id": auth_user_id,
        "user_profile": verify.data[0] if verify.data else None,
        "tenant": tenant_verify.data[0] if tenant_verify.data else None,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
