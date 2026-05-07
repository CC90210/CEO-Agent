/**
 * Prompts Library — canonical prompts for the operator to fire at any agent.
 *
 * Three classes of prompt:
 *   1. CLIENT — what to say when setting up a new client / SSH'ing into
 *      their machine / onboarding their environment.
 *   2. SYSTEM — what to say to optimize, reset, or change the agent's
 *      behavior. Includes the operator-override syntax.
 *   3. OPS — what to say for the operator's own daily moves.
 *
 * The override syntax (CC's spec): every "this is not a regular user
 * message" command starts with `[OVERRIDE]` followed by a context line.
 * Hard-coded prompts are foundational + cannot be deleted from the UI;
 * mutable prompts can be added/edited via the dashboard later.
 *
 * Each prompt routes to a specific agent + opens the chat composer
 * pre-filled. Click → /agents?agent=…&prompt=…
 */

export type PromptAgent = "bravo" | "atlas" | "maven" | "aura" | "hermes";
export type PromptCategory =
  | "client_setup"
  | "client_optimization"
  | "system_override"
  | "system_health"
  | "ops_daily"
  | "ops_review";

export type PromptEntry = {
  id: string;
  category: PromptCategory;
  agent: PromptAgent;
  title: string;
  description: string;
  prompt: string;
  /** Hard-coded foundational prompts can't be deleted from the UI. */
  foundational?: boolean;
  tags?: string[];
};

export const PROMPT_CATEGORIES: Record<PromptCategory, { label: string; description: string }> = {
  client_setup: {
    label: "Client setup",
    description: "Drop these when you're SSH'd into a client machine, walking them through onboarding, or kicking off a new deployment.",
  },
  client_optimization: {
    label: "Client optimization",
    description: "Tune an existing client's deployment — voice, tools, daily flow.",
  },
  system_override: {
    label: "System overrides",
    description: "Force the agent into a specific mode. All start with [OVERRIDE] so the agent knows this isn't a normal message.",
  },
  system_health: {
    label: "System health",
    description: "Diagnose, repair, refactor your own stack.",
  },
  ops_daily: {
    label: "Daily ops",
    description: "What to fire every morning / before sales blocks / before content blocks.",
  },
  ops_review: {
    label: "Review + retro",
    description: "End-of-day, end-of-week, end-of-quarter reflections.",
  },
};

