/**
 * Slash command registry for the Reasoning page.
 *
 * Source of truth: each agent ships a `.agents/workflows/*.md` directory with
 * one file per command. Frontmatter `description:` is what the operator sees.
 * Filename stem becomes the command slug (e.g. `health.md` -> `/health`).
 *
 * Why static here, not read at runtime: the dashboard runs on Vercel
 * serverless — it doesn't have access to the operator's local agent repos.
 * Catalog is curated here per agent, kept in sync with each agent's actual
 * workflows/ dir. CI / a maintenance script could regenerate this from the
 * three repos when commands change.
 *
 * The point of the page: tell the operator EXACTLY what to paste in their
 * terminal to run a given command — including the cd to the right repo and
 * any pre-flight env-var hints.
 */

export type AgentSlug = "bravo" | "atlas" | "maven" | "aura" | "hermes" | "codex";

export type SlashCommand = {
  slug: string;             // e.g. "health" — without the leading slash
  agent: AgentSlug;
  description: string;
  category?: string;        // for grouping in the UI
  /** What the operator pastes into their local terminal. */
  cli_invocation: string;
  /** What `cd` they need to be in first (helpful, but not required). */
  cwd_hint: string;
  /** Optional notes (e.g. "requires X env var", "creates a PR") */
  notes?: string;
};

// ─────────────────────────────────────────────────────────────────
// BRAVO — c:/Users/User/Business-Empire-Agent/.agents/workflows/
// ─────────────────────────────────────────────────────────────────
const BRAVO_REPO = "c:/Users/User/Business-Empire-Agent";

const BRAVO: SlashCommand[] = [
  { slug: "health", agent: "bravo", category: "ops", description: "Full system health diagnostic — test all MCP servers, check configs, verify file integrity",
    cli_invocation: "claude /health",  cwd_hint: BRAVO_REPO, notes: "Auto-fixes broken configs where it can." },
  { slug: "ceo-briefing", agent: "bravo", category: "exec", description: "MRR + pipeline + client health + #1 priority for the day",
    cli_invocation: "python scripts/ceo_dashboard.py briefing", cwd_hint: BRAVO_REPO },
  { slug: "client-health-report", agent: "bravo", category: "clients", description: "Score every active client on health (engagement, payments, recency)",
    cli_invocation: "python scripts/client_health.py report", cwd_hint: BRAVO_REPO },
  { slug: "client-onboard", agent: "bravo", category: "clients", description: "New client onboarding workflow — contract, Stripe, CRM, Slack",
    cli_invocation: "claude /client-onboard", cwd_hint: BRAVO_REPO },
  { slug: "close-review", agent: "bravo", category: "sales", description: "Paste a sales-call transcript, get NEPQ+LAER scoring + objection patterns",
    cli_invocation: "claude /close-review", cwd_hint: BRAVO_REPO },
  { slug: "competitive-report", agent: "bravo", category: "intel", description: "Competitive intelligence sweep on a named competitor or vertical",
    cli_invocation: "python scripts/competitive_intel.py report", cwd_hint: BRAVO_REPO },
  { slug: "commit", agent: "bravo", category: "dev", description: "Smart conventional commit with diff summary",
    cli_invocation: "claude /commit", cwd_hint: BRAVO_REPO },
  { slug: "content", agent: "bravo", category: "content", description: "Long-form content from a raw idea or transcript",
    cli_invocation: "claude /content", cwd_hint: BRAVO_REPO },
  { slug: "create-prd", agent: "bravo", category: "dev", description: "Generate a 15-section PRD for a new feature or client deliverable",
    cli_invocation: "claude /create-prd", cwd_hint: BRAVO_REPO },
  { slug: "debug", agent: "bravo", category: "dev", description: "Systematic debugging session — root cause + 5-whys + fix",
    cli_invocation: "claude /debug", cwd_hint: BRAVO_REPO },
  { slug: "evolve", agent: "bravo", category: "agent", description: "Self-evolution sweep — patch known mistakes, surface drift",
    cli_invocation: "claude /evolve", cwd_hint: BRAVO_REPO },
  { slug: "generate-proposal", agent: "bravo", category: "sales", description: "Auto-write a client proposal from a discovery call summary",
    cli_invocation: "python scripts/proposal_generator.py", cwd_hint: BRAVO_REPO },
  { slug: "hyperthink", agent: "bravo", category: "exec", description: "7-phase hyperthink protocol — multi-hypothesis reasoning for hard calls",
    cli_invocation: "claude /hyperthink", cwd_hint: BRAVO_REPO },
  { slug: "investor-update", agent: "bravo", category: "exec", description: "Generate an investor update from the last quarter's metrics",
    cli_invocation: "claude /investor-update", cwd_hint: BRAVO_REPO },
  { slug: "meeting-prep", agent: "bravo", category: "exec", description: "Brief on a person/company from public sources + CRM history",
    cli_invocation: "claude /meeting-prep", cwd_hint: BRAVO_REPO },
  { slug: "ship", agent: "bravo", category: "dev", description: "Full deployment pipeline — test, build, deploy, verify",
    cli_invocation: "claude /ship", cwd_hint: BRAVO_REPO, notes: "Destructive — requires explicit invocation." },
  { slug: "outreach-send", agent: "bravo", category: "sales", description: "Canonical OASIS cold/follow-up email path through send_gateway",
    cli_invocation: "python scripts/outreach_batch.py", cwd_hint: BRAVO_REPO },
  { slug: "retro", agent: "bravo", category: "ops", description: "Session retrospective — log lessons, patterns, mistakes",
    cli_invocation: "claude /retro", cwd_hint: BRAVO_REPO },
];

