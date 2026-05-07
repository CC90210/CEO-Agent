import Link from "next/link";
import { redirect } from "next/navigation";
import { Sparkles } from "lucide-react";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { OnboardingFlow } from "@/components/landing/OnboardingFlow";
import { PairingStatus } from "@/components/landing/PairingStatus";

export const dynamic = "force-dynamic";

const FRESH_MS = 5 * 60 * 1000;

async function _initialPaired(authUserId: string): Promise<boolean> {
  try {
    const db = getServiceSupabase();
    const { data: profile } = await db
      .from("user_profiles")
      .select("tenant_id")
      .eq("auth_user_id", authUserId)
      .maybeSingle();
    const tenantId = (profile?.tenant_id as string | null) || null;
    if (!tenantId) return false;
    const { data } = await db
      .from("bridge_pairings")
      .select("last_seen_at, revoked_at")
      .eq("tenant_id", tenantId)
      .is("revoked_at", null)
      .order("last_seen_at", { ascending: false })
      .limit(1);
    const last = data?.[0]?.last_seen_at as string | null | undefined;
    if (!last) return false;
    return Date.now() - new Date(last).getTime() < FRESH_MS;
  } catch {
    return false;
  }
}

export default async function OnboardingPage() {
  const user = await getSessionUser().catch(() => null);
  if (!user) redirect("/login?next=/onboarding");
  const initialPaired = await _initialPaired(user.id);

  return (
    <main className="min-h-screen bg-bg-deep relative overflow-hidden">
      {/* Aurora */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-[20%] left-1/2 -translate-x-1/2 w-[1200px] h-[700px] rounded-full opacity-30 blur-3xl"
             style={{ background: "radial-gradient(circle, rgba(59,130,246,0.4), transparent 70%)" }} />
      </div>

      {/* Nav */}
      <header className="relative z-10 mx-auto max-w-5xl px-6 py-5 flex items-center justify-between">
        <Link href="/welcome" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-gradient-to-br from-accent to-cyan-400 shadow-[0_0_20px_-2px_rgba(0,212,255,0.6)]">
            <span className="text-bg-deep font-black text-sm">O</span>
          </div>
          <div className="leading-none">
            <div className="font-black text-fg tracking-tight text-sm">OASIS AI</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-fg-dim">Setup</div>
          </div>
        </Link>
        <Link href="/" className="text-xs text-fg-muted hover:text-fg transition-colors">
          Skip for now →
        </Link>
      </header>

      <section className="relative z-10 mx-auto max-w-3xl px-6 py-8 pb-20">
        <div className="mb-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/5 px-3 py-1 text-xs text-accent mb-4">
            <Sparkles className="w-3 h-3" /> Welcome aboard
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-fg leading-tight tracking-tight">
            Three quick steps to your first chat.
          </h1>
          <p className="mt-3 text-fg-muted">
            Pick how to power your agents, paste a key, optionally pair your machine for file access. Each step is optional — you can change everything later in Settings.
          </p>
        </div>

        <div className="mb-6">
          <PairingStatus initialPaired={initialPaired} />
        </div>

        <OnboardingFlow userEmail={user.email || ""} />
      </section>
    </main>
  );
}
