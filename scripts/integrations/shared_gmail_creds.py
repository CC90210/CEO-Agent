"""
shared_gmail_creds.py — resolve the shared submissions-mailbox Gmail App
Password from the encrypted credential store at RUNTIME.

Runtime home: /srv/sunbiz/ceo-agent/scripts/integrations/ (imported by
send_gateway._send_email_smtp via the shared-mailbox path). Source of record:
JARVIS scripts/vps-staging/ + CC90210/CEO-Agent.

WHY THIS EXISTS
    The VPS used to read GMAIL_APP_PASSWORD only from .env.agents. When the oasis
    Settings UI rotated the submissions App Password (2026-08), that static copy
    went stale and every VPS SMTP send failed auth for ~3 weeks with no self-heal.
    This resolves the CURRENT password from tenant_integration_credentials (the
    exact row the oasis web app authenticates with), so a rotation is picked up
    within one cache TTL — no env edit, no daemon restart, no recurrence.

FAIL-SAFE (this module can only ADD freshness, never break a send)
    The env value is the fallback. Any store miss, network error, decrypt failure,
    or mailbox mismatch returns `env_fallback` UNCHANGED — exactly what the send
    path used before this module existed. It never raises.

MAILBOX MATCH (multi-brand safety)
    It refuses to return a store password unless the store row's from_address
    matches the mailbox being authenticated (GMAIL_USER). A multi-brand tenant can
    therefore never send one mailbox's password as another's.

Decryption is byte-compatible via field_encryption (AES-256-GCM, scrypt over
BRAVO_FIELD_ENCRYPTION_KEY) — the same module the kixie override path already uses.
"""

from __future__ import annotations

import sys
import time
from typing import Optional, Tuple

# The shared submissions mailbox lives under the 'gws' credential service, the
# same service key getSubmissionsCreds() resolves on the web side.
_SERVICE = "gws"
_TTL_S = 300  # 5 min: matches the web app's getSubmissionsCreds cache window.

# tenant_id -> (password, fetched_at). Module-level; each daemon process keeps
# its own short-lived cache, so a rotation is picked up within _TTL_S per worker.
_cache: dict = {}


def _fetch_field(db, tenant_id: str, field_key: str) -> Optional[str]:
    """Decrypted value of one gws field, or None.

    Uses .limit(1).execute() + list handling rather than maybe_single(): the
    Python compat shim spells it maybe_single (snake_case), the JS client
    maybeSingle, and the limit-1 form works on both without depending on either
    name (the kixie override path in send_gateway assumes the camelCase name and
    silently fails on this shim — don't repeat that)."""
    res = (
        db.table("tenant_integration_credentials")
        .select("encrypted_value")
        .eq("tenant_id", tenant_id)
        .eq("service", _SERVICE)
        .eq("field_key", field_key)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if isinstance(rows, dict):  # some shims return the single row directly
        rows = [rows]
    enc = rows[0].get("encrypted_value") if rows else None
    if not enc:
        return None
    # Local import so a field_encryption problem can never break module import
    # time — the caller's try/except then falls back to env.
    from field_encryption import decrypt_field  # type: ignore
    return decrypt_field(enc)


def resolve_app_password(
    db,
    tenant_id: Optional[str],
    env_fallback: str,
    gmail_user: str,
) -> Tuple[str, str]:
    """Return (password, source), source in {"store", "cache", "env_fallback"}.

    NEVER raises. Returns (env_fallback, "env_fallback") on anything unexpected,
    on a missing tenant/db, or when the store row is for a different mailbox than
    `gmail_user`.
    """
    if not tenant_id or db is None:
        return env_fallback, "env_fallback"

    # Key the cache on (tenant, mailbox), not tenant alone: the mailbox-match
    # check below runs only on a cache MISS, so a tenant-only key could serve one
    # mailbox's cached password to a send authenticating as a different mailbox.
    cache_key = (tenant_id, (gmail_user or "").strip().lower())
    now = time.time()
    hit = _cache.get(cache_key)
    if hit and (now - hit[1]) < _TTL_S:
        return hit[0], "cache"

    try:
        from_addr = _fetch_field(db, tenant_id, "from_address")
        # Only override when the store row is for the SAME mailbox we authenticate
        # as. A blank/mismatched from_address means the store isn't authoritative
        # for THIS send — keep the env value rather than risk a cross-mailbox send.
        if not from_addr or (
            gmail_user and from_addr.strip().lower() != gmail_user.strip().lower()
        ):
            return env_fallback, "env_fallback"

        pw = _fetch_field(db, tenant_id, "app_password")
        if pw:
            pw = pw.replace(" ", "").strip()
        if pw:
            _cache[cache_key] = (pw, now)
            return pw, "store"
    except Exception as exc:  # noqa: BLE001 — fail-safe: any error -> env value
        print(
            f"[shared_gmail_creds] resolve failed, using env fallback: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

    return env_fallback, "env_fallback"
