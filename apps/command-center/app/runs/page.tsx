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
  const events = await safe("runs.recent_actions", recentActions(profile.tenant_id, 100), []);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Runs"
        subtitle="Audit log of every change an agent makes to your dashboard data."
      />

      <Card title="What lands here">
        <div className="space-y-3 text-sm text-fg-muted leading-relaxed">
          <p>
            When you chat an agent and it changes something — your MRR target,
            a lead&apos;s status, a profile field, a plan-template entry — it
            emits a <span className="font-mono text-fg">&lt;dashboard-action&gt;</span>{" "}
            marker that the chat route applies to your tenant&apos;s data.
            Every one of those mutations gets logged here, success or failure,
            with the agent that did it and when.
          </p>
          <p>
            <span className="text-fg font-medium">Local bridge vs cloud — both flow through here.</span>{" "}
            The bridge spawns Claude Code on your machine, but the model&apos;s
            response (with action markers) still comes back through{" "}
            <span className="font-mono text-fg">/api/chat</span> on the
            dashboard so the markers can be parsed and applied. Cloud mode
            uses the same path. Two execution surfaces, one audit trail.
          </p>
          <p className="text-fg-dim">
            <span className="text-fg font-medium">When to look here:</span>{" "}
            something unexpected changed — a value you didn&apos;t expect to
            move, a stage transition that surprised you. The Runs log shows
            who did it, what the change was, and whether it succeeded.
          </p>
        </div>
      </Card>

      <Card
        title="Recent agent actions"
        subtitle={
          events.length === 0
            ? "Empty so far — ask an agent to update something to see it here."
            : `Last ${events.length} mutations across all agents.`
        }
      >
        {events.length === 0 ? (
          <EmptyState message="No agent mutations recorded yet. Try chatting Bravo: &quot;set my MRR target to $7000&quot; — that change will land here." />
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
