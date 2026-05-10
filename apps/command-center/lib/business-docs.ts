/**
 * Business Documentation hub — the canonical reference for every doc a
 * functioning C-suite needs. Each entry maps to a doc that lives somewhere
 * (file path on disk, Google Doc, Notion page) plus a chat-fire prompt
 * that asks the right agent to draft / refresh it from scratch.
 *
 * For now the actual docs live as templates the operator can either
 * generate via the agent or store externally. Future iteration: render
 * the doc bodies in-place + edit them inline.
 */

export type DocAgent = "bravo" | "atlas" | "maven" | "aura" | "hermes";
export type DocPillar = "ceo" | "cfo" | "cmo" | "ops" | "legal";

export type BusinessDoc = {
  id: string;
  pillar: DocPillar;
  owner: DocAgent;
  title: string;
  description: string;
  /** Click → /agents?agent=…&prompt=… asks the owning agent to draft it. */
  draft_prompt: string;
  /** Optional file or URL where the canonical version is kept. */
  storage_hint?: string;
  status: "drafted" | "stub" | "missing";
};

export const DOC_PILLARS: Record<DocPillar, { label: string; tagline: string; agent: DocAgent }> = {
  ceo: { label: "CEO — strategy + operations", tagline: "Vision, OKRs, decisions, manifesto", agent: "bravo" },
  cfo: { label: "CFO — money + risk", tagline: "P&L, runway, tax, capital allocation", agent: "atlas" },
  cmo: { label: "CMO — brand + funnel", tagline: "Voice, content, ads, positioning", agent: "maven" },
  ops: { label: "Ops — delivery + processes", tagline: "Onboarding, fulfillment, QA, SLAs", agent: "bravo" },
  legal: { label: "Legal + admin", tagline: "Contracts, terms, IP, incorporations", agent: "bravo" },
};

