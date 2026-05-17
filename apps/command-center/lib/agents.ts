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
  /**
   * Per-agent setup questionnaire (Phase J of giggly-reef). When a
   * tenant onboards and picks this agent, the wizard renders these
   * questions between the agent-picker step and the brand step.
   * Answers persist on manifest.agents[].setup_answers and fold into
   * the agent's system prompt as a "TENANT SETUP" overlay so the
   * agent immediately knows the operator's specifics (TCPA opt-out
   * language for SMS agents, FICO floor for funding agents, primary
   * domain for email agents, etc.).
   *
   * Keep the list tight — wizard-step abandonment scales with question
   * count. Two-to-five questions per agent is the sweet spot; anything
   * deeper should live in /settings post-onboarding.
   */
  setup_questions?: SetupQuestion[];
};

export type SetupQuestionType = "text" | "textarea" | "select" | "boolean" | "number";

export type SetupQuestion = {
  /** Stable key — used as the field name in setup_answers. Snake_case. */
  id: string;
  /** Operator-facing question text. */
  label: string;
  /** Optional one-line clarification under the label. */
  description?: string;
  type: SetupQuestionType;
  /** Required questions block wizard progression until answered. */
  required?: boolean;
  /** For type="select" — list of option values. UI shows them as a dropdown. */
  options?: Array<{ value: string; label: string }>;
  /** Hint text inside the input field (text / textarea / number only). */
  placeholder?: string;
  /** Default value pre-filled in the field. */
  default?: string | number | boolean;
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
    setup_questions: [
      {
        id: "primary_business",
        label: "What's the primary business you're running?",
        description: "Anchors Bravo's recommendations. Single line — 'AI agency for small business' is enough.",
        type: "text",
        required: true,
        placeholder: "OASIS AI Solutions — AI agents for SMBs",
      },
      {
        id: "mrr_target_usd",
        label: "Current MRR target (USD)",
        description: "Bravo uses this as the daily north-star metric.",
        type: "number",
        required: true,
        placeholder: "5000",
        default: 5000,
      },
      {
        id: "tone",
        label: "Outreach voice",
        description: "How Bravo writes when drafting on your behalf.",
        type: "select",
        required: true,
        default: "direct",
        options: [
          { value: "direct", label: "Direct — short, sharp, no fluff" },
          { value: "consultative", label: "Consultative — NEPQ-style questions, mirror objections" },
          { value: "warm", label: "Warm — personal, relational, longer prose" },
        ],
      },
    ],
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
  // Sun Biz Funding — operational primary. Backend admin, Chrome jobs,
  // data collection, workflow runner. Where Ezra goes when work needs done.
  solara: {
    key: "solara",
    label: "Solara",
    role: "Sun Biz operational agent · backend admin · workflows · data collection",
    tagline: "Operations · workflows · data",
    location: "C:\\Users\\User\\Marketing-Agent",
    colorRgb: "251, 191, 36",
    textClass: "text-amber-400",
    family: false,
    description:
      "Solara is the Sun Biz operations brain. She runs the back office — pipeline reports, application packaging, lender matching, renewal sweeps — and keeps the team aligned on what's working and what's stuck.",
    askMeAbout: "Show renewal opportunities · Pipeline this week · Which deals need lender action?",
    setup_questions: [
      {
        id: "fico_floor",
        label: "Minimum FICO you'll qualify",
        description: "Below this, Solara auto-marks applications as unqualified.",
        type: "number",
        required: true,
        default: 450,
        placeholder: "450",
      },
      {
        id: "monthly_revenue_floor_usd",
        label: "Minimum monthly revenue (USD)",
        description: "Solara filters submissions below this before lender matching.",
        type: "number",
        required: true,
        default: 10000,
        placeholder: "10000",
      },
      {
        id: "months_in_business_floor",
        label: "Minimum months in business",
        type: "number",
        required: true,
        default: 6,
        placeholder: "6",
      },
      {
        id: "renewal_window_days",
        label: "Pre-expiry renewal window (days)",
        description: "How early Solara starts working renewal candidates. 60 is industry standard.",
        type: "number",
        default: 60,
        placeholder: "60",
      },
    ],
  },
  // Sun Biz Funding — brand-facing sales persona. Outreach, SMS follow-ups,
  // closing voice. The agent SunBiz leads experience.
  helios: {
    key: "helios",
    label: "Helios",
    role: "Sun Biz sales agent · cold outreach · SMS follow-ups · closing voice",
    tagline: "Outreach · SMS · sales",
    location: "C:\\Users\\User\\Marketing-Agent",
    colorRgb: "245, 158, 11",
    textClass: "text-amber-300",
    family: false,
    description:
      "Helios is the SunBiz sales voice. Personable, results-driven, sharp on cadence — drafts first-touch SMS, runs revival sequences for ghosted leads, brings expired offers back to the table.",
    askMeAbout: "Draft a first-touch SMS · Revival sequence for ghosted leads · Close-the-loop on expired offer",
    setup_questions: [
      {
        id: "opt_out_phrase",
        label: "TCPA opt-out language",
        description: "Helios appends this to every first-touch SMS. Required by federal law.",
        type: "text",
        required: true,
        default: "Reply STOP to opt out.",
        placeholder: "Reply STOP to opt out.",
      },
      {
        id: "send_window_local",
        label: "SMS send window (local time)",
        description: "Helios refuses outbound outside this range.",
        type: "select",
        required: true,
        default: "9am-9pm",
        options: [
          { value: "9am-9pm", label: "9 AM – 9 PM (standard)" },
          { value: "10am-7pm", label: "10 AM – 7 PM (conservative)" },
          { value: "8am-8pm", label: "8 AM – 8 PM (extended)" },
        ],
      },
      {
        id: "weekend_sends",
        label: "Allow weekend sends?",
        description: "Sat/Sun outreach. Most funding shops keep this off.",
        type: "boolean",
        default: false,
      },
      {
        id: "max_blast_size",
        label: "Max audience size per blast",
        description: "Caps how many recipients Helios will queue in a single send. Prevents accidental million-message blasts.",
        type: "number",
        default: 500,
        placeholder: "500",
      },
    ],
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

/**
 * Backward-compatibility aliases. Legacy DB rows + integration registries
 * may still carry slugs like "sunbiz" (the old key for Solara) or "suga_sean"
 * (the old Suga client agent). Resolve them transparently so chat + UI keep
 * working while migrations roll forward.
 */
export const AGENT_KEY_ALIASES: Record<string, string> = {
  solar: "solara",
  sunbiz: "solara",
  // Lyra package removed 2026-05-14 — brand/content work folds into Maven.
  // Legacy "suga_sean" + "lyra*" rows in user_profiles.agents_enabled
  // resolve to Maven so existing tenants keep rendering without DB writes.
  suga_sean: "maven",
  lyra: "maven",
  lyra_brand: "maven",
  lyra_fans: "maven",
  lyra_commerce: "maven",
};

export function resolveAgentKey(key: string): string {
  return AGENT_KEY_ALIASES[key] || key;
}

export function getAgentInfo(key: string): AgentInfo {
  const resolved = resolveAgentKey(key);
  return (
    AGENT_REGISTRY[resolved] || {
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
