import Link from "next/link";
import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import { timeAgo, truncate, statusColor } from "@/lib/fmt";
import { recentDecisions, getActiveProfile, getTenant } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { CommandPalette } from "@/components/reasoning/CommandPalette";
import { QuickActionsGrid } from "@/components/reasoning/QuickActionsGrid";
import { commandsForAgents } from "@/lib/slash-commands";
import { quickActionsFor } from "@/lib/quick-actions";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getManifest } from "@/lib/manifest/loader";

export const dynamic = "force-dynamic";

export default async function ReasoningPage({
  searchParams,
}: {
  searchParams?: Promise<{ dev?: string }>;
}) {
  const sp = (await searchParams) || {};
  const devMode = sp.dev === "1";

  // Phase 5 — manifest is the source of truth for enabled agents per tenant.
  // Same migration as /agents: resolve the slug for the operator's tenant,
  // load the manifest, derive enabled list from manifest.agents. The
  // QuickActionsGrid + CommandPalette downstream still take slug arrays so
  // they keep rendering the right per-agent prompts without any change.
  const profile = await safe("reasoning.profile", getActiveProfile(), null);
  const tenantSlugForReasoning = profile?.tenant_id
    ? await getTenant(profile.tenant_id)
        .then((t) => resolveClientProfileSlug(t || null))
        .catch(() => null)
    : null;
  const manifestForReasoning = await getManifest(tenantSlugForReasoning).catch(() => null);
  const manifestEnabledSlugs = (manifestForReasoning?.agents || [])
    .filter((a) => a.enabled)
    .map((a) => a.slug.toLowerCase());

  const enabled =
    manifestEnabledSlugs.length > 0
      ? manifestEnabledSlugs
      : profile?.agents_enabled || ["bravo"];

  // Agent decisions tape is scoped by tenant_id + enabled agents — see
  // recentDecisions() docstring for the schema-debt explanation. Without
  // this, a SunBiz user would see CC's OASIS Bravo decisions because the
  // table has no tenant_id column yet.
  const decisions = await safe(
    "reasoning.recent_decisions",
    recentDecisions(profile?.tenant_id ?? null, enabled, 20),
    []
  );

  const quickActions = quickActionsFor(enabled);
  const commands = commandsForAgents(enabled);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Reasoning"
        subtitle={
          devMode
            ? "Developer view — full slash-command palette + autonomous decision tape."
            : "Click an action to send it straight to chat. The agent runs it for you — no terminal, no setup."
        }
        action={
          <Tag tone="accent">
            {devMode ? `${commands.length} commands · ${enabled.length} agents` : `${quickActions.length} actions · ${enabled.length} agents`}
          </Tag>
        }
      />

      {devMode ? (
        <Card
          title="Developer command palette"
          subtitle="Click a command to see the exact terminal invocation. Auto-populated from your enabled agents."
          action={
            <Link href="/reasoning" className="text-xs text-fg-muted hover:text-accent transition-colors">
              ← back to quick actions
            </Link>
          }
        >
          {commands.length === 0 ? (
            <EmptyState message="No agents enabled. Toggle agents in Settings → Agents." />
          ) : (
            <CommandPalette commands={commands} enabledAgents={enabled} />
          )}
        </Card>
      ) : (
        <Card
          title="Quick actions"
          subtitle="Each one drops a prompt into chat with the right agent already selected. Hit Enter to send."
          action={
            <Link href="/reasoning?dev=1" className="text-xs text-fg-dim hover:text-accent transition-colors">
              developer view →
            </Link>
          }
        >
          {quickActions.length === 0 ? (
            <EmptyState message="No agents enabled. Toggle agents in Settings → Agents." />
          ) : (
            <QuickActionsGrid actions={quickActions} />
          )}
        </Card>
      )}

      <Card
        title="Agent decisions"
        subtitle={
          decisions.length > 0
            ? `Each row is a choice your agent made on its own — last ${decisions.length} cycles. Confidence + outcome shown so you can see whether the autonomous loop is making good calls.`
            : "Once your agents start cycling autonomously, every decision they make (lead scoring, send vs. skip, prioritize vs. defer) shows up here with confidence + outcome."
        }
      >
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
                      <span className="text-xs text-fg-dim font-mono">cycle {truncate(d.tick_id, 12)}</span>
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
