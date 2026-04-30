import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-static";

const OFFERS = [
  {
    num: "01",
    name: "One-Off Automation",
    pitch: "We automate ONE specific painful process for them.",
    pricing: "$1,500 one-time + $400/mo retainer",
    flow: [
      ["Free 15-min discovery", "Pick the most painful process", "Free"],
      ["Pilot build (5–10 days)", "We build it. They have nothing to lose.", "Free"],
      ["14-day production trial", "They run it on real work", "Free"],
      ["Day 14 review", "We measure: hours saved, $ captured, errors prevented", "Free"],
      ["Conversion", "Pay implementation + lock in maintenance retainer", "$1,500 + $400/mo"],
    ],
    plain_english:
      "We pick one process — like booking, follow-ups, or lead routing — and build the AI to run it. They use it free for 14 days. If it actually saves them money/time, they pay $1,500 to lock it in plus $400/month for us to keep it running, fix bugs, and improve it. If it doesn't deliver, they pay nothing.",
    why_works:
      "Risk transfers to OASIS. We absorb the build cost; they only pay for proven value. Even if only 1 of 4 pilots converts, the lifetime retainer ($4,800/yr × 5 yr = $24K) makes the math work. 2 of 4 = printing.",
  },
  {
    num: "02",
    name: "Custom Software Build",
    pitch: "We build a piece of software they own. Like Gritly. Like a real asset.",
    pricing: "Quote per scope ($8K–40K) + $300–1,500/mo maintenance",
    flow: [
      ["Free strategy session", "Map use cases, identify what to build", "Free"],
      ["Fixed-price scope doc", "Written quote, no retainer until live", "Free"],
      ["Build (4–12 weeks)", "Weekly demos, client owns the IP", "50% deposit on signed scope"],
      ["Launch", "Software goes live", "50% balance + retainer activates"],
      ["Maintenance", "Ongoing support + evolution", "$300–1,500/mo"],
    ],
    plain_english:
      "Some businesses don't need an automation, they need their own custom software — a tool tailored to how they specifically operate. We scope it for free, quote a fixed price, take 50% deposit to start, deliver in 4–12 weeks, take the other 50% on launch. The client OWNS the software (asset on their balance sheet, increases sale value at exit). We charge ongoing maintenance to keep it alive.",
    why_works:
      "Bigger ticket, bigger commitment, clearer asset. The 50/50 deposit aligns incentives — we don't get paid in full until they're using it. Maintenance retainer creates sticky monthly revenue. Best fit for established businesses where 'we should own a custom tool' makes obvious sense (Jonathan Hutton's case — landscaping owner, 15-year exit, custom tool boosts business sale price).",
  },
  {
    num: "03",
    name: "Advisory / Fractional CTO",
    pitch: "Async access + monthly strategy — for businesses that want our brain on retainer.",
    pricing: "$1,500–3,000 sprint + $450–1,500/mo retainer",
    flow: [
      ["Free 30-min pitch", "Define their strategic AI problem", "Free"],
      ["Strategy sprint (7 days)", "1 deliverable: roadmap, audit, or system design", "$1,500–3,000"],
      ["Ongoing access", "Async Slack/email + monthly Google Meet", "$450–1,500/mo"],
    ],
    plain_english:
      "Some clients aren't buying a tool — they're buying our judgment. They want to text us when they're scoping their next big AI initiative, get an opinion before they spend $50K with someone else, and have a monthly strategy session to stay ahead. We charge a one-time sprint to deliver a concrete document (roadmap, audit, or system design), then a monthly retainer for ongoing access. Lower volume, higher margin, builds the OASIS brand.",
    why_works:
      "Recurring revenue without delivery work. Best fit for prospects already paying $5K+/mo for advisory somewhere — they're the buyers who don't blink at $1,500/mo for OASIS-grade AI strategy.",
  },
];

