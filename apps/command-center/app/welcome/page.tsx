import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { FEATURES, VERTICALS } from "@/lib/marketing-data";
import { ArrowRight, CheckCircle2, Phone, Mail, Calendar, Database, Zap } from "lucide-react";

export const dynamic = "force-static";

export const metadata = {
  title: "OASIS AI · The Operating System for AI Agents",
  description:
    "We build AI automations for service businesses, professionals, real estate, and e-commerce. Free 14-day pilot — only pay if it works.",
};

export default function WelcomePage() {
  return (
    <MarketingShell>
      <Hero />
      <Stats />
      <FeatureGrid />
      <VerticalsBlock />
      <ClosingCTA />
    </MarketingShell>
  );
}

function Hero() {
  return (
    <section className="relative pt-24 pb-32 px-6">
      <div className="mx-auto max-w-5xl text-center">
        <div className="inline-flex items-center gap-2 bg-accent-soft border border-accent-muted/30 rounded-full px-4 py-1.5 text-xs font-semibold text-accent mb-8">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse-slow" />
          14-day free pilot · pay only if it works
        </div>
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-fg leading-tight">
          The operating system for{" "}
          <span className="bg-gradient-to-r from-accent to-accent-muted bg-clip-text text-transparent">
            AI agents
          </span>
        </h1>
        <p className="mt-6 text-lg md:text-xl text-fg-muted max-w-2xl mx-auto leading-relaxed">
          We build AI automations that run your business — booking, follow-ups, lead routing, customer service. You watch them work in your live Command Center.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/pricing"
            className="group bg-accent text-bg font-bold px-7 py-3.5 rounded-md hover:bg-accent-muted transition-all flex items-center gap-2 shadow-glow"
          >
            Start your free pilot
            <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
          </Link>
          <Link
            href="/contact"
            className="text-fg-muted hover:text-fg font-medium px-6 py-3.5 transition-colors"
          >
            Book a 15-min call →
          </Link>
        </div>
        <div className="mt-12 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-xs text-fg-dim">
          <Trust>SOC-2 ready architecture</Trust>
          <Trust>Multi-tenant + RLS</Trust>
          <Trust>Average 312% ROI in 90 days</Trust>
        </div>
      </div>
    </section>
  );
}

function Trust({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <CheckCircle2 size={14} className="text-status-engaged" />
      <span>{children}</span>
    </div>
  );
}

function Stats() {
  const stats = [
    { value: "14", label: "Free pilot days, no card needed" },
    { value: "5+", label: "Hours saved per process per week" },
    { value: "312%", label: "Average client ROI in 90 days" },
    { value: "100%", label: "Risk-on-us pilot guarantee" },
  ];
  return (
    <section className="border-y border-bg-border bg-bg-panel">
      <div className="mx-auto max-w-7xl px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-6">
        {stats.map((s) => (
          <div key={s.label} className="text-center">
            <div className="text-3xl md:text-4xl font-bold text-accent tracking-tight">
              {s.value}
            </div>
            <div className="text-xs text-fg-muted mt-1.5">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function FeatureGrid() {
  return (
    <section className="px-6 py-24">
      <div className="mx-auto max-w-7xl">
        <div className="text-center mb-16">
          <div className="text-xs uppercase tracking-[0.18em] font-bold text-accent mb-3">
            What you get
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-fg tracking-tight">
            Built different. Built better.
          </h2>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {FEATURES.map((f, i) => (
            <div
              key={f.title}
              className="bg-bg-panel border border-bg-border rounded-xl p-6 hover:border-accent-muted/40 transition-all"
            >
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-accent-soft border border-accent-muted/30 flex items-center justify-center shrink-0 text-accent font-black">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div>
                  <div className="text-fg font-bold text-base mb-2">{f.title}</div>
                  <p className="text-fg-muted text-sm leading-relaxed">{f.body}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function VerticalsBlock() {
  const icons = [Phone, Mail, Database, Zap];
  return (
    <section className="px-6 py-24 bg-bg-panel border-y border-bg-border">
      <div className="mx-auto max-w-7xl">
        <div className="text-center mb-12">
          <div className="text-xs uppercase tracking-[0.18em] font-bold text-accent mb-3">
            Who we work with
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-fg tracking-tight">
            Built for businesses that ship
          </h2>
          <p className="text-fg-muted mt-3 max-w-2xl mx-auto">
            If you have a process that eats hours every week, we can probably automate it. Pick your vertical to see how.
          </p>
        </div>
        <div className="grid md:grid-cols-4 gap-4">
          {VERTICALS.map((v, i) => {
            const Icon = icons[i % icons.length];
            return (
              <div
                key={v.name}
                className="bg-bg border border-bg-border rounded-xl p-5 hover:border-accent transition-all"
              >
                <Icon size={24} className="text-accent mb-3" />
                <div className="text-fg font-bold mb-1">{v.name}</div>
                <div className="text-fg-dim text-xs">{v.examples}</div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function ClosingCTA() {
  return (
    <section className="px-6 py-24">
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="text-3xl md:text-5xl font-bold text-fg tracking-tight">
          Risk lives with us, not you.
        </h2>
        <p className="text-lg text-fg-muted mt-5 leading-relaxed">
          14 days, free. We build the automation. You run it on your real work. If it doesn't save what we promised, walk — owe nothing. If it does, lock it in.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/pricing"
            className="bg-accent text-bg font-bold px-7 py-3.5 rounded-md hover:bg-accent-muted transition-all shadow-glow"
          >
            See pricing
          </Link>
          <Link
            href="/signup"
            className="border border-bg-border text-fg hover:bg-bg-elev font-medium px-7 py-3.5 rounded-md transition-colors"
          >
            Create your account
          </Link>
        </div>
      </div>
    </section>
  );
}
