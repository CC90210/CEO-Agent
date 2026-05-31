"""
Per-user Gmail OAuth resolution + send path.

Reads the user_integration_credentials table populated by the dashboard's
/api/auth/google-oauth/callback route, decrypts the OAuth bundle, refreshes
the access_token via Google if expired, and exposes a Gmail API send helper.

Used by send_gateway.send() when acted_by_user_id + tenant_id are set —
e.g. an outbound email triggered from Alex's seat goes from alex@... not
the tenant-shared submissions@.

Phase 4 of the SunBiz multi-employee personalization plan (2026-05-29).
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from field_encryption import decrypt_field, encrypt_field

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_API_SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Fields the OAuth callback stores in user_integration_credentials.
# Mirrors lib/tenant-integration-schemas.ts gmail_oauth schema.
_GMAIL_FIELDS = (
    "refresh_token",
    "access_token",
    "expires_at",
    "scope",
    "gmail_address",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def has_user_gmail_connected(db: Any, tenant_id: str, user_id: str) -> bool:
    """Cheap presence check: does this user have ANY gmail_oauth rows?

    Used by the send pipeline to distinguish "user hasn't opted into
    personal Gmail yet (OK to use shared tenant SMTP)" from "user opted
    in but the token resolution failed (MUST block, not silently send
    from the wrong address)". Rule 8 / Codex review 2026-05-29.
    """
    if not tenant_id or not user_id:
        return False
    try:
        r = (
            db.table("user_integration_credentials")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("user_id", user_id)
            .eq("service", "gmail_oauth")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        _log(f"has_connected check failed: {exc}")
        # When in doubt, treat as connected so we fail closed rather
        # than misrepresent identity.
        return True
    return bool(getattr(r, "data", None))


def _log(msg: str) -> None:
    print(f"[user_gmail_oauth] {msg}", file=sys.stderr)


def resolve_user_gmail_bundle(
    db: Any, tenant_id: str, user_id: str
) -> Optional[dict[str, str]]:
    """Read + decrypt the user's gmail_oauth bundle.

    Returns a dict with refresh_token/access_token/expires_at/scope/
    gmail_address keys, or None if the user hasn't connected Gmail or
    the rows are malformed.

    NEVER logs the plaintext tokens. NEVER returns partials — either the
    bundle is complete (refresh_token present) or None.
    """
    if not tenant_id or not user_id:
        return None
    try:
        r = (
            db.table("user_integration_credentials")
            .select("field_key, encrypted_value")
            .eq("tenant_id", tenant_id)
            .eq("user_id", user_id)
            .eq("service", "gmail_oauth")
            .execute()
        )
    except Exception as exc:
        _log(f"db read failed for tenant={tenant_id} user={user_id}: {exc}")
        return None
    rows = getattr(r, "data", None) or []
    if not rows:
        return None
    bundle: dict[str, str] = {}
    for row in rows:
        key = (row.get("field_key") or "").strip()
        if key not in _GMAIL_FIELDS:
            continue
        enc = row.get("encrypted_value")
        if not enc:
            continue
        try:
            bundle[key] = decrypt_field(enc)
        except Exception as exc:
            _log(f"decrypt failed field={key} tenant={tenant_id} user={user_id}: {exc}")
            return None
    if not bundle.get("refresh_token"):
        return None
    return bundle


def _persist_refreshed_token(
    db: Any,
    tenant_id: str,
    user_id: str,
    new_access_token: str,
    new_expires_at: str,
) -> None:
    """Write back the freshly refreshed access_token + expires_at so the
    dashboard's expiry display + the next Python send avoid an unnecessary
    Google round-trip.

    Best-effort: failures here are logged but never block the send. The
    next send will just refresh again.
    """
    now_iso = _now().isoformat()
    for field_key, value in (
        ("access_token", new_access_token),
        ("expires_at", new_expires_at),
    ):
        try:
            encrypted = encrypt_field(value)
        except Exception as exc:
            _log(f"encrypt persist failed field={field_key}: {exc}")
            continue
        try:
            db.table("user_integration_credentials").upsert(
                {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "service": "gmail_oauth",
                    "field_key": field_key,
                    "encrypted_value": encrypted,
                    "updated_at": now_iso,
                },
                on_conflict="tenant_id,user_id,service,field_key",
            ).execute()
        except Exception as exc:
            _log(f"db upsert failed field={field_key}: {exc}")


def _refresh_access_token(refresh_token: str) -> Optional[dict[str, Any]]:
    """Exchange refresh_token for a new access_token via Google.

    Returns {access_token, expires_in} on success, None on failure.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or ""
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or ""
    if not client_id or not client_secret:
        _log("GOOGLE_CLIENT_ID/SECRET missing — can't refresh")
        return None
    try:
        resp = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
    except Exception as exc:
        _log(f"refresh request failed: {exc}")
        return None
    if resp.status_code != 200:
        _log(f"refresh non-200: {resp.status_code} {resp.text[:200]}")
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not data.get("access_token"):
        return None
    return data