export const PROMPTS_LIBRARY: PromptEntry[] = [
  // ── CLIENT SETUP ────────────────────────────────────────────────
  {
    id: "client-fresh-machine-bootstrap",
    category: "client_setup",
    agent: "bravo",
    title: "Bootstrap a fresh client machine",
    description:
      "Run on a brand-new client laptop after install.sh / install.ps1. Verifies install, pairs to dashboard, smoke-tests every CLI tool, lists what's missing.",
    foundational: true,
    tags: ["onboarding", "setup", "verify"],
    prompt:
      "Bootstrap this fresh client machine. Verify the install: check that bravo, python, node, and git are on PATH; confirm the bridge is paired with the dashboard; smoke-test every CLI tool in scripts/; list anything that's missing or broken. Tell me exactly what to fix before this client is production-ready.",
  },
  {
    id: "client-personalize-identity",
    category: "client_setup",
    agent: "bravo",
    title: "Personalize the agent identity",
    description:
      "Replace CC's identity in brain/USER.md + memory/* + .env.agents with the new client's. Run after they paste their wizard answers.",
    foundational: true,
    tags: ["onboarding", "identity"],
    prompt:
      "Personalize this clone for the new client. Read their wizard answers from .bravo/profiles/<active>.json, then replace every CC identifier in brain/USER.md, memory/SESSION_LOG.md, memory/ACTIVE_TASKS.md, and any other file that references 'CC' or 'Conaugh McKenna'. Confirm what you changed before committing.",
  },
  {
    id: "client-wire-integrations",
    category: "client_setup",
    agent: "bravo",
    title: "Wire the client's integrations",
    description:
      "Walk through every integration in the registry. For each, ask the client what they have a key for and paste it via the bridge.",
    tags: ["onboarding", "keys"],
    prompt:
      "Walk this client through wiring every integration in their stack. Read lib/integrations-registry.ts, then for each api_key integration ask which they have available right now. For ones they have, prompt them to paste the key (we save via the local bridge to .env.agents). For ones they don't, tell them which to prioritize and why. Skip OAuth ones for now.",
  },
  {
    id: "client-discover-existing-stack",
    category: "client_setup",
    agent: "bravo",
    title: "Discover what's already running",
    description:
      "Scan the client's existing tools — n8n workflows, Stripe products, Supabase tables, Gmail labels. Map their reality before building on top.",
    tags: ["onboarding", "audit"],
    prompt:
      "Scan this client's existing stack. List their n8n workflows, Stripe products + active subscriptions, Supabase tables + recent activity, Gmail labels + unread counts. Map what they already have so we don't accidentally overwrite anything when we build on top.",
  },
  {
    id: "client-set-north-star",
    category: "client_setup",
    agent: "bravo",
    title: "Set the client's north-star goal",
    description:
      "Capture the client's primary metric + deadline + path-to. Writes to brain/USER.md so every agent reasons against it.",
    tags: ["onboarding", "strategy"],
    prompt:
      "I want to set this client's north-star goal. Ask me: what metric, what target, by when, and what's the current baseline. Then update brain/USER.md with the goal, draft a 30-day path-to, and tell me which agent owns each leg of it (Bravo for ops, Atlas for money, Maven for content/funnel).",
  },

  // ── CLIENT OPTIMIZATION ─────────────────────────────────────────
  {
    id: "client-voice-tune",
    category: "client_optimization",
    agent: "bravo",
    title: "Tune the agent's voice",
    description:
      "Paste 3-5 examples of the client's actual writing → agent rewrites brain/SOUL.md voice section to match.",
    tags: ["voice", "brand"],
    prompt:
      "I'm going to paste 3-5 examples of how this client actually writes (emails, social posts, DMs). Use them to update the voice section of brain/SOUL.md so future drafts match. Pull out: tone words, sentence rhythm, signature phrases, things they never say.",
  },
  {
    id: "client-prune-skills",
    category: "client_optimization",
    agent: "bravo",
    title: "Prune skills that don't apply",
    description:
      "Disable skills that don't match the client's business model. E.g., a real-estate client doesn't need DJ booking flows.",
    tags: ["skills", "scope"],
    prompt:
      "This client doesn't run a {business_type}. Audit skills/ and tell me which skills are irrelevant to their model. For each, propose: disable, archive, or keep as future-option. Don't delete anything yet — just give me the list ranked by 'least relevant' first.",
  },
  {
    id: "client-tighten-cron-schedule",
    category: "client_optimization",
    agent: "bravo",
    title: "Tighten the cron schedule",
    description:
      "Most clients don't need every cron firing. Audit, recommend a leaner schedule based on their volume.",
    tags: ["crons", "ops"],
    prompt:
      "This client's cron schedule is probably over-tuned for someone running CC's volume. Audit every cron in vercel.json + .agents/workflows/ and recommend a leaner schedule based on their actual lead volume + team size. Be specific about which to disable, which to drop in frequency, which to keep.",
  },

  // ── SYSTEM OVERRIDES ────────────────────────────────────────────
  {
    id: "override-correction",
    category: "system_override",
    agent: "bravo",
    title: "Correct the agent's behavior",
    description:
      "When the agent did something wrong and you want it to remember the correction permanently. Saves to memory/MISTAKES.md.",
    foundational: true,
    tags: ["override", "feedback"],
    prompt:
      "[OVERRIDE]\nContext: <describe what the agent did wrong + what it should have done instead>\n\nLog this as a permanent correction in memory/MISTAKES.md with the root cause and the rule to apply going forward. Don't try to fix the immediate task — just lock in the lesson so it never happens again.",
  },
  {
    id: "override-pause-cron",
    category: "system_override",
    agent: "bravo",
    title: "Pause an autonomous loop",
    description:
      "Stop a cron / agent from firing while you debug or travel. Expires automatically after 24h.",
    foundational: true,
    tags: ["override", "cron"],
    prompt:
      "[OVERRIDE]\nContext: pause autonomous agent activity for the next 24h.\n\nDisable every cron in vercel.json by setting it to a date in the past. List what you disabled, the original schedule, and write a re-enable script I can run when I'm back. Do NOT touch any data — just the cron triggers.",
  },
  {
    id: "override-voice-shift",
    category: "system_override",
    agent: "bravo",
    title: "Shift voice for one task",
    description:
      "Override the brand voice for a specific output (e.g., a formal proposal, a legal email).",
    tags: ["override", "voice"],
    prompt:
      "[OVERRIDE]\nContext: for this task only, write in <formal / clinical / playful / etc> voice — NOT the usual brand voice.\n\nDo not save this preference. After this task, revert to brain/SOUL.md voice. The task: <describe>.",
  },
  {
    id: "override-do-not-send",
    category: "system_override",
    agent: "bravo",
    title: "Draft only — never send",
    description:
      "When you want a draft but the agent should NOT auto-fire send_gateway / publish / post.",
    foundational: true,
    tags: ["override", "safety"],
    prompt:
      "[OVERRIDE]\nContext: draft-only mode for the next request.\n\nProduce the draft and stop. Do NOT call send_gateway, late_tool publish, or any mutating script. I will review and fire it manually.",
  },
  {
    id: "override-private-mode",
    category: "system_override",
    agent: "bravo",
    title: "Private mode — no logging",
    description:
      "For sensitive conversations: no SESSION_LOG entry, no agent_events publish, no traces.",
    tags: ["override", "privacy"],
    prompt:
      "[OVERRIDE]\nContext: private mode for this conversation.\n\nDo NOT write to memory/SESSION_LOG.md, do NOT publish to agent_events, do NOT call any persistence path. Hold context in memory only. Confirm you understand before I continue.",
  },

  // ── SYSTEM HEALTH ───────────────────────────────────────────────
  {
    id: "health-full-diagnostic",
    category: "system_health",
    agent: "bravo",
    title: "Full system health diagnostic",
    description:
      "Test every MCP server, check configs, verify file integrity. Auto-fixes mechanical issues.",
    foundational: true,
    tags: ["health", "diagnostic"],
    prompt:
      "Run a full system health diagnostic. Test every MCP server, check the integrity of brain/, memory/, skills/, and scripts/. Verify all credentials in .env.agents are still valid. Auto-fix mechanical issues (broken imports, dead links, stale counts). Give me a clear pass/fail per subsystem at the end.",
  },
  {
    id: "health-self-audit",
    category: "system_health",
    agent: "bravo",
    title: "Self-audit drift",
    description:
      "Detect when files have drifted from canonical state. Score the system, name the drift, propose fixes.",
    tags: ["health", "audit"],
    prompt:
      "Run scripts/self_audit.py and walk me through its output. Score the current state, name the top 3 drift issues, and for each propose the fix as either: auto-fixable (do it now), needs my judgment (ask me), or out of scope (skip).",
  },
  {
    id: "health-bridge-status",
    category: "system_health",
    agent: "bravo",
    title: "Bridge + dashboard status",
    description:
      "Verify the local bridge is paired, heartbeating, and the dashboard sees it as online.",
    tags: ["health", "bridge"],
    prompt:
      "Check the bridge status: is the local chat server running on :9100, is it paired with the dashboard (~/.oasis/bridge_token exists), is the dashboard's /devices showing it as online, and is the heartbeat thread firing every 60s? If anything's off, tell me which to fix first.",
  },

  // ── OPS DAILY ───────────────────────────────────────────────────
  {
    id: "ops-morning-briefing",
    category: "ops_daily",
    agent: "bravo",
    title: "Morning briefing",
    description:
      "MRR, pipeline, client health, top priority — all in one read.",
    foundational: true,
    tags: ["daily", "kickoff"],
    prompt:
      "Give me the morning briefing. MRR + delta from yesterday, pipeline movement, client health alerts, anything from inbound/outbound that needs my eye, and my #1 priority for today. Be punchy.",
  },
  {
    id: "ops-pre-sales-block",
    category: "ops_daily",
    agent: "bravo",
    title: "Pre-sales-block prep",
    description:
      "Before your outreach block: who to call, what they care about, NEPQ openers per lead.",
    tags: ["daily", "sales"],
    prompt:
      "I'm about to start a 90-min outreach block. Pull every qualified lead I haven't touched in 3+ days, rank by score, give me a custom NEPQ opener for each based on their last interaction. Format: lead name + company + opener + 1-line context.",
  },
  {
    id: "ops-pre-content-block",
    category: "ops_daily",
    agent: "maven",
    title: "Pre-content-block prep",
    description:
      "Hook variants + raw outline for today's content drop. Voice-checked.",
    tags: ["daily", "content"],
    prompt:
      "I'm about to record today's content. Give me 3 hook variants and a raw outline in CC's voice. Reference anything noteworthy from this week. Each hook should pass the brand-voice check (no AI-slop openers, no 'It's worth noting that').",
  },
  {
    id: "ops-decision-prep",
    category: "ops_daily",
    agent: "atlas",
    title: "Pre-decision-prep",
    description:
      "Before any commitment over $500 or 10 hrs: Atlas runs the financial + opportunity-cost math.",
    tags: ["daily", "money"],
    prompt:
      "I'm about to commit to <decision>. Run the financial math: cost (real + opportunity), expected return, payback period, and how it shifts my $5K MRR trajectory. Tell me yes/no/wait with one reason.",
  },

  // ── OPS REVIEW ──────────────────────────────────────────────────
  {
    id: "ops-end-of-day",
    category: "ops_review",
    agent: "bravo",
    title: "End-of-day reflection",
    description:
      "What moved, what didn't, one lesson, tomorrow's #1.",
    foundational: true,
    tags: ["review", "daily"],
    prompt:
      "End-of-day reflection. What actually moved today (revenue, pipeline, content, ops). What didn't and why. One lesson worth saving to memory/PATTERNS.md or memory/MISTAKES.md. Tomorrow's #1 priority based on what I just did.",
  },
  {
    id: "ops-weekly-retro",
    category: "ops_review",
    agent: "bravo",
    title: "Weekly retro",
    description:
      "Did we actually move toward $5K MRR this week? What worked, what didn't, what changes next week.",
    tags: ["review", "weekly"],
    prompt:
      "Weekly retrospective. Trajectory toward $5K MRR — are we accelerating or stalling? What worked this week (specific actions, not categories). What didn't. One process change for next week. Save the retro to memory/RETROS.md.",
  },
  {
    id: "ops-quarterly-review",
    category: "ops_review",
    agent: "bravo",
    title: "Quarterly review",
    description:
      "Big-picture: are we still on the right product / market / pricing? What to ship vs. kill.",
    tags: ["review", "quarterly"],
    prompt:
      "Quarterly review. Big-picture only — are we still on the right product, the right market, the right pricing? What's working that we should double down on. What's not working that we should kill. What's missing that we need to ship. Update brain/STATE.md with the new direction if anything changes.",
  },
];

export function promptsByCategory(category: PromptCategory): PromptEntry[] {
  return PROMPTS_LIBRARY.filter((p) => p.category === category);
}
