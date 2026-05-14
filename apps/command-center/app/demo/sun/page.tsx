import { redirect } from "next/navigation";
import { SunBizDashboard } from "@/components/sunbiz/SunBizDashboard";
import { getSessionUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

/**
 * /demo/sun behaviour, Phase 5:
 *
 *   - Authenticated users → 302 to /t/sun. The real manifest-driven
 *     shell renders, sidebar nav works, every route under /t/sun/<path>
 *     dispatches via the catch-all renderer. The "demo mode" framing
 *     stops being a hack-shell and starts being a real tenant view.
 *   - Anonymous users → keep seeing the static SunBizDashboard preview.
 *     This is the marketing surface (no auth, public route per
 *     middleware.ts). The "Sign up" CTAs on that page push visitors
 *     into the authed product.
 *
 * Net effect: the operator (CC), or any SunBiz client signed in, gets
 * the working shell immediately. A marketing visitor gets a clean
 * preview of what SunBiz looks like without pretending to navigate.
 */
export default async function SunDemoPage() {
  const user = await getSessionUser().catch(() => null);
  if (user) {
    redirect("/t/sun");
  }
  return <SunBizDashboard demoMode />;
}