def get_send_credentials(
    db: Any, tenant_id: str, user_id: str
) -> Optional[dict[str, str]]:
    """One-shot: load the user's Gmail bundle, refresh if expired, persist.

    Returns {access_token, gmail_address} on success, None when the user
    has no OAuth setup OR when refresh fails. Callers should treat None
    as "fall back to tenant-shared SMTP path."
    """
    bundle = resolve_user_gmail_bundle(db, tenant_id, user_id)
    if not bundle:
        return None
    access_token = bundle.get("access_token") or ""
    expires_at_raw = bundle.get("expires_at") or ""
    gmail_address = bundle.get("gmail_address") or ""
    refresh_token = bundle.get("refresh_token") or ""

    needs_refresh = True
    if access_token and expires_at_raw:
        try:
            exp_dt = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
            # 60-second safety margin so we never use a token that
            # expires mid-flight.
            needs_refresh = exp_dt <= _now() + timedelta(seconds=60)
        except Exception:
            needs_refresh = True

    if needs_refresh:
        refreshed = _refresh_access_token(refresh_token)
        if not refreshed:
            return None
        access_token = refreshed["access_token"]
        expires_in = int(refreshed.get("expires_in") or 3600)
        new_expires_at = (_now() + timedelta(seconds=expires_in)).isoformat()
        _persist_refreshed_token(
            db, tenant_id, user_id, access_token, new_expires_at
        )

    if not access_token or not gmail_address:
        return None
    return {"access_token": access_token, "gmail_address": gmail_address}


# ─── Shared-inbox tenants ────────────────────────────────────────────
#
# Tenants on the slugs below enforce a SHARED outbound identity — every
# email fires from the tenant-level Gmail/SMTP (e.g. SunBiz's shared
# submissions@sunbizfunding.com) regardless of which seat triggered the
# send. Per-deal routing happens via CC, not From: address.
#
# SunBiz directive 2026-05-31: rep visibility on threads comes from
# CC'ing the assigned rep (handled in the dashboard's shop-out + drip
# CC layers), not from per-user Gmail OAuth. So we short-circuit the
# user-OAuth resolution before it can pick up a stale linked-personal-
# Gmail bundle from Phase 4.
#
# Future: promote to tenants.config JSONB when a second tenant adopts
# the same pattern. Today's two-line set is the entire universe.
_SHARED_INBOX_SLUGS: set[str] = {"submissions"}

# Cached tenant_id -> slug lookup. Tenant slugs are immutable post-
# provisioning, so an unbounded module-level cache is safe in the
# daemon process. Empty string = "looked up, no row found" so we don't
# re-query the miss every send.
_TENANT_SLUG_CACHE: dict[str, str] = {}


