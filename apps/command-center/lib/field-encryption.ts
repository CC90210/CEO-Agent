/**
 * Node-side AES-256-GCM field encryption for per-tenant secrets.
 *
 * Why not pgcrypto: supabase-js round-trips bytea inconsistently (PostgREST
 * version-dependent: hex \x... vs base64 vs raw), which made the pgp_sym_*
 * RPC path fragile in practice. Doing it in Node sidesteps that entirely.
 *
 * Key: derived from BRAVO_FIELD_ENCRYPTION_KEY env via scrypt with a fixed
 * deploy-wide salt. Rotating the env var orphans every stored ciphertext —
 * treat as a master secret, set once, never rotate without a migration.
 *
 * Format on disk: base64(iv).base64(authTag).base64(ciphertext)
 */

import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from "crypto";

const ALGO = "aes-256-gcm";
const KEY_LEN = 32;
const IV_LEN = 12;
const SALT = "oasis-bravo-v1"; // fixed; rotating breaks all stored ciphertexts

let _cachedKey: Buffer | null = null;

function getKey(): Buffer {
  if (_cachedKey) return _cachedKey;
  const passphrase = process.env.BRAVO_FIELD_ENCRYPTION_KEY;
  if (!passphrase || passphrase.length < 16) {
    throw new Error(
      "BRAVO_FIELD_ENCRYPTION_KEY missing or <16 chars. Generate with: " +
        'python -c "import secrets; print(secrets.token_urlsafe(48))"'
    );
  }
  _cachedKey = scryptSync(passphrase, SALT, KEY_LEN);
  return _cachedKey;
}

export function encryptField(plaintext: string): string {
  if (!plaintext) throw new Error("encrypt_empty_string");
  const key = getKey();
  const iv = randomBytes(IV_LEN);
  const cipher = createCipheriv(ALGO, key, iv);
  const ct = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${iv.toString("base64")}.${tag.toString("base64")}.${ct.toString("base64")}`;
}

export function decryptField(packed: string): string {
  if (!packed) throw new Error("decrypt_empty");
  const parts = packed.split(".");
  if (parts.length !== 3) throw new Error("decrypt_format_invalid");
  const [ivB, tagB, ctB] = parts;
  const key = getKey();
  const iv = Buffer.from(ivB, "base64");
  const tag = Buffer.from(tagB, "base64");
  const ct = Buffer.from(ctB, "base64");
  if (iv.length !== IV_LEN) throw new Error("decrypt_iv_invalid");
  const decipher = createDecipheriv(ALGO, key, iv);
  decipher.setAuthTag(tag);
  const pt = Buffer.concat([decipher.update(ct), decipher.final()]);
  return pt.toString("utf8");
}
