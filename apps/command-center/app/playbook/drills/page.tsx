import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import {
  ArrowLeft, ScanFace, Repeat, Mic, BarChart3, Calendar, Clock,
  Sparkles, Target, MessageSquare, TrendingUp, Sword, Brain, Zap,
} from "lucide-react";

export const dynamic = "force-dynamic";

const DRILL_ICONS = {
  scanFace: ScanFace,
  repeat: Repeat,
  mic: Mic,
  barChart3: BarChart3,
  calendar: Calendar,
  clock: Clock,
  sparkles: Sparkles,
  target: Target,
  messageSquare: MessageSquare,
  trendingUp: TrendingUp,
  sword: Sword,
  brain: Brain,
  zap: Zap,
} as const;

/**
 * Daily Drills v2 — refined per CC's spec: "super advanced, optimized,
 * productive, and very personal to me in my business and what value we
 * offer."
 *
 * Re-frame: this isn't generic cold-call drilling. It's OASIS AI sales
 * + content + voice + pipeline diagnosis, anchored against the live
 * $5K MRR target. Every drill ties to a chat prompt OR a dashboard page,
 * not just paper. Phased progression: foundation (days 1-30) → fluency
 * (31-60) → mastery (61-90).
 */

type Drill = {
  num: string;
  name: string;
  timing: string;
  category: "voice" | "sales" | "content" | "pipeline" | "intel";
  intensity: "core" | "advanced";
  body: string;
  output: string;
  /** Click-to-chat prompt for the agent that owns this rep. */
  chat?: { agent: "bravo" | "atlas" | "maven"; prompt: string };
  /** Dashboard page that backs this drill. */
  link?: { href: string; label: string };
  icon: keyof typeof DRILL_ICONS;
};