def _is_shared_inbox_tenant(db: Any, tenant_id: str) -> bool:
    """Return True when this tenant's slug is in _SHARED_INBOX_SLUGS."""
    slug = _TENANT_SLUG_CACHE.get(tenant_id)
    if slug is None:
        try:
            res = (
                db.table("tenants")
                .select("slug")
                .eq("id", tenant_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            slug = ((rows[0] or {}).get("slug") if rows else "") or ""
            _TENANT_SLUG_CACHE[tenant_id] = slug
        except Exception:
            # Fail open — if we can't read tenants, fall through to
            # the existing per-user/tenant-fallback logic rather than
            # silently changing behavior for an unrelated DB outage.
            return False
    return slug in _SHARED_INBOX_SLUGS


def resolve_send_identity(
    db: Any, tenant_id: Optional[str], acted_by_user_id: Optional[str]
) -> dict[str, Any]:
    """Decide who is sending this email — the user's personal Gmail, the
    tenant-shared SMTP identity, or refuse the send entirely.

    Single chokepoint so both send_gateway.send() and the dashboard
    email consumer apply the same identity policy without drift.

    Returns one of:
      - {"mode": "user_oauth", "bundle": {access_token, gmail_address}}
        Caller should send via Gmail API as the user.
      - {"mode": "tenant_smtp"}
        Caller falls through to the tenant-shared SMTP path. Either no
        acted_by_user_id was supplied, the user hasn't connected
        personal Gmail yet, OR the tenant is on the shared-inbox
        roster (SunBiz et al — see _SHARED_INBOX_SLUGS above).
      - {"mode": "block", "reason": str}
        The user opted into personal Gmail but token resolution broke
        (expired refresh token, Google API down, malformed bundle).
        Caller MUST NOT silently fall back -- that would misrepresent
        identity. Surface an error to the operator instead.

    Phase 4 hardening (Codex review 2026-05-29).
    SunBiz shared-inbox short-circuit (2026-05-31).
    """
    if not acted_by_user_id or not tenant_id or db is None:
        return {"mode": "tenant_smtp"}

    # Shared-inbox tenants: never consult user_integration_credentials,
    # even if the user happened to connect personal Gmail before the
    # directive landed. From: is always tenant-shared; the assigned-rep
    # CC layer covers per-deal visibility.
    if _is_shared_inbox_tenant(db, tenant_id):
        return {"mode": "tenant_smtp"}

    try:
        bundle = get_send_credentials(db, tenant_id, acted_by_user_id)
    except Exception as exc:  # noqa: BLE001
        _log(
            f"get_send_credentials raised tenant={tenant_id} "
            f"user={acted_by_user_id}: {exc}"
        )
        bundle = None

    if bundle:
        return {"mode": "user_oauth", "bundle": bundle}

    # Resolution returned None. Distinguish "user never connected" from
    # "user connected but token resolution broke" using the cheap
    # presence check.
    try:
        opted_in = has_user_gmail_connected(db, tenant_id, acted_by_user_id)
    except Exception:  # noqa: BLE001
        # Fail closed on presence-check errors so we never
        # misrepresent identity by silently falling through.
        opted_in = True

    if opted_in:
        return {
            "mode": "block",
            "reason": (
                "user has connected personal Gmail but the OAuth token "
                "resolution failed; refusing to send from tenant-shared identity"
            ),
        }
    return {"mode": "tenant_smtp"}


def send_via_gmail_api(
    access_token: str, raw_mime_bytes: bytes
) -> tuple[bool, Optional[str]]:
    """POST a raw RFC 822 message to gmail.googleapis.com.

    Returns (ok, error_message). Never raises.
    """
    if not access_token:
        return False, "missing access_token"
    try:
        b64_payload = base64.urlsafe_b64encode(raw_mime_bytes).decode("ascii")
        resp = requests.post(
            GMAIL_API_SEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps({"raw": b64_payload}),
            timeout=30,
        )
    except Exception as exc:
        return False, f"network: {exc}"
    if resp.status_code in (200, 202):
        return True, None
    # Surface a trimmed error so callers can log it but never leak tokens.
    snippet = resp.text[:300] if resp.text else ""
    return False, f"gmail_api {resp.status_code}: {snippet}"
