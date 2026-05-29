"""
AES-256-GCM field encryption — Python mirror of oasis-command-center/lib/field-encryption.ts.

The TypeScript side (Next.js routes, settings UI) is the original writer.
Python also writes when send_gateway refreshes an expired Gmail access token
and persists the new value back — the format and key derivation are kept
byte-compatible with the TS implementation so both sides round-trip cleanly.

MUST stay byte-compatible with field-encryption.ts:
  - Algorithm: AES-256-GCM
  - Key: scrypt(BRAVO_FIELD_ENCRYPTION_KEY, salt="oasis-bravo-v1", N=16384, r=8, p=1, dklen=32)
  - IV length: 12 bytes
  - Packed format: base64(iv) + "." + base64(authTag) + "." + base64(ciphertext)

Phase 4 of the SunBiz multi-employee personalization plan (2026-05-29).
"""

from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_KEY_LEN = 32
_IV_LEN = 12
_SALT = b"oasis-bravo-v1"
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1

_cached_key: Optional[bytes] = None


def _get_key() -> bytes:
    global _cached_key
    if _cached_key is not None:
        return _cached_key
    passphrase = os.environ.get("BRAVO_FIELD_ENCRYPTION_KEY") or ""
    if len(passphrase) < 16:
        raise RuntimeError(
            "BRAVO_FIELD_ENCRYPTION_KEY missing or <16 chars in environment"
        )
    kdf = Scrypt(
        salt=_SALT,
        length=_KEY_LEN,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    _cached_key = kdf.derive(passphrase.encode("utf-8"))
    return _cached_key


def decrypt_field(packed: str) -> str:
    """Decrypt a packed ciphertext written by field-encryption.ts.

    Raises ValueError on format mismatch / auth tag failure. Callers must
    treat that as a hard miss — never silently fall back, never log the
    plaintext.
    """
    if not packed:
        raise ValueError("decrypt_empty")
    parts = packed.split(".")
    if len(parts) != 3:
        raise ValueError("decrypt_format_invalid")
    iv_b, tag_b, ct_b = parts
    iv = base64.b64decode(iv_b)
    tag = base64.b64decode(tag_b)
    ct = base64.b64decode(ct_b)
    if len(iv) != _IV_LEN:
        raise ValueError("decrypt_iv_invalid")
    key = _get_key()
    # AESGCM in `cryptography` expects ciphertext || tag concatenated.
    aesgcm = AESGCM(key)
    try:
        pt = aesgcm.decrypt(iv, ct + tag, associated_data=None)
    except Exception as exc:  # cryptography.exceptions.InvalidTag etc.
        raise ValueError(f"decrypt_failed: {exc}") from exc
    return pt.decode("utf-8")


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string so the TS field-encryption.decryptField() can read it.

    Used by send_gateway when it refreshes a user's Gmail access token and
    persists the new value into user_integration_credentials.
    """
    if not plaintext:
        raise ValueError("encrypt_empty")
    key = _get_key()
    iv = secrets.token_bytes(_IV_LEN)
    aesgcm = AESGCM(key)
    # cryptography returns ciphertext || tag concatenated; split for TS format.
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), associated_data=None)
    ct = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return (
        base64.b64encode(iv).decode("ascii")
        + "."
        + base64.b64encode(tag).decode("ascii")
        + "."
        + base64.b64encode(ct).decode("ascii")
    )
