/**
 * Per-agent personalization questionnaire used by /configure step 2 and
 * the post-install setup wizard.
 *
 * Each agent has its own schema because asking Lumen about "MRR target"
 * makes no sense. The schema drives:
 *   1. What inputs render in /configure step 2
 *   2. What env vars get baked into the install command (OASIS_<KEY>)
 *   3. What the wizard pre-fills server-side after install
 *
 * Adding a new agent? Add an entry here. Adding a new question to an
 * existing agent? Append to its array — the env var and form input both
 * generate from the schema.
 */

export type Question = {
  /** Env-var suffix — the install command bakes this as OASIS_<KEY>. */
  key: string;
  /** Field label rendered in the form. */
  label: string;
  /** Placeholder text shown in the empty input. */
  placeholder?: string;
  /** Input type — defaults to text. Numeric coerces to number on submit. */
  type?: "text" | "number" | "select" | "textarea";
  /** For select inputs only — option labels (also used as values). */
  options?: string[];
  /** True if the form should not let the user advance without an answer. */
  required?: boolean;
  /** Optional inline help under the label. */
  help?: string;
};

export const AGENT_QUESTIONS: Record<string, Question[]> = {
  bravo: [
    { key: "OPERATOR_NAME", label: "Your name", placeholder: "Jane Doe", required: true },
    { key: "BRAND", label: "Brand or company", placeholder: "Acme AI", required: true },
    {
      key: "BUSINESS_MODEL",
      label: "Business model",
      placeholder: "Agency, retainer-based · SaaS, monthly subscriptions · etc.",
      help: "Drives how Bravo prioritizes leads, drafts outbound, and sets cadence.",
    },
    {
      key: "ICP",
      label: "Ideal customer profile",
      placeholder: "Local service businesses doing $500K-2M, decision-maker is owner-operator",
      type: "textarea",
    },
    {
      key: "MRR_TARGET",
      label: "MRR target (USD)",
      placeholder: "5000",
      type: "number",
      help: "What's the next milestone you're climbing toward?",
    },
    {
      key: "MRR_DEADLINE",
      label: "Target deadline",
      placeholder: "2026-12-31",
      help: "YYYY-MM-DD — drives the GoalCountdownCard on /.",
    },
    {
      key: "VOICE_SAMPLES",
      label: "How do you actually write? (paste 2-3 examples)",
      placeholder: "Recent emails, social posts, DMs — anything in your real voice.",
      type: "textarea",
      help: "Without this, Bravo's drafts will sound like a generic AI agent.",
    },
  ],

  atlas: [
    { key: "OPERATOR_NAME", label: "Your name", placeholder: "Jane Doe", required: true },
    {
      key: "TAX_JURISDICTION",
      label: "Tax jurisdiction",
      placeholder: "Canada (Ontario), USA (Delaware), UK, etc.",
      required: true,
      help: "Atlas is CRA-accurate for Canada; international support varies. Tell me what you actually file.",
    },
    {
      key: "INCOME_RANGE",
      label: "Annual income range (USD)",
      type: "select",
      options: ["under $50K", "$50K–$150K", "$150K–$500K", "$500K–$1M", "$1M+"],
      help: "Used for tax-bracket calc and FIRE projection inputs. Atlas never shares this.",
    },
    {
      key: "NET_WORTH_TARGET",
      label: "Net worth goal",
      placeholder: "$1M by 35 · $5M by 45 · etc.",
    },
    {
      key: "RISK_TOLERANCE",
      label: "Risk tolerance",
      type: "select",
      options: ["Conservative (capital preservation first)", "Moderate (balanced growth)", "Aggressive (growth first, accept volatility)"],
    },
    {
      key: "INVESTMENT_VEHICLES",
      label: "What you're already running",
      placeholder: "TFSA, RRSP, Stripe Treasury, taxable brokerage, crypto, real estate",
      type: "textarea",
      help: "Atlas reasons against your real position, not a fictional one.",
    },
    {
      key: "BIGGEST_TAX_PAIN",
      label: "Biggest tax pain right now",
      placeholder: "e.g., capital gains on a sale · undeducted home-office · no incorp yet",
    },
  ],

  maven: [
    { key: "OPERATOR_NAME", label: "Your name", placeholder: "Jane Doe", required: true },
    { key: "BRAND", label: "Brand or company", placeholder: "Acme AI", required: true },
    {
      key: "PRIMARY_PLATFORMS",
      label: "Primary platforms",
      placeholder: "Instagram, TikTok, LinkedIn, X, YouTube, Substack",
      help: "Comma-separated. Maven plans cadence + format per platform.",
    },
    {
      key: "CONTENT_PILLARS",
      label: "Your 3-5 content pillars",
      placeholder: "1. Personal sobriety · 2. AI / building in public · 3. Local biz transformation",
      type: "textarea",
    },
    {
      key: "CONTENT_CADENCE",
      label: "Posts per week (target)",
      placeholder: "5",
      type: "number",
    },
    {
      key: "BRAND_VOICE",
      label: "Brand voice in 3 words",
      placeholder: "Direct, warm, opinionated",
    },
    {
      key: "AD_BUDGET_MONTHLY",
      label: "Monthly ad budget (USD, 0 if none)",
      placeholder: "0",
      type: "number",
    },
    {
      key: "COMPETITOR_HANDLES",
      label: "Competitor handles to study",
      placeholder: "@competitor1, @competitor2 — 3-5 max",
      help: "Maven studies these to extract principles, never to copy.",
    },
  ],

  aura: [
    { key: "OPERATOR_NAME", label: "Your name", placeholder: "Jane Doe", required: true },
    {
      key: "WAKE_TIME",
      label: "Wake time",
      placeholder: "06:30",
      help: "24h format. Aura aligns the morning briefing to this.",
    },
    {
      key: "SLEEP_TARGET",
      label: "Sleep target (hours)",
      placeholder: "8",
      type: "number",
    },
    {
      key: "WORKOUT_CADENCE",
      label: "Workouts per week (target)",
      placeholder: "5",
      type: "number",
    },
    {
      key: "HABIT_GOALS",
      label: "Top 3 habits you want to lock in",
      placeholder: "1. Lift 4×/week · 2. No phone first hour · 3. Read 30 min before bed",
      type: "textarea",
    },
    {
      key: "SMART_HOME",
      label: "Smart-home hub",
      placeholder: "Home Assistant on Pi 5, HomeKit, none yet",
      help: "Tells Aura whether to expose lights/climate/lock controls.",
    },
    {
      key: "PRIVACY_PREFERENCE",
      label: "Habit data sharing",
      type: "select",
      options: [
        "Stays in my tenant — never shared with other agents",
        "Bravo can see workout streak (motivational only)",
        "All siblings can see (Atlas for energy ROI, Maven for content)",
      ],
    },
  ],

  hermes: [
    { key: "COMPANY_NAME", label: "Company name", placeholder: "Lowinger Distribution", required: true },
    { key: "OPERATOR_NAME", label: "Your name", placeholder: "Emmanuel Lowinger", required: true },
    {
      key: "DISTRIBUTION_MODEL",
      label: "Distribution model",
      type: "select",
      options: ["Wholesale only", "Retail only", "Both wholesale + retail", "Drop-ship"],
      required: true,
    },
    {
      key: "ERP_SYSTEM",
      label: "ERP system",
      placeholder: "A2000, NetSuite, SAP B1, QuickBooks, none yet",
      help: "Hermes drives A2000 via desktop takeover; web ERPs via Playwright.",
    },
    {
      key: "PO_VOLUME",
      label: "POs per month (average)",
      placeholder: "200",
      type: "number",
    },
    {
      key: "PRIMARY_RETAILERS",
      label: "Primary retailers / chains",
      placeholder: "Walgreens, CVS, Costco, Whole Foods",
    },
    {
      key: "EDI_REQUIRED",
      label: "EDI required",
      type: "select",
      options: ["Yes — 856/810/940/820", "Yes — partial", "No, not yet"],
    },
    {
      key: "CHARGEBACK_PAIN",
      label: "Chargeback frequency",
      type: "select",
      options: ["Weekly+", "Monthly", "Rare", "Never had one"],
    },
  ],

  "life-preservation": [
    {
      key: "FAMILY_MEMBER_NAME",
      label: "Who is Lumen helping you remember?",
      placeholder: "Grandma Marie, Dad, Aunt Sue",
      required: true,
      help: "First name (or what you call them) is enough. Lumen will use this when speaking back to you.",
    },
    {
      key: "RELATIONSHIP",
      label: "Your relationship to them",
      placeholder: "Granddaughter, son, niece, partner",
      required: true,
    },
    {
      key: "TIMEFRAME",
      label: "Approximate timeframe (if known)",
      placeholder: "6-12 months · diagnosed last week · just want to start now",
      help: "Optional. Helps Lumen pace the work — urgent capture vs. unhurried sessions.",
    },
    {
      key: "MOST_IMPORTANT_TO_CAPTURE",
      label: "What feels most important to capture",
      placeholder: "Her voice, her stories about the war, her recipes, the way she said 'you got it, kid'",
      type: "textarea",
      required: true,
      help: "Be specific. The small details are what carries them forward.",
    },
    {
      key: "EXISTING_RECORDINGS",
      label: "What you already have",
      placeholder: "Voicemails, voice memos, family videos, written letters, recipes in her hand",
      type: "textarea",
      help: "Lumen organizes around what exists before suggesting new captures.",
    },
    {
      key: "SHARING_CIRCLE",
      label: "Who will have access (after)",
      type: "select",
      options: [
        "Just me",
        "Immediate family only (parents, siblings, kids)",
        "Extended family",
        "I'll decide later",
      ],
      help: "Lumen is family-gated by default. You control who can interact with the persona.",
    },
    {
      key: "TONE_PREFERENCE",
      label: "When Lumen speaks back, what tone fits them",
      placeholder: "Warm and dry-humored, reverent, irreverent, blunt, gentle",
    },
  ],

  custom: [
    { key: "OPERATOR_NAME", label: "Your name", placeholder: "Jane Doe", required: true },
    { key: "BRAND", label: "Brand or company (optional)", placeholder: "Acme AI" },
    {
      key: "AGENT_ROLE",
      label: "What should this agent do?",
      placeholder: "e.g., 'Wedding planning ops' or 'Real estate deal sourcing'",
      required: true,
      help: "One-sentence description. The wizard scaffolds a Bravo fork tuned for this role.",
    },
    {
      key: "AGENT_NAME",
      label: "What should we call this agent?",
      placeholder: "Echo, Vellum, Forge — single word, mythological/heroic feel",
      help: "The label that shows in the chat picker and on /agents.",
    },
    {
      key: "NORTH_STAR",
      label: "What's success?",
      placeholder: "100 weddings booked in 2027 · 50 deals closed by Q3",
      type: "textarea",
    },
  ],
};

/**
 * Convert form answers to env-var lines for the install command.
 * Skips empty values so the wizard doesn't bake noise into the env.
 */
export function answersToEnvLines(
  answers: Record<string, string>,
  prefix: "powershell" | "bash"
): string {
  const setter = prefix === "powershell" ? "$env:" : "export ";
  return Object.entries(answers)
    .filter(([, v]) => v && v.trim().length > 0)
    .map(([k, v]) => {
      // Quote and escape — basic safety. PowerShell uses double-quotes;
      // bash uses double-quotes too. We escape any embedded quotes.
      const escaped = v.replace(/"/g, '\\"');
      return `${setter}OASIS_${k}="${escaped}"`;
    })
    .join("\n");
}
