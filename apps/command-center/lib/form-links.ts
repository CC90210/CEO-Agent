/**
 * form-links.ts — Phase 3 of the SunBiz CRM build (2026-05-15).
 *
 * Personalized form URLs are HMAC-signed bearer tokens. Solara generates a
 * link with a lead_id + form_id + tenant_id payload + issued-at timestamp;
 * the public form page at /f/<tenant_slug>/<form_slug>/<lead_token>
 * verifies the signature before rendering or accepting submissions.
 *
 * Why HMAC instead of bare row IDs in the URL:
 *   - A prospect's URL is shareable. Without signing, anyone who guesses a
 *     UUID could open another lead's form and submit on their behalf.
 *   - The bearer-token model lets us roll keys (operator suspects leak →
 *     rotate BRAVO_FORM_LINK_HMAC_KEY → all in-flight links die).
 *   - HMAC-SHA256 + canonical JSON encoding matches the resume-hmac
 *     pattern lib/resume-hmac.ts established for /api/chat/resume; one
 *     reviewer audits both files identically.
 *
 * Env: BRAVO_FORM_LINK_HMAC_KEY (any ≥32 char string).
 *   Missing in production → fail closed (signer returns null; verifier
 *   refuses).
 *   Missing in development → degraded "no signing" mode with a one-time
 *   console warning, so dev setup doesn't require a new env var. Production
 *   deploys MUST set it.
 *
 * Token shape: v1.<base64url-payload>.<base64url-hmac>
 *   - Two pieces in the URL so the browser can extract the payload
 *     without contacting the server (cheap pre-render check).
 *   - base64url so the token is URL-safe without percent-encoding.
 *
 * Expiry: tokens carry an `iat` (issued-at) field. The verifier accepts
 * tokens up to FORM_LINK_TTL_DAYS days old by default. Operators can
 * shorten via the FORM_LINK_TTL_DAYS env var when paranoid; CC's stated
 * preference is 60 days (enough for a slow-moving funding deal to mature
 * without making a fresh link a daily ritual).
 */

import { createHmac, timingSafeEqual } from "crypto";

const HMAC_ENV_VAR = "BRAVO_FORM_LINK_HMAC_KEY";
const TTL_ENV_VAR = "FORM_LINK_TTL_DAYS";
const SIG_VERSION = "v1";
const DEFAULT_TTL_DAYS = 60;

export type FormLinkPayload = {
  /** Tenant slug — matches the URL segment for cross-checking. */
  tenant: string;
  /** Form UUID. */
  form_id: string;
  /** Lead UUID — the prospect this link is personalized for. */
  lead_id: string;
  /** Issued-at, unix seconds. */
  iat: number;
};

function shouldEnforce(): boolean {
  const isProd =
    process.env.NODE_ENV === "production" || process.env.VERCEL_ENV === "production";
  const keySet = !!process.env[HMAC_ENV_VAR];
  return isProd || keySet;
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return (
    "{" +
    keys.map((k) => JSON.stringify(k) + ":" + canonicalize(obj[k])).join(",") +
    "}"
  );
}

function getKey(): Buffer | null {
  const raw = process.env[HMAC_ENV_VAR];
  if (!raw || raw.length < 32) return null;
  return Buffer.from(raw, "utf8");
}

function ttlDays(): number {
  const raw = process.env[TTL_ENV_VAR];
  if (!raw) return DEFAULT_TTL_DAYS;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_TTL_DAYS;
  return parsed;
}

/**
 * Sign a payload + return the URL-safe token. Operators embed the result
 * in form URLs: `/f/<tenant>/<form_slug>/<token>`.
 *
 * Returns null in production when the HMAC key is missing — the caller
 * should treat that as "form-links subsystem unconfigured" and refuse to
 * mint a link. Returns "" in dev (no key set) so links still work for
 * local testing.
 */
export function signFormLink(payload: Omit<FormLinkPayload, "iat">): string | null {
  const key = getKey();
  const full: FormLinkPayload = {
    ...payload,
    iat: Math.floor(Date.now() / 1000),
  };
  const payloadJson = canonicalize(full);
  const payloadB64 = Buffer.from(payloadJson, "utf8").toString("base64url");

  if (!key) {
    if (shouldEnforce()) {
      return null;
    }
    if (!(globalThis as Record<string, unknown>).__formLinkHmacWarned) {
      console.warn(
        `[form-links] ${HMAC_ENV_VAR} not set; form-link signing is DISABLED. Set it before any production deploy.`,
      );
      (globalThis as Record<string, unknown>).__formLinkHmacWarned = true;
    }
    return `${SIG_VERSION}.${payloadB64}.`;
  }

  const sig = createHmac("sha256", key).update(payloadJson, "utf8").digest("base64url");
  return `${SIG_VERSION}.${payloadB64}.${sig}`;
}

export type VerifyFormLinkResult =
  | { ok: true; payload: FormLinkPayload }
  | {
      ok: false;
      reason:
        | "server_misconfigured"
        | "malformed"
        | "version_mismatch"
        | "missing_signature"
        | "invalid"
        | "expired";
    };

/**
 * Verify + parse a form-link token. Returns the payload on success so the
 * caller doesn't have to re-decode. Verifies:
 *   1. Version prefix matches.
 *   2. Payload is well-formed JSON with the required fields.
 *   3. HMAC signature matches (timing-safe comparison).
 *   4. Token is within TTL.
 */
export function verifyFormLink(token: string | undefined | null): VerifyFormLinkResult {
  if (!token || typeof token !== "string") {
    return { ok: false, reason: "malformed" };
  }
  const parts = token.split(".");
  if (parts.length !== 3) {
    return { ok: false, reason: "malformed" };
  }
  const [version, payloadB64, sig] = parts;
  if (version !== SIG_VERSION) {
    return { ok: false, reason: "version_mismatch" };
  }

  let payload: FormLinkPayload;
  try {
    const json = Buffer.from(payloadB64, "base64url").toString("utf8");
    payload = JSON.parse(json) as FormLinkPayload;
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (
    typeof payload.tenant !== "string" ||
    typeof payload.form_id !== "string" ||
    typeof payload.lead_id !== "string" ||
    typeof payload.iat !== "number"
  ) {
    return { ok: false, reason: "malformed" };
  }

  const key = getKey();
  if (!key) {
    if (shouldEnforce()) {
      return { ok: false, reason: "server_misconfigured" };
    }
    // Dev mode without key — payload validation already passed; accept it
    // so local testing of the form path works without a new env var.
    return { ok: true, payload };
  }

  if (!sig) {
    return { ok: false, reason: "missing_signature" };
  }
  const canonical = canonicalize(payload);
  const expected = createHmac("sha256", key).update(canonical, "utf8").digest();
  let provided: Buffer;
  try {
    provided = Buffer.from(sig, "base64url");
  } catch {
    return { ok: false, reason: "invalid" };
  }
  if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) {
    return { ok: false, reason: "invalid" };
  }

  // TTL check after signature so we don't leak token validity info to an
  // attacker who can craft an old-but-unsigned payload.
  const ageSeconds = Math.floor(Date.now() / 1000) - payload.iat;
  if (ageSeconds > ttlDays() * 86400) {
    return { ok: false, reason: "expired" };
  }

  return { ok: true, payload };
}