const PARTNERS = [
  {
    tier: "Strategic Partner",
    rate: "30% revenue share for 12 months · per closed deal",
    fit:
      "Business coaches, agencies, or consultants who actively co-sell with us — they bring the relationship, join the discovery call, vouch for OASIS, help close. They have direct decision-maker access in our verticals.",
    plain_english:
      "Our best partners aren't passive intro-givers — they're co-sellers. They show up to the discovery call, lend their credibility, and we close together. For that level of involvement, we pay 30% of all revenue from that deal (implementation + retainer) for the first 12 months. After 12 months, the relationship belongs entirely to OASIS.",
    math: "Example: partner brings 4 deals/year × ($1,500 + $400/mo × 12) = $25,200 revenue/yr. Their cut: $7,560/yr. OASIS net: $17,640/yr — pure upside vs. cold-calling. After year 1, full ownership reverts to us = compounding LTV.",
  },
  {
    tier: "Network Referrer",
    rate: "$500 finder's fee · paid on close",
    fit:
      "Casual intros — friends, satisfied clients, network connections. They send a name and email; we do everything else. No co-selling, no pitch involvement.",
    plain_english:
      "Someone tells you 'you should talk to my buddy Conaugh — he does AI for businesses.' That's a network referral. We pay them a flat $500 when the deal closes, no ongoing percentage, no tracking required. Simple, clean, no friction.",
    math:
      "Per-deal cost is fixed: $500 vs. ~$1,500 implementation revenue + retainer. We're trading a single payment for a customer with $4,800+/yr LTV. Easy decision; easy to explain to the referrer.",
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
        title="Deal Architecture · V2"
        subtitle="How OASIS prices AI work — explained in plain English. Three client offers, two partner paths. Risk transferred to us via the 14-day pilot."
        action={<Tag tone="accent">2026-04-30</Tag>}
      />

      <Card title="The core principle" subtitle="Why this works at all">
        <p className="text-fg leading-relaxed">
          Most AI agencies pitch implementation + retainer cold and ask for $5K up front before delivering anything.
          Conversion is brutal. We do the opposite: we build first, charge after. The 14-day pilot is the lever — every objection collapses because there's literally no scenario where the prospect loses money. They walk if it doesn't work; they pay only if it does.
        </p>
        <p className="text-fg leading-relaxed mt-3">
          The trade-off: we absorb 100% of build cost on losses. Mitigation: we only pilot when discovery confirmed real pain, real budget, real decision authority. Pilot conversion target is 50%+. If we hit that, the math is overwhelmingly positive.
        </p>
      </Card>

      {/* Client Offers */}
      <PageHeader title="Client offers" subtitle="Three ways someone buys from OASIS." />
      <div className="space-y-5">
        {OFFERS.map((o) => (
          <Card key={o.num}>
            <div className="flex items-baseline gap-3 mb-1">
              <span className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
                Offer {o.num}
              </span>
              <span className="text-fg font-bold text-base">{o.name}</span>
              <span className="ml-auto text-status-engaged font-bold text-sm">{o.pricing}</span>
            </div>
            <div className="text-fg-muted text-sm italic mb-4">{o.pitch}</div>

            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-2">
                  Flow
                </div>
                <div className="space-y-1.5">
                  {o.flow.map((step, i) => (
                    <div
                      key={i}
                      className="flex justify-between gap-3 text-xs border-b border-bg-border pb-1.5 last:border-0"
                    >
                      <div className="flex-1">
                        <div className="text-fg font-medium">{step[0]}</div>
                        <div className="text-fg-dim mt-0.5">{step[1]}</div>
                      </div>
                      <div className="text-status-engaged font-bold whitespace-nowrap text-right">
                        {step[2]}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-2">
                  In plain English
                </div>
                <p className="text-fg text-sm leading-relaxed mb-3">{o.plain_english}</p>
                <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1.5">
                  Why it works
                </div>
                <p className="text-fg-muted text-xs leading-relaxed italic">{o.why_works}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Partners */}
      <PageHeader title="Partner paths" subtitle="Two ways someone helps us land deals." />
      <div className="grid md:grid-cols-2 gap-5">
        {PARTNERS.map((p, i) => (
          <Card key={i}>
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-accent font-bold text-base">{p.tier}</span>
            </div>
            <div className="text-status-engaged font-bold text-sm mb-3">{p.rate}</div>
            <div className="text-fg-muted text-sm mb-3 italic">{p.fit}</div>
            <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1">
              In plain English
            </div>
            <p className="text-fg text-sm leading-relaxed mb-3">{p.plain_english}</p>
            <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1">
              Math
            </div>
            <p className="text-fg-muted text-xs leading-relaxed italic">{p.math}</p>
          </Card>
        ))}
      </div>

      <Card title="The recruitment pitch · verbatim">
        <blockquote className="bg-accent-soft border-l-2 border-accent rounded-r-md px-4 py-4 text-fg leading-relaxed">
          "I'm building a partner network around OASIS. If you've got clients who'd benefit from AI in their business — and you'd be willing to introduce us and stay on the call — I pay 30% of every deal we close together for the first year. If it's just a casual intro, I pay $500 flat per close. I keep it simple: you stay the relationship owner, I deliver the work, we both win. Worth a quick chat to see if it fits?"
        </blockquote>
      </Card>
    </div>
  );
}
