/**
 * Quick Actions for the Reasoning page.
 *
 * Replaces the dev-tool slash-command catalog. Each entry maps to a chat
 * prompt the operator can fire by clicking — no terminal, no `cd`, no
 * `claude /command`. Click → routes to /agents with the prompt pre-filled
 * and the right agent selected. Hit Enter to send.
 *
 * Curated to ~5 per agent — the highest-leverage operator moves. The full
 * 56-command palette is still available behind /reasoning?dev=1 for
 * power-users.
 */

export type AgentSlug = "bravo" | "atlas" | "maven" | "aura" | "hermes";

export type QuickAction = {
  agent: AgentSlug;
  title: string;
  description: string;
  /** Dropped into the chat composer when the operator clicks. */
  prompt: string;
  /** Lucide icon name; rendered by the page. */
  icon: "Sparkles" | "Target" | "Mail" | "FileText" | "TrendingUp" | "Activity" | "Users" | "DollarSign" | "Phone" | "Calendar";
  category: "Daily" | "Sales" | "Money" | "Content" | "Ops" | "Life";
};

export const QUICK_ACTIONS: QuickAction[] = [
  // ── BRAVO — daily ops + sales ──
  {
    agent: "bravo", title: "Run the daily briefing", category: "Daily", icon: "Sparkles",
    description: "MRR, pipeline, client health, top priority for today — all in one read.",
    prompt: "Run my daily briefing. Pull MRR, pipeline, client health, recent inbound, and tell me the #1 thing I should focus on today.",
  },
  {
    agent: "bravo", title: "What leads are qualified?", category: "Sales", icon: "Target",
    description: "Surfaces every qualified lead + recommended next move on each.",
    prompt: "Show me every lead in 'qualified' status. For each, summarize the last interaction, give me a recommended next move, and rank by urgency.",
  },
  {
    agent: "bravo", title: "Send a check-in", category: "Sales", icon: "Mail",
    description: "Draft a personalized follow-up to a specific lead. Names them by recency.",
    prompt: "Show me the 5 leads I haven't touched in the longest time but who are still warm. Suggest who to check in with first and draft the message.",
  },
  {
    agent: "bravo", title: "Score a sales call", category: "Sales", icon: "Phone",
    description: "Paste a transcript, get NEPQ + LAER scoring + objection-handling notes.",
    prompt: "I'm going to paste a sales call transcript. Score it against NEPQ + LAER, flag every objection I missed, and tell me what to say differently next time.",
  },
  {
    agent: "bravo", title: "What changed in the last 24h?", category: "Daily", icon: "Activity",
    description: "Activity tape summary — inbound, outbound, deals moved, integrations health.",
    prompt: "Summarize the last 24 hours: every inbound that landed, every outbound I sent, anything that moved in the pipeline, any integration that flipped status.",
  },

  // ── ATLAS — money + tax ──
  {
    agent: "atlas", title: "Net worth + cash position", category: "Money", icon: "DollarSign",
    description: "Snapshot of every account, total net worth, this week's cash movement.",
    prompt: "Pull my full financial snapshot: net worth across all accounts, cash position, what changed in the last 7 days. Flag anything weird.",
  },
  {
    agent: "atlas", title: "What's owing on tax?", category: "Money", icon: "FileText",
    description: "Quarterly tax obligation, estimated GST/HST, deductible spend so far.",
    prompt: "Calculate my Q2 2026 tax obligation. Include GST/HST, income tax, deductibles I haven't claimed yet, and tell me what to set aside this week.",
  },
  {
    agent: "atlas", title: "FIRE projection", category: "Money", icon: "TrendingUp",
    description: "Years-to-retire at current savings rate, optimistic + pessimistic paths.",
    prompt: "Run a FIRE projection with my current numbers. Show me years-to-retire at: current savings rate, +20% rate, and -20% rate. Be honest about assumptions.",
  },
  {
    agent: "atlas", title: "Red-flag transactions", category: "Money", icon: "Activity",
    description: "Any unusual spend, double-charges, or recurring drains in the last 7 days.",
    prompt: "Scan the last 7 days of bank + Stripe activity. Flag anything unusual, doubled, or that looks like a recurring drain I haven't approved.",
  },
  {
    agent: "atlas", title: "Trading P&L this week", category: "Money", icon: "TrendingUp",
    description: "Strategy-by-strategy P&L, win rate, max drawdown — last 7 days.",
    prompt: "Pull this week's trading P&L by strategy. Win rate, max drawdown, and tell me which strategy to scale + which to pause.",
  },

  // ── MAVEN — content + ads ──
  {
    agent: "maven", title: "Tomorrow's content", category: "Content", icon: "Sparkles",
    description: "3 hooks + a draft for tomorrow's drop, in CC's voice.",
    prompt: "Draft tomorrow's content drop. Give me 3 hook variants and a full body draft in CC's voice. Reference recent wins / anything noteworthy from this week.",
  },
  {
    agent: "maven", title: "What's working in ads?", category: "Content", icon: "TrendingUp",
    description: "Live Meta + Google ad performance — winners, losers, ROAS deltas.",
    prompt: "Pull live ad performance from Meta + Google. Tell me which ad sets are winning, which to kill, and what the ROAS shifts look like vs last week.",
  },
  {
    agent: "maven", title: "Funnel audit", category: "Ops", icon: "Activity",
    description: "Booking page + landing pages — drop-off points, conversion bottlenecks.",
    prompt: "Audit my booking page and landing pages. Find the drop-off points, name the conversion bottlenecks, and recommend the 3 highest-leverage fixes.",
  },
  {
    agent: "maven", title: "This week's content calendar", category: "Content", icon: "Calendar",
    description: "Plan the week — pillars, hooks, posting cadence per platform.",
    prompt: "Plan this week's content calendar. For each pillar, give me 3 post ideas, the platform mix, and the posting cadence. Optimize for inbound funnel.",
  },

  // ── AURA — life + home ──
  {
    agent: "aura", title: "Morning briefing", category: "Life", icon: "Sparkles",
    description: "Last night's sleep, today's calendar, recovery score, weather.",
    prompt: "Give me the morning briefing. Last night's sleep score, today's calendar, recovery, weather, and one thing I should prep for.",
  },
  {
    agent: "aura", title: "Sleep + recovery", category: "Life", icon: "Activity",
    description: "Last 7 nights — trend, recovery score, what's helping or hurting.",
    prompt: "Pull the last 7 nights of sleep data. Show me the recovery trend, name the patterns, and tell me what's helping vs hurting.",
  },
  {
    agent: "aura", title: "Habit audit", category: "Life", icon: "TrendingUp",
    description: "Streak status across every tracked habit. Where am I slipping?",
    prompt: "Audit my habits this week. Streak status on each, where I'm slipping, and which one to double down on tomorrow.",
  },
  {
    agent: "aura", title: "What's on the calendar?", category: "Life", icon: "Calendar",
    description: "Today + tomorrow — meetings, prep needed, conflicts to resolve.",
    prompt: "Walk me through today and tomorrow. Every meeting, prep needed for each, anything conflicting, and what I should reschedule.",
  },

  // ── HERMES — commerce ops ──
  {
    agent: "hermes", title: "Open POs + chargebacks", category: "Ops", icon: "FileText",
    description: "Status of every PO, any chargeback action needed, EDI doc queue.",
    prompt: "Status report: every open PO, every chargeback that needs action, and the EDI doc queue. Flag anything past SLA.",
  },
  {
    agent: "hermes", title: "Generate latest EDI 856", category: "Ops", icon: "Mail",
    description: "Build the EDI 856 advance ship notice for the most recent shipment.",
    prompt: "Generate the EDI 856 advance ship notice for the most recent shipment. Validate against the trading partner's spec before submitting.",
  },
  {
    agent: "hermes", title: "A2000 sync log", category: "Ops", icon: "Activity",
    description: "Yesterday's A2000 ERP sync — what landed, what failed, what to retry.",
    prompt: "Show me yesterday's A2000 sync log. What landed, what failed, what needs a manual retry, and any data integrity issues.",
  },
  {
    agent: "hermes", title: "Commerce alerts", category: "Ops", icon: "Sparkles",
    description: "Anything that needs a human eye in the last 24h — failed orders, low stock, bad addresses.",
    prompt: "Surface every commerce alert from the last 24 hours: failed orders, low stock, bad shipping addresses, payment failures. Rank by urgency.",
  },
];

export function quickActionsFor(agentSlugs: string[]): QuickAction[] {
  const set = new Set(agentSlugs);
  return QUICK_ACTIONS.filter((q) => set.has(q.agent));
}
