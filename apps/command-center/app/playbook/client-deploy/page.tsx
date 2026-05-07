import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import {
  ArrowLeft,
  CheckCircle2,
  Sparkles,
  Terminal,
  Users,
  Shield,
  Zap,
  Handshake,
} from "lucide-react";
import {
  PROMPTS_LIBRARY,
  type PromptCategory,
} from "@/lib/prompts-library";

export const dynamic = "force-static";

/**
 * /playbook/client-deploy — the canonical operator runbook for spinning
 * up a new client's machine. Six phases, each backed by chat prompts
 * that fire the right move automatically.
 *
 * CC's spec: "make sure there is a clear path for clients. This is
 * essential. Plan everything so we can attack it properly."
 */

type Phase = {
  number: string;
  title: string;
  duration: string;
  body: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  steps: Array<{
    title: string;
    detail: string;
    /** Either a chat-fire prompt id (looked up in prompts-library) or a static action. */
    promptId?: string;
    cta?: { label: string; href: string };
  }>;
};

const PROMPT_BY_ID = new Map(PROMPTS_LIBRARY.map((p) => [p.id, p]));

const PHASES: Phase[] = [
  {
    number: "01",
    title: "Pre-flight",
    duration: "10 min — before you touch anything",
    icon: Sparkles,
    body:
      "Before opening a terminal, gather what the client needs to have ready. This conversation happens on Telegram / Slack / call — not in the dashboard.",
    steps: [
      {
        title: "Confirm machine specs",
        detail:
          "Mac (10.15+) or Windows 10/11 with admin rights. Python 3.10+, Node 20+, Git. If they don't have Python or Node, we install during phase 02.",
      },
      {
        title: "Ask which AI provider they want",
        detail:
          "Default recommendation: Anthropic direct (one key, full Claude Code experience). Alternative: OpenRouter (cheaper, more model variety). They need to have a key OR be ready to sign up at console.anthropic.com / openrouter.ai during phase 04.",
      },
      {
        title: "Capture identity + business basics",
        detail:
          "Their full name, brand, business model, north-star goal + deadline. This is what the wizard asks; pre-collect so the install is one paste, not a Q&A session.",
      },
      {
        title: "Schedule a 60-minute kickoff session",
        detail:
          "All six phases fit in one hour with you driving. Don't try to async this — the first run benefits from real-time guidance.",
      },
    ],
  },
  {
    number: "02",
    title: "Bootstrap",
    duration: "8 min — install + pair",
    icon: Terminal,
    body:
      "Run the one-line installer. The wizard pairs the machine to your dashboard automatically (HMAC-based self-pair, no token paste required).",
    steps: [
      {
        title: "Send the OS-detected install command",
        detail:
          "From /configure, the appropriate one-liner is auto-detected. Copy it, send to client. They paste, hit Enter, the wizard runs through their pre-collected answers.",
        cta: { label: "Open /configure", href: "/configure" },
      },
      {
        title: "Watch for the auto-pair confirmation",
        detail:
          "When the wizard finishes, it spawns the bridge + heartbeats to /api/bridge/ping. The /devices section should show their machine within 30 seconds. If it doesn't, run the bridge-status diagnostic prompt.",
        promptId: "health-bridge-status",
      },
      {
        title: "Smoke-test every CLI tool",
        detail:
          "Run the bootstrap-fresh-machine prompt. It walks every script, flags anything missing, and tells you exactly what to fix before moving on.",
        promptId: "client-fresh-machine-bootstrap",
      },
    ],
  },
  {
    number: "03",
    title: "Personalize",
    duration: "12 min — make this their agent, not yours",
    icon: Users,
    body:
      "The repo ships with CC's identity baked in. Strip it out and replace with the client's. This is non-optional — until you do it, every draft sounds like CC.",
    steps: [
      {
        title: "Replace operator identity across the codebase",
        detail:
          "The wizard already wrote .bravo/profiles/<client>.json with their answers. The personalize prompt walks brain/USER.md, memory/SESSION_LOG.md, memory/ACTIVE_TASKS.md, and any other file with CC identifiers — replaces with the client's.",
        promptId: "client-personalize-identity",
      },
      {
        title: "Tune the brand voice",
        detail:
          "Ask the client to paste 3-5 examples of how they actually write (recent emails, social posts, DMs). The voice-tune prompt rewrites brain/SOUL.md voice section so future drafts match their tone, not CC's.",
        promptId: "client-voice-tune",
      },
      {
        title: "Set their north-star goal",
        detail:
          "Capture the client's primary metric + deadline + path-to. Writes to brain/USER.md so every agent reasons against it. Without this, content drafts will reference CC's $5K MRR target.",
        promptId: "client-set-north-star",
      },
      {
        title: "Scaffold their daily templates",
        detail:
          "Ask the client to describe their typical weekday + weekend. Build plan_templates from that, materialize today's plan. The Today page should now reflect their rhythm.",
        promptId: "client-scaffold-templates",
      },
    ],
  },
  {
    number: "04",
    title: "Wire integrations",
    duration: "15 min — bring their stack online",
    icon: Zap,
    body:
      "Each api_key integration in the registry has a Connect button that opens a paste-modal. The bridge writes the key to their local secrets file (never touches our servers). Walk through every integration they care about.",
    steps: [
      {
        title: "Walk the integration registry",
        detail:
          "Open /integrations on the client's dashboard. For each api_key tile (Stripe, OpenRouter, Anthropic, Late, Firecrawl, ElevenLabs, etc.), ask if they have a key. If yes, paste via the modal. If no, decide together whether to grab one now or skip.",
        cta: { label: "Open /integrations", href: "/integrations" },
      },
      {
        title: "Discover what's already running",
        detail:
          "Before building on top of their stack, scan what they already have. The discover prompt lists their n8n workflows, Stripe products, Supabase tables, Gmail labels — so you don't accidentally overwrite anything.",
        promptId: "client-discover-existing-stack",
      },
      {
        title: "Verify each integration flips green",
        detail:
          "Each ping fires only on actual tool use, so prompt the agent to make a real call against each newly-connected service. The /integrations page should show a green dot within 30 seconds.",
      },
      {
        title: "Connect MCP servers (optional)",
        detail:
          "If the client has Slack, Notion, GitHub, or custom MCP tooling they want available in chat, walk through setting them up. The mcp-setup prompt generates .claude/mcp.json entries.",
        promptId: "client-mcp-setup",
      },
    ],
  },
  {
    number: "05",
    title: "Scope + tune",
    duration: "10 min — strip what doesn't apply",
    icon: Shield,
    body:
      "The default repo has skills, crons, and prompts tuned for CC's volume + business model. Most of it doesn't apply to the new client. Audit, prune, retune.",
    steps: [
      {
        title: "Prune skills that don't fit",
        detail:
          "If the client doesn't run a DJ side hustle, skills/dj_booking/ is just noise. The prune prompt audits skills/, ranks by least-relevant, recommends disable / archive / keep.",
        promptId: "client-prune-skills",
      },
      {
        title: "Tighten the cron schedule",
        detail:
          "CC's outreach engine fires every 4 hours because he ships 5-10 cold emails/day. A client doing 1-2/week needs a leaner schedule. Audit + recommend.",
        promptId: "client-tighten-cron-schedule",
      },
      {
        title: "Establish revenue baseline",
        detail:
          "First-time financial snapshot via Atlas. P&L, runway, top revenue source, top cost. Saved to brain/CFO_BASELINE.md so every later financial conversation has a starting point.",
        promptId: "client-revenue-baseline",
      },
      {
        title: "Define content pillars",
        detail:
          "If the client publishes content, lock in 3-5 pillars + cadence per platform. Maven runs this.",
        promptId: "client-content-pillars",
      },
    ],
  },
  {
    number: "06",
    title: "Handoff",
    duration: "8 min — they take the wheel",
    icon: Handshake,
    body:
      "Last 8 minutes of the kickoff. Show the client the day-1 prompts they'll run alone. Make sure they know how to correct the agent and where to ask for help.",
    steps: [
      {
        title: "First conversation: orient the client",
        detail:
          "Have the client run the orientation prompt themselves. The agent walks them through what's connected, what's missing, and three specific moves they could fire today.",
        promptId: "client-handoff-first-chat",
      },
      {
        title: "Teach the override syntax",
        detail:
          "Show the client how [OVERRIDE] works with three concrete scenarios. Without this, when the agent does something they don't want, they'll ask you instead of correcting it themselves.",
        promptId: "client-handoff-how-to-correct",
      },
      {
        title: "Customize their daily rhythm",
        detail:
          "Hand the keyboard to the client for this one. They run the rhythm prompt and describe their workday in their own words. Templates regenerate from their answers, not yours.",
        promptId: "client-handoff-daily-rhythm",
      },
      {
        title: "Set support expectations",
        detail:
          "Tell them: (1) override syntax for corrections, (2) Settings page for integrations, (3) /metric-audit if they suspect a number is wrong, (4) you for anything else. Send them a recap email + the dashboard URL.",
      },
    ],
  },
];

