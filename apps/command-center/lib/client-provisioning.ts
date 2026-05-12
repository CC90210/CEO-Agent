import type { SupabaseClient } from "@supabase/supabase-js";
import { getClientProfileSlugForBrand } from "./client-profiles";

type ProvisioningInput = {
  db: SupabaseClient;
  tenantId: string;
  profileId: string;
  brand?: string | null;
  email?: string | null;
};

export async function applyClientProvisioningProfile({
  db,
  tenantId,
  profileId,
  brand,
  email,
}: ProvisioningInput): Promise<{ clientProfileSlug: string | null; primaryAgent: string | null }> {
  const clientProfileSlug = getClientProfileSlugForBrand(brand, email);
  if (!clientProfileSlug) {
    return { clientProfileSlug: null, primaryAgent: null };
  }

  const tenantRes = await db
    .from("tenants")
    .select("custom_fields")
    .eq("id", tenantId)
    .maybeSingle();
  if (tenantRes.error) throw tenantRes.error;

  const customFields = {
    ...((tenantRes.data?.custom_fields || {}) as Record<string, unknown>),
    command_center_profile_slug: clientProfileSlug,
    data_backend: clientProfileSlug === "sun" ? "turso" : "supabase",
    deployment_mode: clientProfileSlug === "sun" ? "dedicated" : "shared",
  };

  const tenantUpdate = await db
    .from("tenants")
    .update({ custom_fields: customFields })
    .eq("id", tenantId);
  if (tenantUpdate.error) throw tenantUpdate.error;

  if (clientProfileSlug === "sun") {
    const profileRes = await db
      .from("user_profiles")
      .select("agents_enabled")
      .eq("id", profileId)
      .maybeSingle();
    if (profileRes.error) throw profileRes.error;

    const agents = new Set<string>(profileRes.data?.agents_enabled || []);
    agents.add("sunbiz");
    const profileUpdate = await db
      .from("user_profiles")
      .update({
        primary_agent: "sunbiz",
        agents_enabled: Array.from(agents),
      })
      .eq("id", profileId);
    if (profileUpdate.error) throw profileUpdate.error;

    return { clientProfileSlug, primaryAgent: "sunbiz" };
  }

  return { clientProfileSlug, primaryAgent: null };
}
