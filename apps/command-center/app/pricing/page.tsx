import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { BUNDLES } from "@/lib/marketing-data";
import { CheckCircle2, ArrowRight } from "lucide-react";

export const dynamic = "force-static";

export const metadata = {
  title: "Pricing · OASIS AI",
  description:
    "Three ways to buy. All include the Command Center. 14-day free pilot on most plans — only pay if it works.",
};

export default function PricingPage() {
  return (
    <MarketingShell>
      <section className="px-6 pt-20 pb-12">
        <div className="mx-auto max-w-3xl text-center">
          <div className="text-xs uppercase tracking-[0.18em] font-bold text-accent mb-3">
            Pricing
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-fg tracking-tight">
            Pick a starting point. Scale from there.
          </h1>
          <p className="text-fg-muted mt-5 text-lg leading-relaxed">
            Every plan includes the Command Center, multi-tenant isolation, and the 14-day free pilot guarantee. Pay only after we prove value.
          </p>
        </div>
      </section>

      <section className="px-6 pb-24">
        <div className="mx-auto max-w-7xl grid md:grid-cols-3 gap-6">
          {BUNDLES.map((b) => (
            <div
              key={b.id}
              className={`relative rounded-2xl border p-7 flex flex-col ${
                b.popular
                  ? "border-accent bg-bg-panel shadow-glow"
                  : "border-bg-border bg-bg-panel"
              }`}
            >
              {b.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-accent text-bg font-bold text-[10px] uppercase tracking-[0.18em] px-3 py-1 rounded-full">
                  {b.tagline}
                </div>
              )}
              <div>
                <div className="text-xs uppercase tracking-[0.14em] font-bold text-fg-muted">
                  {b.name}
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-4xl font-bold text-fg tracking-tight">
                    {b.price_usd > 0 ? `$${b.price_usd.toLocaleString()}` : "Custom"}
                  </span>
                  {b.price_usd > 0 && (
                    <span className="text-sm text-fg-dim">
                      {b.is_one_time ? "one-time" : "/mo"}
                    </span>
                  )}
                </div>
                <p className="text-fg-muted text-sm mt-3 leading-relaxed">
                  {b.description}
                </p>
              </div>

              <ul className="mt-6 space-y-2.5 flex-1">
                {b.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm">
                    <CheckCircle2
                      size={16}
                      className="text-accent shrink-0 mt-0.5"
                    />
                    <span className="text-fg">{f}</span>
                  </li>
                ))}
              </ul>

              <Link
                href={`/checkout?bundle=${b.id}`}
                className={`mt-7 group flex items-center justify-center gap-2 rounded-md px-5 py-3 font-bold transition-all ${
                  b.popular
                    ? "bg-accent text-bg hover:bg-accent-muted"
                    : "border border-bg-border text-fg hover:border-accent hover:text-accent"
                }`}
              >
                {b.cta}
                <ArrowRight
                  size={16}
                  className="group-hover:translate-x-1 transition-transform"
                />
              </Link>
            </div>
          ))}
        </div>

        <div className="mx-auto max-w-3xl mt-16 bg-bg-panel border border-bg-border rounded-xl p-7 text-center">
          <div className="text-xs uppercase tracking-[0.14em] font-bold text-accent mb-3">
            How the pilot works
          </div>
          <p className="text-fg leading-relaxed">
            We build your first automation. You run it for 14 days on real work. On day 14 we sit down together and measure: hours saved, dollars captured, errors prevented. If the numbers hit, you pay implementation + retainer. If they don't, you walk — owe nothing. Risk lives with us, not you.
          </p>
        </div>
      </section>
    </MarketingShell>
  );
}
