import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import ChatWidget from "@/components/ChatWidget";
import { timeAgo, truncate } from "@/lib/fmt";
import { agentStates, recentEvents, getActiveProfile, integrationsHealth } from "@/lib/queries";
import { ALL_AGENT_KEYS, FAMILY_AGENT_KEYS, getAgentInfo } from "@/lib/agents";
import { chatAgentKeys } from "@/lib/agent-personas";
import { catalogFor } from "@/lib/agent-catalog";
import { getAgentStats } from "@/lib/agent-stats";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { Clock, Cog, Download, Workflow } from "lucide-react";
import Link from "next/link";

// Returns true if the tenant has zero non-revoked bridge pairings —
// used to gate the "install bridge" banner above the chat. Suppresses
// for operators who have ever paired (don't nag people who deliberately
// turned the bridge off).
async function _tenantHasNoBridge(tenantId: string | null): Promise<boolean> {
  if (!tenantId) return true;
  try {
    const db = getServiceSupabase();
    const { data } = await db
      .from("bridge_pairings")
      .select("id")
      .eq("tenant_id", tenantId)
      .is("revoked_at", null)
      .limit(1);
    return !data || data.length === 0;
  } catch (err) {
    // Failed to check — don't show banner on transient DB error. Logged
    // so a persistently-broken bridge_pairings query is surfaced in Vercel
    // logs instead of silently suppressing the onboarding nudge.
    console.error("[agents.tenant_has_no_bridge]", err);
    return false;
  }
}

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
  const [states, events, integrations, stats, noBridge] = await Promise.all([
    agentStates(),
    // sinceDays: 0 — same fix as /operations. Default 7-day window left
    // the Event Bus card looking empty when crons / inbound traffic had
    // been quiet for a week, even though the table had history.
    recentEvents(25, { sinceDays: 0 }),
    integrationsHealth(profile?.tenant_id || null),
    getAgentStats(profile?.primary_agent || "bravo"),
    _tenantHasNoBridge(profile?.tenant_id || null),
  ]);

  // AGENT FAMILY card shows only personas (excludes backend executors like
  // Codex). The `agents_enabled` column on user_profiles is the single source
  // of truth — toggling an agent off in /settings must remove it everywhere.
  // Only fall back to the full family set when the profile has no enabled
  // list at all (legacy / brand-new tenants).
  const familySet = new Set(FAMILY_AGENT_KEYS);
  const enabledList = profile?.agents_enabled?.length
    ? profile.agents_enabled
    : FAMILY_AGENT_KEYS;
  const enabled = enabledList.filter((k) => familySet.has(k));
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
                ? "Chat any agent. Two paths: (1) Local bridge — spawns the Claude Code CLI on your machine using your Claude subscription, full file/script access. (2) Cloud mode — uses the API key you saved per agent (OpenRouter / Anthropic / OpenAI / Gemini) to power the chat without a Claude subscription. Same persona either way; the bridge path can also write files. Clients run cloud mode by default."
                : "Talk to any agent in your family — set up your provider + key in Settings → Agents. The key powers the chat (no Claude Code subscription needed)."}
            </div>
          </div>
        </header>
        {noBridge && (
          <div className="rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 flex items-center justify-between gap-3 flex-wrap">
            <div className="text-xs text-fg-muted">
              <span className="font-bold text-fg">Chat is running in cloud mode.</span>{" "}
              Install the Claude Code CLI bridge to power chat with your local subscription + file access.
            </div>
            <Link
              href="/settings#devices"
              className="btn-primary inline-flex items-center gap-1.5 text-xs shrink-0"
            >
              <Download className="w-3 h-3" />
              Install bridge
            </Link>
          </div>
        )}
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
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      r.live
                        ? "bg-status-engaged shadow-[0_0_6px_rgba(16,185,129,0.6)] animate-pulse-slow"
                        : r.lastSignalAt
                          ? "bg-status-warm"
                          : "bg-fg-faint"
                    }`}
                  />
                  <span className={`font-bold uppercase tracking-[0.14em] text-sm ${r.info.textClass || "text-accent"}`}>
                    {r.info.label}
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
              <div className="text-xs text-fg-muted mt-2">{r.info.role}</div>
              {r.info.description && (
                <p className="text-sm text-fg mt-3 leading-relaxed">
                  {r.info.description}
                </p>
              )}
              {r.info.askMeAbout && (
                <div className="text-[11px] text-fg-muted mt-3 italic leading-relaxed">
                  <span className="text-fg-dim not-italic uppercase tracking-wider text-[9px] font-bold">Ask me about: </span>
                  {r.info.askMeAbout}
                </div>
              )}
              <div className="text-[10px] text-fg-dim mt-3 font-mono pt-2 border-t border-bg-border">
                {r.info.location}
                {r.lastSignalAt && (
                  <>
                    {" · "}
                    Last signal {timeAgo(r.lastSignalAt)}
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card
        title="What each agent does for you"
        subtitle="The autonomous workers running on your behalf. They handle the operational grind so you can stay on closing deals, shipping content, and the high-leverage moves only you can make."
      >
        <div className="space-y-5">
          <div className="rounded-lg border border-bg-border bg-bg p-4 text-sm text-fg-muted leading-relaxed">
            <div className="text-fg font-medium mb-1">How to read this</div>
            Each agent has three kinds of jobs running for you: <span className="text-fg">scheduled tasks</span> (run on a clock), <span className="text-fg">always-on processes</span> (running locally on your machine), and <span className="text-fg">workflows</span> (event-triggered, cross-system).
            <div className="mt-2 text-fg-dim text-[11px]">
              Repo stats: {stats.skills} skills · {stats.scripts} scripts · {stats.chat_tools} callable tools · {stats.brain_files} brain files · {stats.workflows} workflows
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
        <ul className="space-y-2.5">
          {entries.map((e) => (
            <li key={e.name} className="text-xs leading-snug">
              <div className="flex items-baseline gap-1.5 flex-wrap">
                <span className="text-fg font-medium">{prettifyEntryName(e.name)}</span>
                <span className="text-[10px] text-fg-dim">· {prettifyMeta(e.meta)}</span>
              </div>
              <div className="text-[11px] text-fg-muted mt-0.5">{e.desc}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Make engineering-style entry names readable. "lead_engine" → "Lead engine",
 * "snapshot-mrr" → "Snapshot MRR", "n8n inbound qualifier" → unchanged.
 * Keeps acronyms uppercase (MRR, EDI, POS, CRM, KPI, AI, CMO, CFO, CEO).
 */
function prettifyEntryName(raw: string): string {
  const ACRONYMS = new Set(["mrr", "edi", "pos", "crm", "kpi", "ai", "cmo", "cfo", "ceo", "n8n", "po", "rsvp", "fire"]);
  const cleaned = raw.replace(/[_-]+/g, " ").trim();
  return cleaned
    .split(/\s+/)
    .map((w, i) => {
      const lower = w.toLowerCase();
      if (ACRONYMS.has(lower)) return lower.toUpperCase();
      if (i === 0) return lower.charAt(0).toUpperCase() + lower.slice(1);
      return lower;
    })
    .join(" ");
}

/**
 * Cron strings → plain English. "0 3 * * *" → "Daily at 3:00 AM UTC".
 * Locations stay as-is (vercel/local/n8n/supabase) since CC understands those
 * after seeing them once.
 */
function prettifyMeta(meta: string): string {
  if (!meta) return "";
  // Cron format: minute hour dom month dow
  const cronMatch = meta.match(/^(\d+|\*)\s+(\d+|\*)\s+(\*)\s+(\*)\s+(\*)$/);
  if (cronMatch) {
    const [, min, hour] = cronMatch;
    if (min === "*" && hour === "*") return "every minute";
    if (min !== "*" && hour !== "*") {
      const h = Number(hour);
      const m = Number(min);
      const ampm = h < 12 ? "AM" : "PM";
      const h12 = h === 0 ? 12 : h <= 12 ? h : h - 12;
      const mm = m.toString().padStart(2, "0");
      return `daily at ${h12}:${mm} ${ampm} UTC`;
    }
    if (min !== "*" && hour === "*") return `every hour at :${min.padStart(2, "0")}`;
    if (min === "*" && hour !== "*") return `every minute during the ${hour}:00 UTC hour`;
  }
  // Step pattern: "*/15 * * * *" → "every 15 minutes"
  const stepMin = meta.match(/^\*\/(\d+)\s+\*\s+\*\s+\*\s+\*$/);
  if (stepMin) return `every ${stepMin[1]} minutes`;
  // Step hour: "0 */4 * * *" → "every 4 hours"
  const stepHour = meta.match(/^(\d+)\s+\*\/(\d+)\s+\*\s+\*\s+\*$/);
  if (stepHour) return `every ${stepHour[2]} hours at :${stepHour[1].padStart(2, "0")}`;
  return meta;
}
