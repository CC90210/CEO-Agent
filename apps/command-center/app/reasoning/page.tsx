import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import { timeAgo, truncate, statusColor } from "@/lib/fmt";
import { recentDecisions, getActiveProfile } from "@/lib/queries";
import { CommandPalette } from "@/components/reasoning/CommandPalette";
import { commandsForAgents } from "@/lib/slash-commands";

export const dynamic = "force-dynamic";

export default async function ReasoningPage() {
  const [profile, decisions] = await Promise.all([
    getActiveProfile(),
    recentDecisions(20),
  ]);

  const enabled = profile?.agents_enabled || ["bravo"];
  const commands = commandsForAgents(enabled);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Reasoning"
        subtitle="Slash commands across your enabled agents + the autonomous decision tape."
        action={<Tag tone="accent">{commands.length} commands · {enabled.length} agents</Tag>}
      />

      <Card
        title="Agent command palette"
        subtitle="Click a command to see the exact terminal invocation. Auto-populated from your enabled agents."
      >
        {commands.length === 0 ? (
          <EmptyState message="No agents enabled. Toggle agents in Settings → Agents." />
        ) : (
          <CommandPalette commands={commands} enabledAgents={enabled} />
        )}
      </Card>

      <Card title="Decision tape" subtitle={`${decisions.length} most recent autonomous-loop decisions`}>
        {decisions.length === 0 ? (
          <EmptyState message="No decisions yet. The reasoning loop hasn't run today — try `python scripts/autonomous_agent.py tick` from your Bravo terminal." />
        ) : (
          <ul className="space-y-3">
            {decisions.map((d) => (
              <li key={d.id} className="rounded-lg border border-bg-border bg-bg-elev p-4">
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <Tag tone="accent">{d.decision_type}</Tag>
                      <span className="text-xs text-fg-dim font-mono">tick {truncate(d.tick_id, 12)}</span>
                    </div>
                    <div className="text-fg font-medium text-sm">
                      {d.target_description || "(no target description)"}
                    </div>
                    {d.reasoning && (
                      <p className="text-sm text-fg-muted mt-2 leading-relaxed">{truncate(d.reasoning, 280)}</p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-sm font-bold ${statusColor(d.outcome_status)}`}>
                      {d.outcome_status || d.chosen_action || "—"}
                    </div>
                    {d.confidence != null && (
                      <div className="text-xs text-fg-dim mt-1 font-mono">
                        conf {Number(d.confidence).toFixed(2)}
                      </div>
                    )}
                    <div className="text-xs text-fg-dim mt-1">{timeAgo(d.created_at)}</div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
