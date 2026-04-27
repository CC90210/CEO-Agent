import { Card, EmptyState } from "@/components/Card";
import { timeAgo, truncate, statusColor } from "@/lib/fmt";
import { recentDecisions } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function DecisionsPage() {
  const decisions = await recentDecisions(50);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Decision tape</h1>
        <p className="text-sm text-fg-muted mt-1">
          Every choice the autonomous reasoning loop made, with reasoning and
          confidence. Most recent first.
        </p>
      </header>

      <Card title="Recent decisions" subtitle={`${decisions.length} rows`}>
        {decisions.length === 0 ? (
          <EmptyState message="No decisions yet. Run python scripts/autonomous_agent.py tick or start the daemon." />
        ) : (
          <ul className="space-y-4">
            {decisions.map((d) => (
              <li
                key={d.id}
                className="rounded border border-bg-border bg-bg-raised p-4"
              >
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1">
                    <div className="flex gap-3 items-center">
                      <span className="font-mono text-xs text-accent">
                        {d.decision_type}
                      </span>
                      <span className="text-xs text-fg-dim font-mono">
                        tick: {d.tick_id}
                      </span>
                    </div>
                    <div className="text-fg mt-2 font-medium">
                      {d.target_description || "(no target description)"}
                    </div>
                    {d.reasoning && (
                      <p className="text-sm text-fg-muted mt-2">
                        {truncate(d.reasoning, 300)}
                      </p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-sm font-bold ${statusColor(d.outcome_status)}`}>
                      {d.outcome_status || d.chosen_action || "—"}
                    </div>
                    {d.confidence != null && (
                      <div className="text-xs text-fg-dim mt-1">
                        conf: {Number(d.confidence).toFixed(2)}
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
                      <summary className="text-xs text-fg-muted cursor-pointer">
                        {d.alternatives_considered.length} alternatives considered
                      </summary>
                      <pre className="text-xs text-fg-dim mt-2 whitespace-pre-wrap">
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
