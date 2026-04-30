import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { Phone, Shield, Layers, Repeat } from "lucide-react";

export const dynamic = "force-dynamic";

const SECTIONS = [
  {
    href: "/playbook/cold-call",
    title: "Cold Call Script V1",
    subtitle: "5 stages · NEPQ · under 3 minutes",
    icon: Phone,
    body:
      "Memorize-grade script paired with the new free 14-day pilot deal architecture. Pattern interrupt → reason → diagnose → pivot to offer → two-option close.",
  },
  {
    href: "/playbook/objections",
    title: "Objection Handlers",
    subtitle: "8 most common · NEPQ-aligned",
    icon: Shield,
    body:
      "Universal rule: question, don't answer. The objection is rarely the real reason. Get them to articulate the real reason — the deal opens up.",
  },
  {
    href: "/playbook/deals",
    title: "Deal Architecture",
    subtitle: "3 client offers · 2 partner tiers",
    icon: Layers,
    body:
      "One-Off Automation (14-day free pilot), Custom Software Build (50/50 deposit), C-Suite Consulting. Strategic partners 50% rev share, network referrers 10%.",
  },
  {
    href: "/playbook/drills",
    title: "Daily Drills",
    subtitle: "3 reps · every single day",
    icon: Repeat,
    body:
      "Mirror Run (5 min, morning). Objection Volley (10 min, midday). Recording Review (10 min, evening). Daily for 90 days. The discipline is the moat.",
  },
];

export default function PlaybookIndex() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Playbook"
        subtitle="The canonical sales operating manual. Memorize the script. Drill the objections. Close the deal."
        action={
          <Tag tone="accent">v1 · 2026-04-30</Tag>
        }
      />

      <div className="grid md:grid-cols-2 gap-5">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <Link
              key={s.href}
              href={s.href}
              className="group block"
            >
              <Card>
                <div className="flex items-start gap-4">
                  <div className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-muted/30 flex items-center justify-center shrink-0 group-hover:bg-accent group-hover:text-bg transition-all">
                    <Icon size={20} className="text-accent group-hover:text-bg" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-fg font-bold text-base group-hover:text-accent transition-colors">
                      {s.title}
                    </div>
                    <div className="text-xs text-fg-muted mt-0.5 uppercase tracking-wider font-medium">
                      {s.subtitle}
                    </div>
                    <p className="text-sm text-fg-muted mt-3 leading-relaxed">
                      {s.body}
                    </p>
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
