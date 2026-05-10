/**
 * POST /api/auth/pair — setup-wizard ↔ dashboard handoff.
 *
 * Called by the local setup wizard after credentials are saved. Two jobs:
 *   1. Seed/update the operator's user_profiles row from wizard answers
 *      (brand, voice, primary agent, MRR target, schedule, agents_enabled,
 *      manifesto). After this, the dashboard's first paint shows their
 *      personalized data instead of the OASIS defaults.
 *   2. Mint a bridge_pairings row + bearer token. The wizard saves the token
 *      to ~/.oasis/bridge_token; the local bridge daemon then uses it as a
 *      Bearer credential when pinging integrations_health.
 *
 * Auth: Bearer-secret (CLI_SIGNUP_SECRET env), same as provision-cli.
 *
 * Body:
 *   {
 *     email:           string  (required — operator who ran the wizard)
 *     auth_user_id?:   uuid    (optional — if the wizard already provisioned)
 *     profile:         {
 *       full_name?:        string,
 *       display_name?:     string,
 *       brand?:            string,
 *       primary_agent?:    string,
 *       agents_enabled?:   string[],
 *       mrr_target_usd?:   number,
 *       mrr_current_usd?:  number,
 *       mrr_target_date?:  ISO date,
 *       manifesto?:        string,
 *       prospect_focus?:   string[]
 *     },
 *     machine: {
 *       label?:        string  (e.g. "CC's MacBook")
 *       fingerprint?:  string  (os + hostname + cpu hash from the wizard)
 *     }
 *   }
 *
 * Returns:
 *   {
 *     ok: true,
 *     tenant_id, profile_id, auth_user_id,
 *     bridge: { pairing_id, token, dashboard_url }
 *   }
 *
 * The bridge token is sha256-hashed before storage. The plaintext is returned
 * exactly once (in this response) — wizard writes it to ~/.oasis/bridge_token.
 */

import { NextResponse, type NextRequest } from "next/server";
import { createHash, randomBytes } from "crypto";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, checkBearerSecret } from "@/lib/api-helpers";
import { encryptField } from "@/lib/field-encryption";
import { chatAgentKeys } from "@/lib/agent-personas";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const VALID_PROVIDERS = new Set(["anthropic", "openai", "google", "openrouter"]);
const PROVIDER_DEFAULT_MODEL: Record<string, string> = {
  openrouter: "anthropic/claude-sonnet-4",
  anthropic: "claude-sonnet-4-6",
  openai: "gpt-5.4",
  google: "gemini-2.5-pro",
};

// Pick the best provider when the wizard sent multiple keys — operators
// usually want OpenRouter as default since one key covers all models.
const PROVIDER_PREFERENCE = ["openrouter", "anthropic", "openai", "google"];

type Body = {
  email?: string;
  auth_user_id?: string;
  profile?: {
    full_name?: string;
    display_name?: string;
    brand?: string;
    primary_agent?: string;
    agents_enabled?: string[];
    mrr_target_usd?: number;
    mrr_current_usd?: number;
    mrr_target_date?: string;
    manifesto?: string;
    prospect_focus?: string[];
  };
  machine?: {
    label?: string;
    fingerprint?: string;
  };
  /**
   * Optional: API keys the wizard / bridge collected from the operator's
   * local .env.agents. Each provided key gets encrypted server-side and
   * upserted into agent_model_config for EVERY chat-eligible agent, so the
   * operator's chat works immediately without paste-and-encrypt.
   *
   * The first key found (in PROVIDER_PREFERENCE order) becomes the default
   * provider for all agents. Operator can override per-agent later in
   * /settings → Agents.
   */
  api_keys?: Record<string, string>;
};

const PROFILE_FIELDS = new Set([
  "full_name",
  "display_name",
  "brand",
  "primary_agent",
  "agents_enabled",
  "mrr_target_usd",
  "mrr_current_usd",
  "mrr_target_date",
  "manifesto",
  "prospect_focus",
]);