const DRILLS: Drill[] = [
  // ── CORE 5 (run every day) ─────────────────────────────────────
  {
    num: "01",
    name: "Voice rep — read-aloud against the brand bible",
    timing: "5 min · 6:30 AM",
    category: "voice",
    intensity: "core",
    body:
      "Read the last 3 things you wrote (DM, email, content draft) aloud. Score each: tone match (brand bible), sentence rhythm, signature phrases. If anything sounds AI-slop or off-brand, rewrite the offending line right now. Voice drift is the #1 reason content stops landing — daily ear-training keeps it tight.",
    output: "Day 30 → you hear off-brand sentences before you write them.",
    chat: {
      agent: "bravo",
      prompt:
        "Score the last 3 things I wrote (pull from chat_messages, latest_drafts, anywhere you have access). For each: tone match against ../CMO-Agent/brain/CONTENT_BIBLE.md, sentence rhythm, signature phrase usage. Flag any AI-slop opener or off-brand sentence and rewrite it.",
    },
    icon: "scanFace",
  },
  {
    num: "02",
    name: "NEPQ rep — situation/problem/solution/consequence",
    timing: "10 min · 11:45 AM (pre-sales block)",
    category: "sales",
    intensity: "core",
    body:
      "Pull a real qualified lead. Out loud, walk through the four NEPQ blocks for THAT specific lead: situation Qs (what's their world look like), problem Qs (what's broken), solution Qs (what would 'fixed' mean to them), consequence Qs (what happens if they don't fix it). Speak like you're on the call. Names, dollar amounts, real specifics. Generic NEPQ doesn't close — personalized NEPQ does.",
    output: "Day 30 → custom NEPQ flow per lead in 90 seconds.",
    chat: {
      agent: "bravo",
      prompt:
        "Pick my hottest qualified lead from the pipeline. Build me a custom NEPQ flow for THAT lead specifically — situation, problem, solution, consequence questions. Each question must reference something specific about their business (industry, size, recent activity). I'll read it aloud as my rep.",
    },
    link: { href: "/pipeline", label: "Live pipeline" },
    icon: "brain",
  },
  {
    num: "03",
    name: "Pipeline triage — name the leak",
    timing: "5 min · 1:00 PM (post-lunch)",
    category: "pipeline",
    intensity: "core",
    body:
      "Open the Pipeline page. Don't just look at counts — find the ONE stage where leads are stalling. Qualified → proposal? Proposal → close? Discovery → qualified? Pick a specific lead in the stalled stage. What's the next concrete touch (today) that moves them? Schedule it before you close the tab.",
    output: "Day 30 → you instinctively spot the leak in the funnel daily, not weekly.",
    chat: {
      agent: "bravo",
      prompt:
        "Pull my full pipeline by stage. Identify the ONE stage where leads are stalling longest right now. For each stalled lead, give me one specific next-touch I can fire today — message draft included. Don't generalize.",
    },
    link: { href: "/pipeline", label: "Pipeline" },
    icon: "target",
  },
  {
    num: "04",
    name: "Content shot — one hook, one draft, one post",
    timing: "20 min · 11:15 AM (content block)",
    category: "content",
    intensity: "core",
    body:
      "One real piece of content, every weekday. Hook draft → body → publish OR queue. The pillar rotates (Sobriety Log / Quote Drop / CEO Log / NEPQ insight / Build-in-public). Content is your #1 inbound funnel — skipping a day skips a piece of MRR. If you blanked, run the chat prompt and a draft lands in 90 seconds.",
    output: "Day 30 → 22 published pieces. Day 90 → inbound funnel becomes the primary lead source.",
    chat: {
      agent: "maven",
      prompt:
        "Draft today's content. Pick the pillar that hasn't fired in the longest stretch. Give me a hook + body in CC's voice (introspective, raw, '2am to a friend' tone). Reference anything noteworthy from this week's wins. Sign off with 'Only good things from now on.' if it lands.",
    },
    link: { href: "/agents?agent=maven", label: "Send to Maven" },
    icon: "sparkles",
  },
  {
    num: "05",
    name: "Daily MRR check + capital decision",
    timing: "5 min · 4:30 PM",
    category: "pipeline",
    intensity: "core",
    body:
      "Open the Today page. Hit the MRR delta. If we moved positive, where did the dollar come from — and how do we replicate? If we moved negative or flat, what's the ONE move that flips it tomorrow? End every day knowing where the revenue lever is.",
    output: "Day 30 → pattern-matching wins. Day 90 → trajectory locked at $5K MRR.",
    chat: {
      agent: "atlas",
      prompt:
        "Today's MRR delta + how we got it. Source breakdown: Stripe one-offs, recurring retainers, rev shares, community growth. If positive, name what to scale tomorrow. If flat or negative, name the one revenue lever I should pull. Be specific to my $5K target by May 15.",
    },
    link: { href: "/", label: "Today" },
    icon: "trendingUp",
  },

  // ── ADVANCED (alternate days, week 3+) ─────────────────────────
  {
    num: "06",
    name: "Objection volley — speed mode",
    timing: "10 min · alternate days · 12:15 PM",
    category: "sales",
    intensity: "advanced",
    body:
      "Open Cold Call Script + Objections. Bravo reads each trigger; you respond aloud, no pause. Track the 2-3 you stumble on. Drill ONLY those for 5 minutes. Speed builds neural pathways — the third pass should be faster than your conscious thought.",
    output: "Day 30 → respond inside 1.2 sec on every objection. No internal panic.",
    chat: {
      agent: "bravo",
      prompt:
        "Run me through the 10 objections from /playbook/script in random order. For each, paste the trigger and wait. After I respond, score me 1-5 on tightness + tone, then give me a tighter version. Only call out the 2-3 weakest at the end.",
    },
    link: { href: "/playbook/script", label: "Script + objections" },
    icon: "sword",
  },
  {
    num: "07",
    name: "Recording review — surgical fix",
    timing: "15 min · alternate days · 4:45 PM",
    category: "sales",
    intensity: "advanced",
    body:
      "Pick ONE call from the last 48h (Otter, phone, Teams). Listen at 1.5×. Look for exactly three things: (a) where did I talk past their answer, (b) where did I flinch on price/timeline, (c) where did I miss a buying signal. Pick ONE fix. Write it on a sticky note next to your monitor.",
    output: "One concrete fix per session. Day 90 → 30+ surgical adjustments compounded.",
    chat: {
      agent: "bravo",
      prompt:
        "I just listened to a call. Here's my note on what I heard: [paste]. Diagnose the root NEPQ failure (was it situation depth, problem clarity, consequence weight, or solution framing?). Give me the one micro-fix to test on tomorrow's calls.",
    },
    icon: "mic",
  },
  {
    num: "08",
    name: "Competitor intelligence — 1 prospect, 1 alternative",
    timing: "10 min · 2x/week · Tue+Thu 3:30 PM",
    category: "intel",
    intensity: "advanced",
    body:
      "Pick one warm prospect. Find what alternative they're considering (Zapier? Freelancer? Hire in-house? Stay manual?). For each alternative, draft the one sentence that reframes the comparison around outcomes (not features). This becomes your 'why us, why now' for that lead.",
    output: "Day 60 → you handle competitive objections proactively, before they're raised.",
    chat: {
      agent: "bravo",
      prompt:
        "Pick my warmest qualified lead. Research what they're likely comparing OASIS to (other AI vendors, freelancers, in-house, status quo). For each, draft the outcome-based reframe in one sentence. Make me dangerous in the next call with them.",
    },
    icon: "zap",
  },
  {
    num: "09",
    name: "Outreach surgery — the 3 you didn't book",
    timing: "10 min · Wed + Fri · 9:30 AM",
    category: "sales",
    intensity: "advanced",
    body:
      "Pull the 3 most recent leads who DIDN'T book. For each, the script asks: was it the opener, the discovery question, or the close? Pick one and rewrite the moment. Don't just write a 'better' version — explain WHY the original didn't land. Patterns surface fast.",
    output: "Day 60 → conversion rate climbs because you stop repeating the same miss.",
    chat: {
      agent: "bravo",
      prompt:
        "Show me the last 3 qualified leads who didn't book. For each: the touchpoint that lost them (cold open / discovery / close), why that specific moment failed, and the rewrite. Look for patterns across all three.",
    },
    icon: "messageSquare",
  },
  {
    num: "10",
    name: "Weekly retro — what compounds",
    timing: "30 min · Sunday 4 PM",
    category: "voice",
    intensity: "advanced",
    body:
      "Sunday wrap. Three questions: (1) What worked this week — repeatable? (2) What didn't — what's the root cause? (3) Which objection / drill / pillar gave me the biggest growth this week? Update the script, update the pillar mix, update brain/PATTERNS.md if anything compounded.",
    output: "Continuous improvement. The system gets smarter every Sunday, not someday.",
    chat: {
      agent: "bravo",
      prompt:
        "Run my weekly retro. Pull this week's KPIs (dials, conversations, bookings, content posted, MRR delta). Diagnose what compounded vs what burned. Give me one process change for next week. Save it to memory/PATTERNS.md if it's worth keeping.",
    },
    icon: "calendar",
  },
];

