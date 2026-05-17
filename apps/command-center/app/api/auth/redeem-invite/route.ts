/**
 * POST /api/auth/redeem-invite — atomic invite redemption.
 *
 * Phase A of the master multi-tenant infra plan (2026-05-17). Called by
 * the signup form and the login form after Supabase auth succeeds, when
 * the URL carried an `?invite=<token>` param. Wraps the existing
 * `redeem_tenant_invite` RPC (migration 037) and stamps onboarding
 * state so the welcome wizard (Phase C) knows this is a fresh invitee.
 *
 * Body: { auth_user_id: string, raw_token: string }
 *
 * Response 200: { ok: true, tenant_id, team_role, first_login: boolean }
 * Response 4xx: { ok: false, error, message? }
 *
 * Why not pass the raw token through the existing /auth/provision route:
 * provision is overloaded — it creates a new tenant for fresh signups.
 * Mixing redeem + provision in one endpoint makes the success-path logic
 * hard to read. Keeping them separate means each route has one job.
 */

import { NextResponse, type NextRequest } from "next/server";
import { redeemInvite } from "@/lib/team";
import { getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { auth_user_id?: string; raw_token?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const authUserId = (body.auth_user_id || "").trim();
  const rawToken = (body.raw_token || "").trim();
  if (!authUserId || !rawToken) {
    return NextResponse.json(
      { ok: false, error: "missing_fields", message: "auth_user_id and raw_token required" },
      { status: 400 },
    );
  }

  // Redeem — atomic in the SECURITY DEFINER RPC. Attaches the user_profile
  // to the inviter's tenant + assigns the invite's team_role.
  const result = await redeemInvite(rawToken, authUserId);
  if (!result.ok) {
    return NextResponse.json(
      { ok: false, error: "redeem_failed", message: result.error },
      { status: 400 },
    );
  }

  // First-login signal: did the user have onboarding_completed_at set
  // already? If not, the welcome wizard should fire post-redirect.
  // (We never CLEAR onboarding_completed_at on redeem — only set it
  // on first successful completion of the wizard. So we just check if
  // it's null right now to decide where to route the user next.)
  let firstLogin = true;
  try {
    const db = getServiceSupabase();
    const { data } = await db
      .from("user_profiles")
      .select("onboarding_completed_at")
      .eq("auth_user_id", authUserId)
      .maybeSingle();
    firstLogin = !data?.onboarding_completed_at;
  } catch {
    // Soft-fail — default to first_login=true so the wizard fires (safer
    // to over-show the wizard than under-show it).
  }

  return NextResponse.json({
    ok: true,
    tenant_id: result.tenantId,
    team_role: result.teamRole,
    first_login: firstLogin,
  });
}
