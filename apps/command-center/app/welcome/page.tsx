import Link from "next/link";
import { ArrowRight, Bot, Cpu, Zap, ShieldCheck, Sparkles, Globe2 } from "lucide-react";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

export default async function WelcomePage() {
  // Already signed in? Send them to the dashboard.
  const user = await getSessionUser().catch(() => null);
  if (user) redirect("/");

  return (
    <main className="min-h-screen bg-bg-deep relative overflow-hidden">
      {/* Aurora backdrop */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-[20%] left-1/2 -translate-x-1/2 w-[1400px] h-[800px] rounded-full opacity-40 blur-3xl"
             style={{ background: "radial-gradient(circle, rgba(59,130,246,0.4), rgba(0,212,255,0.2) 40%, transparent 70%)" }} />
        <div className="absolute bottom-[-10%] right-[-10%] w-[800px] h-[600px] rounded-full opacity-30 blur-3xl"
             style={{ background: "radial-gradient(circle, rgba(0,212,255,0.35), transparent 70%)" }} />
        <div className="absolute inset-0 opacity-[0.04]"
             style={{
               backgroundImage:
                 "linear-gradient(#3b82f6 1px, transparent 1px), linear-gradient(90deg, #3b82f6 1px, transparent 1px)",
               backgroundSize: "48px 48px",
             }} />
      </div>

      {/* Top nav */}
      <header className="relative z-10 mx-auto max-w-7xl px-6 sm:px-10 py-6 flex items-center justify-between">
        <Link href="/welcome" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-gradient-to-br from-accent to-cyan-400 shadow-[0_0_20px_-2px_rgba(0,212,255,0.6)] group-hover:shadow-[0_0_28px_-2px_rgba(0,212,255,0.8)] transition-shadow">
            <span className="text-bg-deep font-black text-sm">O</span>
          </div>
          <div className="leading-none">
            <div className="font-black text-fg tracking-tight">OASIS AI</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-fg-dim">Agent Command Center</div>
          </div>
        </Link>
        <nav className="flex items-center gap-3 sm:gap-5">
          <a href="https://oasisai.work" target="_blank" rel="noopener noreferrer"
             className="text-sm text-fg-muted hover:text-fg transition-colors hidden sm:inline-flex items-center gap-1">
            oasisai.work <Globe2 className="w-3.5 h-3.5" />
          </a>
          <Link href="/login" className="text-sm text-fg-muted hover:text-fg transition-colors">
            Sign in
          </Link>
          <Link href="/signup" className="btn-send !px-3.5 !py-2 text-xs">
            Get started <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="relative z-10 mx-auto max-w-7xl px-6 sm:px-10 pt-12 pb-24">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/5 px-3 py-1 text-xs text-accent mb-6">
            <Sparkles className="w-3 h-3" /> Built by OASIS AI · Multi-agent ops, one console
          </div>
          <h1 className="text-5xl sm:text-7xl font-black text-fg leading-[1.05] tracking-tight">
            Your AI agents,{" "}
            <span className="bg-gradient-to-r from-accent via-cyan-400 to-accent bg-clip-text text-transparent">
              one command center.
            </span>
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-fg-muted leading-relaxed max-w-2xl">
            Chat with Bravo, Maven, Atlas, Aura, or Hermes from a single dashboard. Bring your own API key — Claude, GPT, Gemini, OpenRouter — and switch models per agent. Pipeline, analytics, integrations, and live event bus included.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link href="/configure" className="btn-send !px-5 !py-3 text-sm">
              Configure your own agent <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/login" className="btn-secondary !px-5 !py-3 text-sm">
              Sign in
            </Link>
            <a href="https://oasisai.work" target="_blank" rel="noopener noreferrer"
               className="text-sm text-fg-muted hover:text-fg transition-colors">
              Visit oasisai.work →
            </a>
          </div>
          <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-xs text-fg-dim">
            <span>✓ No credit card</span>
            <span>✓ Bring your own keys</span>
            <span>✓ Open source ready</span>
            <span>✓ Multi-tenant secure</span>
          </div>
        </div>
      </section>

      {/* Feature grid */}
      <section className="relative z-10 mx-auto max-w-7xl px-6 sm:px-10 pb-24">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <FeatureCard
            icon={<Bot className="w-5 h-5" />}
            title="One chat, every agent"
            body="Switch between Bravo, Maven, Atlas, Aura, Hermes mid-conversation. Each runs its own provider + model, configured by you."
          />
          <FeatureCard
            icon={<Cpu className="w-5 h-5" />}
            title="Bring your own model"
            body="OpenRouter for one-key access to every model, or wire Anthropic / OpenAI / Gemini directly. Per-agent overrides supported."
          />
          <FeatureCard
            icon={<Zap className="w-5 h-5" />}
            title="Real-time streaming"
            body="Token-by-token responses. Live event bus tape. Zero placeholders — every dot pulses on actual activity."
          />
          <FeatureCard
            icon={<ShieldCheck className="w-5 h-5" />}
            title="Encrypted at rest"
            body="API keys encrypted with AES-256-GCM before they touch the database. Your tenant data is RLS-isolated end-to-end."
          />
          <FeatureCard
            icon={<Sparkles className="w-5 h-5" />}
            title="Pipeline + analytics built-in"
            body="Outbound and inbound funnel, lead sources, MRR trajectory, integrations health — wired to real Postgres, not screenshots."
          />
          <FeatureCard
            icon={<Globe2 className="w-5 h-5" />}
            title="Connect everything"
            body="24+ integrations from one settings page. Click any service, sign up, paste your key — instantly wired into the stack."
          />
        </div>
      </section>

      {/* CTA strip */}
      <section className="relative z-10 mx-auto max-w-5xl px-6 sm:px-10 pb-24">
        <div className="rounded-2xl border border-accent/30 bg-gradient-to-br from-accent/10 via-bg-elev/40 to-cyan-500/10 backdrop-blur-xl p-8 sm:p-10 relative overflow-hidden">
          <div aria-hidden className="absolute inset-0 opacity-30 pointer-events-none"
               style={{ background: "radial-gradient(800px 200px at 50% 0%, rgba(0,212,255,0.4), transparent)" }} />
          <div className="relative">
            <h2 className="text-2xl sm:text-3xl font-black text-fg leading-tight">
              Spin up your command center in under five minutes.
            </h2>
            <p className="mt-3 text-fg-muted">
              Sign up, paste an OpenRouter key, pick your primary agent. Add a local pairing later for full file-system access — totally optional.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link href="/signup" className="btn-send !px-5 !py-3 text-sm">
                Create your account <ArrowRight className="w-4 h-4" />
              </Link>
              <a href="https://openrouter.ai/sign-up" target="_blank" rel="noopener noreferrer"
                 className="btn-secondary !px-5 !py-3 text-sm">
                Get an OpenRouter key
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 mx-auto max-w-7xl px-6 sm:px-10 py-8 border-t border-bg-border flex flex-wrap items-center justify-between gap-3 text-xs text-fg-dim">
        <span>© {new Date().getFullYear()} OASIS AI · Conaugh McKenna · Collingwood ON</span>
        <div className="flex items-center gap-5">
          <a href="https://oasisai.work" target="_blank" rel="noopener noreferrer" className="hover:text-fg transition-colors">
            oasisai.work
          </a>
          <Link href="/login" className="hover:text-fg transition-colors">Sign in</Link>
          <Link href="/signup" className="hover:text-fg transition-colors">Sign up</Link>
        </div>
      </footer>
    </main>
  );
}

function FeatureCard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="group rounded-xl border border-bg-border bg-bg-elev/50 backdrop-blur p-5 hover:border-accent/40 hover:bg-bg-elev transition-all hover:shadow-[0_0_28px_-12px_rgba(0,212,255,0.4)]">
      <div className="w-9 h-9 rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center text-accent mb-3 group-hover:bg-accent/25 transition-colors">
        {icon}
      </div>
      <h3 className="text-sm font-bold text-fg mb-1.5 tracking-tight">{title}</h3>
      <p className="text-xs text-fg-muted leading-relaxed">{body}</p>
    </div>
  );
}
