import { redirect } from "next/navigation";
import { SunBizDashboard } from "@/components/sunbiz/SunBizDashboard";
import { getSessionUser } from "@/lib/supabase-server";
import { requireTenantPreviewAccess } from "@/lib/tenant-access";

export const dynamic = "force-dynamic";

/**
 * /demo/sun behaviour:
 *
 *   - Anonymous visitors           → static SunBiz preview (marketing surface).
 *   - Authorized signed-in user    → /t/sun (empire op or SunBiz tenant).
 *   - Other signed-in operators    → bounce to / (no foreign-shell hijack).
 *
 * The bounce is what fixes the 2026-05-17 Google-login hijack: CC was
 * landing in SunBiz because this route used to redirect every authed
 * visitor straight to /t/sun.
 */
export default async function SunDemoPage() {
  const user = await getSessionUser().catch(() => null);
  if (!user) return <SunBizDashboard demoMode />;
  await requireTenantPreviewAccess("sun");
  // Returned normally — caller is authorized. Send them into the live
  // SunBiz shell. (Denied callers were redirected to / inside the gate.)
  redirect("/t/sun");
}