// ─────────────────────────────────────────────────────────────────
// MAVEN — c:/Users/User/CMO-Agent/.agents/workflows/
// ─────────────────────────────────────────────────────────────────
const MAVEN_REPO = "c:/Users/User/CMO-Agent";

const MAVEN: SlashCommand[] = [
  { slug: "ad-launch", agent: "maven", category: "ads", description: "Launch a Meta or Google ad campaign from a brief",
    cli_invocation: "claude /ad-launch", cwd_hint: MAVEN_REPO, notes: "Requires Meta/Google Ads API tokens in Maven's env." },
  { slug: "audience", agent: "maven", category: "ads", description: "Build a custom audience from CRM segments or lookalike seed",
    cli_invocation: "claude /audience", cwd_hint: MAVEN_REPO },
  { slug: "campaign-create", agent: "maven", category: "ads", description: "Create a multi-platform campaign with copy + creative variants",
    cli_invocation: "claude /campaign-create", cwd_hint: MAVEN_REPO },
  { slug: "performance", agent: "maven", category: "ads", description: "Pull last-7d ad performance + recommend rebalances",
    cli_invocation: "claude /performance", cwd_hint: MAVEN_REPO },
  { slug: "optimize", agent: "maven", category: "ads", description: "Auto-optimize active campaigns — pause losers, scale winners",
    cli_invocation: "claude /optimize", cwd_hint: MAVEN_REPO },
  { slug: "report", agent: "maven", category: "content", description: "Weekly content + ads report — what shipped, what worked",
    cli_invocation: "claude /report", cwd_hint: MAVEN_REPO },
  { slug: "prime", agent: "maven", category: "content", description: "Load full Maven context for a deep content session",
    cli_invocation: "claude /prime", cwd_hint: MAVEN_REPO },
  { slug: "sync", agent: "maven", category: "ops", description: "Sync Maven's pulse with Bravo (cross-agent coordination)",
    cli_invocation: "claude /sync", cwd_hint: MAVEN_REPO },
  { slug: "health", agent: "maven", category: "ops", description: "Maven system health diagnostic",
    cli_invocation: "claude /health", cwd_hint: MAVEN_REPO },
  { slug: "debug", agent: "maven", category: "dev", description: "Systematic debugging in the Maven codebase",
    cli_invocation: "claude /debug", cwd_hint: MAVEN_REPO },
  { slug: "commit", agent: "maven", category: "dev", description: "Conventional commit for the CMO-Agent repo",
    cli_invocation: "claude /commit", cwd_hint: MAVEN_REPO },
];

// ─────────────────────────────────────────────────────────────────
// ATLAS — c:/Users/User/APPS/CFO-Agent/
// Atlas doesn't have a `.agents/workflows/` dir yet (skill-based).
// Surface the most useful Python entrypoints + the few skills as commands.
// ─────────────────────────────────────────────────────────────────
const ATLAS_REPO = "c:/Users/User/APPS/CFO-Agent";

