import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import {
  PROMPT_CATEGORIES,
  PROMPTS_LIBRARY,
  type PromptCategory,
} from "@/lib/prompts-library";
import { ArrowRight, ShieldAlert } from "lucide-react";

export const dynamic = "force-static";

const CATEGORY_ORDER: PromptCategory[] = [
  "ops_daily",
  "ops_review",
  "client_setup",
  "client_optimization",
  "system_override",
  "system_health",
];

export default function PromptsLibraryPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Prompts Library"
        subtitle="Saved prompts that move the system. Click any one to send it straight to the right agent."
        action={<Tag tone="accent">{PROMPTS_LIBRARY.length} prompts · 5 agents</Tag>}
      />

      <Card title="Operator override syntax" subtitle="When you need the agent to break out of its normal behavior, start with [OVERRIDE].">
        <div className="text-sm text-fg-muted leading-relaxed space-y-2">
          <p>
            Most messages route through the agent's standard reasoning. When you need to <strong className="text-fg">force a specific mode</strong> — pause crons, draft-only, private, voice-shift, correct a mistake — start the message with <code className="bg-bg-elev px-1.5 py-0.5 rounded text-accent">[OVERRIDE]</code> on its own line, then a context line, then the request.
          </p>
          <pre className="bg-bg-deep border border-bg-border rounded p-3 text-xs font-mono text-fg overflow-x-auto whitespace-pre">{`[OVERRIDE]
Context: pause autonomous agent activity for the next 24h.

Disable every cron in vercel.json by setting it to a date in the past...`}</pre>
          <p className="text-xs">
            The agent treats <code className="text-accent">[OVERRIDE]</code> messages as imperative + non-conversational. No drift, no extra guidance, no save-this-as-preference unless you explicitly ask. Foundational override prompts (badged below) are hard-coded and always available.
          </p>
        </div>
      </Card>

      {CATEGORY_ORDER.map((cat) => {
        const def = PROMPT_CATEGORIES[cat];
        const list = PROMPTS_LIBRARY.filter((p) => p.category === cat);
        if (list.length === 0) return null;
        return (
          <Card key={cat} title={def.label} subtitle={def.description}>
            <div className="grid sm:grid-cols-2 gap-2.5">
              {list.map((p) => {
                const href = `/agents?agent=${encodeURIComponent(p.agent)}&prompt=${encodeURIComponent(p.prompt)}`;
                return (
                  <Link
                    key={p.id}
                    href={href}
                    className="group rounded-lg border border-bg-border bg-bg-elev/40 hover:border-accent/50 hover:bg-accent/5 transition-all p-3.5 flex items-start gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-sm font-bold text-fg">{p.title}</span>
                        {p.foundational && (
                          <span className="text-[9px] uppercase tracking-wider font-bold text-accent bg-accent/10 border border-accent/30 px-1.5 py-0.5 rounded">
                            foundational
                          </span>
                        )}
                        <span className="text-[10px] uppercase tracking-wider font-bold text-fg-dim">
                          → {p.agent}
                        </span>
                        <ArrowRight className="w-3.5 h-3.5 text-fg-dim opacity-0 group-hover:opacity-100 transition-opacity ml-auto" />
                      </div>
                      <div className="text-xs text-fg-muted mt-1.5 leading-snug">
                        {p.description}
                      </div>
                      {cat === "system_override" && (
                        <div className="text-[10px] text-status-warm font-mono mt-2 inline-flex items-center gap-1">
                          <ShieldAlert className="w-3 h-3" /> [OVERRIDE] prompt
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
