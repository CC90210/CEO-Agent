/**
 * Single source of truth for the OASIS C-Suite agent registry.
 *
 * Used by /agents and /settings pages, the chat widget, the onboarding wizard,
 * and the sidebar. Add or rename an agent here once; everything updates.
 */

export type AgentInfo = {
  key: string;
  label: string;             // Capitalized display name
  role: string;              // Long descriptor — used by Settings
  tagline: string;           // Short descriptor — used by chat header + onboarding
  location: string;          // Repo / runtime path
  /** RGB triplet (no rgb() wrapper) — drives chat-container glow + pill colors. */
  colorRgb: string;
  /** Tailwind text-* class for inline labels. */
  textClass: string;
  /**
   * True for the C-suite agents shown on /agents AGENT FAMILY card.
   * False for backend executors (Codex) that power agents but aren't
   * standalone "personas" CC interacts with directly. Defaults true
   * when the field is absent so the registry stays backward-compatible.
   */
  family?: boolean;
  /**
   * Plain-English "what they do for you" — 2-3 sentences. Renders on
   * the /agents card so the family reads as personalities with concrete
   * value, not job titles. Operator-facing, not in any system prompt.
   */
  description?: string;
  /**
   * One-line "ask me about" hook to encourage the operator to actually
   * use the agent. Surfaces in the family card under the description.
   */
  askMeAbout?: string;
};

