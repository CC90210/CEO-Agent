import { MarketingShell } from "@/components/MarketingShell";

export const dynamic = "force-static";

export const metadata = { title: "Privacy · OASIS AI" };

export default function PrivacyPage() {
  return (
    <MarketingShell>
      <section className="px-6 py-20">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-4xl font-bold text-fg tracking-tight">Privacy Policy</h1>
          <p className="text-fg-dim text-sm mt-2">Last updated: April 30, 2026</p>

          <div className="mt-10 space-y-6 text-fg leading-relaxed mdx-content">
            <h2>Who we are</h2>
            <p>
              OASIS AI Solutions ("OASIS", "we", "us") operates oasisai.work and the OASIS AI
              Agent Command Center. We're based in Collingwood, Ontario, Canada.
            </p>

            <h2>What we collect</h2>
            <ul>
              <li>Account info (name, email, brand, password hash)</li>
              <li>Operational data you generate using the Command Center (leads, interactions, agent decisions, daily plans)</li>
              <li>Stripe payment metadata (customer ID, subscription ID, plan tier — never the full card number)</li>
              <li>Standard server logs (IP address, user agent, timestamps)</li>
            </ul>

            <h2>How we use it</h2>
            <p>
              Solely to operate the Command Center and the agent automations you've purchased.
              We do not sell, rent, or share your data with third parties for marketing.
              Sub-processors (Supabase, Stripe, Vercel, Anthropic) process data on our behalf
              under their own terms.
            </p>

            <h2>Data isolation</h2>
            <p>
              Every customer's operational data lives in an isolated workspace, enforced by
              row-level security in the database. Service-role keys never reach the browser.
            </p>

            <h2>Your rights</h2>
            <p>
              You can request a copy of your data, ask us to delete it, or export it at any
              time. Email <a href="mailto:conaugh@oasisai.work" className="text-accent">conaugh@oasisai.work</a>.
            </p>

            <h2>CASL compliance (Canadian operators)</h2>
            <p>
              Outbound communications from OASIS automations include CASL-compliant footers.
              Reply STOP to any email to be added to our suppression list within 10 business days.
            </p>

            <h2>Changes to this policy</h2>
            <p>
              We'll post material changes here and notify active customers by email. Continued
              use after a change means you accept the updated terms.
            </p>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
