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
import { isOperatorEmail } from "./operator-credentials";

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
