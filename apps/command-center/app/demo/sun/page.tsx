import { redirect } from "next/navigation";
import { SunBizDashboard } from "@/components/sunbiz/SunBizDashboard";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { isOperatorEmail } from "@/lib/operator-credentials";
import { canPreviewTenantSlug } from "@/lib/tenant-access";

export const dynamic = "force-dynamic";

/**
 * /demo/sun behaviour:
 *
 *   - Anonymous visitors  → static SunBiz preview (marketing surface).
 *   - Empire operator (CC) → redirect into the real /t/sun shell.
 *   - Signed-in operator on a different tenant → redirect to `/` so we
 *     don't hijack their shell with another tenant's Command Center
 *     (2026-05-17 incident: Google login → SunBiz hijack).
 *   - SunBiz tenant operator → /t/sun (their own tenant, legitimate).
 */
export default async function SunDemoPage() {
  const user = await getSessionUser().catch(() => null);
  if (!user) {
    return <SunBizDashboard demoMode />;
  }
  if (isOperatorEmail(user.email)) {
    redirect("/t/sun");
  }
  // Look up the operator's own tenant to decide whether they can see /t/sun.
  // Service-role read is cheap and the page is already force-dynamic.
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
  if (
    canPreviewTenantSlug(
      {
        email: profile.data?.email ?? user.email,
        tenant_slug: tenantSlug,
        command_center_profile_slug: commandSlug,
      },
      "sun",
    )
  ) {
    redirect("/t/sun");
  }
  redirect("/");
}
