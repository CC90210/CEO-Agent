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
