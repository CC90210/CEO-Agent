#!/usr/bin/env python3
"""smoke_n8n_inbound_rpc.py — end-to-end smoke test for the n8n inbound bridge.

Renamed from test_n8n_inbound_rpc.py (2026-05-21) — this is a live-DB
smoke script, not a pytest unit test. Pytest was picking it up via the
`test_*` prefix but found zero test functions, causing a collection error.

Exercises the full server-side chain that the /api/inbound/n8n route handler
also runs:
  1. Issue a fresh secret for the active profile
  2. Hash it (sha256, same as the route handler)
  3. Call record_inbound_from_n8n_v2 RPC with a fake classified email payload
  4. Verify a leads row was found-or-created
  5. Verify a lead_interactions row was inserted with full classification metadata
  6. Verify integrations_health.n8n_inbound was bumped to 'healthy'
  7. Revoke the test secret + assert it now rejects

Run after each migration / route change to prove the bridge actually works.

Env: BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY
Usage:
    python scripts/smoke_n8n_inbound_rpc.py [--profile-email conaugh@oasisai.work]

Exits 0 on full pass, non-zero on first failure.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# V6.8.3: migrated from python-dotenv to lib.secret_loader.
# scripts/<file>.py → parents[1] is the repo root.
_REPO = Path(__file__).resolve().parents[1]
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


GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}OK{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}!!{RESET}  {msg}")


def step(n: int, msg: str) -> None:
    print(f"\n{DIM}Step {n}{RESET}  {msg}")


def db() -> "Client":
    url = os.environ.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat"
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key"
    return create_client(url, key)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke-test the n8n inbound bridge")
    p.add_argument("--profile-email", default="conaugh@oasisai.work")
    p.add_argument("--keep-secret", action="store_true", help="Don't revoke the test secret at the end")
    args = p.parse_args()

    print(f"\n=== n8n inbound bridge smoke test · {args.profile_email} ===")

    client = db()

    # ─────────────────────────────────────────────────────────────────
    step(1, "Resolve profile")
    profile_r = client.table("user_profiles").select("id, email, tenant_id").eq("email", args.profile_email).limit(1).execute()
    if not profile_r.data:
        fail(f"no user_profile for {args.profile_email}")
        return 1
    profile = profile_r.data[0]
    profile_id = profile["id"]
    if not profile.get("tenant_id"):
        fail("profile has no tenant_id — run migration 018 + 019 first")
        return 1
    ok(f"profile_id={profile_id} tenant_id={profile['tenant_id']}")

    # ─────────────────────────────────────────────────────────────────
    step(2, "Issue a fresh test secret")
    raw_secret = uuid.uuid4().hex + uuid.uuid4().hex  # 64 chars
    secret_hash = sha256(raw_secret)
    issue = (
        client.table("n8n_webhook_secrets")
        .insert({"profile_id": profile_id, "secret_hash": secret_hash, "label": "smoke-test"})
        .execute()
    )
    if not issue.data:
        fail("could not insert secret")
        return 1
    secret_id = issue.data[0]["id"]
    ok(f"secret_id={secret_id}")

    # ─────────────────────────────────────────────────────────────────
    step(3, "Call record_inbound_from_n8n_v2 with a fake classified email")
    fake_email = f"smoketest-{uuid.uuid4().hex[:8]}@example.com"
    fake_subject = f"[smoke-test] inbound bridge {datetime.now(timezone.utc).isoformat()}"
    rpc = client.rpc(
        "record_inbound_from_n8n_v2",
        {
            "p_profile_id": profile_id,
            "p_secret_hash": secret_hash,
            "p_from_email": fake_email,
            "p_subject": fake_subject,
            "p_body": "Hi, interested in the 14-day pilot. (smoke-test payload)",
            "p_classification": {
                "intent": "info_request",
                "sentiment": "positive",
                "priority": "medium",
                "category": "business_opportunity",
            },
            "p_received_at": datetime.now(timezone.utc).isoformat(),
        },
    ).execute()
    interaction_id = rpc.data
    if not interaction_id:
        fail(f"RPC returned empty: {rpc}")
        return 1
    ok(f"interaction_id={interaction_id}")

    # ─────────────────────────────────────────────────────────────────
    step(4, "Verify lead was found-or-created")
    lead_r = client.table("leads").select("*").eq("email", fake_email).limit(1).execute()
    if not lead_r.data:
        fail(f"lead row not created for {fake_email}")
        return 1
    lead = lead_r.data[0]
    if lead.get("source") != "n8n_inbound":
        fail(f"lead.source expected 'n8n_inbound', got {lead.get('source')!r}")
        return 1
    if not lead.get("tenant_id"):
        fail("lead.tenant_id is NULL — multi-tenant write path is broken")
        return 1
    if lead.get("tenant_id") != profile.get("tenant_id"):
        fail(f"lead.tenant_id={lead.get('tenant_id')} doesn't match profile.tenant_id={profile.get('tenant_id')}")
        return 1
    ok(f"lead.id={lead['id']} status={lead.get('status')} score={lead.get('score')} tenant_id=ok")

    # ─────────────────────────────────────────────────────────────────
    step(5, "Verify lead_interactions row + classification")
    interaction_r = (
        client.table("lead_interactions").select("*").eq("id", interaction_id).limit(1).execute()
    )
    if not interaction_r.data:
        fail("interaction row not found")
        return 1
    interaction = interaction_r.data[0]
    meta = interaction.get("metadata") or {}
    cls = (meta or {}).get("classification") or {}
    if cls.get("intent") != "info_request":
        fail(f"classification.intent missing or wrong: {cls!r}")
        return 1
    if interaction.get("agent_source") != "n8n":
        fail(f"agent_source expected 'n8n', got {interaction.get('agent_source')!r}")
        return 1
    ok(f"agent_source=n8n · intent={cls.get('intent')} · priority={cls.get('priority')}")

    # ─────────────────────────────────────────────────────────────────
    step(6, "Verify integrations_health.n8n_inbound bumped")
    health_r = (
        client.table("integrations_health")
        .select("*")
        .eq("profile_id", profile_id)
        .eq("service", "n8n_inbound")
        .limit(1)
        .execute()
    )
    if not health_r.data:
        fail("integrations_health.n8n_inbound row missing")
        return 1
    health = health_r.data[0]
    if health.get("status") != "healthy":
        fail(f"status expected 'healthy', got {health.get('status')!r}")
        return 1
    ok(f"status=healthy · last_ping_at={health.get('last_ping_at')}")

    # ─────────────────────────────────────────────────────────────────
    step(7, "Verify wrong secret is rejected")
    bad_hash = sha256("not-the-real-secret")
    try:
        client.rpc(
            "record_inbound_from_n8n_v2",
            {
                "p_profile_id": profile_id,
                "p_secret_hash": bad_hash,
                "p_from_email": "bad@example.com",
                "p_subject": "should fail",
                "p_body": "",
                "p_classification": {},
                "p_received_at": datetime.now(timezone.utc).isoformat(),
            },
        ).execute()
        fail("RPC accepted a bad secret — auth is broken")
        return 1
    except Exception as exc:  # noqa: BLE001
        if "invalid_n8n_secret" in str(exc) or "42501" in str(exc):
            ok("rejected with invalid_n8n_secret")
        else:
            ok(f"rejected with: {str(exc)[:80]}")

    # ─────────────────────────────────────────────────────────────────
    step(8, "Cleanup")
    if args.keep_secret:
        ok(f"kept secret {secret_id} (--keep-secret)")
    else:
        client.table("n8n_webhook_secrets").delete().eq("id", secret_id).execute()
        ok(f"revoked + deleted secret {secret_id}")

    # Clean up the fake lead + interaction so we don't pollute the CRM
    client.table("lead_interactions").delete().eq("id", interaction_id).execute()
    client.table("leads").delete().eq("id", lead["id"]).execute()
    ok("cleaned up smoke-test lead + interaction")

    print(f"\n{GREEN}=== ALL CHECKS PASSED — n8n bridge is live ==={RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
