import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { getActiveProfile } from "@/lib/queries";
import { getServiceSupabase } from "@/lib/supabase-server";
import { unreadCountDb } from "@/lib/agent-inbox-db";
import { safe } from "@/lib/api-helpers";
import { getNavForTenant, getSubtitleForTenant } from "@/lib/nav-config";

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
  let inboxUnread = 0;
  let tenantSlug: string | null = null;
  if (!isFullBleed) {
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
    const emptySnap: { data: { last_tick_at?: string | null } | null } = { data: null };
    const emptyPair: { data: { last_seen_at?: string | null } | null } = { data: null };
    const [snapRes, pairRes] = await Promise.all([
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
      tenantId
        ? safe(
            "layout.bridge_pairings",
            (async () => {
              const db = getServiceSupabase();
              const r = await db
                .from("bridge_pairings")
                .select("last_seen_at")
                .eq("tenant_id", tenantId)
                .is("revoked_at", null)
                .order("last_seen_at", { ascending: false })
                .limit(1)
                .maybeSingle();
              return { data: r.data as { last_seen_at?: string | null } | null };
            })(),
            emptyPair
          )
        : Promise.resolve(emptyPair),
    ]);
    const snap = snapRes.data;
    if (snap?.last_tick_at) {
      primaryAgentLive =
        Date.now() - new Date(snap.last_tick_at).getTime() < 15 * 60 * 1000;
    }
    const pair = pairRes.data;
    if (pair?.last_seen_at) {
      bridgeOnline =
        Date.now() - new Date(pair.last_seen_at).getTime() < 5 * 60 * 1000;
    }
    if (tenantId) {
      inboxUnread = await safe("layout.inbox_unread", unreadCountDb(tenantId), 0);
      // Resolve tenant slug for tenant-aware sidebar nav. One extra cheap
      // query — guarded by safe() so an RLS hiccup never blanks the shell.
      tenantSlug = await safe(
        "layout.tenant_slug",
        (async () => {
          const db = getServiceSupabase();
          const r = await db
            .from("tenants")
            .select("slug")
            .eq("id", tenantId)
            .maybeSingle();
          return (r.data as { slug?: string } | null)?.slug || null;
        })(),
        null
      );
    }
  }

  return (
    <html lang="en">
      <body className="grain">
        {isFullBleed ? (
          children
        ) : (
          <>
            <Sidebar
              brand={profile?.brand || (tenantSlug === "sun" ? "Sun Biz Funding" : "OASIS AI")}
              subtitle={getSubtitleForTenant(tenantSlug)}
              items={getNavForTenant(tenantSlug)}
              operatorName={profile?.display_name || profile?.full_name || "Operator"}
              operatorEmail={profile?.email}
              primaryAgent={profile?.primary_agent || (tenantSlug === "sun" ? "sunbiz" : "bravo")}
              primaryAgentLive={primaryAgentLive}
              bridgeOnline={bridgeOnline}
              inboxUnread={inboxUnread}
            />
            <main className="ml-60 min-h-screen relative z-10">
              <div className="mx-auto max-w-7xl px-8 py-8">{children}</div>
              <footer className="mx-auto max-w-7xl px-8 py-6 text-xs text-fg-faint">
                <div className="border-t border-bg-border pt-4 flex justify-between">
                  <span>
                    {tenantSlug === "sun"
                      ? "Sun Biz Funding · Operations Command · v1.0"
                      : "OASIS AI · Agent Command Center · v1.0"}
                  </span>
                  <span>{tenantSlug === "sun" ? "Funded deals over noise." : '"Only good things from now on."'}</span>
                </div>
              </footer>
            </main>
          </>
        )}
      </body>
    </html>
  );
}
