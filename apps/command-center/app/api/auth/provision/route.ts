/**
 * POST /api/auth/provision
 *
 * Idempotent: creates a tenant + user_profile pair for a Supabase Auth user.
 * Called from the signup form (email/password) and from /auth/callback (OAuth).
 *
 * Body: { auth_user_id, email, full_name, brand }
 * Returns: { ok, tenant_id, profile_id, slug, already_provisioned? }
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { applyClientProvisioningProfile } from "@/lib/client-provisioning";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  let body: { auth_user_id?: string; email?: string; full_name?: string; brand?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { auth_user_id, email, full_name, brand } = body;
  if (!auth_user_id || !email || !full_name) {
    return NextResponse.json(
      { error: "auth_user_id, email, full_name required" },
      { status: 400 }
    );
  }

  const db = getServiceSupabase();

  // Idempotent: already linked?
  const existing = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", auth_user_id)
    .maybeSingle();
  if (existing.data) {
    const client = await applyClientProvisioningProfile({
      db,
      tenantId: existing.data.tenant_id,
      profileId: existing.data.id,
      brand,
      email,
    });
    return NextResponse.json({
      ok: true,
      already_provisioned: true,
      tenant_id: existing.data.tenant_id,
      profile_id: existing.data.id,
      client_profile_slug: client.clientProfileSlug,
      primary_agent: client.primaryAgent,
    });
  }

  // Or maybe a profile exists by email but auth wasn't linked yet (CC's case post-migration)
  const byEmail = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("email", email)
    .maybeSingle();
  if (byEmail.data) {
    await db.from("user_profiles").update({ auth_user_id }).eq("id", byEmail.data.id);
    const client = await applyClientProvisioningProfile({
      db,
      tenantId: byEmail.data.tenant_id,
      profileId: byEmail.data.id,
      brand,
      email,
    });
    return NextResponse.json({
      ok: true,
      already_provisioned: true,
      tenant_id: byEmail.data.tenant_id,
      profile_id: byEmail.data.id,
      client_profile_slug: client.clientProfileSlug,
      primary_agent: client.primaryAgent,
    });
  }

  // Fresh signup — call the signup_tenant RPC
  const r = await db.rpc("signup_tenant", {
    p_auth_user_id: auth_user_id,
    p_email: email,
    p_full_name: full_name,
    p_brand: brand || "OASIS AI",
  });
  if (r.error || !r.data) {
    return NextResponse.json(
      { error: r.error?.message || "provisioning failed" },
      { status: 500 }
    );
  }

  const out = r.data as { tenant_id: string; profile_id: string; slug: string };
  const client = await applyClientProvisioningProfile({
    db,
    tenantId: out.tenant_id,
    profileId: out.profile_id,
    brand,
    email,
  });
  return NextResponse.json({
    ok: true,
    ...out,
    client_profile_slug: client.clientProfileSlug,
    primary_agent: client.primaryAgent,
  });
}