const PHASES = [
  {
    days: "Days 1-30",
    label: "Foundation",
    body:
      "Just hit the 5 core drills. Don't add anything. Discipline > variety. The data will look bad — that's expected. Your reps haven't compounded yet.",
    target: "1 conversation per 4 dials. 1 piece of content / weekday. MRR flat or +5%.",
  },
  {
    days: "Days 31-60",
    label: "Fluency",
    body:
      "Add the advanced drills (06-10) on their cadence. NEPQ + objection responses become reflexive. Content voice locks in. You stop reading the script and start riffing.",
    target: "1 conversation per 3 dials. 1 booking per 5 conversations. MRR +20%.",
  },
  {
    days: "Days 61-90",
    label: "Mastery",
    body:
      "Reps move from 'drill' to 'how I work.' Voice is yours, not borrowed. Pipeline triage is reflex, not chore. The system runs you, you don't run it.",
    target: "1 booking per 4 conversations. Content drives 50%+ of inbound. MRR at $5K.",
  },
];

const WARMUP = [
  "Phone charged. Headset on. Water + coffee within reach.",
  "Notifications off — Slack/email/Telegram on critical-only.",
  "OASIS Command Center open · Pipeline tab on second monitor.",
  "Today's call list pulled, sorted by lead score.",
  "Two specific calendar slots ready (e.g. 'Tue 2pm or Thu 10am').",
  "Voice rep done — voice in muscle memory.",
  "Voicemail script written down (you'll need it on 60% of dials).",
  "Stand. Roll shoulders. Breathe in 4 / hold 4 / out 4. Three rounds.",
  "First call: a throwaway practice dial to a prospect you don't actually want.",
];

const CATEGORY_TONE: Record<Drill["category"], string> = {
  voice: "text-pink-400 border-pink-400/30 bg-pink-400/10",
  sales: "text-accent border-accent/30 bg-accent/10",
  content: "text-purple-400 border-purple-400/30 bg-purple-400/10",
  pipeline: "text-emerald-400 border-emerald-400/30 bg-emerald-400/10",
  intel: "text-amber-400 border-amber-400/30 bg-amber-400/10",
};

