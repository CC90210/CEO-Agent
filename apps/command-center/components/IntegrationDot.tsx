import { timeAgo } from "@/lib/fmt";
import type { IntegrationHealth } from "@/lib/supabase";

const SERVICE_LABELS: Record<string, string> = {
  supabase: "Supabase",
  stripe: "Stripe",
  gmail: "Gmail SMTP",
  n8n_inbound: "n8n Inbound Webhook",
  telegram: "Telegram Bridge",
  browser_harness: "Browser Harness",
};

export function IntegrationDot({ health }: { health: IntegrationHealth }) {
  const colorMap: Record<string, string> = {
    healthy: "bg-status-engaged shadow-[0_0_8px_rgba(16,185,129,0.6)]",
    degraded: "bg-status-warm shadow-[0_0_8px_rgba(245,158,11,0.5)]",
    down: "bg-status-hot shadow-[0_0_8px_rgba(239,68,68,0.5)]",
    unconfigured: "bg-fg-faint",
  };

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-bg-elev rounded-lg border border-bg-border">
      <div className="flex items-center gap-3">
        <div
          className={`w-2.5 h-2.5 rounded-full ${colorMap[health.status]} ${
            health.status === "healthy" ? "animate-pulse-slow" : ""
          }`}
        />
        <div>
          <div className="text-sm font-medium text-fg">
            {SERVICE_LABELS[health.service] || health.service}
          </div>
          <div className="text-xs text-fg-dim mt-0.5">
            {health.status === "unconfigured"
              ? "Not connected"
              : health.last_ping_at
                ? `Last ping ${timeAgo(health.last_ping_at)}`
                : "No pings yet"}
          </div>
        </div>
      </div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-fg-muted">
        {health.status}
      </div>
    </div>
  );
}
