"use client";

import Link from "next/link";
import {
  Sparkles, Target, Mail, FileText, TrendingUp, Activity,
  Users, DollarSign, Phone, Calendar, ArrowRight,
} from "lucide-react";
import type { QuickAction } from "@/lib/quick-actions";
import { getAgentInfo } from "@/lib/agents";

const ICON_MAP = {
  Sparkles, Target, Mail, FileText, TrendingUp, Activity,
  Users, DollarSign, Phone, Calendar,
} as const;

/**
 * Renders curated quick actions per agent. Click → routes to /agents with
 * the prompt + agent baked into the URL. ChatWidget reads the params on
 * mount, pre-fills the composer, and selects the right agent. Operator
 * hits Enter (or autosend) and goes.
 */
export function QuickActionsGrid({ actions }: { actions: QuickAction[] }) {
  // Group by agent so the page reads as "what each agent can do for you"
  const byAgent = actions.reduce<Record<string, QuickAction[]>>((acc, q) => {
    if (!acc[q.agent]) acc[q.agent] = [];
    acc[q.agent].push(q);
    return acc;
  }, {});

  // Stable order: preferred sequence first, then any other agents in the
  // order they appeared. Lets new agent packs (Solara/Helios, Lyra, etc.)
  // render without each one being hand-added here.
  const PREFERRED_ORDER = ["bravo", "atlas", "maven", "aura", "hermes", "lumen", "life-preservation", "solara", "helios", "lyra", "lyra_brand", "lyra_fans", "lyra_commerce"];
  const seen = new Set<string>();
  const agentOrder: string[] = [];
  for (const slug of PREFERRED_ORDER) {
    if (byAgent[slug]?.length && !seen.has(slug)) {
      agentOrder.push(slug);
      seen.add(slug);
    }
  }
  for (const q of actions) {
    if (!seen.has(q.agent)) {
      agentOrder.push(q.agent);
      seen.add(q.agent);
    }
  }

  return (
    <div className="space-y-6">
      {agentOrder
        .filter((slug) => byAgent[slug]?.length)
        .map((slug) => {
          const info = getAgentInfo(slug as string);
          return (
            <div key={slug as string}>
              <div className="flex items-baseline gap-2 mb-2.5">
                <span className={`font-bold uppercase tracking-[0.14em] text-sm ${info.textClass}`}>
                  {info.label}
                </span>
                <span className="text-xs text-fg-muted">{info.tagline}</span>
              </div>
              <div className="grid sm:grid-cols-2 gap-2.5">
                {byAgent[slug].map((q) => {
                  const Icon = ICON_MAP[q.icon] || Sparkles;
                  const href = `/agents?agent=${encodeURIComponent(q.agent)}&prompt=${encodeURIComponent(q.prompt)}`;
                  return (
                    <Link
                      key={q.title}
                      href={href}
                      className="group rounded-lg border border-bg-border bg-bg-elev/40 hover:border-accent/50 hover:bg-accent/5 transition-all p-3.5 flex items-start gap-3"
                    >
                      <div className={`w-8 h-8 rounded-md flex items-center justify-center bg-bg-elev border border-bg-border ${info.textClass} flex-shrink-0`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-bold text-fg">{q.title}</span>
                          <ArrowRight className="w-3.5 h-3.5 text-fg-dim opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <div className="text-xs text-fg-muted mt-1 leading-snug">
                          {q.description}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
    </div>
  );
}
