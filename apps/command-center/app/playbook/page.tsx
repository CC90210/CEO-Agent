import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { Phone, Layers, Repeat } from "lucide-react";

export const dynamic = "force-static";

const SECTIONS = [
  {
    href: "/playbook/script",
    title: "Cold Call Script + Objections",
    subtitle: "5 stages - 4 tracks - 10 objections - secondary disarm",
    icon: Phone,
    body:
      "One memorize-grade page. Pattern interrupt, reason, diagnose, pivot, close. Pick your prospect track at the top and run the right language live. Includes the Agree/Validate/Isolate disarm for when prospects double down on 'we're good'.",
  },
  {
    href: "/playbook/deals",
    title: "Deal Architecture",
    subtitle: "Three offers - two partner paths - one decision rule",
    icon: Layers,
    body:
      "Three client offers, two partner paths, and the canonical 50% strategic-partner model. The math is simple enough to defend in any room.",
  },
  {
    href: "/playbook/drills",
    title: "Daily Drills",
    subtitle: "5 reps - 30 min/day - 90-day discipline",
    icon: Repeat,
    body:
      "Mirror Run, Objection Volley, Recording Review, KPI Log, Weekly Retro. The boring discipline that turns cold calling into muscle memory.",
  },
];

export default function PlaybookIndex() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Playbook"
        subtitle="The canonical sales operating manual. Memorize the script. Drill the objections. Close the deal."
        action={<Tag tone="accent">v3 - canonical</Tag>}
      />

      <div className="grid md:grid-cols-3 gap-5">
        {SECTIONS.map((section) => {
          const Icon = section.icon;
          return (
            <Link key={section.href} href={section.href} className="group block">
              <Card>
                <div className="flex items-start gap-4">
                  <div className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-muted/30 flex items-center justify-center shrink-0 group-hover:bg-accent group-hover:text-bg transition-all">
                    <Icon size={20} className="text-accent group-hover:text-bg" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-fg font-bold text-base group-hover:text-accent transition-colors">
                      {section.title}
                    </div>
                    <div className="text-xs text-fg-muted mt-0.5 uppercase tracking-wider font-medium">
                      {section.subtitle}
                    </div>
                    <p className="text-sm text-fg-muted mt-3 leading-relaxed">{section.body}</p>
                  </div>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
