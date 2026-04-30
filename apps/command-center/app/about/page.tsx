import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";

export const dynamic = "force-static";

export const metadata = { title: "About · OASIS AI" };

export default function AboutPage() {
  return (
    <MarketingShell>
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl">
          <div className="text-xs uppercase tracking-[0.18em] font-bold text-accent mb-3">
            About
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-fg tracking-tight">
            We build AI agents you can actually run a business with.
          </h1>

          <div className="mt-10 space-y-6 text-fg leading-relaxed text-lg">
            <p>
              OASIS AI Solutions is an AI automation studio based in Collingwood, Ontario.
              We work with service businesses, professional firms, real-estate teams,
              and e-commerce brands that have a process eating hours every week — and
              are tired of doing it manually.
            </p>
            <p>
              Most AI agencies sell vague consulting hours and disappear. We deliver
              production AI that runs your operations — booking, follow-ups, lead
              routing, intake, customer service — and you watch it work in real time
              from the OASIS Command Center.
            </p>
            <p>
              We made the call early: every engagement starts with a 14-day free
              pilot. We absorb the build cost. You only pay if the work delivers.
              That's not a marketing hook — it's how we run, every customer.
            </p>
            <p className="text-fg-muted italic">
              "Direction isn't intention. Direction is velocity."
            </p>
          </div>

          <div className="mt-12 grid md:grid-cols-2 gap-4">
            <Link
              href="/pricing"
              className="bg-accent text-bg font-bold px-6 py-3 rounded-md hover:bg-accent-muted text-center transition-colors shadow-glow"
            >
              See pricing
            </Link>
            <Link
              href="/contact"
              className="border border-bg-border text-fg hover:bg-bg-elev font-medium px-6 py-3 rounded-md text-center transition-colors"
            >
              Book a call
            </Link>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
