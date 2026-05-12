/**
 * POST /api/auth/provision-cli — setup-wizard signup endpoint.
 *
 * Called from `install/bootstrap.py --create-command-center-account`. Creates
 * a Supabase Auth user for the operator and emails them a "set your password"
 * link via inviteUserByEmail. Idempotent — re-running for an existing email
 * returns the existing IDs without re-emailing.
 *
 * Auth: Bearer-secret (CLI_SIGNUP_SECRET env). Different from the BRIDGE_SECRET
 * the (now-removed) Stripe bridge used. This is purely for the CC's own
 * setup-wizard account creation.
 *
 * Body:
 *   { email, full_name, brand?, prefer_oauth? }
 *
 * If prefer_oauth=true, no invite email is sent — operator is told to use
 * "Continue with Google" on the login page.
 */
import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, checkBearerSecret } from "@/lib/api-helpers";
import { applyClientProvisioningProfile } from "@/lib/client-provisioning";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!checkBearerSecret(req, "CLI_SIGNUP_SECRET")) return bad(401, "unauthorized");

  let body: {
    email?: string;
    full_name?: string;
    brand?: string;
    prefer_oauth?: boolean;
    agent?: string;
  };
  try { body = await req.json(); } catch { return bad(400, "invalid JSON"); }
  const email = (body.email || "").trim().toLowerCase();
  if (!email || !email.includes("@")) return bad(400, "valid email required");
  const fullName = body.full_name?.trim() || email.split("@")[0];
  const brand = body.brand?.trim() || "OASIS AI";
  const agentToAdd = (body.agent || "").trim().toLowerCase();
  const VALID_AGENTS = new Set(["bravo", "atlas", "maven", "aura", "hermes", "codex", "sunbiz"]);

  const db = getServiceSupabase();

  // Find existing auth user by email (admin API)
  const list = await db.auth.admin.listUsers();
  const existing = list.data?.users?.find((u) => (u.email || "").toLowerCase() === email);

  let authUserId: string;
  let isNewUser = false;
  let welcomeSent = false;

  if (existing) {
    authUserId = existing.id;
  } else if (body.prefer_oauth) {
    // Create user without inviting — they'll sign in with Google
    const created = await db.auth.admin.createUser({
      email,
      email_confirm: true,
      user_metadata: { full_name: fullName, brand, source: "setup_wizard_oauth" },
    });
    if (created.error || !created.data?.user) return bad(500, created.error?.message || "create failed");
    authUserId = created.data.user.id;
    isNewUser = true;
  } else {
    // Send invite + set-password email
    const redirectTo =
      (process.env.PUBLIC_APP_URL?.replace(/\/$/, "") || "https://agent-dashboard-cc90210.vercel.app") +
      "/auth/reset-password";
    const invited = await db.auth.admin.inviteUserByEmail(email, {
      redirectTo,
      data: { full_name: fullName, brand, source: "setup_wizard" },
    });
    if (invited.error || !invited.data?.user) return bad(500, invited.error?.message || "invite failed");
    authUserId = invited.data.user.id;
    isNewUser = true;
    welcomeSent = true;
  }

  // Resolve or create profile + tenant via signup_tenant RPC
  const byAuth = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", authUserId)
    .maybeSingle();
  let profileId: string;
  let tenantId: string;
  if (byAuth.data) {
    profileId = byAuth.data.id;
    tenantId = byAuth.data.tenant_id;
  } else {
    const byEmail = await db
      .from("user_profiles")
      .select("id, tenant_id")
      .eq("email", email)
      .maybeSingle();
    if (byEmail.data) {
      await db.from("user_profiles").update({ auth_user_id: authUserId }).eq("id", byEmail.data.id);
      profileId = byEmail.data.id;
      tenantId = byEmail.data.tenant_id;
    } else {
      const r = await db.rpc("signup_tenant", {
        p_auth_user_id: authUserId,
        p_email: email,
        p_full_name: fullName,
        p_brand: brand,
      });
      if (r.error || !r.data) return bad(500, r.error?.message || "signup_tenant failed");
      const out = r.data as { tenant_id: string; profile_id: string };
      profileId = out.profile_id;
      tenantId = out.tenant_id;
    }
  }

  // 7. If --agent <slug> was passed, ensure that agent is in the profile's
  //    agents_enabled array. Lets the wizard idempotently extend an existing
  //    operator's enabled agents when they install a second agent.
  let agent_added = false;
  if (agentToAdd && VALID_AGENTS.has(agentToAdd)) {
    const cur = await db
      .from("user_profiles")
      .select("agents_enabled")
      .eq("id", profileId)
      .maybeSingle();
    const enabled = new Set<string>(cur.data?.agents_enabled || ["bravo"]);
    if (!enabled.has(agentToAdd)) {
      enabled.add(agentToAdd);
      await db
        .from("user_profiles")
        .update({ agents_enabled: Array.from(enabled) })
        .eq("id", profileId);
      agent_added = true;
    }
  }

  const client = await applyClientProvisioningProfile({
    db,
    tenantId,
    profileId,
    brand,
    email,
  });

  return NextResponse.json({
    ok: true,
    auth_user_id: authUserId,
    profile_id: profileId,
    tenant_id: tenantId,
    is_new_user: isNewUser,
    welcome_sent: welcomeSent,
    agent_added,
    requested_agent: agentToAdd || null,
    client_profile_slug: client.clientProfileSlug,
    primary_agent: client.primaryAgent,
    sign_in_url: (process.env.PUBLIC_APP_URL || "https://agent-dashboard-cc90210.vercel.app") + "/login",
  });
}
