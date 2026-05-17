/**
 * /onboarding/welcome — first-login personal-settings wizard for invitees.
 *
 * Phase C of the master multi-tenant infra plan (2026-05-17). After an
 * invitee redeems their invite via /invite/<token>, they land here for
 * a quick 3-step personalisation before being released to the dashboard.
 *
 * Step 1 — Confirm identity (name + display name + timezone)
 * Step 2 — Workspace preferences (default agent + daily-briefing channel)
 * Step 3 — Optional: connect a personal AI account (skippable; tenant
 *           default is used until they do)
 *
 * Re-entrant: existing employees can re-open the same wizard from
 * Settings → Personal. The middleware redirect only fires when
 * onboarding_completed_at is null AND invited_by is non-null (i.e. the
 * user joined via an invite and hasn't finished the wizard yet).
 *
 * Server component renders the shell + initial profile snapshot; client
 * component handles the multi-step form state.
 */

import { redirect } from "next/navigation";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getManifest } from "@/lib/manifest/loader";
import { OasisLogo } from "@/components/brand/OasisLogo";
import { WelcomeWizardClient } from "./WelcomeWizardClient";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default async function WelcomePage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const db = getServiceSupabase();
  const { data: profile } = await db
    .from("user_profiles")
    .select(
      "id, full_name, display_name, email, team_role, primary_agent, custom_fields, tenant_id, onboarding_completed_at, invited_by",
    )
    .eq("auth_user_id", user.id)
    .maybeSingle();

  if (!profile) {
    // No profile yet — bounce to /onboarding/wizard which handles the
    // fresh-tenant case. (Invitees should always have a profile because
    // the redeem RPC creates one.)
    redirect("/onboarding/wizard");
  }

  const tenant = profile.tenant_id
    ? (
        await db
          .from("tenants")
          .select("id, name, slug, custom_fields")
          .eq("id", profile.tenant_id)
          .maybeSingle()
      ).data
    : null;

  // Enabled agents for the operator's tenant — limits the "default agent"
  // dropdown to ones their workspace actually has. Falls back to a sane
  // pair if the manifest isn't seeded yet.
  const { data: manifest } = await db
    .from("tenant_manifests")
    .select("manifest")
    .eq("tenant_id", profile.tenant_id || "")
    .maybeSingle();
  let enabledAgents: string[] =
    Array.isArray(
      (manifest?.manifest as { agents?: Array<{ slug: string; enabled?: boolean }> } | null)?.agents,
    )
      ? ((manifest!.manifest as { agents: Array<{ slug: string; enabled?: boolean }> }).agents
          .filter((a) => a.enabled !== false)
          .map((a) => a.slug))
      : [];

  if (!enabledAgents.length && tenant) {
    const seedSlug = resolveClientProfileSlug(tenant);
    if (seedSlug) {
      const seedManifest = await getManifest(seedSlug).catch(() => null);
      enabledAgents =
        seedManifest?.agents
          .filter((agent) => agent.enabled !== false)
          .map((agent) => agent.slug) ?? [];
    }
  }

  if (!enabledAgents.length) enabledAgents = ["bravo"];

  return (
    <div className="min-h-screen bg-bg-deep flex flex-col items-center py-12 px-6">
      <div className="w-full max-w-2xl space-y-6">
        <div className="flex justify-center mb-4">
          <OasisLogo />
        </div>

        <header className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-fg">
            Welcome{profile.full_name ? `, ${profile.full_name.split(" ")[0]}` : ""}
          </h1>
          <p className="text-fg-muted text-sm">
            You&apos;ve joined{" "}
            <span className="text-fg font-semibold">{tenant?.name || "the workspace"}</span>. Let&apos;s
            set up your personal preferences — takes about a minute.
          </p>
        </header>

        <WelcomeWizardClient
          initialProfile={{
            full_name: profile.full_name || "",
            display_name: profile.display_name || "",
            primary_agent: profile.primary_agent || enabledAgents[0] || "bravo",
            custom_fields: (profile.custom_fields as Record<string, unknown>) || {},
          }}
          enabledAgents={enabledAgents}
          alreadyCompleted={!!profile.onboarding_completed_at}
        />
      </div>
    </div>
  );
}
