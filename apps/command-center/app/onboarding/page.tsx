import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

/**
 * Legacy /onboarding — deprecated. The canonical onboarding path is
 * /onboarding/wizard (industry-template flow). The bridge-pairing + API-key
 * setup the legacy flow used to bundle live in Settings now; this page is
 * kept as a thin redirect so any stale link, bookmark, or cached redirect
 * lands users at the right place.
 *
 * No operator-only branch anymore — even CC reaches Settings to manage
 * bridge pairings + API keys, not /onboarding.
 */
export default async function OnboardingPage() {
  const user = await getSessionUser().catch((err) => {
    console.error("[onboarding.session]", err);
    return null;
  });
  if (!user) redirect("/login?next=/onboarding/wizard");
  redirect("/onboarding/wizard");
}