export default function DrillsPage() {
  const core = DRILLS.filter((d) => d.intensity === "core");
  const advanced = DRILLS.filter((d) => d.intensity === "advanced");

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <PageHeader
        title="Daily Drills"
        subtitle="Sales is a physical skill. The pianist runs scales daily; the boxer shadowboxes daily. You'll drill voice, NEPQ, pipeline, content, and capital — every day, against your real OASIS pipeline. Not theory. Reps wired into your dashboard."
        action={<Tag tone="accent">5 core · 5 advanced · 90-day path to $5K MRR</Tag>}
      />

      {/* 90-day phases */}
      <Card title="The 90-day path" subtitle="Three phases. The data will look bad until day 30. Trust the protocol.">
        <div className="grid md:grid-cols-3 gap-3">
          {PHASES.map((p) => (
            <div key={p.days} className="rounded-lg border border-bg-border bg-bg-elev p-4">
              <div className="text-[10px] uppercase tracking-wider font-bold text-accent">{p.days}</div>
              <div className="text-fg font-bold text-sm mt-0.5">{p.label}</div>
              <p className="text-xs text-fg-muted mt-2 leading-relaxed">{p.body}</p>
              <div className="text-[10px] text-fg-dim font-mono mt-3 pt-2 border-t border-bg-border leading-relaxed">
                <span className="text-accent">target → </span>
                {p.target}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Pre-call warm-up */}
      <Card title="Pre-call warm-up checklist" subtitle="Run before every call block">
        <ul className="space-y-2">
          {WARMUP.map((w, i) => (
            <li key={i} className="flex items-start gap-3 text-sm text-fg">
              <span className="text-accent font-bold shrink-0 mt-0.5">▢</span>
              <span>{w}</span>
            </li>
          ))}
        </ul>
      </Card>

      {/* Core 5 — every day */}
      <Card
        title="Core 5 · run every weekday"
        subtitle="Skip these and the system breaks. Each one wires into a real dashboard surface or chat prompt — no abstract paper drills."
      >
        <div className="grid lg:grid-cols-2 gap-4">
          {core.map((d) => (
            <DrillCard key={d.num} drill={d} />
          ))}
        </div>
      </Card>

      {/* Advanced 5 — alternating cadence */}
      <Card
        title="Advanced 5 · cadence-based"
        subtitle="Layer on after week 3 — they assume the core 5 are reflex. Each runs on its own day-of-week so you don't burn out."
      >
        <div className="grid lg:grid-cols-2 gap-4">
          {advanced.map((d) => (
            <DrillCard key={d.num} drill={d} />
          ))}
        </div>
      </Card>

      <Card title="Why this works when nothing else has" subtitle="The 90-day rule, restated">
        <p className="text-fg leading-relaxed">
          Ten drills. Five every day, five on cadence. Most people quit at week 3 because the early data is bad. The data turns at week 5 and is incredible by week 9. The only thing standing between you and $5K MRR is daily, boring, dashboard-anchored discipline. <span className="text-accent font-medium">Every drill links to a chat prompt or a live dashboard page</span> — they're not paper exercises. The system runs them with you.
        </p>
      </Card>
    </div>
  );
}

function DrillCard({ drill: d }: { drill: Drill }) {
  const Icon = DRILL_ICONS[d.icon];
  const chatHref = d.chat
    ? `/agents?agent=${encodeURIComponent(d.chat.agent)}&prompt=${encodeURIComponent(d.chat.prompt)}`
    : null;
  return (
    <Card>
      <div className="flex items-baseline justify-between mb-3 gap-2 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-accent-soft border border-accent/30 flex items-center justify-center text-accent shrink-0">
            <Icon size={16} />
          </div>
          <div>
            <span className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
              Drill {d.num}
            </span>
            <div className="text-fg font-bold text-base leading-tight">{d.name}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          <span
            className={`text-[10px] uppercase tracking-wider font-bold border rounded-full px-2 py-0.5 ${CATEGORY_TONE[d.category]}`}
          >
            {d.category}
          </span>
          <span className="text-fg-muted text-xs flex items-center gap-1">
            <Clock size={11} /> {d.timing}
          </span>
        </div>
      </div>
      <p className="text-fg leading-relaxed text-sm">{d.body}</p>
      <div className="mt-3 pt-3 border-t border-bg-border text-xs">
        <span className="text-accent font-bold uppercase tracking-wider">Output → </span>
        <span className="text-fg-muted italic">{d.output}</span>
      </div>
      {(chatHref || d.link) && (
        <div className="mt-3 flex items-center gap-3 flex-wrap text-xs">
          {chatHref && (
            <Link
              href={chatHref}
              className="text-accent hover:text-accent-bright inline-flex items-center gap-1"
            >
              <Sparkles size={12} /> run as chat
            </Link>
          )}
          {d.link && (
            <Link href={d.link.href} className="text-fg-muted hover:text-accent inline-flex items-center gap-1">
              <BarChart3 size={12} /> {d.link.label}
            </Link>
          )}
          {d.intensity === "advanced" && (
            <Repeat size={12} className="text-fg-dim ml-auto" />
          )}
        </div>
      )}
    </Card>
  );
}