function StepRow({ step }: { step: Phase["steps"][number] }) {
  const prompt = step.promptId ? PROMPT_BY_ID.get(step.promptId) : null;
  const promptHref = prompt
    ? `/agents?agent=${encodeURIComponent(prompt.agent)}&prompt=${encodeURIComponent(prompt.prompt)}`
    : null;
  return (
    <li className="border-l-2 border-bg-border pl-4 py-2 hover:border-accent/40 transition-colors">
      <div className="flex items-start gap-2">
        <CheckCircle2 className="w-4 h-4 text-fg-dim shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold text-fg">{step.title}</div>
          <div className="text-xs text-fg-muted mt-1 leading-relaxed">{step.detail}</div>
          <div className="flex items-center gap-3 mt-1.5 flex-wrap">
            {promptHref && (
              <Link
                href={promptHref}
                className="text-[11px] text-accent hover:text-accent-bright inline-flex items-center gap-1"
              >
                <Sparkles className="w-3 h-3" /> run this prompt
              </Link>
            )}
            {step.cta && (
              <Link
                href={step.cta.href}
                className="text-[11px] text-fg-muted hover:text-accent inline-flex items-center gap-1"
              >
                {step.cta.label} →
              </Link>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

export default function ClientDeployPage() {
  const totalSteps = PHASES.reduce((acc, p) => acc + p.steps.length, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <PageHeader
        title="Client deployment runbook"
        subtitle="Your canonical playbook for onboarding a fresh client. Six phases, ~60 minutes, with chat-fire prompts wired into each step. The system runs every move with you."
        action={<Tag tone="accent">{PHASES.length} phases · {totalSteps} steps · ~60 min</Tag>}
      />

      <Card title="What this is" subtitle="Read this once before your first deploy.">
        <div className="text-sm text-fg-muted leading-relaxed space-y-2">
          <p>
            Every client follows the same six-phase arc: <strong className="text-fg">pre-flight → bootstrap → personalize → wire integrations → scope + tune → handoff</strong>. Each phase has 3-5 concrete steps, and most steps link to a chat prompt that the agent runs for you (so you&apos;re not retyping the same instruction every time).
          </p>
          <p>
            The dashboard you&apos;re on right now is the same dashboard the client will have on day 2 — just with their identity, their integrations, their voice. The bridge architecture means their machine is fully self-contained: their API keys, their data, their files. Nothing routes through our servers.
          </p>
          <p>
            <strong className="text-fg">Anti-patterns to avoid:</strong> don&apos;t skip personalize (their content will sound like CC). Don&apos;t skip cron tightening (you&apos;ll wake them up at 3am with notifications meant for someone running 10x their volume). Don&apos;t skip the override-syntax demo in handoff (they&apos;ll come back to you for every correction instead of fixing it themselves).
          </p>
        </div>
      </Card>

      {PHASES.map((phase) => {
        const Icon = phase.icon;
        return (
          <Card
            key={phase.number}
            title={`Phase ${phase.number} · ${phase.title}`}
            subtitle={phase.duration}
            action={<Icon size={20} className="text-accent" />}
          >
            <p className="text-sm text-fg-muted leading-relaxed mb-4">{phase.body}</p>
            <ul className="space-y-1">
              {phase.steps.map((step, i) => (
                <StepRow key={i} step={step} />
              ))}
            </ul>
          </Card>
        );
      })}

      <Card title="After day 1" subtitle="What to schedule + watch for">
        <div className="text-sm text-fg-muted leading-relaxed space-y-2">
          <ul className="list-disc list-inside space-y-1.5">
            <li>
              <strong className="text-fg">Day 7 check-in:</strong> 15-min call. Ask them to walk through their week using the dashboard. Surface any friction.
            </li>
            <li>
              <strong className="text-fg">Day 14 voice + content audit:</strong> review the content they&apos;ve published. Run the voice-tune prompt again with fresh examples — by now there&apos;s real data on what lands with their audience.
            </li>
            <li>
              <strong className="text-fg">Day 30 north-star check:</strong> are they on pace toward their goal? Atlas runs the math, Maven audits the funnel, Bravo names what to change.
            </li>
            <li>
              <strong className="text-fg">Quarterly:</strong> repeat the metric audit prompt against their dashboard. Confirms every number is real and not drifting.
            </li>
          </ul>
        </div>
      </Card>
    </div>
  );
}