const ATLAS: SlashCommand[] = [
  { slug: "atlas-cash", agent: "atlas", category: "exec", description: "Cash position + runway in months",
    cli_invocation: "python -m atlas cash", cwd_hint: ATLAS_REPO, notes: "Atlas doesn't have slash commands yet — these are CLI entrypoints." },
  { slug: "atlas-tax", agent: "atlas", category: "tax", description: "CRA-accurate tax estimate for the current period",
    cli_invocation: "python -m atlas tax estimate", cwd_hint: ATLAS_REPO },
  { slug: "atlas-budget", agent: "atlas", category: "exec", description: "Monthly budget vs actuals",
    cli_invocation: "python -m atlas budget", cwd_hint: ATLAS_REPO },
  { slug: "atlas-fire", agent: "atlas", category: "exec", description: "FIRE projections — savings rate, target net worth, years to FI",
    cli_invocation: "python -m atlas fire", cwd_hint: ATLAS_REPO },
  { slug: "atlas-pulse", agent: "atlas", category: "ops", description: "Atlas heartbeat — active strategies + 24h P&L",
    cli_invocation: "cat data/pulse/cfo_pulse.json", cwd_hint: ATLAS_REPO },
];

// ─────────────────────────────────────────────────────────────────
// CODEX — pseudo-agent (delegation tool, no slash commands per se)
// ─────────────────────────────────────────────────────────────────
const CODEX_PLUGIN = "/c/Users/User/.claude/codex-plugin";

const CODEX: SlashCommand[] = [
  { slug: "codex-task", agent: "codex", category: "dev", description: "Delegate a backend/debugging task to OpenAI Codex (background)",
    cli_invocation: `node "${CODEX_PLUGIN}/scripts/codex-companion.mjs" task --write "<context + task>"`,
    cwd_hint: BRAVO_REPO, notes: "Always inject stack/file paths/constraints for non-vague results." },
  { slug: "codex-review", agent: "codex", category: "dev", description: "Pre-ship code review of the current branch",
    cli_invocation: `node "${CODEX_PLUGIN}/scripts/codex-companion.mjs" review`,
    cwd_hint: BRAVO_REPO },
  { slug: "codex-adversarial", agent: "codex", category: "dev", description: "Adversarial review — Codex tries to break the design",
    cli_invocation: `node "${CODEX_PLUGIN}/scripts/codex-companion.mjs" adversarial-review "<focus>"`,
    cwd_hint: BRAVO_REPO },
  { slug: "codex-status", agent: "codex", category: "dev", description: "Check status of running Codex tasks",
    cli_invocation: `node "${CODEX_PLUGIN}/scripts/codex-companion.mjs" status`,
    cwd_hint: BRAVO_REPO },
  { slug: "codex-result", agent: "codex", category: "dev", description: "Read result from last finished Codex task",
    cli_invocation: `node "${CODEX_PLUGIN}/scripts/codex-companion.mjs" result`,
    cwd_hint: BRAVO_REPO },
];

// ─────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────

export const ALL_COMMANDS: SlashCommand[] = [...BRAVO, ...MAVEN, ...ATLAS, ...CODEX];

export function commandsForAgents(enabled: string[]): SlashCommand[] {
  const set = new Set(enabled);
  return ALL_COMMANDS.filter((c) => set.has(c.agent));
}

export function commandsByCategory(commands: SlashCommand[]): Record<string, SlashCommand[]> {
  const out: Record<string, SlashCommand[]> = {};
  for (const c of commands) {
    const cat = c.category || "other";
    if (!out[cat]) out[cat] = [];
    out[cat].push(c);
  }
  // Stable sort within each category
  for (const k of Object.keys(out)) {
    out[k].sort((a, b) => a.slug.localeCompare(b.slug));
  }
  return out;
}

export const AGENT_DISPLAY: Record<AgentSlug, { name: string; color: string }> = {
  bravo:  { name: "Bravo",  color: "#3b82f6" },
  atlas:  { name: "Atlas",  color: "#10b981" },
  maven:  { name: "Maven",  color: "#a855f7" },
  aura:   { name: "Aura",   color: "#f59e0b" },
  hermes: { name: "Hermes", color: "#ef4444" },
  codex:  { name: "Codex",  color: "#9ca0a8" },
};
