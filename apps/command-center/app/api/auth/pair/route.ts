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

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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

export async function POST(req: NextRequest) {
  if (!checkBearerSecret(req, "CLI_SIGNUP_SECRET")) {
    return bad(401, "missing or invalid Bearer secret");
  }

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return bad(400, "body must be JSON");
  }
  const email = (body.email || "").trim().toLowerCase();
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

  // ---- 2. Mint a bridge_pairings row --------------------------------------
  if (!profileRow.tenant_id) {
    return bad(412, "profile has no tenant_id — provision step incomplete");
  }
  const tokenPlain = `oab_${randomBytes(32).toString("hex")}`;
  const tokenHash = sha256(tokenPlain);

  const machine = body.machine || {};
  const ins = await db
    .from("bridge_pairings")
    .insert({
      tenant_id: profileRow.tenant_id,
      user_id: profileRow.auth_user_id || null,
      label: machine.label || "Local install",
      bridge_token_hash: tokenHash,
      machine_fingerprint: machine.fingerprint || null,
      last_seen_at: new Date().toISOString(),
    })
    .select("id")
    .single();
  if (ins.error || !ins.data) {
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
      pairing_id: ins.data.id,
      token: tokenPlain,
      dashboard_url: baseUrl.replace(/\/$/, "") + "/",
    },
  });
}
