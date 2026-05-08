/**
 * POST /api/auth/pair-code/redeem
 *
 * Called by `bravo setup` on a new machine after the operator pastes the
 * code shown by /settings → Devices → Generate code. Exchanges the code
 * for a bridge_pairings row + bearer token.
 *
 * Auth: code itself is the authentication. No session, no bearer secret.
 * The code is single-use and 15-min-lived (see migration 032 + the mint
 * endpoint at ../route.ts) so the leak window is intentionally tight.
 *
 * Body:
 *   { code: "ABC-DEF-GHJ", machine: { label?: string, fingerprint?: string } }
 *
 * Returns:
 *   {
 *     ok: true,
 *     tenant_id, profile_id, auth_user_id,
 *     bridge: { pairing_id, token, dashboard_url }
 *   }
 *
 * Error states:
 *   404 — unknown / expired / already-consumed code
 *   410 — code was already redeemed (different from 404 to make the CLI's
 *         error message clearer)
 *   500 — pairing insert failed (DB issue)
 */

import { NextResponse, type NextRequest } from "next/server";
import { createHash, randomBytes } from "crypto";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function sha256(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

function isValidCodeShape(s: unknown): s is string {
  return typeof s === "string" && /^[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}$/.test(s);
}

export async function POST(req: NextRequest) {
  let body: { code?: unknown; machine?: { label?: unknown; fingerprint?: unknown } };
  try {
    body = await req.json();
  } catch {
    return bad(400, "invalid JSON");
  }
  const code = typeof body.code === "string" ? body.code.trim().toUpperCase() : "";
  if (!isValidCodeShape(code)) return bad(400, "invalid code shape (expect XXX-XXX-XXX)");

  const db = getServiceSupabase();
  const lookup = await db
    .from("bridge_pair_codes")
    .select("id, tenant_id, auth_user_id, email, expires_at, consumed_at")
    .eq("code", code)
    .maybeSingle();
  if (lookup.error) return bad(500, `lookup_failed: ${lookup.error.message}`);
  if (!lookup.data) return bad(404, "code not found or expired");

  const row = lookup.data;
  if (row.consumed_at) return bad(410, "code already redeemed");
  if (new Date(row.expires_at).getTime() < Date.now()) {
    return bad(404, "code expired");
  }

  // ATOMICALLY CLAIM THE CODE FIRST.
  //
  // The natural ordering "insert pairing → mark code consumed" is RACE-y:
  // two concurrent requests with the same code both see consumed_at=null,
  // both insert pairings, then only one consume succeeds. Result: a
  // single code mints two valid pairings.
  //
  // Fix: run the consume UPDATE first with `WHERE id = ? AND consumed_at
  // IS NULL` and `.select()` it — the database will only return the row
  // if the predicate held at update time. If returns 0 rows, another
  // request beat us; abort with 410 BEFORE creating any pairing. This is
  // PostgreSQL's standard "atomic claim" idiom.
  const claimRes = await db
    .from("bridge_pair_codes")
    .update({ consumed_at: new Date().toISOString() })
    .eq("id", row.id)
    .is("consumed_at", null)
    .select("id");
  if (claimRes.error) {
    return bad(500, `claim_failed: ${claimRes.error.message}`);
  }
  if (!claimRes.data || claimRes.data.length === 0) {
    // Lost the race — someone else just consumed this code.
    return bad(410, "code already redeemed");
  }

  // Mint the bridge pairing — same shape as /api/auth/pair so the CLI's
  // existing token storage logic in `bravo setup` works unchanged.
  const tokenPlain = `oab_${randomBytes(32).toString("hex")}`;
  const tokenHash = sha256(tokenPlain);

  const machine = body.machine || {};
  const machineLabel = typeof machine.label === "string" ? machine.label.slice(0, 80) : "Local install";
  const machineFp = typeof machine.fingerprint === "string" ? machine.fingerprint.slice(0, 200) : null;

  const ins = await db
    .from("bridge_pairings")
    .insert({
      tenant_id: row.tenant_id,
      user_id: row.auth_user_id,
      label: machineLabel,
      bridge_token_hash: tokenHash,
      machine_fingerprint: machineFp,
      last_seen_at: new Date().toISOString(),
    })
    .select("id")
    .single();
  if (ins.error || !ins.data) {
    // The code is already marked consumed but the pairing failed. That
    // means this code is now permanently dead — not ideal, but the
    // alternative (rolling back the consume) opens the door to the race
    // we just closed. Far better to make the operator generate a fresh
    // code than to risk double-claim.
    return bad(500, `pair_insert_failed_after_claim: ${ins.error?.message || "unknown"}`);
  }

  // Annotate the consumed code with the pairing id for audit trail.
  // Best-effort — the code is already consumed, so this update can fail
  // without affecting correctness.
  await db
    .from("bridge_pair_codes")
    .update({ consumed_by_pairing_id: ins.data.id })
    .eq("id", row.id);
  const consumedOk = true;

  // Find the user's profile id for parity with /api/auth/pair response shape
  const profile = await db
    .from("user_profiles")
    .select("id")
    .eq("auth_user_id", row.auth_user_id)
    .maybeSingle();

  const baseUrl =
    process.env.BRAVO_DASHBOARD_URL ||
    "https://agent-dashboard-cc90210.vercel.app";

  return NextResponse.json({
    ok: true,
    tenant_id: row.tenant_id,
    profile_id: profile.data?.id ?? null,
    auth_user_id: row.auth_user_id,
    bridge: {
      pairing_id: ins.data.id,
      token: tokenPlain,
      dashboard_url: baseUrl.replace(/\/$/, "") + "/",
    },
    code_consumed: consumedOk,
  });
}
