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

export const dynamic = "force-dynamic";

const DEPLOY_ICONS = {
  sparkles: Sparkles,
  terminal: Terminal,
  users: Users,
  zap: Zap,
  shield: Shield,
  handshake: Handshake,
} as const;

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
  icon: keyof typeof DEPLOY_ICONS;
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
    icon: "sparkles",
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
          "Three real options. (1) Anthropic direct — one key, full Claude Code CLI experience, ~$20-50/mo for moderate use. Default recommendation. (2) OpenRouter — one key covers every model, cheaper, more variety. (3) Local model via Ollama or LM Studio — zero per-call cost after the model download, runs entirely on their machine, no data leaves. Trade-off: smaller models (Llama 3.3 70B at the top end with a beefy GPU) are noticeably less capable than Claude Sonnet for agentic work. Good fit for clients with strict data-residency requirements or large-volume use cases. Pre-collect their preference so phase 04 is paste-only, not a Q&A.",
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
    icon: "terminal",
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
          "When the wizard finishes, it spawns the bridge + heartbeats to /api/bridge/ping. The /devices section should show their machine within 30 seconds. The pair endpoint is now idempotent by machine_fingerprint (migration 030 + commit d0e15e0): re-runs ROTATE the token on the existing row instead of creating duplicates. Old rows show up as 'revoked' if anything legacy needed cleanup.",
        promptId: "health-bridge-status",
      },
      {
        title: "Smoke-test every CLI tool",
        detail:
          "Run the bootstrap-fresh-machine prompt. It walks every script, flags anything missing, and tells you exactly what to fix before moving on.",
        promptId: "client-fresh-machine-bootstrap",
      },
      {
        title: "Verify zero terminal popups",
        detail:
          "Modern Windows clients should see ZERO console flash on bridge spawn or heartbeat. Triple-flag suppression: pythonw.exe (no console subsystem) + CREATE_NO_WINDOW + STARTUPINFO/SW_HIDE for .cmd shims. If the client reports a recurring popup, run the popup-audit prompt — same diagnostic CC ran on 2026-05-09 to find the four leaked Bash polling loops.",
        promptId: "client-popup-audit",
      },
      {
        title: "Show them the restart command",
        detail:
          "`bravo bridge restart` (commit 35716f4) stops both the heartbeat daemon AND the chat-server, waits for :9100 to free, then re-spawns both. Single command. Replaces the old 'kill python.exe in Task Manager' ritual after code changes.",
        promptId: "client-bridge-restart",
      },
    ],
  },
  {
    number: "03",
    title: "Personalize",
    duration: "12 min — make this their agent, not yours",
    icon: "users",
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
    icon: "zap",
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
          "If the client has Slack, Notion, GitHub, or custom MCP tooling they want available in chat, walk through setting them up. The mcp-setup prompt generates .claude/mcp.json entries. NOTE: as of 2026-05-09 (commit 15a5f89), credential-bearing MCP servers use Node shims at scripts/mcp_shims/<name>.js (NOT the older .cmd wrapper pattern). Each shim loads .env.agents via dotenv and spawns with windowsHide:true — no cmd.exe flash.",
        promptId: "client-mcp-setup",
      },
    ],
  },
  {
    number: "05",
    title: "Scope + tune",
    duration: "10 min — strip what doesn't apply",
    icon: "shield",
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
    icon: "handshake",
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
        title: "Pair their second machine (optional)",
        detail:
          "If the client has a desktop AND a laptop, both can pair to the same dashboard tenant — one machine acts as production (cron daemons stay there), the other adds a chat-server only. The shared dashboard auto-detects which bridge is local. CC's setup uses Windows-as-production + Mac-as-secondary; either direction works. See brain/MULTI_MACHINE_PAIRING_PROMPT.md for the paste-ready agent prompt.",
        promptId: "client-second-machine-pair",
      },
      {
        title: "Set support expectations",
        detail:
          "Tell them: (1) override syntax for corrections, (2) Settings page for integrations, (3) /metric-audit if they suspect a number is wrong, (4) `bravo bridge restart` for any 'chat feels stuck' issue, (5) you for anything else. Send them a recap email + the dashboard URL.",
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

      <Card
        title="Two ways to deploy a client"
        subtitle="Pick the model first. Everything below assumes Path A (full bridge). Path B (cloud-only) is documented here and built out as cloud tools ship."
      >
        <div className="text-sm text-fg-muted leading-relaxed space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-lg border border-accent/40 bg-accent/5 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Tag tone="accent">Path A · Full bridge</Tag>
                <span className="text-[10px] uppercase tracking-wider text-fg-muted">power users · teams · OASIS internal</span>
              </div>
              <div className="text-fg font-medium">Install on their machine. Local Claude Code CLI. Full repo access.</div>
              <ul className="text-xs space-y-1 list-disc pl-4 text-fg-muted">
                <li>Bridge daemon runs on the client&apos;s machine. Files, scripts, MCPs all live local.</li>
                <li>Client supplies their own Claude / OpenRouter / Anthropic key. Never routes through our servers.</li>
                <li>Same capability surface CC has: read brain/, run scripts, send_gateway, every skill.</li>
                <li>Requires admin rights, Python 3.10+, Node 20+, Git. Heavier kickoff (~60 min).</li>
              </ul>
              <div className="text-[11px] text-fg-dim pt-1">
                <strong className="text-fg">Use when:</strong> client is technical, runs their own ops infra, wants full control, or you&apos;re onboarding an OASIS partner who&apos;ll build on top.
              </div>
            </div>

            <div className="rounded-lg border border-bg-border bg-bg p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Tag tone="info">Path B · Cloud only</Tag>
                <span className="text-[10px] uppercase tracking-wider text-fg-muted">most clients · &quot;easy mode&quot;</span>
              </div>
              <div className="text-fg font-medium">No install. Sign up, connect integrations via OAuth. Agent runs in our cloud against their data.</div>
              <ul className="text-xs space-y-1 list-disc pl-4 text-fg-muted">
                <li>Setup wizard collects API key + integration permissions only. No local files.</li>
                <li>Client connects Gmail / Calendar / Stripe via OAuth (we don&apos;t store credentials — we store the OAuth refresh token, scoped to their tenant).</li>
                <li>Agent runs through <code className="text-accent">/api/chat</code> using cloud-tools (send_email, query_stripe, post_lead, etc.) instead of local file reads.</li>
                <li>Setup is 10-15 minutes. Browser only. Works for any client regardless of OS or technical level.</li>
              </ul>
              <div className="text-[11px] text-fg-dim pt-1">
                <strong className="text-fg">Use when:</strong> client is a local service business, doesn&apos;t want to install anything, just wants the outcomes (qualified leads, automated outreach, MRR tracking, content queue).
              </div>
              <div className="text-[11px] text-status-warm pt-1">
                <strong>Status:</strong> the cloud-tools layer (send_email, query_stripe, etc.) is being built out. Until it ships, Path B chat answers strategy/drafting questions but cannot execute. The full Path B onboarding wizard is Tier B work — flagged as the next major build.
              </div>
            </div>
          </div>

          <div className="text-xs text-fg-dim leading-relaxed pt-2 border-t border-bg-border">
            <strong className="text-fg">On the &quot;what powers the model&quot; question:</strong> Path A uses the operator&apos;s Claude Code CLI subscription (best capability surface — pre-baked Read/Edit/Bash/Glob/Grep/MCP tooling). Path B uses any Anthropic-compatible API key (Anthropic / OpenRouter / OpenAI / Google) — same model intelligence, but the tool surface is whatever we wire into <code className="text-accent">/api/chat</code>. They&apos;re not equivalent today: API-key path needs each tool built explicitly, CLI path inherits the whole Claude Code harness for free. We can replicate any individual capability on the cloud side, but it&apos;s case-by-case engineering.
          </div>
        </div>
      </Card>

      <Card title="What this is (Path A)" subtitle="Read this once before your first full-bridge deploy.">
        <div className="text-sm text-fg-muted leading-relaxed space-y-2">
          <p>
            Every <em>Path A</em> client follows the same six-phase arc: <strong className="text-fg">pre-flight → bootstrap → personalize → wire integrations → scope + tune → handoff</strong>. Each phase has 3-5 concrete steps, and most steps link to a chat prompt that the agent runs for you (so you&apos;re not retyping the same instruction every time).
          </p>
          <p>
            The dashboard you&apos;re on right now is the same dashboard the client will have on day 2 — just with their identity, their integrations, their voice. The bridge architecture means their machine is fully self-contained: their API keys, their data, their files. Nothing routes through our servers.
          </p>
          <p>
            <strong className="text-fg">Anti-patterns to avoid:</strong> don&apos;t skip personalize (their content will sound like CC). Don&apos;t skip cron tightening (you&apos;ll wake them up at 3am with notifications meant for someone running 10x their volume). Don&apos;t skip the override-syntax demo in handoff (they&apos;ll come back to you for every correction instead of fixing it themselves).
          </p>
        </div>
      </Card>

      <Card title="What's running under the hood" subtitle="The machinery you can answer client questions about without grepping the source.">
        <div className="text-sm text-fg-muted leading-relaxed space-y-3">
          <div>
            <strong className="text-fg">The bridge daemon</strong> — runs as <code className="text-accent">pythonw.exe -m bravo_cli.bridge_chat_server</code> on Windows / <code className="text-accent">python -m ...</code> via launchd on Mac. PID at <code className="text-accent">~/.oasis/bridge_chat.pid</code>. Listens on <code className="text-accent">127.0.0.1:9100</code>. Restart with <code className="text-accent">bravo bridge restart</code> (one command, kills both daemons + restarts both, waits for port to free).
          </div>
          <div>
            <strong className="text-fg">The warm process pool</strong> — keeps a hot Claude Code subprocess per chat tab. Max 8 processes, idle reaper at 15min. Skips the 5-30s cold-start on turn 2+. Live state visible at <code className="text-accent">/operations</code> &gt; Warm Process Pool, or <code className="text-accent">curl localhost:9100/warm-status</code>.
          </div>
          <div>
            <strong className="text-fg">The heartbeat</strong> — fires every 60s from the chat-server. Probes ffmpeg / whisper / playwright on the client&apos;s machine, posts the results to <code className="text-accent">/api/bridge/ping</code>. The dashboard&apos;s /integrations page reflects what&apos;s actually installed locally. All probes pass <code className="text-accent">creationflags=CREATE_NO_WINDOW + STARTUPINFO/SW_HIDE</code> — zero terminal popups even though <code className="text-accent">playwright.cmd</code> requires cmd.exe (commit 59d773c).
          </div>
          <div>
            <strong className="text-fg">The pair token</strong> — minted on first <code className="text-accent">bravo bridge serve</code>. Stored at <code className="text-accent">~/.oasis/bridge_token</code> (chmod 600 on Unix). SHA-256 hashed in the <code className="text-accent">bridge_pairings</code> table. Idempotent by <code className="text-accent">(tenant_id, machine_fingerprint)</code> via partial unique index — re-pairing rotates the token instead of creating duplicates.
          </div>
          <div>
            <strong className="text-fg">MCP servers</strong> — credential-bearing ones (Supabase, GitHub, n8n, Late, Firecrawl, Obsidian) use <code className="text-accent">scripts/mcp_shims/&lt;name&gt;.js</code> Node shims. Each loads <code className="text-accent">.env.agents</code> via dotenv, spawns with <code className="text-accent">windowsHide:true</code>. No plaintext secrets in any MCP config.
          </div>
        </div>
      </Card>

      {PHASES.map((phase) => {
        const Icon = DEPLOY_ICONS[phase.icon];
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
