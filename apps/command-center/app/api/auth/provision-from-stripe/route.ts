/**
 * POST /api/auth/provision-from-stripe
 *
 * The bridge endpoint between the marketing site and the Command Center.
 * Called by oasis-ai-platform's Stripe webhook (api/stripe/webhook.ts) on
 * checkout.session.completed for Command-Center-eligible plans.
 *
 * Flow:
 *   1. Authenticate via shared bridge secret (BRIDGE_SECRET env)
 *   2. Look up auth.users by email; create if missing (with random password)
 *   3. Resolve or create the user_profile + tenant via signup_tenant RPC
 *   4. Stamp the Stripe customer_id + subscription_id on the tenant
 *   5. Send a magic-link / password-reset email so the customer can set
 *      their password
 *
 * Idempotent — re-firing for an existing user is a no-op.
 *
 * Body:
 *   {
 *     email: string,
 *     full_name?: string,
 *     brand?: string,
 *     stripe_customer_id?: string,
 *     stripe_subscription_id?: string,
 *     plan_tier?: string,
 *     send_welcome_email?: boolean    // default true
 *   }
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { randomBytes } from "crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

export async function POST(req: NextRequest) {
  // 1. Auth
  const auth = req.headers.get("authorization") || "";
  const expected = process.env.BRIDGE_SECRET;
  if (!expected || auth !== `Bearer ${expected}`) {
    return bad(401, "unauthorized");
  }

  // 2. Body
  let body: {
    email?: string;
    full_name?: string;
    brand?: string;
    stripe_customer_id?: string;
    stripe_subscription_id?: string;
    plan_tier?: string;
    send_welcome_email?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return bad(400, "invalid JSON");
  }
  const email = (body.email || "").trim().toLowerCase();
  if (!email || !email.includes("@")) return bad(400, "valid email required");

  const fullName = body.full_name?.trim() || email.split("@")[0];
  const brand = body.brand?.trim() || "OASIS AI";
  const planTier = body.plan_tier || "starter";

  const db = getServiceSupabase();

  // 3. Find or create auth user. Two creation paths:
  //    - send_welcome_email=true (default, real Stripe purchase): inviteUserByEmail
  //      creates the user AND emails a "set your password" link in one step.
  //    - send_welcome_email=false (smoke tests / silent provisioning):
  //      createUser with a random password, no email sent.
  const sendWelcome = body.send_welcome_email !== false;
  let authUserId: string | null = null;
  let isNewUser = false;
  try {
    const list = await db.auth.admin.listUsers();
    const existing = list.data?.users?.find(
      (u) => (u.email || "").toLowerCase() === email
    );
    if (existing) {
      authUserId = existing.id;
    } else if (sendWelcome) {
      const redirectTo =
        (process.env.PUBLIC_APP_URL?.replace(/\/$/, "") || "https://oasisai.work/app") +
        "/auth/reset-password";
      const invited = await db.auth.admin.inviteUserByEmail(email, {
        redirectTo,
        data: { full_name: fullName, brand, source: "stripe" },
      });
      if (invited.error || !invited.data?.user) {
        return bad(500, `auth invite failed: ${invited.error?.message || "unknown"}`);
      }
      authUserId = invited.data.user.id;
      isNewUser = true;
    } else {
      const tempPwd = randomBytes(24).toString("base64url");
      const created = await db.auth.admin.createUser({
        email,
        password: tempPwd,
        email_confirm: true,
        user_metadata: { full_name: fullName, brand, source: "stripe-silent" },
      });
      if (created.error || !created.data?.user) {
        return bad(500, `auth user create failed: ${created.error?.message || "unknown"}`);
      }
      authUserId = created.data.user.id;
      isNewUser = true;
    }
  } catch (e: unknown) {
    return bad(500, `auth admin error: ${e instanceof Error ? e.message : "unknown"}`);
  }

  // 4. Resolve or create profile + tenant
  let profileId: string | null = null;
  let tenantId: string | null = null;

  const byAuth = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", authUserId)
    .maybeSingle();
  if (byAuth.data) {
    profileId = byAuth.data.id;
    tenantId = byAuth.data.tenant_id;
  } else {
    // Maybe a profile by email exists from a prior manual seed — link it
    const byEmail = await db
      .from("user_profiles")
      .select("id, tenant_id")
      .eq("email", email)
      .maybeSingle();
    if (byEmail.data) {
      await db
        .from("user_profiles")
        .update({ auth_user_id: authUserId })
        .eq("id", byEmail.data.id);
      profileId = byEmail.data.id;
      tenantId = byEmail.data.tenant_id;
    } else {
      // Fresh: signup_tenant RPC creates tenant + profile atomically
      const r = await db.rpc("signup_tenant", {
        p_auth_user_id: authUserId,
        p_email: email,
        p_full_name: fullName,
        p_brand: brand,
      });
      if (r.error || !r.data) {
        return bad(500, `signup_tenant failed: ${r.error?.message || "unknown"}`);
      }
      const out = r.data as { tenant_id: string; profile_id: string };
      profileId = out.profile_id;
      tenantId = out.tenant_id;
    }
  }

  // 5. Stamp Stripe identifiers + activate the tenant
  if (tenantId) {
    const tenantUpdate: Record<string, unknown> = {
      purchase_status: "active",
      plan_tier: planTier,
    };
    if (body.stripe_customer_id) tenantUpdate.stripe_customer_id = body.stripe_customer_id;
    if (body.stripe_subscription_id)
      tenantUpdate.stripe_subscription_id = body.stripe_subscription_id;
    await db.from("tenants").update(tenantUpdate).eq("id", tenantId);
  }

  // 6. Welcome email status:
  //    - send_welcome_email=true + new user: inviteUserByEmail emailed the
  //      welcome + set-password link as part of step 3 above.
  //    - send_welcome_email=false: no email regardless.
  //    - Existing users: no email — they already have credentials and are
  //      just gaining a new tenant entitlement. The Stripe receipt covers
  //      the "you bought it" message.
  const welcomeSent = isNewUser && sendWelcome;

  return NextResponse.json({
    ok: true,
    auth_user_id: authUserId,
    profile_id: profileId,
    tenant_id: tenantId,
    welcome_sent: welcomeSent,
    is_new_user: isNewUser,
  });
}

export async function GET() {
  return bad(405, "POST only");
}
