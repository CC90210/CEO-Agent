import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import ChatWidget from "@/components/ChatWidget";
import { timeAgo, truncate } from "@/lib/fmt";
import { agentStates, recentEvents, getActiveProfile, integrationsHealth } from "@/lib/queries";
import { ALL_AGENT_KEYS, getAgentInfo } from "@/lib/agents";
import { chatAgentKeys } from "@/lib/agent-personas";
import { catalogFor } from "@/lib/agent-catalog";
import { getAgentStats } from "@/lib/agent-stats";
import { getMemoryFreshness } from "@/lib/memory-freshness";
import { MemoryFreshnessCard } from "@/components/MemoryFreshnessCard";
import { getSessionUser } from "@/lib/supabase-server";
import { Clock, Cog, Workflow } from "lucide-react";

export const dynamic = "force-dynamic";

function isOperatorEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const e = email.trim().toLowerCase();
  const operator = (process.env.OPERATOR_EMAIL || "").trim().toLowerCase();
  if (operator && e === operator) return true;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(e);
}

// An agent is "live" if its state_snapshot ticked in the last 15 minutes
const FRESHNESS_MS = 15 * 60 * 1000;

export default async function AgentsPage() {
  const profile = await getActiveProfile();
  const user = await getSessionUser();
  const isAdmin = isOperatorEmail(user?.email);
  const [states, events, integrations, stats, memoryRows] = await Promise.all([
    agentStates(),
    recentEvents(25),
    integrationsHealth(profile?.tenant_id || null),
    getAgentStats(profile?.primary_agent || "bravo"),
    getMemoryFreshness(),
  ]);

  const enabled = profile?.agents_enabled || ALL_AGENT_KEYS;
  const byName = new Map(states.map((s) => [s.agent_name, s]));
  const integrationByName = new Map(integrations.map((i) => [i.service, i]));

  const rows = enabled.map((name) => {
    const state = byName.get(name) || null;
    // Fall back to integrations_health for agents that ping there instead of state_snapshot
    const intg = integrationByName.get(name) || null;
    const lastTickMs = state?.last_tick_at ? new Date(state.last_tick_at).getTime() : 0;
    const lastPingMs = intg?.last_ping_at ? new Date(intg.last_ping_at).getTime() : 0;
    const freshestMs = Math.max(lastTickMs, lastPingMs);
    const live = freshestMs > 0 && Date.now() - freshestMs < FRESHNESS_MS;
    return {
      name,
      info: getAgentInfo(name),
      state,
      intg,
      live,
      lastSignalAt: freshestMs ? new Date(freshestMs).toISOString() : null,
    };
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Agents"
        subtitle="Every agent wired to your Command Center, plus the live event bus tape."
        action={
          <Tag tone="accent">
            {rows.filter((r) => r.live).length} / {enabled.length} live
          </Tag>
        }
      />

      <section className="space-y-2">
        <header className="flex items-end justify-between flex-wrap gap-2">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-fg">Chat</h2>
            <div className="text-xs text-fg-muted mt-1">
              {isAdmin
                ? "Chat any agent in your family. Local bridge → Claude Code CLI on your machine (full repo access). Cloud mode → your saved key, falls back to platform default."
                : "Talk to any agent in your family — set up your provider + key in Settings → Agents."}
            </div>
          </div>
        </header>
        <ChatWidget
          agentKeys={chatAgentKeys().filter((k) => enabled.includes(k))}
          defaultAgent={profile?.primary_agent || "bravo"}
          isAdmin={isAdmin}
        />
      </section>

      <Card title="Agent family" subtitle={`Primary: ${profile?.primary_agent || "—"}`}>
        <ul className="grid md:grid-cols-2 gap-4">
          {rows.map((r) => (
            <li
              key={r.name}
              className="rounded-lg border border-bg-border bg-bg-elev p-4 transition-all hover:border-accent-muted/40"
            >
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      r.live
                        ? "bg-status-engaged shadow-[0_0_6px_rgba(16,185,129,0.6)] animate-pulse-slow"
                        : r.lastSignalAt
                          ? "bg-status-warm"
                          : "bg-fg-faint"
                    }`}
                  />
                  <span className="text-accent font-bold uppercase tracking-[0.14em] text-sm">
                    {r.name}
                  </span>
                </div>
                {r.live ? (
                  <span className="text-xs text-status-engaged font-mono">
                    live · {r.state ? `tick ${r.state.tick_count}` : "ping"}
                  </span>
                ) : r.lastSignalAt ? (
                  <span className="text-xs text-status-warm">
                    idle · {timeAgo(r.lastSignalAt)}
                  </span>
                ) : (
                  <span className="text-xs text-fg-dim">never seen</span>
                )}
              </div>
              <div className="text-sm text-fg mt-2.5">{r.info.role}</div>
              <div className="text-xs text-fg-dim mt-1.5 font-mono">{r.info.location}</div>
              {r.lastSignalAt && (
                <div className="text-xs text-fg-muted mt-3 pt-3 border-t border-bg-border">
                  Last signal {timeAgo(r.lastSignalAt)}
                  {r.state?.last_tick_id && (
                    <>
                      {" "}
                      ·{" "}
                      <span className="font-mono">{truncate(r.state.last_tick_id, 12)}</span>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <MemoryFreshnessCard rows={memoryRows} />

      <Card
        title="Capabilities"
        subtitle="What each enabled agent owns — cron jobs, backend processes, workflows. Tenant-aware: disabled agents drop out."
      >
        <div className="space-y-5">
          <div className="rounded-lg border border-bg-border bg-bg p-3">
            <div className="text-[10px] uppercase tracking-wider font-bold text-fg-muted mb-2">
              Live repo stats — auto-counted from the filesystem + bridge manifest
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 text-xs">
              <StatPill label="Skills" value={stats.skills} />
              <StatPill label="Scripts" value={stats.scripts} />
              <StatPill label="Chat tools" value={stats.chat_tools} />
              <StatPill label="Brain files" value={stats.brain_files} />
              <StatPill label="Memory" value={stats.memory_files} />
              <StatPill label="Workflows" value={stats.workflows} />
              <StatPill label="Sub-agents" value={stats.sub_agents} />
            </div>
            <div className="text-[11px] text-fg-dim mt-2">
              Per-agent blocks below show curated highlights. Add a script in <span className="font-mono">scripts/</span> + run{" "}
              <span className="font-mono">build_bridge_manifest.py</span> → counts update on next refresh.
            </div>
          </div>
          {enabled.map((key) => {
            const info = getAgentInfo(key);
            const cat = catalogFor(key);
            const total = cat.crons.length + cat.processes.length + cat.workflows.length;
            if (total === 0) return null;
            return (
              <div
                key={key}
                className="rounded-lg border border-bg-border bg-bg-elev p-4 space-y-3"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`font-bold uppercase tracking-[0.14em] text-sm ${info.textClass}`}>
                    {info.label}
                  </span>
                  <span className="text-xs text-fg-muted">{info.tagline}</span>
                  <span className="ml-auto text-[10px] uppercase tracking-wider text-fg-dim">
                    {total} highlighted
                  </span>
                </div>
                <div className="grid sm:grid-cols-3 gap-3">
                  <CatalogColumn
                    title="Crons"
                    icon={<Clock className="w-3.5 h-3.5" />}
                    entries={cat.crons.map((c) => ({
                      name: c.name,
                      meta: c.schedule || c.location,
                      desc: c.description,
                    }))}
                  />
                  <CatalogColumn
                    title="Processes"
                    icon={<Cog className="w-3.5 h-3.5" />}
                    entries={cat.processes.map((p) => ({
                      name: p.name,
                      meta: p.location,
                      desc: p.description,
                    }))}
                  />
                  <CatalogColumn
                    title="Workflows"
                    icon={<Workflow className="w-3.5 h-3.5" />}
                    entries={cat.workflows.map((w) => ({
                      name: w.name,
                      meta: w.location,
                      desc: w.description,
                    }))}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="Event bus" subtitle="Cross-agent coordination, most recent first">
        {events.length === 0 ? (
          <EmptyState message="No events yet. Events publish when the reasoning loop ticks or n8n inbound fires." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {events.map((e) => {
              const payload = e.payload || {};
              const cls = (payload as Record<string, unknown>).classification as
                | Record<string, unknown>
                | undefined;
              const subject = (payload as Record<string, unknown>).subject as string | undefined;
              return (
                <li key={e.id} className="py-2.5">
                  <div className="flex justify-between items-baseline gap-3">
                    <Tag tone="accent">{e.event_type}</Tag>
                    <span className="text-xs text-fg-dim">
                      {e.publisher_agent} · {timeAgo(e.published_at)}
                    </span>
                  </div>
                  {subject && (
                    <div className="text-fg mt-1.5 text-sm">{truncate(subject, 100)}</div>
                  )}
                  {cls && (
                    <div className="text-xs text-fg-muted mt-1">
                      intent: {String(cls.intent || "—")} · priority:{" "}
                      {String(cls.priority || "—")} · sentiment:{" "}
                      {String(cls.sentiment || "—")}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-bg-border bg-bg-elev px-2.5 py-1.5">
      <div className="text-fg font-mono text-sm font-semibold">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-fg-muted">{label}</div>
    </div>
  );
}

function CatalogColumn({
  title,
  icon,
  entries,
}: {
  title: string;
  icon: React.ReactNode;
  entries: Array<{ name: string; meta: string; desc: string }>;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-fg-muted mb-2">
        {icon}
        {title}
        <span className="text-fg-dim font-mono normal-case tracking-normal">
          ({entries.length})
        </span>
      </div>
      {entries.length === 0 ? (
        <div className="text-[11px] text-fg-faint italic">none</div>
      ) : (
        <ul className="space-y-1.5">
          {entries.map((e) => (
            <li key={e.name} className="text-xs leading-snug">
              <div className="flex items-baseline gap-1.5 flex-wrap">
                <span className="text-fg font-medium font-mono">{e.name}</span>
                <span className="text-[10px] text-fg-dim font-mono">· {e.meta}</span>
              </div>
              <div className="text-[11px] text-fg-muted">{e.desc}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
