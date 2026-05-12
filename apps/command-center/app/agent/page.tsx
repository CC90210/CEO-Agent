import ChatWidget from "@/components/ChatWidget";
import { Card, PageHeader, Tag } from "@/components/Card";
import { safe } from "@/lib/api-helpers";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";
import { getSessionUser } from "@/lib/supabase-server";
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
  sunbiz: {
    label: "Solara",
    pitch:
      "Your Sun Biz digital employee. Solara helps your team work leads, follow up fast, organize applications, track offers, and stay ahead of renewals.",
  },
  suga_sean: {
    label: "Suga",
    pitch:
      "Brand-ops agent for Suga Sean O'Malley. Routes fan engagement, merch drops, social posting, and sponsorship triage.",
  },
};

function firstNameOf(name: string | null | undefined, fallback = "Jordan"): string {
  const raw = (name || "").trim();
  if (!raw) return fallback;
  return raw.split(/\s+/)[0] || fallback;
}

export default async function ClientAgentPage() {
  const [profile, user] = await Promise.all([
    safe("agent.profile", getActiveProfile(), null),
    getSessionUser().catch(() => null),
  ]);
  const healthRows = await safe(
    "agent.health",
    integrationsHealth(profile?.tenant_id || null),
    [] as IntegrationHealth[]
  );
  // Tenant-scoped: only the agents this tenant has purchased / been provisioned for.
  const enabled = (profile?.agents_enabled || []).filter(Boolean);
  const primary = profile?.primary_agent || enabled[0] || "sunbiz";
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
    primary === "sunbiz" &&
    healthRows.some((row) => row.service === "jotform" && row.status === "healthy");
  const welcomeMessages =
    primary === "sunbiz"
      ? {
          sunbiz: jotformHealthy
            ? `Hello ${clientName}, I'm Solara. I've successfully connected to your JotForm and I'm ready to begin processing your funding pipeline.`
            : `Hello ${clientName}, I'm Solara. I'm in your Command Center and ready to help with leads, follow-up, applications, offers, and renewals.`,
        }
      : undefined;
  const cardSubtitle =
    primary === "sunbiz"
      ? "Talk to Solara in plain English. She can help you organize the funding pipeline, draft follow-up, and explain what needs attention next."
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