export const BUSINESS_DOCS: BusinessDoc[] = [
  // ── CEO ─────────────────────────────────────────────────────────
  {
    id: "ceo-manifesto",
    pillar: "ceo", owner: "bravo",
    title: "Company manifesto",
    description: "Why we exist, who we serve, what we will + won't do. The one-page reference every other doc derives from.",
    storage_hint: "brain/SOUL.md",
    status: "drafted",
    draft_prompt:
      "Draft the company manifesto for this business. One page. Cover: north-star metric + deadline, who we serve (buyer profile + their pain), what we sell, what we explicitly will NOT do (anti-vision), the philosophy. Pull from brain/SOUL.md + brain/USER.md. Strong voice, no corporate fluff.",
  },
  {
    id: "ceo-okrs",
    pillar: "ceo", owner: "bravo",
    title: "Quarterly OKRs",
    description: "3 objectives, 3 key results each, this quarter. Tied to the north-star.",
    storage_hint: "brain/OKRs.md",
    status: "drafted",
    draft_prompt:
      "Draft this quarter's OKRs. 3 objectives max — each with 3 measurable key results. Anchor against the north-star. For each KR specify: baseline, target, owner agent, weekly check cadence. Save to brain/OKRs.md.",
  },
  {
    id: "ceo-decisions-log",
    pillar: "ceo", owner: "bravo",
    title: "Decisions log",
    description: "Big calls + the reasoning behind them. Written-down so we can audit later.",
    storage_hint: "brain/DECISIONS.md",
    status: "stub",
    draft_prompt:
      "Initialize a decisions log at brain/DECISIONS.md. Format per entry: date, decision, options considered, choice + why, expected outcome, follow-up date. Add a starter row for the most recent strategic call this week.",
  },
  {
    id: "ceo-org-chart",
    pillar: "ceo", owner: "bravo",
    title: "Org chart + agent registry",
    description: "Who owns what — humans + agents. Decision rights matrix.",
    status: "stub",
    draft_prompt:
      "Build an org chart for the business. List every human (CC, Adon, partners), every AI agent (Bravo/Atlas/Maven/Aura/Hermes), and what each owns. Include a RACI matrix for the top 10 recurring decisions: who's Responsible, Accountable, Consulted, Informed.",
  },

  // ── CFO ─────────────────────────────────────────────────────────
  {
    id: "cfo-pnl-snapshot",
    pillar: "cfo", owner: "atlas",
    title: "Monthly P&L snapshot",
    description: "Revenue by source, costs by category, net. Pulled from Stripe + bank.",
    status: "drafted",
    draft_prompt:
      "Pull this month's P&L snapshot. Revenue by source (Stripe one-offs, recurring retainers, rev shares, community subs, base, other). Costs by category (tools, contractors, ads, hosting). Net. Compare to last month + the 3-month trend. Flag anything weird.",
  },
  {
    id: "cfo-runway",
    pillar: "cfo", owner: "atlas",
    title: "Runway + cash position",
    description: "Months of runway at current burn. Stress-tested at +20% burn / 0 new revenue.",
    status: "drafted",
    draft_prompt:
      "Calculate current runway. Months at current burn, months at +20% burn, months at 0 new revenue. Show me the breakeven MRR vs current and the gap. Recommend one cost to cut + one revenue line to push.",
  },
  {
    id: "cfo-tax-calendar",
    pillar: "cfo", owner: "atlas",
    title: "Tax calendar + reserves",
    description: "GST/HST, income tax, quarterly remittances. What to set aside this week.",
    status: "drafted",
    draft_prompt:
      "Build the tax calendar for Q2 2026. List every CRA filing deadline, the estimated obligation, the source of the data (Stripe gross, business expenses, etc.), and what cash to set aside this week. Dollar-precise.",
  },
  {
    id: "cfo-capital-allocation",
    pillar: "cfo", owner: "atlas",
    title: "Capital allocation policy",
    description: "Where every dollar of profit goes. Reinvest / save / personal split.",
    status: "stub",
    draft_prompt:
      "Draft the capital allocation policy. For every $1 of net profit: how much reinvested into growth, how much into reserves (3 / 6 / 12-month), how much to personal, how much to FIRE accounts. Anchor to CC's $5K MRR + retire-by-30 horizon.",
  },
  {
    id: "cfo-pricing-doc",
    pillar: "cfo", owner: "atlas",
    title: "Pricing strategy",
    description: "Per-product pricing + the math behind each. When to raise, when to bundle.",
    status: "stub",
    draft_prompt:
      "Draft the pricing strategy. For each product (OASIS retainers, PropFlow, Nostalgic Requests, consulting): current price, cost basis, margin, comparable market, recommended next price + when to raise. Include a bundling table.",
  },

  // ── CMO ─────────────────────────────────────────────────────────
  {
    id: "cmo-brand-bible",
    pillar: "cmo", owner: "maven",
    title: "Brand voice bible",
    description: "Tone, vocab, signature phrases, things we never say. Every piece of content checked against this.",
    storage_hint: "../CMO-Agent/brain/CONTENT_BIBLE.md",
    status: "drafted",
    draft_prompt:
      "Refresh the brand voice bible. Audit my last 30 pieces of content (Skool, social, email) and update tone words, vocab, signature phrases, sentence rhythm, and a 'never say this' list. Store at ../CMO-Agent/brain/CONTENT_BIBLE.md.",
  },
  {
    id: "cmo-content-pillars",
    pillar: "cmo", owner: "maven",
    title: "Content pillars",
    description: "3-5 themes every post belongs to. Pillars × platforms × cadence.",
    status: "drafted",
    draft_prompt:
      "Define the content pillars. 3-5 themes (Sobriety / Quote / CEO Log / others). For each: what it's about, why it lands with the audience, target cadence per platform, sample hook archive. Render as a matrix.",
  },
  {
    id: "cmo-buyer-profile",
    pillar: "cmo", owner: "maven",
    title: "Buyer profile (ICP)",
    description: "Who actually buys + why. One-page persona for every product line.",
    status: "stub",
    draft_prompt:
      "Build the buyer profile (ICP) for each product. For OASIS retainers: who's the company, who's the decision-maker, what triggered them to look, what objection kills the deal, where they hang out. Same for PropFlow + Nostalgic. Be specific.",
  },
  {
    id: "cmo-funnel-map",
    pillar: "cmo", owner: "maven",
    title: "Funnel map + conversion rates",
    description: "Awareness → discovery → close. Real conversion at each stage.",
    status: "stub",
    draft_prompt:
      "Map the full funnel. Awareness sources (organic, ads, referral, inbound) → discovery (how they find us) → consideration (booking call) → close. For each stage, real conversion rate from the last 90 days. Highlight the 1 stage with the biggest leak.",
  },
  {
    id: "cmo-ads-budget",
    pillar: "cmo", owner: "maven",
    title: "Ads budget + ROAS targets",
    description: "Per-channel spend cap + minimum ROAS to keep the channel alive.",
    status: "stub",
    draft_prompt:
      "Draft the ads budget. Per channel (Meta, Google, LinkedIn): monthly cap, minimum ROAS to keep running, kill threshold. Pull current performance from Maven's last 30d. Recommend reallocation if any channel is below threshold.",
  },

  // ── OPS ─────────────────────────────────────────────────────────
  {
    id: "ops-client-onboarding",
    pillar: "ops", owner: "bravo",
    title: "Client onboarding SOP",
    description: "Day 0 → day 30. Checklist, comms cadence, success criteria.",
    status: "drafted",
    draft_prompt:
      "Build the client onboarding SOP. Day 0 (contract + Stripe), Day 1-3 (kickoff + access), Week 1 (first delivery), Week 2 (check-in), Day 30 (NPS + retention). Include the comms cadence and success criteria for each milestone.",
  },
  {
    id: "ops-delivery-checklist",
    pillar: "ops", owner: "bravo",
    title: "Delivery checklist",
    description: "What to ship per retainer billing cycle. QA gate before send.",
    status: "drafted",
    draft_prompt:
      "Build the delivery checklist for an OASIS retainer. Every billing cycle: what gets built, what gets reviewed, what gets reported. Include the QA gate criteria — what we never ship until they pass.",
  },
  {
    id: "ops-incident-runbook",
    pillar: "ops", owner: "bravo",
    title: "Incident response runbook",
    description: "When something breaks: triage, comms, fix, post-mortem.",
    status: "stub",
    draft_prompt:
      "Draft the incident response runbook. For severity-1 (client production down), severity-2 (workflow degraded), severity-3 (cosmetic): who triages, who communicates with the client, fix path, post-mortem template. Include comms templates.",
  },
  {
    id: "ops-vendor-list",
    pillar: "ops", owner: "bravo",
    title: "Vendor + tool registry",
    description: "Every paid tool, what we use it for, replacement cost.",
    status: "stub",
    draft_prompt:
      "Build the vendor + tool registry. Every paid SaaS we use, what role it plays, monthly cost, replacement cost (time + setup), single point of failure y/n. Sort by 'highest pain if it disappears tomorrow' first.",
  },

  // ── LEGAL ───────────────────────────────────────────────────────
  {
    id: "legal-msa-template",
    pillar: "legal", owner: "bravo",
    title: "MSA template",
    description: "Master services agreement we use for retainers. Lawyer-reviewed.",
    status: "stub",
    draft_prompt:
      "Draft the MSA template for OASIS retainers. Cover: services scope, term, fees, IP ownership, confidentiality, indemnification, termination, governing law (Ontario). Plain English where possible. Flag every clause where I should get a lawyer's review.",
  },
  {
    id: "legal-privacy-policy",
    pillar: "legal", owner: "bravo",
    title: "Privacy policy",
    description: "What data we collect, how we use it, how clients delete it.",
    status: "stub",
    draft_prompt:
      "Draft a privacy policy for oasisai.work. Cover: what data we collect (signup, dashboard activity, integrations), how we use it, how we store it (Supabase RLS), how clients request deletion. CCPA + PIPEDA compliant.",
  },
  {
    id: "legal-incorporation-checklist",
    pillar: "legal", owner: "bravo",
    title: "Incorporation + admin checklist",
    description: "Federal incorp, GST/HST registration, business bank, accountant, etc.",
    status: "stub",
    draft_prompt:
      "Build the incorporation + admin checklist for OASIS AI in Ontario. Federal incorp, GST/HST registration threshold, payroll if applicable, business bank account, accountant, insurance. For each: status, next action, deadline, cost.",
  },
];

export function docsByPillar(pillar: DocPillar): BusinessDoc[] {
  return BUSINESS_DOCS.filter((d) => d.pillar === pillar);
}
