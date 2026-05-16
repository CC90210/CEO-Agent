/**
 * resume-hmac.ts — Phase H of giggly-reef.
 *
 * The Anthropic tool_use_pending pause hands a `resume_state` payload to the
 * browser, which posts it back to /api/chat/resume to continue the model
 * iteration. Without a signature, a malicious browser extension / XSS /
 * replay could synthesize arbitrary `resume_state` payloads and trick the
 * route into running the LLM with a forged history.
 *
 * For CC's single-operator case this is moot — attacker can only mess with
 * their own session — but the production multi-tenant SaaS path needs the
 * defense. HMAC-SHA256 with a server-only secret turns resume_state into a
 * signed token: server signs on emit, server verifies on receipt, browser
 * is just a passthrough that cannot mint valid payloads.
 *
 * Env: CHAT_RESUME_HMAC_KEY (any ≥32 char string). Legacy name
 *      BRAVO_RESUME_HMAC_KEY honored as fallback during the
 *      transition window.
 *   Missing in production → fail closed (route returns 503). Missing in
 *   development → degraded "no signing" mode logs a warning but allows
 *   the flow to work without the secret, so dev setup doesn't require a
 *   new env var. Production deploys MUST set it.
 *
 * Canonicalization: keys sorted recursively so JSON.stringify variations
 * between Node versions / object construction orders don't produce
 * verification false-negatives.
 */

import { createHmac, timingSafeEqual } from "crypto";

// Renamed 2026-05-15 from BRAVO_RESUME_HMAC_KEY — the chat-resume HMAC
// signs tokens for ANY tenant's chat, not just Bravo's. Neutral name
// reflects that. Legacy fallback for the transition window.
const HMAC_ENV_VAR = "CHAT_RESUME_HMAC_KEY";
const HMAC_ENV_VAR_LEGACY = "BRAVO_RESUME_HMAC_KEY";
const SIG_VERSION = "v1"; // bump when changing the canonicalization or algorithm

/**
 * Whether HMAC verification is enforced. Production = always. Dev = only
 * when the env var is set, otherwise unsigned (with a console warning).
 */
function shouldEnforce(): boolean {
  const isProd = process.env.NODE_ENV === "production" || process.env.VERCEL_ENV === "production";
  const keySet = !!(process.env[HMAC_ENV_VAR] || process.env[HMAC_ENV_VAR_LEGACY]);
  return isProd || keySet;
}

/**
 * Deterministic JSON encoding — sorted keys recursively. JSON.stringify is
 * close to deterministic but object key order can drift if construction
 * paths differ across iterations. Sorting removes that footgun.
 */
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
  // Prefer the canonical env var; fall back to the legacy name during
  // the transition. Once Vercel's legacy key is deleted, the fallback
  // is harmless dead-code.
  const raw =
    process.env[HMAC_ENV_VAR] || process.env[HMAC_ENV_VAR_LEGACY];
  if (!raw || raw.length < 32) return null;
  return Buffer.from(raw, "utf8");
}

/**
 * Identity binding stamped into a signed resume_state. The verifier
 * returns this to the caller so /api/chat/resume can re-check that
 * the resuming session's tenant matches the tenant the state was
 * issued under.
 *
 * 2026-05-16 Codex review finding #3 added the binding. Pre-binding,
 * a valid resume_signature would replay across tenants — a SunBiz
 * user who somehow captured an OASIS HQ resume signature could feed
 * it back through their own session and resume the LLM iteration
 * under OASIS context. Binding closes that door.
 */
export type ResumeBinding = {
  tenant_id: string;
  user_id: string;
  agent_key: string;
};

/**
 * Sign a resume_state payload. Returns a string of the form `v1.<base64>`.
 * When the HMAC key isn't set in non-production environments, returns an
 * empty string + logs a warning — the verifier accepts empty signatures
 * in that mode too. In production with a missing key, returns null so the
 * caller can choose to fail closed.
 *
 * The identity `binding` is stamped into the signed payload. Verifier
 * must re-check the binding against the caller's resolved identity to
 * prevent cross-tenant replay (see verifyResumeState below).
 */
export function signResumeState(state: unknown, binding?: ResumeBinding): string | null {
  const key = getKey();
  if (!key) {
    if (shouldEnforce()) {
      // Production with no key — caller should fail closed.
      return null;
    }
    // Dev without a key — emit a one-time warning so the operator knows
    // the protection isn't active, but don't block local development.
    if (!(globalThis as any).__resumeHmacWarned) {
      console.warn(
        `[resume-hmac] ${HMAC_ENV_VAR} not set; resume_state signing is DISABLED. Set it before any production deploy.`
      );
      (globalThis as any).__resumeHmacWarned = true;
    }
    return "";
  }
  const payload = { state, binding: binding ?? null };
  const canonical = canonicalize(payload);
  const sig = createHmac("sha256", key).update(canonical, "utf8").digest("base64url");
  return `${SIG_VERSION}.${sig}`;
}

export type VerifyResult =
  | { ok: true; binding: ResumeBinding | null }
  | { ok: false; reason: "server_misconfigured" | "missing_signature" | "version_mismatch" | "invalid" };

/**
 * Verify a resume_state payload against its claimed signature. Returns
 * { ok: true, binding } when the signature matches (or { ok: true,
 * binding: null } when the dev-mode "no key configured + no signature
 * claimed" case applies). Specific failure reasons returned so the
 * route can give the operator an actionable error.
 *
 * IMPORTANT: callers MUST cross-check the returned binding's tenant_id
 * against the caller's resolved tenant before resuming the LLM
 * iteration. The HMAC alone proves the state is server-issued; it does
 * NOT prove the resuming session has the right to that state.
 */
export function verifyResumeState(
  state: unknown,
  signature: string | undefined | null,
  binding?: ResumeBinding,
): VerifyResult {
  const key = getKey();
  if (!key) {
    if (shouldEnforce()) {
      return { ok: false, reason: "server_misconfigured" };
    }
    // Dev mode — accept anything since we couldn't have signed it either.
    return { ok: true, binding: binding ?? null };
  }
  if (!signature || typeof signature !== "string") {
    return { ok: false, reason: "missing_signature" };
  }
  const [version, sig] = signature.split(".", 2);
  if (version !== SIG_VERSION) {
    return { ok: false, reason: "version_mismatch" };
  }
  if (!sig) {
    return { ok: false, reason: "missing_signature" };
  }
  const payload = { state, binding: binding ?? null };
  const canonical = canonicalize(payload);
  const expected = createHmac("sha256", key).update(canonical, "utf8").digest();
  let provided: Buffer;
  try {
    provided = Buffer.from(sig, "base64url");
  } catch {
    return { ok: false, reason: "invalid" };
  }
  if (provided.length !== expected.length) {
    return { ok: false, reason: "invalid" };
  }
  return timingSafeEqual(provided, expected)
    ? { ok: true, binding: binding ?? null }
    : { ok: false, reason: "invalid" };
}