export const AGENT_REGISTRY: Record<string, AgentInfo> = {
  bravo: {
    key: "bravo",
    label: "Bravo",
    role: "Lead architect · business ops · content voice",
    tagline: "Lead architect · ops · voice",
    location: "this repo",
    colorRgb: "0, 212, 255",
    textClass: "text-accent",
    description:
      "Your CEO operating system. Bravo runs the day — ranks the leads worth calling first, drafts your outbound, finalizes today's plan, runs the daily briefing, and keeps the whole agent family rowing in the same direction.",
    askMeAbout: "Run the daily briefing · Draft a follow-up to Jonathan · What's blocking $5K?",
  },
  atlas: {
    key: "atlas",
    label: "Atlas",
    role: "CFO · finance · tax · trading · budget",
    tagline: "CFO · finance · tax · trading",
    location: "C:\\Users\\User\\APPS\\CFO-Agent",
    colorRgb: "52, 211, 153",
    textClass: "text-emerald-400",
    description:
      "Your CFO. Atlas guards capital first, minimizes tax second, compounds gains third. Real net-worth tracking, FIRE projections, jurisdiction-aware tax strategy, and a 12-strategy trading engine — all opinionated, all data-driven, all on your side.",
    askMeAbout: "Show this week's net worth · What's owing on tax this quarter · Run a FIRE projection",
  },
  maven: {
    key: "maven",
    label: "Maven",
    role: "CMO · content production · paid ads · funnels",
    tagline: "CMO · content · ads · funnels",
    location: "C:\\Users\\User\\CMO-Agent",
    colorRgb: "244, 114, 182",
    textClass: "text-pink-400",
    description:
      "Your CMO. Maven turns one piece of raw video into the week's content calendar across every platform, audits funnels for leaks, optimizes ad spend by ROAS, and protects brand voice — no AI slop, no purple gradients, no generic 'Unlock the power of...' copy.",
    askMeAbout: "Draft 3 hooks for tomorrow · Audit the booking page · What's working in the latest ads?",
  },
  aura: {
    key: "aura",
    label: "Aura",
    role: "Life · home · habits · voice",
    tagline: "Life · home · habits · voice",
    location: "C:\\Users\\User\\AURA",
    colorRgb: "192, 132, 252",
    textClass: "text-purple-400",
    description:
      "Your life surface. Aura runs the morning briefing, syncs sleep + recovery, surfaces small wins instead of lectures, and quietly handles the smart-home + habits layer so rest, movement, and presence stay non-negotiable infrastructure.",
    askMeAbout: "Run the morning briefing · Last night's sleep + recovery · Habit audit for this week",
  },
  hermes: {
    key: "hermes",
    label: "Hermes",
    role: "Commerce agent · POS · EDI · chargebacks",
    tagline: "Commerce · POS · EDI",
    location: "C:\\Users\\User\\hermes",
    colorRgb: "251, 191, 36",
    textClass: "text-amber-400",
    description:
      "Your commerce ops agent. Hermes drives the PO → POS → invoice loop for wholesale distributors — A2000 desktop takeover, web ERPs, GS1-128 labels, EDI 856/810/940/820, chargeback prevention. Local-first, audit-everything, fail-stopped.",
    askMeAbout: "Status of open POs · Draft EDI 856 for the latest shipment · Yesterday's A2000 sync log",
  },
  sunbiz: {
    key: "sunbiz",
    label: "Solara",
    role: "Sun Biz funding operations agent · leads · SMS · deals · renewals",
    tagline: "Funding ops · renewals · outreach",
    location: "C:\\Users\\User\\Marketing-Agent",
    colorRgb: "251, 191, 36",
    textClass: "text-amber-400",
    family: false,
    description:
      "Solara is the client funding-ops agent for Sun Biz Funding. It routes leads, SMS outreach, applications, offers, funded deals, commissions, and renewal follow-up into the business command center.",
    askMeAbout: "Show renewal opportunities · Send a compliant SMS follow-up · What deals need lender action?",
  },
  suga_sean: {
    key: "suga_sean",
    label: "Suga",
    role: "Suga Sean O'Malley · fan ops + brand agent",
    tagline: "Fans · merch · social · sponsorship",
    location: "C:\\Users\\User\\APPS\\suga-sean-agent",
    colorRgb: "236, 72, 153",
    textClass: "text-pink-400",
    family: false,
    description:
      "Suga is the client brand-ops agent for Sean O'Malley. It routes fan engagement, merch drops, social posting, and sponsorship triage into the business command center.",
    askMeAbout: "Draft a fan reply pack · What merch drop converted best last week? · Which sponsorship leads are warm?",
  },
  // Registry key stays "life-preservation" so filesystem paths
  // (~/life-preservation, tmp/agent_inbox routing, sibling_repos, etc.)
  // remain stable. Only the human-facing label changed to "Lumen".
  "life-preservation": {
    key: "life-preservation",
    label: "Lumen",
    role: "Memory keeper · holds the voice and presence of loved ones",
    tagline: "Memory · voice · legacy",
    location: "C:\\Users\\User\\life-preservation",
    colorRgb: "248, 213, 145", // soft amber — like a small light
    textClass: "text-amber-200",
    description:
      "A small steady light. Lumen captures the voice, stories, and presence of someone you love before they pass — guided interviews that surface meaningful detail, voice-clone coaching, memory organization. Family-led, family-gated, never extracted.",
    askMeAbout: "Plan an interview session · What questions surface the small details · What's missing from her story?",
  },
  // Backend delegation executor — powers custom agents, not a standalone
  // persona. family:false hides it from the AGENT FAMILY card on /agents.
  codex: {
    key: "codex",
    label: "Codex",
    role: "Backend executor · powers custom agents · not standalone",
    tagline: "Backend · delegation",
    location: "OpenAI Codex",
    colorRgb: "148, 163, 184",
    textClass: "text-slate-400",
    family: false,
  },
};

export const ALL_AGENT_KEYS = Object.keys(AGENT_REGISTRY);

/**
 * Subset of ALL_AGENT_KEYS that should appear on the /agents AGENT FAMILY
 * card. Excludes backend executors (Codex) — they power agents but aren't
 * the personas CC interacts with directly.
 */
export const FAMILY_AGENT_KEYS = ALL_AGENT_KEYS.filter(
  (k) => AGENT_REGISTRY[k].family !== false
);

export function getAgentInfo(key: string): AgentInfo {
  return (
    AGENT_REGISTRY[key] || {
      key,
      label: key.charAt(0).toUpperCase() + key.slice(1),
      role: "Custom agent",
      tagline: "Custom agent",
      location: "—",
      colorRgb: "0, 212, 255",
      textClass: "text-accent",
    }
  );
}
