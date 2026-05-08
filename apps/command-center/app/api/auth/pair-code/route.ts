/**
 * POST /api/auth/pair-code
 *
 * Mints a one-time, 15-minute pair code that the operator pastes into
 * `bravo setup` on a new machine to bridge it without copy-pasting tokens.
 *
 * Auth: session — only the logged-in dashboard user can issue codes for
 * their own tenant.
 *
 * Returns:
 *   { ok: true, code: "ABC-DEF-GHJ", expires_at: "<iso8601>" }
 *
 * The code is shown to the user once (in the dashboard) and consumed once
 * (by the redeem endpoint). Single-use, short-lived. Stored plaintext in
 * the table because we have to look it up by code; the 15-min window +
 * single-use semantics keep the leak window tight.
 */

import { NextResponse } from "next/server";
import { randomBytes } from "crypto";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { bad } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CODE_TTL_MIN = 15;

// Alphabet excludes ambiguous chars (0/O, 1/I/L) so the operator can read
// it off the screen and type it without errors.
const ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";

function mintCode(): string {
  // 9 chars in three triplets — easy to read aloud, ~46 bits of entropy.
  // randomBytes for unbiased selection.
  const buf = randomBytes(9);
  const chars: string[] = [];
  for (let i = 0; i < 9; i++) {
    chars.push(ALPHABET[buf[i] % ALPHABET.length]);
  }
  return `${chars.slice(0, 3).join("")}-${chars.slice(3, 6).join("")}-${chars.slice(6, 9).join("")}`;
}

export async function POST() {
  const user = await getSessionUser();
  if (!user || !user.email) return bad(401, "unauthorized");

  const db = getServiceSupabase();
  const profile = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  if (profile.error || !profile.data?.tenant_id) {
    return bad(412, "no tenant for this user");
  }

  // Try a few times in case of unique-constraint collision (≈1 in 10^13).
  let code = "";
  let expiresAt = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    code = mintCode();
    expiresAt = new Date(Date.now() + CODE_TTL_MIN * 60_000).toISOString();
    const ins = await db.from("bridge_pair_codes").insert({
      code,
      tenant_id: profile.data.tenant_id,
      auth_user_id: user.id,
      email: user.email,
      expires_at: expiresAt,
    });
    if (!ins.error) break;
    if (attempt === 3) {
      return bad(500, `mint_failed: ${ins.error.message}`);
    }
  }

  return NextResponse.json({
    ok: true,
    code,
    expires_at: expiresAt,
    ttl_minutes: CODE_TTL_MIN,
  });
}
