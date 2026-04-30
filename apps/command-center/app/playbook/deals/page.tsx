import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-static";

const OFFERS = [
  {
    num: "01",
    name: "One-Off Automation",
    pitch: "For service businesses with one painful manual process.",
    flow: [
      ["Discovery", "15-min call, identify ONE high-pain process", "Free"],
      ["Pilot Build", "We build it, hand it over (5–10 days)", "Free"],
      ["Free Trial", "Client runs it in production (14 days)", "Free"],
      ["Quantification", "Joint review on day 14 — hours, $, errors saved", "Free"],
      ["Conversion", "Pay implementation + lock retainer", "$1,500 + $400–800/mo"],
    ],
    why: "1 in 4 pilots converts → effective build cost 4× → still profitable on lifetime retainer. 2 in 4 → printing.",
  },
  {
    num: "02",
    name: "Custom Software Build",
    pitch: "Gritly-style. Client owns it. Asset on their balance sheet.",
    flow: [
      ["Strategy Session", "Map use cases, scope the build", "Free"],
      ["Scope + Quote", "Fixed-price quote, no retainer until live", "Free"],
      ["Build", "4–12 weeks, weekly demos", "50% deposit on signed scope"],
      ["Launch", "Software goes live", "50% balance + retainer activates"],
      ["Maintenance", "Support, evolution, asset stays theirs", "$300–1,500/mo"],
    ],
    why: "15-year exit value angle. Custom software increases business sale price meaningfully. (Jonathan Hutton's hook.)",
  },
  {
    num: "03",
    name: "C-Suite Consulting",
    pitch: "Fractional CTO/strategist for already-paying advisory tiers.",
    flow: [
      ["Pitch Call", "Define the strategic problem (30 min)", "Free"],
      ["Strategy Sprint", "1 deliverable: roadmap, audit, or system design", "$1,500–3,000"],
      ["Retainer", "Async access + monthly Google Meets", "$450–1,500/mo"],
    ],
    why: "Lower volume, higher margin. Builds OASIS brand authority. Alejandro-tier prospects already paying for advisory somewhere.",
  },
];

const PARTNERS = [
  {
    tier: "Tier 1 · Strategic Partner",
    share: "50% revenue share · lifetime of client",
    fit:
      "Consultants, business coaches, agencies with adjacent services. Direct decision-maker relationships. Co-sells (joins discovery calls, vouches, closes together).",
    math:
      "4 deals/year × $600/mo retainer × 12 = $28.8K. Half ($14.4K) is pure upside vs. cold-calling solo. Beats a $60K sales hire.",
    structure: [
      "50% of net revenue (implementation + retainer) for the lifetime of the client",
      "Paid monthly via Stripe split or invoice",
      "Co-branded option: their logo on the work they sourced",
      "90-day exclusivity in their vertical",
    ],
  },
  {
    tier: "Tier 2 · Network Referrer",
    share: "10% of first-year retainer",
    fit:
      "Casual intros. Friends-of-friends, satisfied clients passing our name. No co-selling, just 'you should talk to Conaugh.'",
    math:
      "Three structures, partner picks: 10% of Year 1 retainer · 5% implementation + 10% of first 6 months retainer · flat $200 finder's fee at close.",
    structure: [
      "10% of first-year retainer (default)",
      "5% of implementation + 10% of first 6 months retainer (smoother payout)",
      "$200 flat finder's fee (one-off, no tracking)",
    ],
  },
];

export default function DealArchitecturePage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <PageHeader
        title="Deal Architecture · V1"
        subtitle="Old way: implementation + retainer pitched cold. Friction up front, low conversion. New way: we take the risk, prove value, then they pay."
        action={<Tag tone="accent">2026-04-30</Tag>}
      />

      {/* Client Offers */}
      <div className="grid md:grid-cols-3 gap-5">
        {OFFERS.map((o) => (
          <Card key={o.num}>
            <div className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
              Offer {o.num}
            </div>
            <div className="text-fg font-bold text-base mt-1">{o.name}</div>
            <div className="text-fg-muted text-xs mt-1 mb-4">{o.pitch}</div>

            <div className="space-y-2">
              {o.flow.map((step, i) => (
                <div
                  key={i}
                  className="flex justify-between gap-2 text-xs border-b border-bg-border pb-1.5 last:border-0"
                >
                  <div>
                    <div className="text-fg font-medium">{step[0]}</div>
                    <div className="text-fg-dim mt-0.5">{step[1]}</div>
                  </div>
                  <div className="text-status-engaged font-bold whitespace-nowrap text-right">
                    {step[2]}
                  </div>
                </div>
              ))}
            </div>

            <div className="text-xs text-fg-muted italic mt-4 leading-relaxed">
              <span className="text-fg-dim font-semibold not-italic">Why →</span>{" "}
              {o.why}
            </div>
          </Card>
        ))}
      </div>

      {/* Partner Tiers */}
      <PageHeader
        title="Partner Tiers"
        subtitle="Recruit a network. Don't cold-call your way to $50K MRR alone."
      />

      <div className="space-y-4">
        {PARTNERS.map((p, i) => (
          <Card key={i}>
            <div className="flex items-baseline justify-between mb-3">
              <span className="text-accent font-bold text-base">{p.tier}</span>
              <span className="text-status-engaged font-bold text-sm">
                {p.share}
              </span>
            </div>
            <div className="text-fg-muted text-sm mb-3">{p.fit}</div>
            <div className="text-xs text-fg-dim italic mb-3">
              <span className="text-fg-muted font-semibold not-italic">Math →</span>{" "}
              {p.math}
            </div>
            <ul className="text-sm text-fg space-y-1.5 mt-2">
              {p.structure.map((s, j) => (
                <li key={j} className="flex gap-2">
                  <span className="text-accent">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      {/* Recruitment pitch */}
      <Card title="The recruitment pitch · verbatim">
        <blockquote className="bg-accent-soft border-l-2 border-accent rounded-r-md px-4 py-4 text-fg leading-relaxed">
          "I'm building a partner network around OASIS — anyone who's already trusted in [their vertical] and wants a no-friction way to bring AI into their book of business. I don't sell into your clients without you. You stay the relationship owner. We just plug in the AI piece, you get half of every deal we close together. If that's interesting, I'll send you the one-pager. If not, no harm — figured you'd be the right call."
        </blockquote>
      </Card>
    </div>
  );
}
