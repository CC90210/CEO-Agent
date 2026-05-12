import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-dynamic";

const OFFERS = [
  {
    num: "01",
    name: "One-Off Automation",
    pitch: "Automate one specific painful process, prove ROI, then convert.",
    pricing: "$1,500 one-time + $400-800/mo retainer",
    flow: [
      ["Free 15-min discovery", "Pick the most painful process", "Free"],
      ["Pilot build (5-10 days)", "We build it. They have nothing to lose.", "Free"],
      ["14-day production trial", "They run it on real work", "Free"],
      ["Day 14 review", "Measure hours saved, revenue captured, errors prevented", "Free"],
      ["Conversion", "Implementation fee + maintenance retainer activates", "$1,500 + $400-800/mo"],
    ],
    plain:
      "We pick one process, such as booking, follow-ups, lead routing, or admin triage, and build the AI to run it. They use it free for 14 days. If it saves real time or money, they pay to lock it in. If it does not deliver, they owe nothing.",
    why:
      "The risk moves from the prospect to OASIS. Only pilot when discovery confirms real pain, budget, and decision authority. Target conversion: 50%+.",
  },
  {
    num: "02",
    name: "Custom Software Build",
    pitch: "Build software they own, like a real business asset.",
    pricing: "$8K-40K scope + $300-1,500/mo maintenance",
    flow: [
      ["Free strategy session", "Map use cases and asset value", "Free"],
      ["Fixed-price scope doc", "Written quote, no retainer until live", "Free"],
      ["Build (4-12 weeks)", "Weekly demos, client owns the IP", "50% deposit"],
      ["Launch", "Software goes live", "50% balance + retainer"],
      ["Maintenance", "Ongoing support and evolution", "$300-1,500/mo"],
    ],
    plain:
      "Some businesses do not need a small automation. They need a custom operating tool tailored to how they work. This is the Jonathan Hutton / Basque Landscaping lane: owned software, exit value, and a maintenance relationship after launch.",
    why:
      "Bigger ticket, clearer commitment, stronger asset story. Best for established owners with messy operations and a long-term business value angle.",
  },
  {
    num: "03",
    name: "Advisory / Fractional CTO",
    pitch: "Async access plus monthly strategy for buyers who want judgment.",
    pricing: "$1,500-3,000 sprint + $450-1,500/mo retainer",
    flow: [
      ["Free 30-min pitch", "Define the strategic AI problem", "Free"],
      ["Strategy sprint (7 days)", "Roadmap, audit, or system design", "$1,500-3,000"],
      ["Ongoing access", "Async support + monthly Google Meet", "$450-1,500/mo"],
    ],
    plain:
      "Some clients are not buying a tool. They are buying OASIS judgment before they spend $50K in the wrong direction. Charge once for a concrete roadmap, then monthly for access and decision support.",
    why:
      "High-margin recurring revenue without daily delivery work. Best for sophisticated buyers already used to paying for strategic advice.",
  },
];

const PARTNERS = [
  {
    tier: "Strategic Partner",
    rate: "50% of net revenue - lifetime of the client",
    fit:
      "Business coaches, agencies, and consultants who originate the deal, join discovery, lend credibility, and help close.",
    plain:
      "They are not passive intro-givers. They are co-sellers. They stay the relationship owner, OASIS owns delivery, and they get half of net revenue from every client they originate for as long as that client pays.",
    math:
      "Example: 4 partner deals/year x ($1,500 + $600/mo x 12) = $34,800/year. Partner earns $17,400. OASIS keeps $17,400 from clients we likely would not have landed through cold outreach alone.",
  },
  {
    tier: "Network Referrer",
    rate: "10% first-year retainer OR 5% implementation + 10% first 6 months OR $200 flat",
    fit:
      "Casual intros from friends, clients, and network contacts. They send the name; OASIS handles the sale.",
    plain:
      "This is intentionally lighter than a strategic partner. If they want no tracking, pay a clean $200 close fee. If they want upside, use one of the short-term commission options.",
    math:
      "The referrer has a reason to send the next name, but OASIS keeps the long-term client economics and avoids managing a fake partner relationship.",
  },
];

