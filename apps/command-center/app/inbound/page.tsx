import { Card, EmptyState } from "@/components/Card";
import { timeAgo, truncate, intentColor, statusColor } from "@/lib/fmt";
import { recentInbound } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function InboundPage() {
  const inbound = await recentInbound(60);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Inbound</h1>
        <p className="text-sm text-fg-muted mt-1">
          Every classified reply, DM, and inbound message, enriched with
          sentiment + intent + priority.
        </p>
      </header>

      <Card title="Recent inbound" subtitle={`${inbound.length} rows`}>
        {inbound.length === 0 ? (
          <EmptyState message="No inbound yet. IMAP polling is scheduled via scheduler.py → check scheduler logs." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider border-b border-bg-border">
                  <th className="py-2 pr-4">When</th>
                  <th className="py-2 pr-4">Intent</th>
                  <th className="py-2 pr-4">Priority</th>
                  <th className="py-2 pr-4">Sentiment</th>
                  <th className="py-2 pr-4">From</th>
                  <th className="py-2 pr-4">Subject</th>
                </tr>
              </thead>
              <tbody>
                {inbound.map((i) => {
                  const meta = (i.metadata || {}) as Record<string, unknown>;
                  const cls = (meta.classification || {}) as Record<string, unknown>;
                  return (
                    <tr
                      key={i.id}
                      className="border-b border-bg-border last:border-0"
                    >
                      <td className="py-2 pr-4 text-fg-dim">
                        {timeAgo(i.created_at)}
                      </td>
                      <td className={`py-2 pr-4 ${intentColor(cls.intent as string)}`}>
                        {(cls.intent as string) || "—"}
                      </td>
                      <td className={`py-2 pr-4 ${statusColor(cls.priority as string)}`}>
                        {(cls.priority as string) || "—"}
                      </td>
                      <td className="py-2 pr-4 text-fg-muted">
                        {(cls.sentiment as string) || "—"}
                      </td>
                      <td className="py-2 pr-4 text-fg-muted font-mono text-xs">
                        {truncate((meta.from_identity as string) || "", 30)}
                      </td>
                      <td className="py-2 pr-4 text-fg">
                        {truncate(i.subject, 60)}
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
