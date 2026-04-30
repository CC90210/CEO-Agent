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
      "Stand in front of a mirror. Run the full script aloud. Watch your face — eye contact, tension in the jaw, hands. The voice on cold calls is heard, but the body is what makes you confident. If you can hold yourself loose in the mirror, you'll hold yourself loose on the phone.",
  },
  {
    num: "02",
    name: "Objection Volley",
    timing: "10 min · midday",
    body:
      "Pull up the objection table. For each objection, say the trigger out loud, pause one second, then deliver the response. Speed up each round. Goal: by Day 14, you respond inside 1.5 seconds. No thinking. Pure muscle memory.",
  },
  {
    num: "03",
    name: "Recording Review",
    timing: "10 min · evening",
    body:
      "Record one of your real calls per day (Otter, your phone, doesn't matter). Listen back at 1.5×. Listen for: (a) where you talked too much, (b) where you missed a question they asked you, (c) where you flinched on price/objection. Note one specific fix. Apply tomorrow.",
  },
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
        action={<Tag tone="accent">3 reps · 25 min/day</Tag>}
      />

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
          </Card>
        ))}
      </div>

      <Card title="The 90-Day Rule">
        <p className="text-fg leading-relaxed">
          If you do these three drills every day for 90 days, you'll be a professional cold-caller. Not a guy doing cold calls — a professional. Most people quit at week 3 because the early data is bad. The data turns at week 5 and is incredible by week 9. The only thing standing between you and that is daily, boring discipline.
        </p>
      </Card>
    </div>
  );
}
