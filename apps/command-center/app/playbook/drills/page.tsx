import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft, ScanFace, Repeat, Mic, BarChart3, Calendar, Clock } from "lucide-react";

export const dynamic = "force-static";

const DRILLS = [
  {
    num: "01",
    name: "Mirror Run",
    timing: "5 min · 6:30 AM (after wake)",
    body:
      "Stand in front of a mirror. Run the full cold-call script aloud — recite, don't read. Watch your face: eye contact, jaw tension, hands. The voice on cold calls is heard, but the body is what makes you confident. If you can hold yourself loose in the mirror, you'll hold yourself loose on the phone.",
    output: "Day 14 → script flows without thinking.",
    icon: ScanFace,
  },
  {
    num: "02",
    name: "Objection Volley",
    timing: "10 min · 12:15 PM (lunch break)",
    body:
      "Open Playbook → Cold Call Script & Objections. For each of the 10 objections, say the trigger out loud, pause one second, then deliver your response. Speed up each round. By the third pass, you should be responding faster than you can think.",
    output: "Day 14 → respond inside 1.5 sec. No thinking. Pure muscle memory.",
    icon: Repeat,
  },
  {
    num: "03",
    name: "Recording Review",
    timing: "10 min · 4:30 PM (admin block)",
    body:
      "Record one of your real calls (Otter, your phone, doesn't matter — Ontario law allows one-party consent). Listen back at 1.5×. Listen for: (a) where you talked too much, (b) where you missed a question they asked, (c) where you flinched on price or objection. Note ONE specific fix.",
    output: "One concrete weekly improvement based on real call data, not vibes.",
    icon: Mic,
  },
  {
    num: "04",
    name: "KPI Log",
    timing: "5 min · 5:00 PM (end of work day)",
    body:
      "Open the Pipeline page. Log today's numbers: dials made, conversations had, bookings secured. The ratios matter more than the raw counts. Healthy ratios: 1 conversation per 3-4 dials, 1 booking per 4-5 conversations. Track them weekly.",
    output: "Data-driven understanding of where your funnel actually breaks.",
    icon: BarChart3,
  },
  {
    num: "05",
    name: "Weekly Retro",
    timing: "30 min · Sunday afternoon",
    body:
      "Sit down and review the week's recordings, KPIs, and notes. Answer three questions: (1) What worked I should repeat? (2) What broke I need to fix? (3) Which objection caught me most this week — what's the better response? Update your script if needed. Run /retro from Bravo for a structured pass.",
    output: "Continuous improvement. The script evolves with the data.",
    icon: Calendar,
  },
];

const WARMUP = [
  "Phone charged. Headset on. Water + coffee within reach.",
  "Notifications off — Slack/email/Telegram on critical-only.",
  "OASIS Command Center on second monitor (Pipeline page).",
  "Today's call list pulled, sorted by score.",
  "Two specific calendar slots ready (e.g. 'Tue 2pm or Thu 10am').",
  "Mirror Run done — script in muscle memory.",
  "Voicemail script written down (you'll need it on 60% of dials).",
  "Stand. Roll shoulders. Breathe in 4 / hold 4 / out 4. Three rounds.",
  "First call: a throwaway practice dial to a prospect you don't actually want.",
];

export default function DrillsPage() {
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
        subtitle="Sales is a physical skill. Pianists run scales daily — boxers shadowbox daily. You'll script-drill daily until the words move through you without effort."
        action={<Tag tone="accent">5 reps · 30 min/day · 90-day discipline</Tag>}
      />

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

      <div className="grid lg:grid-cols-2 gap-4">
        {DRILLS.map((d) => {
          const Icon = d.icon;
          return (
            <Card key={d.num}>
              <div className="flex items-baseline justify-between mb-3">
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
                <span className="text-fg-muted text-xs flex items-center gap-1 shrink-0">
                  <Clock size={11} /> {d.timing}
                </span>
              </div>
              <p className="text-fg leading-relaxed text-sm">{d.body}</p>
              <div className="mt-3 pt-3 border-t border-bg-border text-xs">
                <span className="text-accent font-bold uppercase tracking-wider">Output → </span>
                <span className="text-fg-muted italic">{d.output}</span>
              </div>
            </Card>
          );
        })}
      </div>

      <Card title="The 90-Day Rule" subtitle="Why this works when nothing else has">
        <p className="text-fg leading-relaxed">
          Five drills, every day, 90 days. By the end you're a professional cold-caller — not a guy doing cold calls, a professional. Most people quit at week 3 because the early data is bad. The data turns at week 5 and is incredible by week 9. The only thing standing between you and that is daily, boring discipline. <span className="text-accent font-medium">Every drill is wired into your daily schedule on the Today page</span> — they're not a separate thing to remember.
        </p>
      </Card>
    </div>
  );
}
