import ChatWidget from "@/components/ChatWidget";
import { Card, PageHeader, Tag } from "@/components/Card";
import { safe } from "@/lib/api-helpers";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";
import { getSessionUser } from "@/lib/supabase-server";
import { resolveAgentKey } from "@/lib/agents";
import type { IntegrationHealth } from "@/lib/supabase";

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

const AGENT_LABELS: Record<string, { label: string; pitch: string }> = {
  solara: {
    label: "Solara",
    pitch:
      "Your Sun Biz operations brain. Solara runs the back office — pipeline reports, application packaging, lender matching, renewal sweeps — so the team always knows what's moving and what's stuck.",
  },
  helios: {
    label: "Helios",
    pitch:
      "Your Sun Biz sales voice. Personable, results-driven, sharp on cadence — drafts first-touch SMS, runs revival sequences for ghosted leads, brings expired offers back to the table.",
  },
  lyra: {
    label: "Lyra",
    pitch:
      "Your brand-command primary. Lyra holds the weekly pulse — what posted, what landed, what moved subscribers and sponsorships — and keeps voice continuity across the sub-agents.",
  },
};

function firstNameOf(name: string | null | undefined, fallback = "Jordan"): string {
  const raw = (name || "").trim();
  if (!raw) return fallback;
  return raw.split(/\s+/)[0] || fallback;
}

export default async function ClientAgentPage({
  searchParams,
}: {
  searchParams?: Promise<{ agent?: string }>;
}) {
  const [profile, user, params] = await Promise.all([
    safe("agent.profile", getActiveProfile(), null),
    getSessionUser().catch(() => null),
    searchParams ?? Promise.resolve({} as { agent?: string }),
  ]);
  const healthRows = await safe(
    "agent.health",
    integrationsHealth(profile?.tenant_id || null),
    [] as IntegrationHealth[]
  );
  // Tenant-scoped: only the agents this tenant has purchased / been provisioned for.
  // Normalize legacy slugs (sunbiz → solara, suga_sean → lyra) so old DB rows still resolve.
  const enabled = (profile?.agents_enabled || []).filter(Boolean).map(resolveAgentKey);
  const profilePrimary = resolveAgentKey(profile?.primary_agent || enabled[0] || "solara");
  // Honor ?agent=<slug> only if the user actually has that agent enabled —
  // prevents an arbitrary URL param from making us claim an agent the user
  // didn't purchase. Falls back to their provisioned primary.
  const requested = params?.agent ? resolveAgentKey(params.agent.toLowerCase()) : null;
  const primary = (requested && enabled.includes(requested)) ? requested : profilePrimary;
  // Primary first, then siblings, dedup. If no agents enabled (fresh tenant),
  // fall back to the primary alone so the page still renders something.
  const agentKeys = Array.from(new Set([primary, ...enabled])).filter(Boolean);
  const primaryMeta = AGENT_LABELS[primary] ?? { label: "Agents", pitch: "Chat with the agents enabled on this workspace." };
  const headerTitle = agentKeys.length > 1 ? "Agents" : primaryMeta.label;
  const headerSubtitle =
    agentKeys.length > 1
      ? `Chat with the ${agentKeys.length} agents on this workspace. Switch between them in the chat header.`
      : primaryMeta.pitch;
  const clientName = firstNameOf(profile?.display_name || profile?.full_name);
  const jotformHealthy =
    primary === "solara" &&
    healthRows.some((row) => row.service === "jotform" && row.status === "healthy");
  const welcomeMessages =
    primary === "solara"
      ? {
          solara: jotformHealthy
            ? `Hello ${clientName}, I'm Solara. I've successfully connected to your JotForm and I'm ready to begin processing your funding pipeline.`
            : `Hello ${clientName}, I'm Solara. I'm in your Command Center and ready to help with leads, follow-up, applications, offers, and renewals.`,
        }
      : primary === "helios"
      ? {
          helios: `Hello ${clientName}, I'm Helios. I'll draft your outreach, run the follow-up cadence, and bring expired offers back to the table — just tell me which lead to open with.`,
        }
      : undefined;
  const cardSubtitle =
    primary === "solara"
      ? "Talk to Solara in plain English. She can help you organize the funding pipeline, draft follow-up, and explain what needs attention next."
      : primary === "helios"
      ? "Helios drafts the outreach, runs the cadence, and keeps deals warm. Sales voice, not corporate."
      : "Cloud mode works once a model key is configured. Local bridge mode unlocks client-machine files and tools.";

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={headerTitle}
        subtitle={headerSubtitle}
        action={<Tag tone="accent">{primary}</Tag>}
      />
      <Card
        title={agentKeys.length > 1 ? "Agent chat" : `${primaryMeta.label} chat`}
        subtitle={cardSubtitle}
      >
        <ChatWidget
          agentKeys={agentKeys}
          defaultAgent={primary}
          isAdmin={isOperatorEmail(user?.email)}
          welcomeMessages={welcomeMessages}
        />
      </Card>
    </div>
  );
}
