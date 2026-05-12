import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import {
  PROMPT_CATEGORIES,
  PROMPTS_LIBRARY,
  type PromptCategory,
  type PromptAudience,
} from "@/lib/prompts-library";
import { ArrowRight, ShieldAlert, User as UserIcon, Users } from "lucide-react";

export const dynamic = "force-dynamic";

const OPERATOR_CATEGORIES: PromptCategory[] = [
  "ops_daily",
  "ops_review",
  "system_override",
  "system_health",
];

const CLIENT_CATEGORIES: PromptCategory[] = [
  "client_setup",
  "client_optimization",
  "client_handoff",
];

function PromptCard({ p }: { p: typeof PROMPTS_LIBRARY[number] }) {
  const href = `/agents?agent=${encodeURIComponent(p.agent)}&prompt=${encodeURIComponent(p.prompt)}`;
  const isOverride = p.category === "system_override";
  return (
    <Link
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
        {isOverride && (
          <div className="text-[10px] text-status-warm font-mono mt-2 inline-flex items-center gap-1">
            <ShieldAlert className="w-3 h-3" /> [OVERRIDE] prompt
          </div>
        )}
      </div>
    </Link>
  );
}

export default function PromptsLibraryPage() {
  // Operator section: prompts tagged "operator" + the "shared" ones that
  // are universally useful (override syntax, health checks, end-of-day).
  const operatorPrompts = PROMPTS_LIBRARY.filter(
    (p) => p.audience === "operator" || p.audience === "shared"
  );
  // Client deployment section: prompts tagged "client" + the shared ones
  // (operator runs them when SSH'd into a client's machine).
  const clientPrompts = PROMPTS_LIBRARY.filter(
    (p) => p.audience === "client" || p.audience === "shared"
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Prompts Library"
        subtitle="Saved prompts that move the system. Two audiences: yours (your daily operator moves) and the client toolkit (what to fire when you're setting up someone else's machine)."
        action={
          <Tag tone="accent">
            {operatorPrompts.length} operator · {clientPrompts.length} client
          </Tag>
        }
      />

      <Card title="Operator override syntax" subtitle="When you need the agent to break out of its normal behavior, start with [OVERRIDE].">
        <div className="text-sm text-fg-muted leading-relaxed space-y-2">
          <p>
            Most messages route through the agent&apos;s standard reasoning. When you need to <strong className="text-fg">force a specific mode</strong> — pause crons, draft-only, private, voice-shift, correct a mistake — start the message with <code className="bg-bg-elev px-1.5 py-0.5 rounded text-accent">[OVERRIDE]</code> on its own line, then a context line, then the request.
          </p>
          <pre className="bg-bg-deep border border-bg-border rounded p-3 text-xs font-mono text-fg overflow-x-auto whitespace-pre">{`[OVERRIDE]
Context: pause autonomous agent activity for the next 24h.

Disable every cron in vercel.json by setting it to a date in the past...`}</pre>
          <p className="text-xs">
            The agent treats <code className="text-accent">[OVERRIDE]</code> messages as imperative + non-conversational. Foundational override prompts (badged below) are hard-coded and always available across both operator + client deployments.
          </p>
        </div>
      </Card>

      {/* ── YOUR PROMPTS (operator) ────────────────────────────── */}
      <div>
        <div className="flex items-baseline gap-2 mb-3">
          <UserIcon className="w-4 h-4 text-accent" />
          <h2 className="text-lg font-bold text-fg">Your prompts</h2>
          <span className="text-xs text-fg-muted">
            personal to your OASIS AI deployment + universal moves
          </span>
        </div>
        <div className="space-y-4">
          {OPERATOR_CATEGORIES.map((cat) => {
            const def = PROMPT_CATEGORIES[cat];
            const list = operatorPrompts.filter((p) => p.category === cat);
            if (list.length === 0) return null;
            return (
              <Card key={cat} title={def.label} subtitle={def.description}>
                <div className="grid sm:grid-cols-2 gap-2.5">
                  {list.map((p) => (
                    <PromptCard key={p.id} p={p} />
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* ── CLIENT DEPLOYMENT TOOLKIT ──────────────────────────── */}
      <div>
        <div className="flex items-baseline gap-2 mb-3">
          <Users className="w-4 h-4 text-pink-400" />
          <h2 className="text-lg font-bold text-fg">Client deployment toolkit</h2>
          <span className="text-xs text-fg-muted">
            run these when you&apos;re setting up a new client&apos;s machine
          </span>
        </div>
        <div className="space-y-4">
          {CLIENT_CATEGORIES.map((cat) => {
            const def = PROMPT_CATEGORIES[cat];
            const list = clientPrompts.filter((p) => p.category === cat);
            if (list.length === 0) return null;
            return (
              <Card key={cat} title={def.label} subtitle={def.description}>
                <div className="grid sm:grid-cols-2 gap-2.5">
                  {list.map((p) => (
                    <PromptCard key={p.id} p={p} />
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
