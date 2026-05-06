import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { getActiveProfile } from "@/lib/queries";
import { getServiceSupabase } from "@/lib/supabase-server";

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
    pathname.startsWith("/login") ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/forgot-password") ||
    pathname.startsWith("/auth/callback") ||
    pathname.startsWith("/auth/reset-password") ||
    pathname.startsWith("/onboarding");

  let profile = null;
  let primaryAgentLive = false;
  let bridgeOnline = false;
  if (!isFullBleed) {
    // Each side-channel query is wrapped independently — one failure
    // (Hermes snapshot row missing, bridge_pairings table absent in dev,
    // RLS blocking a service-role call, etc.) must NOT take down the
    // whole layout. Failure mode prior to this hardening: any throw
    // here blanked the dashboard with a 500.
    try {
      profile = await getActiveProfile();
    } catch {
      profile = null;
    }
    const agent = profile?.primary_agent || "bravo";
    const tenantId = profile?.tenant_id || null;

    // Run agent-state + bridge lookups in parallel, isolated.
    const [snapRes, pairRes] = await Promise.all([
      (async () => {
        try {
          const db = getServiceSupabase();
          return await db
            .from("agent_state_snapshot")
            .select("last_tick_at")
            .eq("agent_name", agent)
            .maybeSingle();
        } catch {
          return { data: null };
        }
      })(),
      (async () => {
        if (!tenantId) return { data: null };
        try {
          const db = getServiceSupabase();
          return await db
            .from("bridge_pairings")
            .select("last_seen_at")
            .eq("tenant_id", tenantId)
            .is("revoked_at", null)
            .order("last_seen_at", { ascending: false })
            .limit(1)
            .maybeSingle();
        } catch {
          return { data: null };
        }
      })(),
    ]);
    const snap = snapRes.data as { last_tick_at?: string | null } | null;
    if (snap?.last_tick_at) {
      primaryAgentLive =
        Date.now() - new Date(snap.last_tick_at).getTime() < 15 * 60 * 1000;
    }
    const pair = pairRes.data as { last_seen_at?: string | null } | null;
    if (pair?.last_seen_at) {
      bridgeOnline =
        Date.now() - new Date(pair.last_seen_at).getTime() < 5 * 60 * 1000;
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
              brand={profile?.brand || "OASIS AI"}
              operatorName={profile?.display_name || profile?.full_name || "Operator"}
              operatorEmail={profile?.email}
              primaryAgent={profile?.primary_agent || "bravo"}
              primaryAgentLive={primaryAgentLive}
              bridgeOnline={bridgeOnline}
            />
            <main className="ml-60 min-h-screen relative z-10">
              <div className="mx-auto max-w-7xl px-8 py-8">{children}</div>
              <footer className="mx-auto max-w-7xl px-8 py-6 text-xs text-fg-faint">
                <div className="border-t border-bg-border pt-4 flex justify-between">
                  <span>OASIS AI · Agent Command Center · v1.0</span>
                  <span>"Only good things from now on."</span>
                </div>
              </footer>
            </main>
          </>
        )}
      </body>
    </html>
  );
}
