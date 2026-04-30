/**
 * OASIS AI marketing data — pricing tiers + value props.
 *
 * Sourced from oasis-ai-platform's pricingData.ts. Trimmed to what the
 * unified marketing site shows. Every priced product carries a
 * `command_center_included: true` flag so the Stripe webhook knows to
 * fire the bridge for those purchases.
 */

export type Bundle = {
  id: string;
  name: string;
  price_usd: number;
  is_one_time: boolean;
  tagline: string;
  description: string;
  features: string[];
  cta: string;
  popular?: boolean;
  command_center_included: boolean;
  stripe_price_env?: string; // env var name holding the Stripe price ID
};

export const BUNDLES: Bundle[] = [
  {
    id: "launchpad",
    name: "OASIS Launchpad",
    price_usd: 2500,
    is_one_time: true,
    tagline: "Best for getting started",
    description:
      "Pick one painful process. We automate it, you watch. 14-day free pilot — pay only after we prove it saves you time and money.",
    features: [
      "90-min discovery + custom roadmap",
      "1 production-ready automation",
      "14-day free pilot, joint review on day 14",
      "30 days of priority implementation support",
      "Command Center access (track + measure ROI)",
      "Monthly impact report",
    ],
    cta: "Start your pilot",
    command_center_included: true,
    stripe_price_env: "STRIPE_PRICE_LAUNCHPAD",
  },
  {
    id: "integration-suite",
    name: "Integration Suite",
    price_usd: 5000,
    is_one_time: true,
    tagline: "Most popular",
    popular: true,
    description:
      "Full operational transformation. 3-5 automations, voice AI, CRM integration, and 90 days of dedicated support.",
    features: [
      "Full business process audit",
      "3-5 core automations of your choice",
      "Voice AI phone system",
      "CRM integration + RAG knowledge base",
      "Dedicated implementation manager",
      "90 days optimization + support",
      "Command Center access (full agent fleet)",
      "Avg 312% ROI within 90 days",
    ],
    cta: "Book consultation",
    command_center_included: true,
    stripe_price_env: "STRIPE_PRICE_INTEGRATION_SUITE",
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price_usd: 0,
    is_one_time: false,
    tagline: "Custom builds, custom pricing",
    description:
      "Custom software builds (Gritly-style assets you own), AI strategy advisory, and white-glove deployment. Quoted per scope.",
    features: [
      "Free strategy session + scope quote",
      "Custom-built software (you own the IP)",
      "Fixed-price deliverable, 50/50 deposit",
      "Dedicated team for the duration",
      "Command Center white-label option",
      "Priority Slack channel",
    ],
    cta: "Book a call",
    command_center_included: true,
  },
];

export type Feature = {
  title: string;
  body: string;
};

export const FEATURES: Feature[] = [
  {
    title: "AI agents that actually run your ops",
    body: "Not chatbots. Real automations that book appointments, route leads, draft emails, and follow up — measured against the time + money they save you.",
  },
  {
    title: "14-day free pilot, every time",
    body: "We absorb the build cost. You only pay if it works. There's no scenario where you lose money trying.",
  },
  {
    title: "Live Command Center for every client",
    body: "Watch every agent in real time. Pipeline, decisions, integrations health, daily ops plan. The operating system for the AI workforce you just bought.",
  },
  {
    title: "Multi-tenant, isolated, secure",
    body: "Your data lives in your own workspace. RLS-enforced isolation. Service-role keys never reach the browser. SOC-2-ready architecture.",
  },
];

export type Vertical = {
  name: string;
  examples: string;
};

export const VERTICALS: Vertical[] = [
  { name: "Service Trades", examples: "HVAC · plumbing · landscaping · roofing" },
  { name: "Professional Services", examples: "Accountants · lawyers · advisors · consultants" },
  { name: "Real Estate", examples: "Agents · brokers · property managers" },
  { name: "E-commerce / Retail", examples: "Shopify stores · DTC brands · direct retail" },
];
