import { Card, EmptyState } from "@/components/Card";
import { timeAgo, truncate } from "@/lib/fmt";
import { recentOutbound, channelUtilization } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function OutboundPage() {
  const [outbound, caps] = await Promise.all([
    recentOutbound(60),
    channelUtilization(),
  ]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Outbound</h1>
        <p className="text-sm text-fg-muted mt-1">
          Every message the send gateway let through. CASL-compliant by
          construction.
        </p>
      </header>

      <Card title="Today's channel usage" subtitle="Hard caps enforced by the gateway">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {caps.map((c) => (
            <div key={c.channel} className="rounded border border-bg-border p-3">
              <div className="flex justify-between text-xs text-fg-muted uppercase tracking-wider">
                <span>{c.channel}</span>
                <span>{c.used}/{c.cap}</span>
              </div>
              <div className="mt-2 h-2 w-full bg-bg-raised rounded-full overflow-hidden">
                <div
                  className={`h-full ${
                    c.pct >= 90
                      ? "bg-status-hot"
                      : c.pct >= 60
                        ? "bg-status-warm"
                        : "bg-accent"
                  }`}
                  style={{ width: `${Math.min(c.pct, 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Recent sends" subtitle={`${outbound.length} most recent`}>
        {outbound.length === 0 ? (
          <EmptyState message="No outbound sends yet. send_gateway is the only path — check python scripts/send_gateway.py stats." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider border-b border-bg-border">
                  <th className="py-2 pr-4">When</th>
                  <th className="py-2 pr-4">Channel</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">Brand</th>
                  <th className="py-2 pr-4">Subject</th>
                  <th className="py-2 pr-4">Cooldown until</th>
                </tr>
              </thead>
              <tbody>
                {outbound.map((o) => {
                  const meta = (o.metadata || {}) as Record<string, unknown>;
                  return (
                    <tr
                      key={o.id}
                      className="border-b border-bg-border last:border-0"
                    >
                      <td className="py-2 pr-4 text-fg-dim">{timeAgo(o.created_at)}</td>
                      <td className="py-2 pr-4 text-fg-muted">{o.channel}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-accent">
                        {o.agent_source || "—"}
                      </td>
                      <td className="py-2 pr-4 text-fg-muted">
                        {(meta.brand as string) || "—"}
                      </td>
                      <td className="py-2 pr-4 text-fg">{truncate(o.subject, 60)}</td>
                      <td className="py-2 pr-4 text-fg-dim">
                        {o.cooldown_until ? timeAgo(o.cooldown_until) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