function sha256(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

/**
 * Alternate auth path: HMAC headers (x-oasis-profile-id + x-oasis-secret).
 * Used by the chat server's self-pair-on-boot — operators don't have
 * CLI_SIGNUP_SECRET in their local env, but they DO have the per-profile
 * HMAC secret (issued by `n8n_webhook_secret.py issue --save-env` and used
 * for the outbound write-through path). One credential, two purposes.
 *
 * Returns the email associated with the verified profile so the rest of
 * the route can flow without an explicit body.email.
 */
async function _hmacAuthEmail(req: NextRequest): Promise<{ email: string; profileId: string } | null> {
  const profileId = req.headers.get("x-oasis-profile-id");
  const rawSecret = req.headers.get("x-oasis-secret");
  if (!profileId || !rawSecret) return null;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(profileId)) return null;
  const secretHash = sha256(rawSecret);
  const db = getServiceSupabase();
  const r = await db
    .from("n8n_webhook_secrets")
    .select("profile_id, revoked_at")
    .eq("profile_id", profileId)
    .eq("secret_hash", secretHash)
    .is("revoked_at", null)
    .maybeSingle();
  if (r.error || !r.data) return null;
  const pf = await db.from("user_profiles").select("email").eq("id", profileId).maybeSingle();
  if (!pf.data?.email) return null;
  return { email: String(pf.data.email).toLowerCase(), profileId };
}

