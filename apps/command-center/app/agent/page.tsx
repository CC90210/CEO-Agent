import ChatWidget from "@/components/ChatWidget";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getActiveProfile } from "@/lib/queries";
import { getSessionUser } from "@/lib/supabase-server";

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
      "Funding-ops agent for Sun Biz Funding. Reasons through leads, lender fit, applications, SMS follow-up, commissions, and renewal strategy.",
  },
  suga_sean: {
    label: "Suga",
    pitch:
      "Brand-ops agent for Suga Sean O'Malley. Routes fan engagement, merch drops, social posting, and sponsorship triage.",
  },
};

export default async function ClientAgentPage() {
  const [profile, user] = await Promise.all([
    getActiveProfile().catch(() => null),
    getSessionUser().catch(() => null),
  ]);
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

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={headerTitle}
        subtitle={headerSubtitle}
        action={<Tag tone="accent">{primary}</Tag>}
      />
      <Card
        title={agentKeys.length > 1 ? "Agent chat" : `${primaryMeta.label} chat`}
        subtitle="Cloud mode works once a model key is configured. Local bridge mode unlocks client-machine files and tools."
      >
        <ChatWidget
          agentKeys={agentKeys}
          defaultAgent={primary}
          isAdmin={isOperatorEmail(user?.email)}
        />
      </Card>
    </div>
  );
}
