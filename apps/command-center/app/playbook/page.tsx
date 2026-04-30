import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { Phone, Layers, Repeat } from "lucide-react";

export const dynamic = "force-static";

const SECTIONS = [
  {
    href: "/playbook/script",
    title: "Cold Call Script + Objections",
    subtitle: "5 stages · 4 prospect tracks · 10 objection handlers",
    icon: Phone,
    body:
      "One memorize-grade page. Pattern interrupt → reason → diagnose → pivot → close. Pick your prospect track at the top — service trades, professional services, real estate, or e-commerce — and the language updates. Objection table sticky at the bottom for live calls.",
  },
  {
    href: "/playbook/deals",
    title: "Deal Architecture",
    subtitle: "How OASIS prices · what each tier earns",
    icon: Layers,
    body:
      "Three plain-English client offers (one-off automation, custom build, advisory). Two partner paths (revenue share, finder's fee). Risk-transferred via 14-day pilot. The math you can defend in any room.",
  },
  {
    href: "/playbook/drills",
    title: "Daily Drills",
    subtitle: "5 reps · 30 min/day · 90-day discipline",
    icon: Repeat,
    body:
      "Mirror Run · Objection Volley · Recording Review · KPI Log · Weekly Retro. The boring discipline that turns 'a guy doing cold calls' into a professional cold-caller. Plus a printable warm-up checklist.",
  },
];

export default function PlaybookIndex() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Playbook"
        subtitle="The canonical sales operating manual. Memorize the script. Drill the objections. Close the deal."
        action={<Tag tone="accent">v2 · 2026-04-30</Tag>}
      />

      <div className="grid md:grid-cols-3 gap-5">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <Link key={s.href} href={s.href} className="group block">
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
                    <p className="text-sm text-fg-muted mt-3 leading-relaxed">{s.body}</p>
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
