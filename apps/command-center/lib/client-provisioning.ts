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

  const isDedicated = clientProfileSlug === "sun" || clientProfileSlug === "suga";
  const customFields = {
    ...((tenantRes.data?.custom_fields || {}) as Record<string, unknown>),
    command_center_profile_slug: clientProfileSlug,
    data_backend: isDedicated ? "turso" : "supabase",
    deployment_mode: isDedicated ? "dedicated" : "shared",
  };

  const tenantUpdate = await db
    .from("tenants")
    .update({ custom_fields: customFields })
    .eq("id", tenantId);
  if (tenantUpdate.error) throw tenantUpdate.error;

  const profileAgentMap: Record<string, { primary: string; enabled: string[] }> = {
    sun: {
      // Operational primary (Solara) + sales-facing sub-agent (Helios).
      // Old config enabled "suga_sean" on the sun profile — that was a copy
      // mistake; SunBiz never shipped the Suga client agent.
      primary: "solara",
      enabled: ["solara", "helios"],
    },
    suga: {
      // Brand-command work folds into Maven (CMO). Lyra package retired
      // 2026-05-14 — single tenant doesn't justify a forked agent line.
      primary: "maven",
      enabled: ["maven"],
    },
  };
  const agentConfig = profileAgentMap[clientProfileSlug];
  const primaryAgent = agentConfig?.primary ?? null;

  if (primaryAgent) {
    const profileRes = await db
      .from("user_profiles")
      .select("agents_enabled")
      .eq("id", profileId)
      .maybeSingle();
    if (profileRes.error) throw profileRes.error;

    const agents = new Set<string>(profileRes.data?.agents_enabled || []);
    for (const agent of agentConfig.enabled) {
      agents.add(agent);
    }
    const profileUpdate = await db
      .from("user_profiles")
      .update({
        primary_agent: primaryAgent,
        agents_enabled: Array.from(agents),
        // Brand-hinted signups have already chosen their profile by
        // brand name; the industry-template wizard would just ask
        // redundant questions. Mark onboarding complete so middleware
        // doesn't bounce them through /onboarding/wizard.
        onboarding_completed_at: new Date().toISOString(),
      })
      .eq("id", profileId);
    if (profileUpdate.error) throw profileUpdate.error;

    return { clientProfileSlug, primaryAgent };
  }

  return { clientProfileSlug, primaryAgent: null };
}
