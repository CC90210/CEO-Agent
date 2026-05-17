import type { SupabaseClient } from "@supabase/supabase-js";
import { applyClientProvisioningProfile } from "@/lib/client-provisioning";

type ProvisionInput = {
  authUserId: string;
  email: string;
  fullName: string;
  brand?: string | null;
  db: SupabaseClient;
};

export type ProvisionResult = {
  ok: true;
  tenant_id: string;
  profile_id: string;
  slug?: string;
  already_provisioned?: boolean;
  client_profile_slug: string | null;
  primary_agent: string | null;
};

export async function provisionAuthenticatedUser({
  authUserId,
  email,
  fullName,
  brand,
  db,
}: ProvisionInput): Promise<ProvisionResult> {
  const existing = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", authUserId)
    .maybeSingle();

  if (existing.data) {
    const client = await applyClientProvisioningProfile({
      db,
      tenantId: existing.data.tenant_id,
      profileId: existing.data.id,
      brand,
      email,
    });
    return {
      ok: true,
      already_provisioned: true,
      tenant_id: existing.data.tenant_id,
      profile_id: existing.data.id,
      client_profile_slug: client.clientProfileSlug,
      primary_agent: client.primaryAgent,
    };
  }

  const byEmail = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("email", email)
    .maybeSingle();

  if (byEmail.data) {
    await db.from("user_profiles").update({ auth_user_id: authUserId }).eq("id", byEmail.data.id);
    const client = await applyClientProvisioningProfile({
      db,
      tenantId: byEmail.data.tenant_id,
      profileId: byEmail.data.id,
      brand,
      email,
    });
    return {
      ok: true,
      already_provisioned: true,
      tenant_id: byEmail.data.tenant_id,
      profile_id: byEmail.data.id,
      client_profile_slug: client.clientProfileSlug,
      primary_agent: client.primaryAgent,
    };
  }

  const r = await db.rpc("signup_tenant", {
    p_auth_user_id: authUserId,
    p_email: email,
    p_full_name: fullName,
    p_brand: brand || "OASIS AI",
  });

  if (r.error || !r.data) {
    throw new Error(r.error?.message || "provisioning failed");
  }

  const out = r.data as { tenant_id: string; profile_id: string; slug: string };
  const client = await applyClientProvisioningProfile({
    db,
    tenantId: out.tenant_id,
    profileId: out.profile_id,
    brand,
    email,
  });

  return {
    ok: true,
    ...out,
    client_profile_slug: client.clientProfileSlug,
    primary_agent: client.primaryAgent,
  };
}
