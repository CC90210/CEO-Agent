import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import { timeAgo, truncate, statusColor } from "@/lib/fmt";
import { recentDecisions } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function ReasoningPage() {
  const decisions = await recentDecisions(50);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Reasoning"
        subtitle="Every choice the autonomous reasoning loop made — reasoning, confidence, alternatives."
      />

      <Card title="Decision tape" subtitle={`${decisions.length} rows`}>
        {decisions.length === 0 ? (
          <EmptyState message="No decisions. Run python scripts/autonomous_agent.py tick or start the daemon." />
        ) : (
          <ul className="space-y-3">
            {decisions.map((d) => (
              <li
                key={d.id}
                className="rounded-lg border border-bg-border bg-bg-elev p-4"
              >
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <Tag tone="accent">{d.decision_type}</Tag>
                      <span className="text-xs text-fg-dim font-mono">
                        tick {truncate(d.tick_id, 12)}
                      </span>
                    </div>
                    <div className="text-fg font-medium text-sm">
                      {d.target_description || "(no target description)"}
                    </div>
                    {d.reasoning && (
                      <p className="text-sm text-fg-muted mt-2 leading-relaxed">
                        {truncate(d.reasoning, 280)}
                      </p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div
                      className={`text-sm font-bold ${statusColor(d.outcome_status)}`}
                    >
                      {d.outcome_status || d.chosen_action || "—"}
                    </div>
                    {d.confidence != null && (
                      <div className="text-xs text-fg-dim mt-1 font-mono">
                        conf {Number(d.confidence).toFixed(2)}
                      </div>
                    )}
                    <div className="text-xs text-fg-dim mt-1">
                      {timeAgo(d.created_at)}
                    </div>
                  </div>
                </div>
                {Array.isArray(d.alternatives_considered) &&
                  d.alternatives_considered.length > 0 && (
                    <details className="mt-3">
                      <summary className="text-xs text-fg-muted cursor-pointer hover:text-accent">
                        {d.alternatives_considered.length} alternatives considered
                      </summary>
                      <pre className="text-xs text-fg-dim mt-2 whitespace-pre-wrap font-mono bg-bg-panel rounded p-2 border border-bg-border">
                        {JSON.stringify(d.alternatives_considered, null, 2)}
                      </pre>
                    </details>
                  )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