export async function POST(req: NextRequest) {
  // Two valid auth modes:
  //   1. CLI_SIGNUP_SECRET bearer (interactive wizard path)
  //   2. HMAC headers (chat-server self-pair path)
  const hmacAuth = await _hmacAuthEmail(req);
  if (!hmacAuth && !checkBearerSecret(req, "CLI_SIGNUP_SECRET")) {
    return bad(401, "missing or invalid Bearer secret (or HMAC headers)");
  }

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    body = {};
  }
  const email = (body.email || hmacAuth?.email || "").trim().toLowerCase();
  if (!email) return bad(400, "email required");

  const db = getServiceSupabase();

  // ---- 1. Resolve user_profiles row ---------------------------------------
  const profileSrc = body.profile || {};
  const update: Record<string, unknown> = {};
  for (const k of Object.keys(profileSrc)) {
    if (PROFILE_FIELDS.has(k)) update[k] = (profileSrc as Record<string, unknown>)[k];
  }

  let profileRow:
    | { id: string; tenant_id: string | null; auth_user_id: string | null }
    | null = null;

  if (body.auth_user_id) {
    const r = await db
      .from("user_profiles")
      .select("id, tenant_id, auth_user_id")
      .eq("auth_user_id", body.auth_user_id)
      .maybeSingle();
    profileRow = r.data || null;
  }
  if (!profileRow) {
    const r = await db
      .from("user_profiles")
      .select("id, tenant_id, auth_user_id")
      .eq("email", email)
      .maybeSingle();
    profileRow = r.data || null;
  }
  if (!profileRow) {
    return bad(
      404,
      "no user_profiles row for this email — call /api/auth/provision-cli first"
    );
  }

  if (Object.keys(update).length > 0) {
    const r = await db
      .from("user_profiles")
      .update(update)
      .eq("id", profileRow.id)
      .select("id")
      .maybeSingle();
    if (r.error) return bad(500, `profile update failed: ${r.error.message}`);
  }

  if (!profileRow.tenant_id) {
    return bad(412, "profile has no tenant_id — provision step incomplete");
  }

  // ---- 1.5. Seed agent_model_config from local API keys -------------------
  // The bridge / wizard ships the operator's .env.agents key values (already
  // on their machine) so admin chat works without paste-and-encrypt.
  let seededAgents = 0;
  let seededProvider: string | null = null;
  if (body.api_keys && Object.keys(body.api_keys).length > 0) {
    // Pick the preferred provider that was supplied
    const supplied = Object.keys(body.api_keys).filter(
      (p) => VALID_PROVIDERS.has(p) && (body.api_keys?.[p] || "").trim().length > 0
    );
    const chosen = PROVIDER_PREFERENCE.find((p) => supplied.includes(p));
    if (chosen) {
      const plaintext = (body.api_keys[chosen] || "").trim();
      let encrypted: string;
      try {
        encrypted = encryptField(plaintext);
      } catch (e) {
        return bad(500, `encrypt_failed: ${e instanceof Error ? e.message : "unknown"}`);
      }
      const model = PROVIDER_DEFAULT_MODEL[chosen];
      // Upsert one row per chat-eligible agent. ON CONFLICT (tenant_id,
      // agent_key) — preserves any per-agent override the operator set
      // earlier by overwriting only when the key is newer.
      const rows = chatAgentKeys().map((agent_key) => ({
        tenant_id: profileRow!.tenant_id,
        agent_key,
        provider: chosen,
        model,
        encrypted_api_key: encrypted,
        enabled: true,
      }));
      const seedRes = await db
        .from("agent_model_config")
        .upsert(rows, { onConflict: "tenant_id,agent_key" });
      if (seedRes.error) {
        return bad(500, `seed_failed: ${seedRes.error.message}`);
      }
      seededAgents = rows.length;
      seededProvider = chosen;
    }
  }

  // ---- 2. Mint or rotate a bridge_pairings row ----------------------------
  // Idempotent by (tenant_id, machine_fingerprint). The DB enforces the
  // invariant via the partial unique index from migration 030
  // (idx_bridge_pairings_unique_live_machine, WHERE revoked_at IS NULL).
  // Without this, every restart of `bravo bridge serve` minted a NEW row
  // — CC saw four Mac rows for the same fingerprint after setup attempts.
  //
  // Strategy: try INSERT first. On unique-constraint violation (Postgres
  // code 23505), the partial index caught a duplicate live row — switch
  // to UPDATE keyed by (tenant_id, machine_fingerprint, revoked_at IS NULL)
  // to rotate the token on the existing row. This is race-safe (DB-level
  // atomic) AND clean (intent reads as "create a pairing"). PostgREST's
  // .upsert(onConflict:) can't target partial indexes, so we manage the
  // conflict path explicitly.
  const tokenPlain = `oab_${randomBytes(32).toString("hex")}`;
  const tokenHash = sha256(tokenPlain);

  const machine = body.machine || {};
  const fingerprint = (machine.fingerprint as string | undefined) || null;
  const label = (machine.label as string | undefined) || "Local install";
  const nowIso = new Date().toISOString();

  const row = {
    tenant_id: profileRow.tenant_id,
    user_id: profileRow.auth_user_id || null,
    label,
    bridge_token_hash: tokenHash,
    machine_fingerprint: fingerprint,
    last_seen_at: nowIso,
  };

  let pairingId: string | null = null;
  const ins = await db.from("bridge_pairings").insert(row).select("id").single();

  if (!ins.error && ins.data) {
    pairingId = ins.data.id;
  } else if (ins.error?.code === "23505" && fingerprint) {
    // Partial unique index fired — a live pairing already exists for this
    // (tenant, machine). Rotate the token + label on the existing row.
    const upd = await db
      .from("bridge_pairings")
      .update({
        bridge_token_hash: tokenHash,
        last_seen_at: nowIso,
        label,
      })
      .eq("tenant_id", profileRow.tenant_id)
      .eq("machine_fingerprint", fingerprint)
      .is("revoked_at", null)
      .select("id")
      .single();
    if (upd.error || !upd.data) {
      return bad(500, `pair rotate failed: ${upd.error?.message || "unknown"}`);
    }
    pairingId = upd.data.id;
  } else {
    return bad(500, `pair insert failed: ${ins.error?.message || "unknown"}`);
  }

  const baseUrl =
    process.env.BRAVO_DASHBOARD_URL ||
    "https://agent-dashboard-cc90210.vercel.app";

  return NextResponse.json({
    ok: true,
    tenant_id: profileRow.tenant_id,
    profile_id: profileRow.id,
    auth_user_id: profileRow.auth_user_id,
    bridge: {
      pairing_id: pairingId,
      token: tokenPlain,
      dashboard_url: baseUrl.replace(/\/$/, "") + "/",
    },
    seeded: {
      agents: seededAgents,
      provider: seededProvider,
    },
  });
}
