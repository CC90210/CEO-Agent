/**
 * A2: System health banner — sticky top of / dashboard. Renders nothing
 * when totalIssues === 0; otherwise renders one row with severity styling
 * and per-signal counts so CC can see in <2s what's wrong.
 */

import Link from "next/link";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { SystemHealth } from "@/lib/system-health";

export function SystemHealthBanner({
  health,
  showAllClear = false,
}: {
  health: SystemHealth;
  showAllClear?: boolean;
}) {
  // Defensive — never throw on a malformed health prop. The page already
  // wraps the data fetch in safe(), but a bad shape here must still render
  // null instead of bubbling to the route's error boundary.
  if (!health || typeof health !== "object") return null;
  const totalIssues = Number.isFinite(health.totalIssues) ? health.totalIssues : 0;
  const staleAgents = Number.isFinite(health.staleAgents) ? health.staleAgents : 0;
  const staleAgentNames = Array.isArray(health.staleAgentNames) ? health.staleAgentNames : [];
  const integrationsDown = Number.isFinite(health.integrationsDown) ? health.integrationsDown : 0;
  const memoryStale = Number.isFinite(health.memoryStale) ? health.memoryStale : 0;
  const inboxUnread = Number.isFinite(health.inboxUnread) ? health.inboxUnread : 0;
  const bridgeOffline = !!health.bridgeOffline;
  if (totalIssues === 0) {
    if (!showAllClear) return null;
    return (
      <div className="rounded-lg border border-status-engaged/30 bg-status-engaged/5 px-4 py-2.5 text-xs text-status-engaged flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
        <span>All systems green — agents fresh, bridge online, memory current.</span>
      </div>
    );
  }

  const items: Array<{ label: string; href?: string }> = [];
  if (staleAgents > 0) {
    items.push({
      label: `${staleAgents} agent${staleAgents > 1 ? "s" : ""} stale${staleAgentNames.length ? ` (${staleAgentNames.join(", ")})` : ""}`,
      href: "/agents",
    });
  }
  if (bridgeOffline) {
    items.push({ label: "local bridge offline", href: "/operations" });
  }
  if (integrationsDown > 0) {
    items.push({
      label: `${integrationsDown} integration${integrationsDown > 1 ? "s" : ""} down`,
      href: "/integrations",
    });
  }
  if (memoryStale > 0) {
    items.push({
      label: `${memoryStale} memory file${memoryStale > 1 ? "s" : ""} stale`,
      href: "/agents",
    });
  }
  if (inboxUnread > 0) {
    items.push({
      label: `${inboxUnread} inbox message${inboxUnread > 1 ? "s" : ""}`,
      href: "/inbox",
    });
  }

  return (
    <div
      className="rounded-lg border border-status-warm/40 bg-status-warm/10 px-4 py-2.5 text-xs text-status-warm flex items-start gap-3"
      role="status"
    >
      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="font-bold uppercase tracking-wider mb-1 text-[10px]">
          System health · {totalIssues} issue{totalIssues > 1 ? "s" : ""}
        </div>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-fg">
          {items.map((it, i) =>
            it.href ? (
              <li key={i}>
                <Link
                  href={it.href}
                  className="underline decoration-status-warm/40 hover:decoration-status-warm transition-colors"
                >
                  {it.label}
                </Link>
              </li>
            ) : (
              <li key={i}>{it.label}</li>
            )
          )}
        </ul>
      </div>
    </div>
  );
}
