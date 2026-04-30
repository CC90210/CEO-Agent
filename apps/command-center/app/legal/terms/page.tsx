import { MarketingShell } from "@/components/MarketingShell";

export const dynamic = "force-static";

export const metadata = { title: "Terms · OASIS AI" };

export default function TermsPage() {
  return (
    <MarketingShell>
      <section className="px-6 py-20">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-4xl font-bold text-fg tracking-tight">Terms of Service</h1>
          <p className="text-fg-dim text-sm mt-2">Last updated: April 30, 2026</p>

          <div className="mt-10 space-y-6 text-fg leading-relaxed mdx-content">
            <h2>1. Acceptance</h2>
            <p>
              By signing up for an OASIS account or purchasing an OASIS plan, you accept these
              Terms. If you don't agree, don't use the service.
            </p>

            <h2>2. The 14-day free pilot</h2>
            <p>
              Most OASIS plans include a 14-day free production pilot. We build one automation;
              you run it on real work for 14 days; on day 14 we measure impact together. If the
              automation does not deliver the projected hours/dollars saved, you owe nothing
              and walk. If it does, the implementation fee + retainer activates on day 15.
              Conversion criteria are written into your scope doc before the pilot begins.
            </p>

            <h2>3. Subscriptions</h2>
            <p>
              Monthly retainers renew automatically until cancelled. Cancel anytime through your
              Settings → Billing page or by emailing conaugh@oasisai.work. Refunds for unused
              portions of a paid month are issued at our discretion; the 14-day pilot makes
              this a rare situation.
            </p>

            <h2>4. Custom software builds</h2>
            <p>
              Custom-build engagements are quoted per scope. 50% deposit on signed scope; 50%
              on launch. The client owns the resulting software (IP transfer in your scope doc).
              Maintenance retainer is a separate, optional, monthly arrangement.
            </p>

            <h2>5. Acceptable use</h2>
            <p>
              You will not use OASIS or its agents to send spam, harass anyone, violate CASL,
              GDPR, CCPA, or local equivalents, run pump-and-dump schemes, or scrape data you
              don't have permission to access. Violations result in suspension.
            </p>

            <h2>6. Limitation of liability</h2>
            <p>
              OASIS's liability for any claim is capped at the amount you paid us in the prior
              12 months. We are not liable for indirect or consequential damages.
            </p>

            <h2>7. Governing law</h2>
            <p>
              Ontario, Canada. Disputes go to courts in Simcoe County.
            </p>

            <h2>8. Contact</h2>
            <p>
              Questions: <a href="mailto:conaugh@oasisai.work" className="text-accent">conaugh@oasisai.work</a>.
            </p>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
