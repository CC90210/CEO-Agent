import { Card, EmptyState, PageHeader, Tag } from "@/components/Card";
import { recentActions, getActiveProfile } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { timeAgo } from "@/lib/fmt";

export const dynamic = "force-dynamic";

type ActionPayload = {
  type?: string;
  ok?: boolean;
  summary?: string | null;
  error?: string | null;
  before?: unknown;
  after?: unknown;
  user_id?: string;
};

export default async function RunsPage() {
  const profile = await getActiveProfile();
  if (!profile?.tenant_id) {
    return (
      <div>
        <PageHeader title="Runs" subtitle="No tenant context." />
        <Card title="Action history">
          <EmptyState message="Sign in to load mutation history." />
        </Card>
      </div>
    );
  }
  const events = await safe(recentActions(profile.tenant_id, 100), []);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Runs"
        subtitle="Every dashboard mutation an agent has applied. Captures dashboard-action markers from /api/chat."
      />
      <Card
        title="Recent agent actions"
        subtitle={
          events.length === 0
            ? "No mutations yet. Ask an agent to update something."
            : `Last ${events.length} mutations across all agents.`
        }
      >
        {events.length === 0 ? (
          <EmptyState message="No agent mutations recorded yet." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {events.map((ev) => {
              const p = (ev.payload || {}) as ActionPayload;
              const ok = !!p.ok;
              return (
                <li
                  key={ev.id}
                  className="py-3 flex items-start gap-3 text-sm"
                >
                  <Tag tone={ok ? "engaged" : "warm"}>{ok ? "ok" : "err"}</Tag>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                        {ev.publisher_agent}
                      </span>
                      <span className="font-mono text-fg">
                        {p.type || "?"}
                      </span>
                    </div>
                    <div className="text-fg-muted mt-0.5 break-words">
                      {ok
                        ? p.summary || "(no summary)"
                        : p.error || "(no error message)"}
                    </div>
                  </div>
                  <span className="text-xs text-fg-dim font-mono flex-shrink-0">
                    {timeAgo(ev.published_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
