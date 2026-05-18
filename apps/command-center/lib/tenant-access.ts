/**
 * Tenant-preview access gate.
 *
 * `/t/<slug>` and the `/demo/sun` redirect into `/t/sun` were rendering ANY
 * tenant's shell to ANY signed-in user — so CC logging into the OASIS portal
 * with Google could land on the SunBiz Command Center (2026-05-17 incident).
 *
 * Rule:
 *   - Empire operators (OPERATOR_EMAIL / ADMIN_EMAILS) can preview any slug.
 *   - Every other operator may only preview slugs that match their own
 *     tenant's slug or their command_center_profile_slug.
 *
 * Service-role read of the tenants row stays out of the hot path: the layout
 * already has the profile + tenant slug; this helper just compares strings.
 */
import { redirect } from "next/navigation";
import { isOperatorEmail } from "./operator-credentials";
import { getServiceSupabase, getSessionUser } from "./supabase-server";

export type TenantAccessProfile = {
  email?: string | null;
  tenant_slug?: string | null;
  command_center_profile_slug?: string | null;
};

export function canPreviewTenantSlug(
  profile: TenantAccessProfile | null | undefined,
  slug: string | null | undefined,
): boolean {
  const target = (slug || "").trim().toLowerCase();
  if (!target) return false;
  if (!profile) return false;
  if (isOperatorEmail(profile.email)) return true;
  const own = (profile.tenant_slug || "").trim().toLowerCase();
  if (own && own === target) return true;
  const profileSlug = (profile.command_center_profile_slug || "").trim().toLowerCase();
  if (profileSlug && profileSlug === target) return true;
  return false;
}

/**
 * Server-side gate for /t/<slug> pages and /demo/sun. Looks up the signed-in
 * operator's tenant, applies canPreviewTenantSlug, and redirects when access
 * is denied. Throws via Next's redirect() — callers don't need to handle
 * the negative case.
 */
export async function requireTenantPreviewAccess(slug: string): Promise<void> {
  const target = slug.toLowerCase();
  const user = await getSessionUser().catch(() => null);
  if (!user) {
    redirect(`/login?next=${encodeURIComponent(`/t/${target}`)}`);
  }
  const db = getServiceSupabase();
  const profile = await db
    .from("user_profiles")
    .select("email, tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = profile.data?.tenant_id || null;
  let tenantSlug: string | null = null;
  let commandSlug: string | null = null;
  if (tenantId) {
    const t = await db
      .from("tenants")
      .select("slug, custom_fields")
      .eq("id", tenantId)
      .maybeSingle();
    tenantSlug = (t.data?.slug as string | undefined) ?? null;
    const custom = (t.data?.custom_fields || {}) as Record<string, unknown>;
    const cf = custom.command_center_profile_slug;
    commandSlug = typeof cf === "string" ? cf : null;
  }
  const allowed = canPreviewTenantSlug(
    {
      email: profile.data?.email ?? user.email,
      tenant_slug: tenantSlug,
      command_center_profile_slug: commandSlug,
    },
    target,
  );
  if (!allowed) redirect("/");
}
