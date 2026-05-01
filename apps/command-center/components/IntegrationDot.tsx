import { timeAgo } from "@/lib/fmt";
import type { IntegrationHealth } from "@/lib/supabase";
import { categorize } from "@/lib/integrations-registry";

export function IntegrationDot({ health }: { health: IntegrationHealth }) {
  const def = categorize(health);
  const label = def?.label || health.service;
  const description = def?.description;

  const colorMap: Record<string, string> = {
    healthy: "bg-status-engaged shadow-[0_0_8px_rgba(16,185,129,0.6)]",
    degraded: "bg-status-warm shadow-[0_0_8px_rgba(245,158,11,0.5)]",
    down: "bg-status-hot shadow-[0_0_8px_rgba(239,68,68,0.5)]",
    unconfigured: "bg-fg-faint",
  };

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-bg-elev rounded-lg border border-bg-border hover:border-accent/30 transition-colors">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className={`w-2.5 h-2.5 rounded-full shrink-0 ${colorMap[health.status]} ${
            health.status === "healthy" ? "animate-pulse-slow" : ""
          }`}
        />
        <div className="min-w-0">
          <div className="text-sm font-medium text-fg truncate">{label}</div>
          <div className="text-xs text-fg-dim mt-0.5 truncate">
            {health.status === "unconfigured"
              ? description || "Not yet pinged"
              : health.last_ping_at
                ? `Last ping ${timeAgo(health.last_ping_at)}`
                : "No pings yet"}
          </div>
        </div>
      </div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-fg-muted shrink-0">
        {health.status}
      </div>
    </div>
  );
}
