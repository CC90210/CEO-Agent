import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-static";

const DRILLS = [
  {
    num: "01",
    name: "Mirror Run",
    timing: "5 min · morning",
    body:
      "Stand in front of a mirror. Run the full script aloud — don't read, recite from memory. Watch your face: eye contact, jaw tension, hands. The voice on cold calls is heard, but the body is what makes you confident. If you can hold yourself loose in the mirror, you'll hold yourself loose on the phone.",
    output: "By Day 14 you can run the full script without looking at it.",
  },
  {
    num: "02",
    name: "Objection Volley",
    timing: "10 min · midday",
    body:
      "Pull up the objection table. For each trigger, say it out loud, pause one second, then deliver your response. Speed up each round. By the third pass, you should be responding faster than you can think.",
    output: "By Day 14 you respond inside 1.5 seconds. No thinking. Pure muscle memory.",
  },
  {
    num: "03",
    name: "Recording Review",
    timing: "10 min · evening",
    body:
      "Record one of your real calls (Otter, your phone, doesn't matter — Ontario law allows one-party consent). Listen back at 1.5×. Listen for: (a) where you talked too much, (b) where you missed a question they asked, (c) where you flinched on price or objection. Note ONE specific fix. Apply it tomorrow.",
    output: "Concrete weekly improvement based on real call data, not vibes.",
  },
  {
    num: "04",
    name: "KPI Log",
    timing: "5 min · end of day",
    body:
      "Open the Pipeline page. Log today's numbers: dials made, conversations had, bookings secured. The ratios matter more than the raw counts. Healthy ratios: 1 conversation per 3-4 dials, 1 booking per 4-5 conversations. Track them weekly.",
    output: "Data-driven understanding of where your funnel actually breaks.",
  },
  {
    num: "05",
    name: "Weekly Retro",
    timing: "30 min · Friday afternoon",
    body:
      "Once a week, sit down and review the week's call recordings, KPIs, and notes. Answer three questions: (1) What worked that I should repeat? (2) What broke that I need to fix? (3) What objection caught me most often this week — and what's the better response? Update your script if needed.",
    output: "Continuous improvement. The script evolves with the data.",
  },
];

const WARMUP = [
  "Phone charged, headset on, water and coffee within reach.",
  "Notifications off — Slack, email, Telegram on critical-only.",
  "OASIS Command Center on second monitor, Pipeline page open.",
  "Today's call list pulled, sorted by score.",
  "Two specific calendar slots ready (e.g. 'Tuesday at 2 or Thursday at 10').",
  "Mirror Run completed — script in muscle memory.",
  "Voicemail script written down (you'll need it on 60% of dials).",
  "Stand up. Roll your shoulders. Breathe in 4 / hold 4 / out 4. Three rounds.",
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
        subtitle="Sales is a physical skill. Pianists do scales every day. You'll script-drill every day until the words move through you without effort."
        action={<Tag tone="accent">5 reps · 30 min/day</Tag>}
      />

      <Card title="Pre-call warm-up checklist" subtitle="Run this before every call block">
        <ul className="space-y-2">
          {WARMUP.map((w, i) => (
            <li key={i} className="flex items-start gap-3 text-sm text-fg">
              <span className="text-accent font-bold shrink-0">▢</span>
              <span>{w}</span>
            </li>
          ))}
        </ul>
      </Card>

      <div className="space-y-4">
        {DRILLS.map((d) => (
          <Card key={d.num}>
            <div className="flex items-baseline justify-between mb-2">
              <div>
                <span className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
                  Drill {d.num}
                </span>
                <span className="text-fg font-bold text-base ml-3">{d.name}</span>
              </div>
              <span className="text-fg-muted text-xs">{d.timing}</span>
            </div>
            <p className="text-fg leading-relaxed">{d.body}</p>
            <div className="mt-3 pt-3 border-t border-bg-border text-xs">
              <span className="text-fg-muted font-bold uppercase tracking-wider">Output → </span>
              <span className="text-fg-muted italic">{d.output}</span>
            </div>
          </Card>
        ))}
      </div>

      <Card title="The 90-Day Rule">
        <p className="text-fg leading-relaxed">
          If you do these five drills every day for 90 days, you'll be a professional cold-caller. Not a guy doing cold calls — a professional. Most people quit at week 3 because the early data is bad. The data turns at week 5 and is incredible by week 9. The only thing standing between you and that is daily, boring discipline.
        </p>
      </Card>
    </div>
  );
}
