#!/usr/bin/env python3
"""provision_secrets.py — materialize a tenant's integration secrets onto this host.

CC's credential model (2026-06): the operator hands a SunBiz VPS only Supabase
(URL + service-role key + BRAVO_FIELD_ENCRYPTION_KEY) and GitHub. Every other
integration secret (Gmail App Password for submissions@, Kixie, TextTorrent,
Twilio, SMTP, AI provider key) is entered ONCE in the Command Center, stored
encrypted in Supabase, and pulled down here by this script. This is the
"credentials migrate with the workspace" mechanism.

Source of truth (writer): oasis-command-center
  - tenant_integration_credentials(tenant_id, service, field_key, encrypted_value)
    written by lib/tenant-integration-store.ts (AES-256-GCM field-encryption.ts)
  - agent_model_config(tenant_id, user_id, agent_key, provider, encrypted_api_key)
    holds the AI provider key (tenant default = user_id IS NULL)

This consumer reuses the validated, Node-byte-compatible decrypt in
scripts/integrations/field_encryption.py and writes into the canonical secrets
file (scripts/lib/secret_loader.ENV_FILE), preserving operator-only keys.

Dry-run by default — prints which ENV keys WOULD be set (names only, never
values). Pass --apply to write. Idempotent.

USAGE (on the VPS):
  python3 scripts/provision_secrets.py --tenant sun            # preview
  python3 scripts/provision_secrets.py --tenant sun --apply    # write + chmod 600

REQUIRES env: BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY, BRAVO_FIELD_ENCRYPTION_KEY
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))  # so 'integrations' + 'lib' import cleanly

from integrations.field_encryption import decrypt_field  # noqa: E402
from lib.secret_loader import ENV_FILE  # canonical .env.agents path  # noqa: E402

# ---------------------------------------------------------------------------
# (service, field_key) -> ENV VAR NAME.
# Mirrors oasis-command-center/lib/tenant-integration-store.ts ENV_FALLBACKS
# (the authoritative per-tenant resolver map) so the runtime reads the same
# names the dashboard documents. gws.from_address is fanned out to the three
# Gmail keys the Python SMTP path actually reads (GMAIL_USER / GMAIL_ADDRESS
# for the login, GMAIL_FROM_ADDRESS for the From header).
# ---------------------------------------------------------------------------
ENV_MAP: dict[str, dict[str, list[str]]] = {
    "gws": {
        "app_password": ["GMAIL_APP_PASSWORD"],
        "from_address": ["GMAIL_USER", "GMAIL_ADDRESS", "GMAIL_FROM_ADDRESS"],
    },
    "texttorrent": {
        "api_key": ["TEXTTORRENT_API_KEY"],
        "from_number": ["TEXTTORRENT_FROM_NUMBER"],
    },
    "twilio": {
        "account_sid": ["TWILIO_ACCOUNT_SID"],
        "auth_token": ["TWILIO_AUTH_TOKEN"],
        "from_number": ["TWILIO_FROM_NUMBER"],
    },
    "smtp": {
        "host": ["SMTP_HOST"],
        "port": ["SMTP_PORT"],
        "user": ["SMTP_USER"],
        "password": ["SMTP_PASSWORD"],
        "from_address": ["SMTP_FROM_ADDRESS"],
    },
    # Kixie is DB-resident for the TS typed client, but the Python bridge reads
    # these from env; harmless to materialize so both sides agree.
    "kixie": {
        "api_key": ["KIXIE_API_KEY"],
        "business_id": ["KIXIE_BUSINESS_ID"],
        "from_number": ["KIXIE_FROM_NUMBER"],
        "default_agent_email": ["KIXIE_DEFAULT_AGENT_EMAIL"],
        "webhook_secret": ["KIXIE_WEBHOOK_SECRET"],
    },
}

# Sensible non-secret defaults written only if absent.
STATIC_DEFAULTS = {"EMAIL_FROM_NAME": "SunBiz Funding"}

# provider -> AI key env var (from agent_model_config).
AI_PROVIDER_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Operator-only keys that this script must NEVER overwrite or remove.
PRESERVE_PREFIXES = ("BRAVO_SUPABASE_", "BRAVO_FIELD_ENCRYPTION_KEY", "GITHUB_", "GH_")


def _client():
    try:
        from supabase import create_client  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: supabase python client not importable: {exc}", file=sys.stderr)
        sys.exit(2)
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY required.", file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


def _resolve_tenant(sb, slug: str) -> str:
    r = sb.table("tenants").select("id, slug").eq("slug", slug).limit(1).execute()
    if not r.data:
        print(f"ERROR: tenant slug '{slug}' not found.", file=sys.stderr)
        sys.exit(3)
    return str(r.data[0]["id"])


def _collect(sb, tenant_id: str) -> tuple[dict[str, str], list[str]]:
    """Return (env_to_write, problems)."""
    out: dict[str, str] = {}
    problems: list[str] = []

    rows = (
        sb.table("tenant_integration_credentials")
        .select("service, field_key, encrypted_value")
        .eq("tenant_id", tenant_id)
        .execute()
    ).data or []
    by_sf = {(r["service"], r["field_key"]): r.get("encrypted_value") for r in rows}

    for service, fields in ENV_MAP.items():
        for field_key, env_names in fields.items():
            packed = by_sf.get((service, field_key))
            if not packed:
                continue
            try:
                value = decrypt_field(packed)
            except Exception as exc:
                problems.append(f"{service}.{field_key}: decrypt failed ({exc})")
                continue
            if not value:
                continue
            for env_name in env_names:
                out[env_name] = value

    # AI provider key from agent_model_config (tenant default row).
    try:
        amc = (
            sb.table("agent_model_config")
            .select("provider, encrypted_api_key, user_id, agent_key")
            .eq("tenant_id", tenant_id)
            .is_("user_id", "null")
            .execute()
        ).data or []
        for row in amc:
            packed = row.get("encrypted_api_key")
            prov = (row.get("provider") or "").lower()
            env_name = AI_PROVIDER_ENV.get(prov)
            if packed and env_name and env_name not in out:
                try:
                    out[env_name] = decrypt_field(packed)
                except Exception as exc:
                    problems.append(f"agent_model_config[{prov}]: decrypt failed ({exc})")
    except Exception as exc:
        problems.append(f"agent_model_config read skipped ({exc})")

    return out, problems


def _parse_env_file(path: Path) -> dict[str, str]:
    existing: dict[str, str] = {}
    if not path.exists():
        return existing
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        existing[k.strip()] = v
    return existing


def _is_preserved(key: str) -> bool:
    return any(key == p or key.startswith(p) for p in PRESERVE_PREFIXES)


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync a tenant's integration secrets to the host secrets file.")
    ap.add_argument("--tenant", default="sun", help="Tenant slug (default: sun)")
    ap.add_argument("--apply", action="store_true", help="Write the secrets file (default: dry run)")
    args = ap.parse_args()

    sb = _client()
    tenant_id = _resolve_tenant(sb, args.tenant)
    materialized, problems = _collect(sb, tenant_id)

    # Merge: existing file wins for PRESERVED keys; materialized wins otherwise.
    existing = _parse_env_file(ENV_FILE)
    final = dict(existing)
    set_names: list[str] = []
    for k, v in materialized.items():
        if _is_preserved(k):
            continue  # never let the tenant store clobber operator-only secrets
        if final.get(k) != v:
            set_names.append(k)
        final[k] = v
    for k, v in STATIC_DEFAULTS.items():
        if k not in final:
            final[k] = v
            set_names.append(k)

    # Report — NAMES ONLY, never values.
    print(f"tenant: {args.tenant} ({tenant_id})")
    print(f"materialized {len(materialized)} secret env var(s) from the tenant store:")
    for name in sorted(materialized.keys()):
        print(f"  - {name}")
    if "GMAIL_USER" in materialized:
        print("  (Gmail identity present -> SunBiz will send as its own submissions@ address)")
    else:
        print("  WARNING: no Gmail identity found — outbound email will be refused by the email guard until gws.from_address is set in the Command Center.")
    if problems:
        print("\nproblems:")
        for p in problems:
            print(f"  ! {p}")

    if not args.apply:
        print(f"\nDRY RUN — re-run with --apply to write {ENV_FILE} (chmod 600).")
        return

    lines = [f"{k}={v}" for k, v in final.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass
    print(f"\n✅ Wrote {len(set_names)} updated key(s) to the secrets file (chmod 600). Operator-only keys preserved.")


if __name__ == "__main__":
    main()
