import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { getActiveProfile, getBridgeOnline } from "@/lib/queries";
import { getServiceSupabase } from "@/lib/supabase-server";
import { safe } from "@/lib/api-helpers";
import {
  DEMO_CLIENT_PROFILE_COOKIE,
  resolveClientProfileSlug,
} from "@/lib/client-profiles";
import {
  getManifest,
  manifestExists,
  manifestLogoToSidebarLogo,
  manifestNavToNavItems,
  manifestPrimaryAgentSlug,
} from "@/lib/manifest/loader";
import { SEED_MANIFESTS } from "@/lib/manifest/seeds";

export const metadata: Metadata = {
  title: "OASIS AI · Agent Command Center",
  description:
    "The operating system for your AI agents. Outbound, inbound, decisions, pipeline, and the daily ops plan — all in one place.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Auth + marketing pages render their own full-screen layouts; skip the
  // sidebar shell. The pathname is set as a header by middleware.ts.
  const hdrs = await headers();
  const pathname = hdrs.get("x-pathname") || hdrs.get("x-invoke-path") || "";
  const isFullBleed =
    pathname.startsWith("/welcome") ||
    pathname.startsWith("/download") ||
    pathname.startsWith("/configure") ||
    pathname.startsWith("/login") ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/forgot-password") ||
    pathname.startsWith("/auth/callback") ||
    pathname.startsWith("/auth/reset-password") ||
    pathname.startsWith("/onboarding");

  let profile = null;
  let primaryAgentLive = false;
  let bridgeOnline = false;
  let tenantProfileSlug: string | null = null;
  let demoProfileSlug: string | null = null;
  let pathOverrideSlug: string | null = null;
  if (!isFullBleed) {
    const cookieStore = await cookies();
    // Path-based tenant slug (Phase 1): `/t/<slug>/...` URLs anchor the shell to
    // that tenant's manifest regardless of the viewer's home tenant. Demo paths
    // still take precedence — `/demo/sun` is the public, auth-free preview.
    const tSlugMatch = pathname.match(/^\/t\/([a-z0-9][a-z0-9_-]{1,62})(?:\/|$)/i);
    const pathTenantSlug = tSlugMatch ? tSlugMatch[1].toLowerCase() : null;
    const requestedDemoProfile =
      pathname.startsWith("/demo/sun")
        ? "sun"
        : cookieStore.get(DEMO_CLIENT_PROFILE_COOKIE)?.value || null;
    const normalisedDemo = (requestedDemoProfile || "").trim().toLowerCase();
    demoProfileSlug =
      normalisedDemo && normalisedDemo !== "default" && SEED_MANIFESTS[normalisedDemo]
        ? normalisedDemo
        : null;
    // Path slug wins when present and not in demo. Lets `/t/<slug>/...` render
    // that tenant's manifest for any operator previewing it. Validates via
    // manifestExists so wizard-created DB-only slugs are honoured too — not
    // just the in-code seeds (the bug the Phase 2 wizard would have hit).
    if (!demoProfileSlug && pathTenantSlug) {
      const exists = await manifestExists(pathTenantSlug);
      if (exists) pathOverrideSlug = pathTenantSlug;
    }

    // Each side-channel query is wrapped independently — one failure
    // (Hermes snapshot row missing, bridge_pairings table absent in dev,
    // RLS blocking a service-role call, etc.) must NOT take down the
    // whole layout. Failure mode prior to this hardening: any throw
    // here blanked the dashboard with a 500. Each catch logs via safe()
    // so a stuck sidebar indicator is searchable in Vercel logs instead
    // of silently rendering as "offline".
    profile = await safe("layout.profile", getActiveProfile(), null);
    const agent = profile?.primary_agent || "bravo";
    const tenantId = profile?.tenant_id || null;

    // Run agent-state + bridge lookups in parallel, isolated.
    // Bridge-online check uses the shared getBridgeOnline() helper so the
    // header dot, Settings page, and any future caller agree on what
    // "online" means (last_seen_at within 5 minutes, revoked_at IS NULL).
    const emptySnap: { data: { last_tick_at?: string | null } | null } = { data: null };
    const [snapRes, bridgeOnlineResolved] = await Promise.all([
      safe(
        "layout.agent_state_snapshot",
        (async () => {
          const db = getServiceSupabase();
          const r = await db
            .from("agent_state_snapshot")
            .select("last_tick_at")
            .eq("agent_name", agent)
            .maybeSingle();
          return { data: r.data as { last_tick_at?: string | null } | null };
        })(),
        emptySnap
      ),
      safe("layout.bridge_online", getBridgeOnline(tenantId), false),
    ]);
    const snap = snapRes.data;
    if (snap?.last_tick_at) {
      primaryAgentLive =
        Date.now() - new Date(snap.last_tick_at).getTime() < 15 * 60 * 1000;
    }
    bridgeOnline = bridgeOnlineResolved;
    if (tenantId) {
      // Resolve the dashboard/client profile slug. Tenants can override the
      // raw tenant slug via tenants.custom_fields.command_center_profile_slug
      // so one command-center shell can render different products cleanly.
      tenantProfileSlug = await safe(
        "layout.tenant_profile_slug",
        (async () => {
          const db = getServiceSupabase();
          const r = await db
            .from("tenants")
            .select("slug, custom_fields")
            .eq("id", tenantId)
            .maybeSingle();
          const tenant = (r.data as { slug?: string; custom_fields?: Record<string, unknown> | null } | null);
          return resolveClientProfileSlug({
            slug: tenant?.slug || "",
            custom_fields: tenant?.custom_fields || {},
          });
        })(),
        null
      );
    }
  }
  const demoMode = !!demoProfileSlug;
  const manifestSlug = demoMode
    ? demoProfileSlug
    : pathOverrideSlug ?? tenantProfileSlug;
  const manifest = isFullBleed ? null : await getManifest(manifestSlug);

  return (
    <html lang="en">
      <body className="grain">
        {isFullBleed || !manifest ? (
          children
        ) : (
          <>
            <Sidebar
              brand={demoMode ? manifest.brand.name : profile?.brand || manifest.brand.name}
              logo={manifestLogoToSidebarLogo(manifest.brand.logo)}
              subtitle={manifest.brand.subtitle}
              items={manifestNavToNavItems(manifest.nav)}
              operatorName={
                demoMode
                  ? "Sun Demo Operator"
                  : profile?.display_name || profile?.full_name || "Operator"
              }
              operatorEmail={demoMode ? "demo@sunbizfunding.com" : profile?.email}
              primaryAgent={
                demoMode
                  ? manifestPrimaryAgentSlug(manifest)
                  : profile?.primary_agent || manifestPrimaryAgentSlug(manifest)
              }
              primaryAgentLive={demoMode ? false : primaryAgentLive}
              bridgeOnline={demoMode ? false : bridgeOnline}
              demoMode={demoMode}
              demoLabel={`${manifest.brand.name} demo`}
            />
            <main className="ml-60 min-h-screen relative z-10">
              <div className="mx-auto max-w-7xl px-8 py-8">{children}</div>
              <footer className="mx-auto max-w-7xl px-8 py-6 text-xs text-fg-faint">
                <div className="border-t border-bg-border pt-4 flex justify-between">
                  <span>{manifest.brand.footer_label}</span>
                  <span>{manifest.brand.footer_tagline}</span>
                </div>
              </footer>
            </main>
          </>
        )}
      </body>
    </html>
  );
}
