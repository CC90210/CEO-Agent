import { timeAgo } from "@/lib/fmt";
import type { IntegrationHealth } from "@/lib/supabase";
import { categorize } from "@/lib/integrations-registry";
import { ExternalLink, KeyRound, Sparkles } from "lucide-react";

const COMPLEXITY_LABEL: Record<string, { label: string; tone: string }> = {
  trivial: { label: "easy setup", tone: "text-status-engaged" },
  simple: { label: "minutes", tone: "text-accent" },
  moderate: { label: "moderate", tone: "text-status-warm" },
  advanced: { label: "advanced", tone: "text-status-hot" },
};

export function IntegrationDot({ health }: { health: IntegrationHealth }) {
  const def = categorize(health);
  const label = def?.label || health.service;
  const description = def?.description;
  const signupUrl = def?.signup_url;
  const apiKeyUrl = def?.api_key_url;
  const complexity = def?.setup_complexity;
  const isRecommended = def?.service === "openrouter";

  const colorMap: Record<string, string> = {
    healthy: "bg-status-engaged shadow-[0_0_10px_rgba(16,185,129,0.65)]",
    degraded: "bg-status-warm shadow-[0_0_10px_rgba(245,158,11,0.5)]",
    down: "bg-status-hot shadow-[0_0_10px_rgba(239,68,68,0.5)]",
    unconfigured: "bg-fg-faint",
  };
  const statusLabel: Record<string, string> = {
    healthy: "live",
    degraded: "degraded",
    down: "down",
    unconfigured: "not connected",
  };

  return (
    <div className={`group rounded-xl border bg-bg-elev px-4 py-3.5 transition-all ${
      isRecommended
        ? "border-accent/40 hover:border-accent/70 hover:shadow-[0_0_24px_-8px_rgba(0,212,255,0.4)]"
        : "border-bg-border hover:border-accent/40"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div
            className={`w-2.5 h-2.5 rounded-full shrink-0 mt-1.5 ${colorMap[health.status]} ${
              health.status === "healthy" ? "animate-pulse-slow" : ""
            }`}
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-sm font-semibold text-fg truncate">{label}</div>
              {isRecommended && (
                <span className="provider-chip recommended !py-0.5 !px-1.5 !text-[10px]">
                  <Sparkles className="w-2.5 h-2.5" /> recommended
                </span>
              )}
              {complexity && COMPLEXITY_LABEL[complexity] && (
                <span className={`text-[10px] uppercase tracking-wider font-bold ${COMPLEXITY_LABEL[complexity].tone}`}>
                  {COMPLEXITY_LABEL[complexity].label}
                </span>
              )}
            </div>
            <div className="text-xs text-fg-dim mt-1 truncate">
              {description || "—"}
            </div>
            <div className="text-[10px] text-fg-muted mt-1.5 font-mono">
              {statusLabel[health.status]}
              {health.last_ping_at && health.status !== "unconfigured" && (
                <> · last ping {timeAgo(health.last_ping_at)}</>
              )}
            </div>
          </div>
        </div>
      </div>

      {(signupUrl || apiKeyUrl) && (
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-bg-border opacity-80 group-hover:opacity-100 transition-opacity">
          {signupUrl && (
            <a
              href={signupUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-fg-muted hover:text-accent inline-flex items-center gap-1 transition-colors"
              title="Open signup page"
            >
              <ExternalLink className="w-3 h-3" /> Sign up
            </a>
          )}
          {apiKeyUrl && apiKeyUrl !== signupUrl && (
            <a
              href={apiKeyUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-fg-muted hover:text-accent inline-flex items-center gap-1 transition-colors"
              title="Open API key page"
            >
              <KeyRound className="w-3 h-3" /> API key
            </a>
          )}
          {def?.setup_doc_url && (
            <a
              href={def.setup_doc_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-fg-muted hover:text-accent inline-flex items-center gap-1 ml-auto transition-colors"
              title="Open setup docs"
            >
              docs <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      )}
    </div>
  );
}