const DECISION_RULES = [
  ["Painful repeat process", "Offer 1", "Build one automation, prove ROI in 14 days, convert to retainer."],
  ["Established owner + exit value", "Offer 2", "Build owned software that increases operational and resale value."],
  ["Strategic buyer", "Offer 3", "Sell judgment, roadmap clarity, and async access."],
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
        title="Deal Architecture - V3"
        subtitle="Three client offers, two partner paths, and one simple rule for choosing the right lane."
        action={<Tag tone="accent">canonical</Tag>}
      />

      <Card title="The core principle" subtitle="Why the offer converts">
        <p className="text-fg leading-relaxed">
          Most AI agencies ask for a big implementation fee before the prospect has proof. OASIS flips the risk:
          prove value first, then charge. The only rule is discipline - no free pilot unless discovery confirms real
          pain, real budget, and real decision authority.
        </p>
      </Card>

      <Card title="Decision rule" subtitle="Pick the offer by buyer maturity">
        <div className="grid md:grid-cols-3 gap-3">
          {DECISION_RULES.map(([signal, offer, body]) => (
            <div key={signal} className="bg-bg-elev border border-bg-border rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted">{signal}</div>
              <div className="text-accent font-bold mt-1">{offer}</div>
              <p className="text-sm text-fg-muted mt-1.5 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </Card>

      <PageHeader title="Client offers" subtitle="How someone buys from OASIS." />
      <div className="space-y-5">
        {OFFERS.map((offer) => (
          <Card key={offer.num}>
            <div className="flex flex-wrap items-baseline gap-3 mb-1">
              <span className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
                Offer {offer.num}
              </span>
              <span className="text-fg font-bold text-base">{offer.name}</span>
              <span className="ml-auto text-status-engaged font-bold text-sm">{offer.pricing}</span>
            </div>
            <div className="text-fg-muted text-sm italic mb-4">{offer.pitch}</div>

            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-2">
                  Flow
                </div>
                <div className="space-y-1.5">
                  {offer.flow.map((step) => (
                    <div
                      key={step[0]}
                      className="flex justify-between gap-3 text-xs border-b border-bg-border pb-1.5 last:border-0"
                    >
                      <div className="flex-1">
                        <div className="text-fg font-medium">{step[0]}</div>
                        <div className="text-fg-dim mt-0.5">{step[1]}</div>
                      </div>
                      <div className="text-status-engaged font-bold whitespace-nowrap text-right">{step[2]}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-2">
                  In plain English
                </div>
                <p className="text-fg text-sm leading-relaxed mb-3">{offer.plain}</p>
                <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1.5">
                  Why it works
                </div>
                <p className="text-fg-muted text-xs leading-relaxed italic">{offer.why}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <PageHeader title="Partner paths" subtitle="Strategic co-sellers get upside. Casual intros stay simple." />
      <div className="grid md:grid-cols-2 gap-5">
        {PARTNERS.map((partner) => (
          <Card key={partner.tier}>
            <div className="text-accent font-bold text-base">{partner.tier}</div>
            <div className="text-status-engaged font-bold text-sm mt-2 mb-3">{partner.rate}</div>
            <div className="text-fg-muted text-sm mb-3 italic">{partner.fit}</div>
            <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1">
              In plain English
            </div>
            <p className="text-fg text-sm leading-relaxed mb-3">{partner.plain}</p>
            <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1">
              Math
            </div>
            <p className="text-fg-muted text-xs leading-relaxed italic">{partner.math}</p>
          </Card>
        ))}
      </div>

      <Card title="Partner pitch - verbatim">
        <blockquote className="bg-accent-soft border-l-2 border-accent rounded-r-md px-4 py-4 text-fg leading-relaxed">
          "I'm building a partner network around OASIS - basically, people who already have trust in their market
          and want a no-friction way to bring AI into their book of business. I don't sell into your clients without
          you. You stay the relationship owner. We plug in the AI piece, and if you actively bring and help close the
          deal, you get half of net revenue for the lifetime of that client. If it is just a casual intro, I keep that
          simpler with a small close fee or short-term commission. Worth a quick chat to see if it fits?"
        </blockquote>
      </Card>
    </div>
  );
}
