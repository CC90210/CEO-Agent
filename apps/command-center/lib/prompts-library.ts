/**
 * Prompts Library — canonical prompts for the operator to fire at any agent.
 *
 * Two distinct audiences, per CC's spec:
 *   - operator  — personal to OASIS AI's setup. References specific clients,
 *                 partners, MRR target, NEPQ, content pillars. Don't ship to
 *                 clients.
 *   - client    — generic, runs on a client's machine when CC has SSH'd in
 *                 or is walking them through onboarding.
 *   - shared    — works either context.
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
  | "client_handoff"
  | "system_override"
  | "system_health"
  | "system_integration"
  | "ops_daily"
  | "ops_review";

export type PromptAudience = "operator" | "client" | "shared";

export type PromptEntry = {
  id: string;
  category: PromptCategory;
  audience: PromptAudience;
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
  client_handoff: {
    label: "Client handoff",
    description: "Day 1 prompts the client can run themselves once you walk away.",
  },
  system_override: {
    label: "System overrides",
    description: "Force the agent into a specific mode. All start with [OVERRIDE] so the agent knows this isn't a normal message.",
  },
  system_health: {
    label: "System health",
    description: "Diagnose, repair, refactor your stack.",
  },
  system_integration: {
    label: "System integration",
    description: "Drop a GitHub repo, research doc, open-source tool, or competitor pattern. The agent runs the canonical V6.8 cross-reference audit, plans the import, ships it across the relevant siblings.",
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
  // ── SYSTEM INTEGRATION (V6.8.3, 2026-05-16) ───────────────────
  // Canonical surface for "I found a thing, integrate it" moments.
  // Mirrors the disciplined pattern from the mattpocock/skills audit
  // (commits 5aeb5fb → bec2fcc → 5335556). The full prompt body lives
  // in prompts/INTEGRATE_NEW_TOOL.md; this entry is the dashboard click.
  {
    id: "integrate-new-tool",
    category: "system_integration",
    audience: "operator",
    agent: "bravo",
    title: "Integrate a new tool / repo / research",
    description:
      "Paste a GitHub URL, an open-source repo, a research doc, a transcript, a competitor pattern, or any external resource. Bravo (or the right sibling) runs the canonical 6-phase audit: identify → cross-reference → plan → execute → verify symbiosis → commit + propagate. Anti-slop guardrails enforced. Output is load-bearing code, not paperwork.",
    foundational: true,
    tags: ["integration", "audit", "v6.8", "research", "github"],
    prompt:
      "I'm dropping you a new external resource to integrate into the empire. " +
      "Use the canonical workflow in `prompts/INTEGRATE_NEW_TOOL.md` end-to-end. " +
      "Identity probe first — figure out which agent (Bravo / Maven / Atlas / client) this belongs in. " +
      "Run Phase 1 (identify the problem this solves — don't import for the sake of importing). " +
      "Spawn the Phase 2 parallel audit (researcher + Explore agents). " +
      "Synthesize the cross-reference table yourself — never delegate synthesis. " +
      "Write a plan to `~/.claude/plans/<slug>.md` with ADR-0001 hard/soft dependency classification and completeness scores 0-10. " +
      "Call ExitPlanMode for non-trivial work, wait for my approval. " +
      "Execute in layers: substrate → conventions → vocabulary → distribution. " +
      "Run the 4 symbiosis tests after each layer (graph rebuild, retriever pickup, resolver behavior, end-to-end). " +
      "Commit per layer with V6.X.Y semantic-versioning. " +
      "Propagate to siblings via CONTEXT.md + V68_AGENT_OS_PATTERNS.md contract when cross-agent. " +
      "Log a probationary pattern in memory/PATTERNS.md. " +
      "Finish with the memory sync line. " +
      "Resource to integrate: ",
  },
  // ── CLIENT SETUP ────────────────────────────────────────────────
  {
    id: "client-fresh-machine-bootstrap",
    category: "client_setup",
    audience: "client",
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
    audience: "client",
    agent: "bravo",
    title: "Personalize the agent identity",
    description:
      "Replace CC's identity in brain/USER.md + memory/* + the operator secrets file with the new client's. Run after they paste their wizard answers.",
    foundational: true,
    tags: ["onboarding", "identity"],
    prompt:
      "Personalize this clone for the new client. Read their wizard answers from .bravo/profiles/<active>.json, then replace every CC identifier in brain/USER.md, memory/SESSION_LOG.md, memory/ACTIVE_TASKS.md, and any other file that references 'CC' or 'Conaugh McKenna'. Confirm what you changed before committing.",
  },
  {
    id: "client-wire-integrations",
    category: "client_setup",
    audience: "client",
    agent: "bravo",
    title: "Wire the client's integrations",
    description:
      "Walk through every integration in the registry. For each, ask the client what they have a key for and paste it via the bridge.",
    tags: ["onboarding", "keys"],
    prompt:
      "Walk this client through wiring every integration in their stack. Read lib/integrations-registry.ts, then for each api_key integration ask which they have available right now. For ones they have, prompt them to paste the key (we save via the local bridge to the operator secrets file). For ones they don't, tell them which to prioritize and why. Skip OAuth ones for now.",
  },
  {
    id: "client-discover-existing-stack",
    category: "client_setup",
    audience: "client",
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
    audience: "client",
    agent: "bravo",
    title: "Set the client's north-star goal",
    description:
      "Capture the client's primary metric + deadline + path-to. Writes to brain/USER.md so every agent reasons against it.",
    tags: ["onboarding", "strategy"],
    prompt:
      "I want to set this client's north-star goal. Ask me: what metric, what target, by when, and what's the current baseline. Then update brain/USER.md with the goal, draft a 30-day path-to, and tell me which agent owns each leg of it (Bravo for ops, Atlas for money, Maven for content/funnel).",
  },
  {
    id: "client-scaffold-templates",
    category: "client_setup",
    audience: "client",
    agent: "bravo",
    title: "Scaffold their day-1 templates",
    description:
      "Set up the operator's weekday + weekend plan templates with their actual schedule, not CC's defaults.",
    tags: ["onboarding", "templates"],
    prompt:
      "Set up this client's plan templates. Ask me their typical weekday rhythm (wake, deep work, meetings, content, ops, wind-down) and weekend pattern. Write to plan_templates table for both kinds, then materialize today's plan. Show me the schedule before saving so I can edit.",
  },
  {
    id: "client-cron-scope",
    category: "client_setup",
    audience: "client",
    agent: "bravo",
    title: "Scope cron jobs to this client",
    description:
      "Most crons in the default repo are CC-specific. Audit, recommend which to enable / disable for this client.",
    tags: ["onboarding", "crons"],
    prompt:
      "Audit every cron in vercel.json and .agents/workflows/ for this client. For each, tell me: does it apply to their business model? Should we enable, disable, or change frequency? Don't disable anything yet — just give me the recommendation list.",
  },
  {
    id: "client-mcp-setup",
    category: "client_setup",
    audience: "client",
    agent: "bravo",
    title: "Connect their MCP servers",
    description:
      "Each client may want their own MCP servers (Slack, Notion, custom). Walk them through configuring .claude/mcp.json.",
    tags: ["onboarding", "mcp"],
    prompt:
      "Walk this client through setting up their MCP servers. Ask which they want (Slack, Notion, GitHub, custom). For each, generate the .claude/mcp.json entry, walk them through the auth step, then verify the server connects via Claude Code. Skip ones they don't need. NOTE: credential-bearing MCPs (Supabase, GitHub, n8n, Late, Firecrawl, Obsidian) MUST use the scripts/mcp_shims/<name>.js Node-shim pattern (not .cmd wrappers) — the shim loads .env.agents via dotenv and passes windowsHide:true so no cmd.exe flashes on spawn. See scripts/mcp_shims/supabase.js for the canonical pattern when adding a new one.",
  },
  {
    id: "client-second-machine-pair",
    category: "client_setup",
    audience: "client",
    agent: "bravo",
    title: "Pair a second machine to the same dashboard",
    description:
      "Walk a desktop+laptop client through pairing both machines. One stays as production (cron daemons), the other is chat-server only. Foundational — uses the fingerprint-idempotent pair endpoint.",
    foundational: true,
    tags: ["onboarding", "multi-machine", "pair"],
    prompt:
      "Pair this second machine to the same dashboard tenant as the existing one. Read brain/MULTI_MACHINE_PAIRING_PROMPT.md (was MAC_COMMAND_CENTER_PROMPT pre-2026-05-09) for the canonical 12-step playbook. Hard constraint: only ONE machine runs scheduler.py / skool_engine.py daemon / telegram_agent.js — those are state-mutating singletons. The second machine runs ONLY `bravo bridge serve` (the operator-side chat-server). Both bridges paired = both chat-servers visible on /devices. The pair endpoint is idempotent by machine_fingerprint (commit d0e15e0 + migration 030) so re-running is safe. Verify: dashboard /operations shows 2 paired machines, both online, no duplicates.",
  },

  // ── CLIENT OPTIMIZATION ─────────────────────────────────────────
  {
    id: "client-voice-tune",
    category: "client_optimization",
    audience: "client",
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
    audience: "client",
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
    audience: "client",
    agent: "bravo",
    title: "Tighten the cron schedule",
    description:
      "Most clients don't need every cron firing. Audit, recommend a leaner schedule based on their volume.",
    tags: ["crons", "ops"],
    prompt:
      "This client's cron schedule is probably over-tuned for someone running CC's volume. Audit every cron in vercel.json + .agents/workflows/ and recommend a leaner schedule based on their actual lead volume + team size. Be specific about which to disable, which to drop in frequency, which to keep.",
  },
  {
    id: "client-revenue-baseline",
    category: "client_optimization",
    audience: "client",
    agent: "atlas",
    title: "Establish revenue baseline",
    description:
      "First-time financial snapshot for the client. P&L, runway, where the cash is, what's exposed.",
    tags: ["finance", "onboarding"],
    prompt:
      "First-time financial snapshot for this client. Pull whatever you can from their Stripe / bank exports / receipts. Net MRR, monthly burn, runway, top revenue source, top cost. Flag any concentration risk (one client > 40%) or unclaimed deductibles. Save the snapshot to brain/CFO_BASELINE.md.",
  },
  {
    id: "client-content-pillars",
    category: "client_optimization",
    audience: "client",
    agent: "maven",
    title: "Define content pillars",
    description:
      "3-5 themes every post for this client should belong to. Build the matrix.",
    tags: ["content", "brand"],
    prompt:
      "Define 3-5 content pillars for this client. Each pillar: what it's about, who it serves, why it lands with their audience, target cadence per platform. Render as a matrix. Anchor against their north-star goal.",
  },

  // ── CLIENT HANDOFF (day-1 self-serve) ──────────────────────────
  {
    id: "client-handoff-first-chat",
    category: "client_handoff",
    audience: "client",
    agent: "bravo",
    title: "First conversation: orient yourself",
    description:
      "What the client runs first when they sit down on day 1 alone with the dashboard.",
    foundational: true,
    tags: ["handoff", "day-one"],
    prompt:
      "Walk me through what you can do for me. Pull my goal from brain/USER.md, list the integrations that are connected vs missing, and give me 3 specific things I can ask you today that would move me toward my goal.",
  },
  {
    id: "client-handoff-how-to-correct",
    category: "client_handoff",
    audience: "client",
    agent: "bravo",
    title: "Teach me how to correct you",
    description:
      "Show the client how to use [OVERRIDE] when the agent does something they don't want.",
    foundational: true,
    tags: ["handoff", "feedback"],
    prompt:
      "Teach me how to course-correct you. Walk me through the [OVERRIDE] syntax with 3 example scenarios: (1) the voice was off, (2) you sent something I didn't want sent, (3) I want you to pause autonomous activity for the day. Show me the exact syntax for each.",
  },
  {
    id: "client-handoff-daily-rhythm",
    category: "client_handoff",
    audience: "client",
    agent: "bravo",
    title: "Set my daily rhythm",
    description:
      "Customize the Today page templates to the client's actual day, not CC's defaults.",
    foundational: true,
    tags: ["handoff", "templates"],
    prompt:
      "Help me customize my Today page. My typical workday looks like: <I'll describe>. Build the weekday + weekend templates around that, save them, and materialize today's plan from the new template.",
  },

  // ── SYSTEM OVERRIDES ────────────────────────────────────────────
  {
    id: "override-correction",
    category: "system_override",
    audience: "shared",
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
    audience: "shared",
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
    audience: "shared",
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
    audience: "shared",
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
    audience: "shared",
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
    audience: "shared",
    agent: "bravo",
    title: "Full system health diagnostic",
    description:
      "Test every MCP server, check configs, verify file integrity. Auto-fixes mechanical issues.",
    foundational: true,
    tags: ["health", "diagnostic"],
    prompt:
      "Run a full system health diagnostic. Test every MCP server, check the integrity of brain/, memory/, skills/, and scripts/. Verify all credentials are still valid. Auto-fix mechanical issues (broken imports, dead links, stale counts). Give me a clear pass/fail per subsystem at the end.",
  },
  {
    id: "health-self-audit",
    category: "system_health",
    audience: "shared",
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
    audience: "shared",
    agent: "bravo",
    title: "Bridge + dashboard status",
    description:
      "Verify the local bridge is paired, heartbeating, and the dashboard sees it as online.",
    tags: ["health", "bridge"],
    prompt:
      "Check the bridge status: is the local chat server running on :9100, is it paired with the dashboard, is /devices showing it as online, and is the heartbeat thread firing every 60s? If anything's off, tell me which to fix first.",
  },
  {
    id: "health-metric-audit",
    category: "system_health",
    audience: "shared",
    agent: "bravo",
    title: "Audit every dashboard metric",
    description:
      "Walk every number on every page, verify it's real or flag it as facade.",
    tags: ["health", "audit", "transparency"],
    prompt:
      "Walk through every metric on the Today, Pipeline, Operations, Agents, and Reasoning pages. For each: trace it to the backing query + table, verify the data is real (not a hardcoded placeholder), flag anything stale or fake. Update brain/METRIC_AUDIT.md with your findings.",
  },
  {
    id: "client-bridge-restart",
    category: "system_health",
    audience: "shared",
    agent: "bravo",
    title: "Restart the bridge cleanly",
    description:
      "One command. Stops both the heartbeat daemon AND the chat-server, waits for :9100 to free, restarts both. Foundational.",
    foundational: true,
    tags: ["bridge", "restart", "operator"],
    prompt:
      "Run `bravo bridge restart` to cleanly cycle both the heartbeat daemon and the chat-server. After it completes, verify with `curl -s http://127.0.0.1:9100/warm-status` — expect `{\"ok\": true, ...}`. If port :9100 doesn't free in time, the restart waits and retries. This is the canonical 'chat feels stuck' move — replaces the old 'kill python.exe in Task Manager' ritual.",
  },
  {
    id: "client-popup-audit",
    category: "system_health",
    audience: "shared",
    agent: "bravo",
    title: "Audit recurring terminal popups",
    description:
      "If a terminal window keeps popping up, run this. Enumerates orphan polling loops, missing CREATE_NO_WINDOW flags, scheduled-task state. Foundational.",
    foundational: true,
    tags: ["health", "popup", "diagnostic"],
    prompt:
      "A terminal window keeps popping up on the operator's screen. Diagnose the source using the same playbook CC ran on 2026-05-09: (1) start a silent watcher script that logs every NEW cmd.exe / conhost / wscript spawn with parent + grandparent for 5 min; (2) bucket the captured spawns by parent process — common culprits are leaked Bash background loops (`until` polling), the bridge heartbeat probing for `playwright.cmd` without STARTUPINFO+SW_HIDE, the BravoSystemHealth scheduled task firing reap_orphan_mcps, and claude.exe spawning MCP servers via `cmd /c npx`; (3) for each culprit, recommend one of: kill the orphan loop (background bash with `KillShell`), patch the subprocess call to add `creationflags=WINDOWLESS_FLAGS` from `_subprocess_helpers` AND `startupinfo=windowless_startupinfo()` for .cmd shims, or switch from python.exe to pythonw.exe for any long-lived daemon. Reference: commits 64ae7b6 (helper consolidation) + 59d773c (heartbeat fix) + 871d71a (skool daemon fix). Report findings + ship the fixes.",
  },

  // ── OPS DAILY ───────────────────────────────────────────────────
  {
    id: "ops-morning-briefing",
    category: "ops_daily",
    audience: "operator",
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
    audience: "operator",
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
    audience: "operator",
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
    audience: "operator",
    agent: "atlas",
    title: "Pre-decision-prep",
    description:
      "Before any commitment over $500 or 10 hrs: Atlas runs the financial + opportunity-cost math.",
    tags: ["daily", "money"],
    prompt:
      "I'm about to commit to <decision>. Run the financial math: cost (real + opportunity), expected return, payback period, and how it shifts my $5K MRR trajectory. Tell me yes/no/wait with one reason.",
  },
  {
    id: "ops-inbox-triage",
    category: "ops_daily",
    audience: "shared",
    agent: "bravo",
    title: "Inbox triage",
    description:
      "Sort the inbound: respond now, schedule, archive, ignore.",
    tags: ["daily", "comms"],
    prompt:
      "Triage my inbox. For each unread email or DM in the last 24h, classify: respond now (high signal), schedule for later (defer with date), archive (no action needed), or ignore (noise). For respond-now, draft my reply. Don't send anything — draft only.",
  },

  // ── OPS REVIEW ──────────────────────────────────────────────────
  {
    id: "ops-end-of-day",
    category: "ops_review",
    audience: "shared",
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
    audience: "operator",
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
    audience: "shared",
    agent: "bravo",
    title: "Quarterly review",
    description:
      "Big-picture: are we still on the right product / market / pricing? What to ship vs. kill.",
    tags: ["review", "quarterly"],
    prompt:
      "Quarterly review. Big-picture only — are we still on the right product, the right market, the right pricing? What's working that we should double down on. What's not working that we should kill. What's missing that we need to ship. Update brain/STATE.md with the new direction if anything changes.",
  },

  // ── INBOX HANDOFFS ─────────────────────────────────────────────
  // Triggers that ask one agent to post a structured handoff to
  // another via tmp/agent_inbox/ + Supabase agent_messages. These
  // are how CC moves work between agents without copy-pasting.
  {
    id: "ops-inbox-handoff-bravo-to-atlas",
    category: "ops_daily",
    audience: "operator",
    agent: "bravo",
    title: "Hand off to Atlas (CFO)",
    description:
      "Tell Bravo to draft a handoff for Atlas — tax/cashflow/budget review. Posts to inbox so Atlas picks it up next run.",
    tags: ["inbox", "handoff", "atlas"],
    prompt:
      "I need Atlas to review something. Take what we just discussed, write a clear, specific handoff (priority + needs-reply), and post it to the agent inbox addressed to atlas. Keep the body to 5–8 lines, concrete asks only. Confirm the message id back to me.",
  },
  {
    id: "ops-inbox-handoff-bravo-to-maven",
    category: "ops_daily",
    audience: "operator",
    agent: "bravo",
    title: "Hand off to Maven (CMO)",
    description:
      "Tell Bravo to draft a handoff for Maven — content, ads, funnels. Posts to inbox so Maven picks it up next run.",
    tags: ["inbox", "handoff", "maven"],
    prompt:
      "I need Maven to take this on. Summarize the brief in 5–8 lines, set priority, mark needs-reply if you want a back-and-forth, and post it to the agent inbox addressed to maven. Confirm the message id back to me.",
  },
  {
    id: "ops-inbox-check",
    category: "ops_daily",
    audience: "shared",
    agent: "bravo",
    title: "Check the inbox",
    description:
      "Read all unread messages, summarize what each one needs, and recommend which to action first.",
    tags: ["inbox", "review"],
    prompt:
      "Read every unread message in the agent inbox. For each: who sent it, what they need, the priority. Then rank them by what'll move the business most. End with a one-line recommendation on what I should action first.",
  },
];

export function promptsByCategory(category: PromptCategory): PromptEntry[] {
  return PROMPTS_LIBRARY.filter((p) => p.category === category);
}

export function promptsByAudience(audience: PromptAudience): PromptEntry[] {
  return PROMPTS_LIBRARY.filter(
    (p) => p.audience === audience || p.audience === "shared"
  );
}
