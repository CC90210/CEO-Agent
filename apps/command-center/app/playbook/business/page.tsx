import { Card, PageHeader, Tag } from "@/components/Card";
import Link from "next/link";
import {
  BUSINESS_DOCS,
  DOC_PILLARS,
  type DocPillar,
} from "@/lib/business-docs";
import { Briefcase, DollarSign, Megaphone, Wrench, Scale, ArrowRight, Check, FileText } from "lucide-react";
import { getAgentInfo } from "@/lib/agents";

export const dynamic = "force-static";

const PILLAR_ICON: Record<DocPillar, React.ComponentType<{ className?: string }>> = {
  ceo: Briefcase,
  cfo: DollarSign,
  cmo: Megaphone,
  ops: Wrench,
  legal: Scale,
};

const PILLAR_ORDER: DocPillar[] = ["ceo", "cfo", "cmo", "ops", "legal"];

export default function BusinessDocsPage() {
  const drafted = BUSINESS_DOCS.filter((d) => d.status === "drafted").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Business Documentation"
        subtitle="Every document a real C-suite needs. Click to ask the owning agent to draft / refresh it."
        action={
          <Tag tone="accent">
            {drafted} drafted · {BUSINESS_DOCS.length - drafted} stubs
          </Tag>
        }
      />

      <Card title="How this hub works" subtitle="Each pillar maps to one of your AI execs. Click a doc to send it to that agent — they'll draft, review, or refresh.">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
          {PILLAR_ORDER.map((p) => {
            const def = DOC_PILLARS[p];
            const info = getAgentInfo(def.agent);
            const Icon = PILLAR_ICON[p];
            return (
              <div key={p} className="rounded-md border border-bg-border bg-bg-elev/40 px-2.5 py-2">
                <div className={`inline-flex items-center gap-1.5 ${info.textClass}`}>
                  <Icon className="w-3.5 h-3.5" />
                  <span className="text-[10px] uppercase tracking-wider font-bold">
                    {def.label.split(" — ")[0]}
                  </span>
                </div>
                <div className="text-[10px] text-fg-muted mt-1 leading-snug">{def.tagline}</div>
                <div className="text-[10px] text-fg-dim font-mono mt-1">→ {def.agent}</div>
              </div>
            );
          })}
        </div>
      </Card>

      {PILLAR_ORDER.map((p) => {
        const def = DOC_PILLARS[p];
        const list = BUSINESS_DOCS.filter((d) => d.pillar === p);
        if (list.length === 0) return null;
        const Icon = PILLAR_ICON[p];
        const info = getAgentInfo(def.agent);
        return (
          <Card
            key={p}
            title={def.label}
            subtitle={def.tagline}
            action={
              <span className={`text-[10px] uppercase tracking-wider font-bold ${info.textClass} inline-flex items-center gap-1`}>
                <Icon className="w-3 h-3" /> owned by {def.agent}
              </span>
            }
          >
            <div className="grid sm:grid-cols-2 gap-2.5">
              {list.map((d) => {
                const href = `/agents?agent=${encodeURIComponent(d.owner)}&prompt=${encodeURIComponent(d.draft_prompt)}`;
                return (
                  <Link
                    key={d.id}
                    href={href}
                    className="group rounded-lg border border-bg-border bg-bg-elev/40 hover:border-accent/50 hover:bg-accent/5 transition-all p-3.5 flex items-start gap-3"
                  >
                    <div className={`w-8 h-8 rounded-md flex items-center justify-center bg-bg-elev border border-bg-border flex-shrink-0 ${info.textClass}`}>
                      <FileText className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-sm font-bold text-fg">{d.title}</span>
                        {d.status === "drafted" && (
                          <span className="text-[9px] uppercase tracking-wider font-bold text-status-engaged bg-status-engaged/10 border border-status-engaged/30 px-1.5 py-0.5 rounded inline-flex items-center gap-0.5">
                            <Check className="w-2.5 h-2.5" /> drafted
                          </span>
                        )}
                        {d.status === "stub" && (
                          <span className="text-[9px] uppercase tracking-wider font-bold text-status-warm bg-status-warm/10 border border-status-warm/30 px-1.5 py-0.5 rounded">
                            stub
                          </span>
                        )}
                        {d.status === "missing" && (
                          <span className="text-[9px] uppercase tracking-wider font-bold text-fg-dim bg-bg-elev border border-bg-border px-1.5 py-0.5 rounded">
                            missing
                          </span>
                        )}
                        <ArrowRight className="w-3.5 h-3.5 text-fg-dim opacity-0 group-hover:opacity-100 transition-opacity ml-auto" />
                      </div>
                      <div className="text-xs text-fg-muted mt-1 leading-snug">{d.description}</div>
                      {d.storage_hint && (
                        <div className="text-[10px] text-fg-dim font-mono mt-1.5">
                          stored at {d.storage_hint}
                        </div>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
